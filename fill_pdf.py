"""
The One Ring 2e - Compilatore scheda PDF
=========================================
Compila i campi form di un PDF a partire da personaggi.json
e un file di configurazione generato da parse_pdf_fields.py.

Requisiti:
    pip install pypdf --break-system-packages

Utilizzo:
    # Prima genera la configurazione:
    python parse_pdf_fields.py scheda.pdf --character personaggi.json

    # Poi compila:
    python fill_pdf.py
    python fill_pdf.py --config config_scheda_editabile.json
    python fill_pdf.py --input scheda.pdf --config config.json --output output/
"""

import json
import sys
import argparse
import io
import re
from pathlib import Path
from pypdf import PdfReader, PdfWriter
from PIL import Image
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib import colors

# ── Configurazione ─────────────────────────────────────────────────────────────
CHARACTERS_FILE = Path(__file__).parent / "personaggi.json"
PDF_TEMPLATE    = Path(__file__).parent / "scheda_editabile.pdf"
PDF_CONFIG      = Path(__file__).parent / "config_scheda_editabile.json"
OUTPUT_DIR      = Path(__file__).parent / "output_pdf"

# Pagina 2 — coordinate fisse ricavate dall'analisi del PDF
PAGE2_SIZE      = (790.866, 612.283)   # larghezza x altezza (pt) — orizzontale
PAGE2_BIO_RECT  = (366.8, 56.9, 748.9, 474.1)   # x0,y0,x1,y1
PAGE2_IMG_RECT  = (30.0, 30.0, 336.8, 582.3)    # spazio sicuro sinistra
# ──────────────────────────────────────────────────────────────────────────────


def register_baskerville() -> tuple[str, str, str]:
    """
    Registra il font Baskerville in ReportLab da file .ttc (TrueType Collection).
    I file .ttc contengono più varianti — le identifica per nome stile.
    Restituisce (regular, bold, italic) da usare in ParagraphStyle.
    Se non trovato o fallisce, usa Times-Roman come fallback.
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase.pdfmetrics import registerFontFamily

    TTC_PATH = "/System/Library/Fonts/Supplemental/Baskerville.ttc"

    if not Path(TTC_PATH).exists():
        print("  ⚠ Baskerville.ttc non trovato, uso Times-Roman")
        return "Times-Roman", "Times-Bold", "Times-Italic"

    # Mappa stile → nome registrato
    registered = {}
    style_map = {
        "regular":      ("Regular", "Roman", "Book"),
        "bold":         ("Bold", "SemiBold", "SemiB"),
        "italic":       ("Italic",),
        "bold_italic":  ("Bold Italic", "SemiBold Italic"),
    }

    for idx in range(20):
        try:
            font = TTFont(f"_baskerville_probe_{idx}", TTC_PATH, subfontIndex=idx)
            style = str(font.face.styleName).strip()
            for variant, keywords in style_map.items():
                if any(k.lower() in style.lower() for k in keywords):
                    if variant not in registered:
                        reg_name = f"Baskerville-{variant.capitalize()}"
                        pdfmetrics.registerFont(
                            TTFont(reg_name, TTC_PATH, subfontIndex=idx)
                        )
                        registered[variant] = reg_name
                        print(f"  ✓ Baskerville indice {idx}: '{style}' → {reg_name}")
                    break
        except Exception:
            break

    if "regular" not in registered:
        print("  ⚠ Variante Regular non trovata, uso Times-Roman")
        return "Times-Roman", "Times-Bold", "Times-Italic"

    regular = registered["regular"]
    bold    = registered.get("bold",        regular)
    italic  = registered.get("italic",      regular)
    bold_it = registered.get("bold_italic", bold)

    try:
        registerFontFamily(
            "Baskerville",
            normal=regular, bold=bold,
            italic=italic,  boldItalic=bold_it,
        )
    except Exception as e:
        print(f"  ⚠ registerFontFamily: {e}")

    return regular, bold, italic


def markdown_to_reportlab(md: str) -> list:
    """Converte Markdown in lista di Paragraph/Spacer per ReportLab."""
    styles = getSampleStyleSheet()
    TEXT_COLOR = colors.Color(173/255, 79/255, 66/255)

    font_regular, font_bold, font_italic = register_baskerville()

    body_style = ParagraphStyle(
        "TORBody", parent=styles["Normal"],
        fontSize=12, leading=13, fontName=font_regular,
        textColor=TEXT_COLOR, spaceAfter=4,
    )
    h2_style = ParagraphStyle(
        "TORh2", parent=styles["Heading2"],
        fontSize=13, leading=15, fontName=font_bold,
        textColor=TEXT_COLOR, spaceBefore=8, spaceAfter=4,
    )
    h1_style = ParagraphStyle(
        "TORh1", parent=styles["Heading1"],
        fontSize=14, leading=17, fontName=font_bold,
        textColor=TEXT_COLOR, spaceBefore=10, spaceAfter=6,
    )

    def inline(text: str) -> str:
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'\*(.+?)\*',     r'<i>\1</i>', text)
        text = re.sub(r'~~(.+?)~~',     r'<strike>\1</strike>', text)
        return text

    elements = []
    lines = md.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r'^## ?', line):
            text = re.sub(r'^## ?', '', line).strip()
            if text:
                elements.append(Paragraph(inline(text), h2_style))
        elif re.match(r'^# ?', line):
            text = re.sub(r'^# ?', '', line).strip()
            if text:
                elements.append(Paragraph(inline(text), h1_style))
        elif re.match(r'^[-*] ', line):
            items = []
            while i < len(lines) and re.match(r'^[-*] ', lines[i]):
                items.append(f"• {inline(lines[i][2:])}")
                i += 1
            elements.append(Paragraph("<br/>".join(items), body_style))
            continue
        elif line.strip() == "":
            elements.append(Spacer(1, 6))
        else:
            if line.strip():
                elements.append(Paragraph(inline(line), body_style))
        i += 1
    return elements


def render_bio_overlay(bio_md: str, bio_rect: tuple, page_size: tuple) -> io.BytesIO:
    """Renderizza il bio Markdown come overlay PDF con testo formattato."""
    from reportlab.platypus import Frame, BaseDocTemplate, PageTemplate

    x0, y0, x1, y1 = bio_rect
    w, h = x1 - x0, y1 - y0
    buf = io.BytesIO()

    doc = BaseDocTemplate(
        buf, pagesize=page_size,
        leftMargin=0, rightMargin=0, topMargin=0, bottomMargin=0,
    )
    frame = Frame(x0, y0, w, h, leftPadding=4, rightPadding=4,
                  topPadding=4, bottomPadding=4, showBoundary=0)
    doc.addPageTemplates([PageTemplate(id="bio", frames=[frame])])
    doc.build(markdown_to_reportlab(bio_md))
    buf.seek(0)
    return buf


def render_image_page2(image_path: Path, img_rect: tuple, page_size: tuple) -> io.BytesIO:
    """Renderizza l'immagine centrata nel rettangolo disponibile."""
    from reportlab.lib.utils import ImageReader

    x0, y0, x1, y1 = img_rect
    w, h = x1 - x0, y1 - y0

    img = Image.open(str(image_path)).convert("RGB")
    iw, ih = img.size
    scale = min(w / iw, h / ih)
    new_w, new_h = iw * scale, ih * scale
    draw_x = x0 + (w - new_w) / 2
    draw_y = y0 + (h - new_h) / 2

    # Converti in ImageReader che reportlab accetta
    img_buf = io.BytesIO()
    img.save(img_buf, format="PNG")
    img_buf.seek(0)
    img_reader = ImageReader(img_buf)

    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=page_size)
    c.drawImage(img_reader, draw_x, draw_y, width=new_w, height=new_h)
    c.save()
    buf.seek(0)
    return buf


def fill_page2(writer: PdfWriter, char: dict, base_dir: Path) -> None:
    """Compila pagina 2: bio formattata e immagine nella colonna sinistra."""
    bio_md         = char.get("bio", "")
    image_path_str = char.get("image_path", "")

    if bio_md:
        # NON scriviamo il testo plain nel campo form (apparirebbe in rosso
        # con lo stile del campo e si sovrapporrebbe all'overlay).
        # Usiamo solo l'overlay ReportLab per la formattazione ricca.
        try:
            bio_buf = render_bio_overlay(bio_md, PAGE2_BIO_RECT, PAGE2_SIZE)
            writer.pages[1].merge_page(PdfReader(bio_buf).pages[0])
            print("  ✓ Bio formattata inserita")
        except Exception as e:
            print(f"  ⚠ Bio overlay non riuscito: {e}")

    if image_path_str:
        image_path = Path(image_path_str)
        if not image_path.is_absolute():
            image_path = base_dir / image_path
        if image_path.exists():
            try:
                img_buf = render_image_page2(image_path, PAGE2_IMG_RECT, PAGE2_SIZE)
                writer.pages[1].merge_page(PdfReader(img_buf).pages[0])
                print(f"  ✓ Immagine pagina 2: {image_path.name}")
            except Exception as e:
                print(f"  ⚠ Immagine pagina 2 non inserita: {e}")
        else:
            print(f"  ⚠ Immagine non trovata: {image_path}")


def get_image_field_rect(reader: PdfReader, field_name: str) -> list | None:
    """
    Trova il rettangolo (x0, y0, x1, y1) del campo immagine nel PDF
    leggendo le annotazioni della pagina.
    """
    fields = reader.get_fields()
    field = fields.get(field_name)
    if not field:
        return None

    # Il campo può avere kids (sottocampi): prende il rect del primo kid
    if "/Kids" in field:
        try:
            kid = field["/Kids"][0].get_object()
            rect = kid.get("/Rect")
            if rect:
                return [float(r) for r in rect]
        except Exception:
            pass

    # Altrimenti cerca nelle annotazioni della pagina
    for annot in reader.pages[0].annotations:
        obj = annot.get_object()
        if str(obj.get("/T", "")) == field_name:
            rect = obj.get("/Rect")
            if rect:
                return [float(r) for r in rect]

    return None


def insert_image_overlay(
    writer: PdfWriter,
    reader: PdfReader,
    image_path: Path,
    field_rect: list,
    page_size: tuple = (595, 842)
) -> None:
    """
    Sovrappone un'immagine al PDF nelle coordinate del campo specificato.
    L'immagine viene ritagliata al centro (crop quadrato) e ridimensionata
    per adattarsi al rettangolo mantenendo le proporzioni.
    """
    x0, y0, x1, y1 = field_rect
    w = x1 - x0
    h = y1 - y0

    # Apri e prepara l'immagine
    img = Image.open(str(image_path)).convert("RGB")

    # Crop quadrato centrato (migliora la resa nei campi portrait)
    iw, ih = img.size
    side = min(iw, ih)
    left = (iw - side) // 2
    top  = (ih - side) // 2
    img = img.crop((left, top, left + side, top + side))

    # Salva in buffer temporaneo
    img_buf = io.BytesIO()
    img.save(img_buf, format="PNG")
    img_buf.seek(0)

    # Crea overlay PDF con l'immagine posizionata
    overlay_buf = io.BytesIO()
    c = rl_canvas.Canvas(overlay_buf, pagesize=page_size)
    c.drawImage(
        img_buf, x0, y0,
        width=w, height=h,
        preserveAspectRatio=True,
        anchor='c'
    )
    c.save()

    # Sovrapponi al PDF
    overlay_buf.seek(0)
    overlay_reader = PdfReader(overlay_buf)
    writer.pages[0].merge_page(overlay_reader.pages[0])


def get_nested(obj, path: str):
    """
    Naviga un dizionario/lista con dot-notation e array[N].
    Esempio: get_nested(char, "skills.awe.rating") → 2
    """
    parts = path.replace("][", ".").replace("[", ".").replace("]", "").split(".")
    for part in parts:
        if obj is None:
            return None
        if isinstance(obj, list):
            try:
                obj = obj[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


def resolve_value(char: dict, json_path: str, field_type: str = "/Tx"):
    """
    Risolve un json_path nel valore da scrivere nel PDF.

    - Campi /Tx (testo): restituisce il valore come stringa, incluso "0"
    - Campi /Btn (checkbox/radio): restituisce "/0" se truthy, None altrimenti
    - Sintassi "path>=N": restituisce "/0" se valore >= N (radio abilità)
    """
    if not json_path:
        return None

    # Operatore >= per campi radio abilità (es. "skills.awe.rating>=3")
    if ">=" in json_path:
        path, threshold = json_path.split(">=")
        val = get_nested(char, path.strip())
        return "/0" if (val or 0) >= int(threshold.strip()) else None

    val = get_nested(char, json_path)

    if val is None:
        return None

    # Campi checkbox/radio (/Btn)
    if field_type == "/Btn":
        return "/0" if val else None

    # Campi testo (/Tx): converti sempre in stringa, incluso 0 e ""
    return str(val)


def build_pdf_values(char: dict, config: dict) -> dict:
    """
    Costruisce il dizionario {field_name: value} da passare a pypdf,
    escludendo i campi immagine (gestiti tramite overlay separato).
    """
    fv = {}
    fields = config.get("fields", {})

    for field_name, field_conf in fields.items():
        json_path = field_conf.get("json_path", "")
        field_type = field_conf.get("type", "/Tx")
        note = field_conf.get("_note", "")

        if not json_path:
            continue
        # Salta i campi immagine — gestiti da insert_image_overlay
        if "overlay" in note or "image_path" in json_path:
            continue

        value = resolve_value(char, json_path, field_type)
        if value is not None:
            fv[field_name] = value

    return fv


def find_image_field(config: dict) -> tuple[str, str] | None:
    """
    Trova il campo immagine nel config (quello con json_path = info.image_path).
    Restituisce (field_name, json_path) o None.
    """
    for field_name, field_conf in config.get("fields", {}).items():
        if field_conf.get("json_path") == "info.image_path":
            return field_name, "info.image_path"
    return None


def fill_character_pdf(
    char: dict,
    template_path: Path,
    config: dict,
    output_path: Path
) -> None:
    name = char["character_name"]
    print(f"\n  Compilazione: {name}")

    reader = PdfReader(str(template_path))
    writer = PdfWriter()
    writer.append(reader)

    # Compila i campi form
    field_values = build_pdf_values(char, config)
    writer.update_page_form_field_values(writer.pages[0], field_values)

    # Inserisce immagine se presente
    image_path_str = char.get("info", {}).get("image_path", "")
    if image_path_str:
        image_path = Path(image_path_str)
        if not image_path.is_absolute():
            image_path = Path(__file__).parent / image_path
        if image_path.exists():
            image_field_info = find_image_field(config)
            if image_field_info:
                image_field_name, _ = image_field_info
                rect = get_image_field_rect(reader, image_field_name)
                if rect:
                    try:
                        insert_image_overlay(writer, reader, image_path, rect)
                        print(f"  ✓ Immagine inserita: {image_path.name}")
                    except Exception as e:
                        print(f"  ⚠ Immagine non inserita: {e}")
                else:
                    print(f"  ⚠ Rettangolo campo '{image_field_name}' non trovato")
        else:
            print(f"  ⚠ Immagine non trovata: {image_path}")

    # Pagina 2: bio formattata + immagine (se il PDF ha 2 pagine)
    if len(writer.pages) > 1:
        fill_page2(writer, char, Path(__file__).parent)

    with open(str(output_path), "wb") as f:
        writer.write(f)

    filled = sum(1 for v in field_values.values() if v)
    print(f"  ✓ {output_path.name} ({filled} campi compilati)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compila scheda PDF TOR 2e da personaggi.json + configurazione",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Workflow:
  1. python parse_pdf_fields.py scheda.pdf --character personaggi.json
     → genera config_scheda.json con mapping automatico
  2. Rivedi config_scheda.json e completa i campi senza mapping
  3. python fill_pdf.py --config config_scheda.json
        """
    )
    parser.add_argument("--input",      default=str(PDF_TEMPLATE),
                        help="PDF template da compilare")
    parser.add_argument("--config",     default=str(PDF_CONFIG),
                        help="File di configurazione JSON dei campi")
    parser.add_argument("--output",     default=str(OUTPUT_DIR),
                        help="Directory di output")
    parser.add_argument("--characters", default=str(CHARACTERS_FILE),
                        help="File JSON dei personaggi")
    args = parser.parse_args()

    template   = Path(args.input)
    config_path = Path(args.config)
    output_dir = Path(args.output)
    chars_file = Path(args.characters)

    # Validazioni
    for path, label in [
        (template,   "PDF template"),
        (config_path, "file configurazione"),
        (chars_file,  "file personaggi"),
    ]:
        if not path.exists():
            print(f"✗ {label} non trovato: {path}")
            if label == "file configurazione":
                print("  Genera la configurazione con:")
                print(f"  python parse_pdf_fields.py {template.name} "
                      f"--character {chars_file.name}")
            sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    with open(chars_file, encoding="utf-8") as f:
        characters = [c for c in json.load(f) if "character_name" in c]

    mapped = sum(1 for f in config["fields"].values() if f.get("json_path"))
    total  = len(config["fields"])
    print(f"Configurazione: {config_path.name}")
    print(f"  Campi totali: {total}, con mapping: {mapped}, senza: {total - mapped}")
    print(f"\nPersonaggi: {len(characters)}")

    for char in characters:
        safe = char["character_name"].replace(" ", "_").replace("/", "-")
        output_path = output_dir / f"scheda_{safe}.pdf"
        fill_character_pdf(char, template, config, output_path)

    print(f"\n✓ PDF salvati in: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
