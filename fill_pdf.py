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
from pypdf.generic import NameObject
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

# Pagina 2 — dimensione e rotazione si leggono dal template.
# Le aree di bio e immagine si leggono dai campi PAGE2_BIO_FIELD / PAGE2_IMG_FIELD
# se il template li contiene; altrimenti si usano le coordinate di ripiego
# (in punti, nel sistema di coordinate della pagina non ruotata).
PAGE1_IMG_FIELD = "immagine-pg"   # campo ritratto di pagina 1, se il config non lo mappa
PAGE2_BIO_FIELD = "bio"
PAGE2_IMG_FIELD = "immagine-bio"
BIO_FONT_MAX    = 12.0   # corpo massimo della bio (pt)
BIO_FONT_MIN    = 7.0    # sotto questo non si scende
BIO_FONT_PASSO  = 0.25
# Colori della bio, scelti con la prova di stampa sulla Xerox C235 (laser):
# restano nitidi solo i colori a un inchiostro o a inchiostri pieni.
#   testo:  antracite = solo nero all'85% (CMYK 0 0 0 85)
#   titoli: rosso pieno = magenta + giallo al 100% (CMYK 0 100 100 0)
BIO_COLORE_TESTO  = colors.CMYKColor(0, 0, 0, 0.85)
BIO_COLORE_TITOLI = colors.CMYKColor(0, 1, 1, 0)
PAGE2_BIO_RECT  = (366.8, 56.9, 748.9, 474.1)   # x0,y0,x1,y1 — ripiego
PAGE2_IMG_RECT  = (30.0, 30.0, 336.8, 582.3)    # spazio sicuro sinistra — ripiego
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


_FONT_BIO = None


def markdown_to_reportlab(md: str, size: float = BIO_FONT_MAX) -> list:
    """Converte Markdown in lista di Paragraph/Spacer per ReportLab.
    `size` è il corpo del testo; titoli, interlinea e spazi sono in proporzione."""
    global _FONT_BIO
    styles = getSampleStyleSheet()

    if _FONT_BIO is None:                      # registra i font una volta sola
        _FONT_BIO = register_baskerville()
    font_regular, font_bold, font_italic = _FONT_BIO
    k = size / 12.0                            # i valori originali erano per 12 pt

    body_style = ParagraphStyle(
        "TORBody", parent=styles["Normal"],
        fontSize=size, leading=13 * k, fontName=font_regular,
        textColor=BIO_COLORE_TESTO, spaceAfter=4 * k,
    )
    h2_style = ParagraphStyle(
        "TORh2", parent=styles["Heading2"],
        fontSize=13 * k, leading=15 * k, fontName=font_bold,
        textColor=BIO_COLORE_TITOLI, spaceBefore=8 * k, spaceAfter=4 * k,
    )
    h1_style = ParagraphStyle(
        "TORh1", parent=styles["Heading1"],
        fontSize=14 * k, leading=17 * k, fontName=font_bold,
        textColor=BIO_COLORE_TITOLI, spaceBefore=10 * k, spaceAfter=6 * k,
    )

    def inline(text: str) -> str:
        # grassetti nel colore dei titoli (CMYK pieno, nitido in stampa)
        c = BIO_COLORE_TITOLI
        rosso = f"cmyk({c.cyan:g},{c.magenta:g},{c.yellow:g},{c.black:g})"
        text = re.sub(r'\*\*(.+?)\*\*', rf'<font color="{rosso}"><b>\1</b></font>', text)
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
            elements.append(Spacer(1, 6 * k))
        else:
            if line.strip():
                elements.append(Paragraph(inline(line), body_style))
        i += 1
    return elements


def _altezza_elementi(elementi: list, frame) -> float:
    """Altezza totale occupata dagli elementi nella larghezza utile del frame."""
    tot, prec_after = 0.0, 0.0
    for i, el in enumerate(elementi):
        _, h = el.wrap(frame._aW, frame._aH)
        before = el.getSpaceBefore() if i else 0.0
        tot += h + max(before, prec_after)     # come Frame: spazi non sommati
        prec_after = el.getSpaceAfter()
    return tot


def _quanti_ci_stanno(elementi: list, frame) -> int:
    """Numero di elementi che entrano nel frame (per non generare una
    seconda pagina vuota se il testo è troppo lungo anche al minimo)."""
    for n in range(len(elementi), 0, -1):
        if _altezza_elementi(elementi[:n], frame) <= frame._aH:
            return n
    return 1


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

    # Corpo del testo: il più grande (fino a BIO_FONT_MAX) che sta nel riquadro
    size = BIO_FONT_MAX
    while True:
        elementi = markdown_to_reportlab(bio_md, size)
        if size <= BIO_FONT_MIN or _altezza_elementi(elementi, frame) <= frame._aH:
            break
        size = round(size - BIO_FONT_PASSO, 2)
    if size < BIO_FONT_MAX:
        print(f"  ✓ Bio ridotta a {size:g} pt per stare nel riquadro")
    if size <= BIO_FONT_MIN and _altezza_elementi(elementi, frame) > frame._aH:
        print(f"  ⚠ Bio troppo lunga anche a {BIO_FONT_MIN:g} pt: verrà tagliata")

    doc.addPageTemplates([PageTemplate(id="bio", frames=[frame])])
    doc.build(elementi[:_quanti_ci_stanno(elementi, frame)])
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


# ── Layout letto dal template ─────────────────────────────────────────────────

def dimensioni_pagina(page) -> tuple[float, float]:
    """Larghezza e altezza della pagina nel suo sistema di coordinate
    (non ruotato): è lo spazio in cui vanno disegnati gli overlay."""
    box = page.mediabox
    return float(box.width), float(box.height)


def rect_campo_su_pagina(page, nome: str) -> tuple | None:
    """Rettangolo (x0, y0, x1, y1) del widget del campo `nome` sulla pagina."""
    for ref in page.get("/Annots") or []:
        annot = ref.get_object()
        if annot.get("/Subtype") != "/Widget":
            continue
        if _nome_campo(annot) == nome or str(annot.get("/T", "")) == nome:
            x0, y0, x1, y1 = [float(v) for v in annot["/Rect"]]
            return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
    return None


def fill_page2(writer: PdfWriter, char: dict, base_dir: Path) -> None:
    """Compila pagina 2: bio formattata e immagine nella colonna sinistra."""
    bio_md         = char.get("bio", "")
    image_path_str = char.get("info", {}).get("image_path", "")

    page      = writer.pages[1]
    page_size = dimensioni_pagina(page)
    bio_rect  = rect_campo_su_pagina(page, PAGE2_BIO_FIELD) or PAGE2_BIO_RECT
    img_rect  = rect_campo_su_pagina(page, PAGE2_IMG_FIELD) or PAGE2_IMG_RECT
    if int(page.get("/Rotate", 0)) % 360:
        print("  ⚠ Pagina 2 ruotata: le coordinate di ripiego sono per la pagina "
              "non ruotata, verifica il risultato o aggiungi i campi al template")

    if bio_md:
        # NON scriviamo il testo plain nel campo form (apparirebbe in rosso
        # con lo stile del campo e si sovrapporrebbe all'overlay).
        # Usiamo solo l'overlay ReportLab per la formattazione ricca.
        try:
            bio_buf = render_bio_overlay(bio_md, bio_rect, page_size)
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
                img_buf = render_image_page2(image_path, img_rect, page_size)
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
    page_size: tuple | None = None
) -> None:
    """
    Sovrappone un'immagine al PDF nelle coordinate del campo specificato.
    L'immagine viene ritagliata al centro (crop quadrato) e ridimensionata
    per adattarsi al rettangolo mantenendo le proporzioni.
    """
    if page_size is None:
        page_size = dimensioni_pagina(writer.pages[0])
    x0, y0, x1, y1 = field_rect
    w = x1 - x0
    h = y1 - y0

    # Apri e prepara l'immagine
    img = Image.open(str(image_path)).convert("RGB")

    # Se la pagina è ruotata (/Rotate), l'immagine va disegnata ruotata in senso
    # opposto, così appare dritta quando il lettore gira la pagina
    rotazione = int(writer.pages[0].get("/Rotate", 0)) % 360
    if rotazione:
        img = img.rotate(rotazione, expand=True)   # PIL ruota in senso antiorario

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
    from reportlab.lib.utils import ImageReader
    c.drawImage(
        ImageReader(img_buf), x0, y0,
        width=w, height=h,
        preserveAspectRatio=True,
        anchor='c'
    )
    c.save()

    # Sovrapponi al PDF
    overlay_buf.seek(0)
    overlay_reader = PdfReader(overlay_buf)
    writer.pages[0].merge_page(overlay_reader.pages[0])


# ── Campi ruotati (/MK /R) ─────────────────────────────────────────────────────
# La pagina 1 del template è un A4 verticale con /Rotate 90 e tutti i campi di
# testo hanno /MK /R 90. Il generatore di aspetto di pypdf non gestisce bene
# questa rotazione (e il risultato cambia da una versione all'altra): il testo
# finisce in colonna, minuscolo o in verticale. Anteprima di macOS mostra
# proprio quell'aspetto, perché non lo rigenera.
# Per i widget ruotati quindi scriviamo noi lo stream di aspetto: box "sdraiato"
# (lunghezza = lato lungo del Rect) e /Matrix che lo ruota nel Rect.

TESTO_MARGINE = 2.0      # pt di margine interno
TESTO_MAX_PT  = 24.0     # dimensione massima del font con dimensione automatica
TESTO_MAX_PT_MULTI = 12.0  # ... per i campi multilinea
TESTO_MIN_PT  = 4.0


def _rotazione_widget(annot) -> int:
    """Restituisce la rotazione /MK /R del widget (0, 90, 180, 270)."""
    mk = annot.get("/MK")
    if mk is None:
        return 0
    try:
        return int(mk.get_object().get("/R", 0)) % 360
    except Exception:
        return 0


def _attributo_campo(annot, chiave, default=None):
    """Legge un attributo dal widget o, se manca, dai campi genitori."""
    nodo = annot
    while nodo is not None:
        if chiave in nodo:
            return nodo[chiave]
        genitore = nodo.get("/Parent")
        nodo = genitore.get_object() if genitore is not None else None
    return default


def _nome_campo(annot) -> str:
    """Nome completo del campo (es. 'padre.figlio')."""
    parti, nodo = [], annot
    while nodo is not None:
        if "/T" in nodo:
            parti.append(str(nodo["/T"]))
        genitore = nodo.get("/Parent")
        nodo = genitore.get_object() if genitore is not None else None
    return ".".join(reversed(parti))


def _misuratore(font_dict):
    """Restituisce una funzione larghezza(testo, size) basata su /Widths del font,
    con ripiego sulle metriche Times-Roman di ReportLab."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    widths = font_dict.get("/Widths") if font_dict is not None else None
    if widths:
        first = int(font_dict.get("/FirstChar", 0))
        widths = [float(w) for w in widths.get_object()]

        def larghezza(testo: str, size: float) -> float:
            tot = 0.0
            for b in testo.encode("cp1252", "replace"):
                i = b - first
                tot += widths[i] if 0 <= i < len(widths) else 500.0
            return tot * size / 1000.0
        return larghezza
    return lambda testo, size: stringWidth(testo, "Times-Roman", size)


def _a_capo(testo: str, larghezza, size: float, max_w: float) -> list[str]:
    """Spezza il testo in righe che stanno in max_w."""
    righe = []
    for par in testo.split("\n"):
        parole, corrente = par.split(" "), ""
        for parola in parole:
            prova = f"{corrente} {parola}".strip()
            if corrente and larghezza(prova, size) > max_w:
                righe.append(corrente)
                corrente = parola
            else:
                corrente = prova
        righe.append(corrente)
    return righe


def _pdf_stringa(testo: str) -> str:
    raw = testo.encode("cp1252", "replace").decode("latin-1")
    return raw.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def scrivi_aspetto_ruotato(writer: PdfWriter, annot, valore: str) -> None:
    """Crea lo stream di aspetto (/AP /N) di un campo di testo ruotato di 90/270°."""
    from pypdf.generic import (ArrayObject, DecodedStreamObject, DictionaryObject,
                               FloatObject)

    rot = _rotazione_widget(annot)
    x0, y0, x1, y1 = [float(v) for v in annot["/Rect"]]
    w, h = abs(x1 - x0), abs(y1 - y0)
    lungo, spesso = h, w                     # il testo corre lungo l'altezza del Rect

    # Aspetto predefinito: "/Font size Tf colore"
    acroform = writer._root_object["/AcroForm"]
    da = str(_attributo_campo(annot, "/DA", acroform.get("/DA", "/Helv 0 Tf 0 g")))
    m = re.search(r"/([^\s/]+)\s+([\d.]+)\s+Tf", da)
    font_nome = m.group(1) if m else "Helv"
    size = float(m.group(2)) if m else 0.0
    colore = da[m.end():].strip() if m else "0 g"
    if not colore:
        colore = "0 g"

    dr_font = acroform.get("/DR", {}).get_object().get("/Font", {})
    font_ref = dr_font.get_object().get(f"/{font_nome}") if dr_font else None
    font_dict = font_ref.get_object() if font_ref is not None else None
    larghezza = _misuratore(font_dict)

    multilinea = bool(int(_attributo_campo(annot, "/Ff", 0)) & 4096)
    allinea = int(_attributo_campo(annot, "/Q", 0))
    max_w = lungo - 2 * TESTO_MARGINE
    max_h = spesso - 2 * TESTO_MARGINE

    # Dimensione automatica del font (size 0 nel /DA)
    if size <= 0:
        size = min(TESTO_MAX_PT_MULTI if multilinea else TESTO_MAX_PT, max_h * 0.8)
        while size > TESTO_MIN_PT:
            if multilinea:
                righe = _a_capo(valore, larghezza, size, max_w)
                if len(righe) * size * 1.15 <= max_h and \
                        all(larghezza(r, size) <= max_w for r in righe):
                    break
            elif larghezza(valore, size) <= max_w:
                break
            size -= 0.5
    righe = _a_capo(valore, larghezza, size, max_w) if multilinea \
        else [valore.replace("\n", " ")]

    interlinea = size * 1.15
    if multilinea:
        y = spesso - TESTO_MARGINE - size * 0.9
    else:
        y = (spesso - size * 0.7) / 2
    comandi = [f"/{font_nome} {size:.2f} Tf {colore}"]
    for riga in righe:
        lw = larghezza(riga, size)
        if allinea == 1:
            x = (lungo - lw) / 2
        elif allinea == 2:
            x = lungo - TESTO_MARGINE - lw
        else:
            x = TESTO_MARGINE
        comandi.append(f"1 0 0 1 {x:.2f} {y:.2f} Tm ({_pdf_stringa(riga)}) Tj")
        y -= interlinea

    contenuto = (
        "/Tx BMC\nq\n"
        f"1 1 {lungo - 2:.2f} {spesso - 2:.2f} re W n\n"
        "BT\n" + "\n".join(comandi) + "\nET\nQ\nEMC\n"
    )

    matrice = [0, 1, -1, 0, w, 0] if rot == 90 else [0, -1, 1, 0, 0, h]
    stream = DecodedStreamObject()
    stream.set_data(contenuto.encode("latin-1"))
    stream.update({
        NameObject("/Type"): NameObject("/XObject"),
        NameObject("/Subtype"): NameObject("/Form"),
        NameObject("/BBox"): ArrayObject([FloatObject(0), FloatObject(0),
                                          FloatObject(lungo), FloatObject(spesso)]),
        NameObject("/Matrix"): ArrayObject([FloatObject(v) for v in matrice]),
    })
    if font_ref is not None:
        stream[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject(f"/{font_nome}"): font_ref})
        })
    annot[NameObject("/AP")] = DictionaryObject(
        {NameObject("/N"): writer._add_object(stream)}
    )


def correggi_campi_ruotati(writer: PdfWriter, page, field_values: dict) -> int:
    """Riscrive l'aspetto dei campi di testo ruotati compilati. Restituisce quanti."""
    corretti = 0
    for ref in page.get("/Annots") or []:
        annot = ref.get_object()
        if annot.get("/Subtype") != "/Widget":
            continue
        if _attributo_campo(annot, "/FT") != "/Tx":
            continue
        if _rotazione_widget(annot) not in (90, 270):
            continue
        nome = _nome_campo(annot)
        valore = field_values.get(nome, field_values.get(nome.split(".")[-1]))
        if valore is None or str(valore) == "":
            continue
        scrivi_aspetto_ruotato(writer, annot, str(valore))
        corretti += 1
    return corretti


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


# ── Appiattimento del modulo ──────────────────────────────────────────────────
# Anteprima di macOS ignora l'aspetto salvato nei campi e li ridisegna da sé:
# non gestisce la rotazione /MK /R (testo in verticale) e non mostra le
# caselle spuntate di questo template. Appiattendo, l'aspetto di ogni campo
# viene "stampato" nel contenuto della pagina e i campi spariscono: il PDF
# appare identico in qualsiasi lettore, ma non è più modificabile.

def _trasforma_punto(m, x, y):
    a, b, c, d, e, f = m
    return a * x + c * y + e, b * x + d * y + f


def appiattisci_pagina(writer: PdfWriter, page) -> int:
    """Disegna l'aspetto di ogni widget nel contenuto della pagina e rimuove
    i widget. Restituisce il numero di campi appiattiti."""
    from pypdf.generic import (ArrayObject, DecodedStreamObject, DictionaryObject,
                               IndirectObject)

    annots = page.get("/Annots")
    if not annots:
        return 0

    risorse = page.get("/Resources")
    risorse = risorse.get_object() if risorse is not None else DictionaryObject()
    xobjs = risorse.get("/XObject")
    xobjs = xobjs.get_object() if xobjs is not None else DictionaryObject()

    comandi, restanti, n = [], ArrayObject(), 0
    for ref in annots:
        annot = ref.get_object()
        if annot.get("/Subtype") != "/Widget":
            restanti.append(ref)
            continue
        n += 1
        if int(annot.get("/F", 0)) & 2:          # nascosto
            continue
        ap = annot.get("/AP")
        normal = ap.get_object().get("/N") if ap is not None else None
        if normal is None:
            continue
        normal_obj = normal.get_object()
        if "/BBox" not in normal_obj:           # stati (caselle): usa /AS
            stato = annot.get("/AS")
            if stato is None or stato not in normal_obj:
                continue
            normal = normal_obj[stato]
            normal_obj = normal.get_object()
        if "/BBox" not in normal_obj:
            continue

        # Algoritmo 8.1 (PDF 1.7): BBox trasformato da /Matrix → adattato al /Rect
        bx0, by0, bx1, by1 = [float(v) for v in normal_obj["/BBox"]]
        m = [float(v) for v in normal_obj.get("/Matrix", [1, 0, 0, 1, 0, 0])]
        pts = [_trasforma_punto(m, x, y) for x in (bx0, bx1) for y in (by0, by1)]
        tx0, tx1 = min(p[0] for p in pts), max(p[0] for p in pts)
        ty0, ty1 = min(p[1] for p in pts), max(p[1] for p in pts)
        if tx1 - tx0 <= 0 or ty1 - ty0 <= 0:
            continue
        rx0, ry0, rx1, ry1 = [float(v) for v in annot["/Rect"]]
        rx0, rx1 = min(rx0, rx1), max(rx0, rx1)
        ry0, ry1 = min(ry0, ry1), max(ry0, ry1)
        sx, sy = (rx1 - rx0) / (tx1 - tx0), (ry1 - ry0) / (ty1 - ty0)

        nome = f"/FlatW{n}"
        rif = normal if isinstance(normal, IndirectObject) else writer._add_object(normal_obj)
        xobjs[NameObject(nome)] = rif
        comandi.append(
            f"q {sx:.6f} 0 0 {sy:.6f} {rx0 - tx0 * sx:.6f} {ry0 - ty0 * sy:.6f} cm "
            f"{nome} Do Q"
        )

    risorse[NameObject("/XObject")] = xobjs
    page[NameObject("/Resources")] = risorse

    # Aggiunge i disegni in coda al contenuto, isolando quello esistente
    vecchio = page.get_contents()
    dati = b"q\n" + (vecchio.get_data() if vecchio is not None else b"") + b"\nQ\n"
    dati += ("\n".join(comandi) + "\n").encode("latin-1")
    nuovo = DecodedStreamObject()
    nuovo.set_data(dati)
    page.replace_contents(nuovo)

    if restanti:
        page[NameObject("/Annots")] = restanti
    else:
        del page["/Annots"]
    return n


def appiattisci_modulo(writer: PdfWriter) -> int:
    """Appiattisce tutte le pagine e rimuove il modulo dal documento."""
    totale = sum(appiattisci_pagina(writer, p) for p in writer.pages)
    if "/AcroForm" in writer._root_object:
        del writer._root_object["/AcroForm"]
    return totale


def fill_character_pdf(
    char: dict,
    template_path: Path,
    config: dict,
    output_path: Path,
    appiattisci: bool = True,
) -> None:
    name = char["character_name"]
    print(f"\n  Compilazione: {name}")

    reader = PdfReader(str(template_path))
    writer = PdfWriter()
    writer.append(reader)

    # Compila i campi form
    field_values = build_pdf_values(char, config)
    # Tutte le pagine: un campo (es. "nome") può comparire anche a pagina 2
    n_ruotati = 0
    for page in writer.pages:
        if page.get("/Annots"):
            writer.update_page_form_field_values(page, field_values)
            n_ruotati += correggi_campi_ruotati(writer, page, field_values)
    print(f"  ✓ Aspetto rigenerato per {n_ruotati} campi ruotati")

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
            else:
                # Nessun campo mappato su info.image_path: usa il campo del template
                image_field_name = PAGE1_IMG_FIELD
            if image_field_name:
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

    if appiattisci:
        n_flat = appiattisci_modulo(writer)
        print(f"  ✓ Modulo appiattito ({n_flat} campi)")

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
    parser.add_argument("--editabile", action="store_true",
                        help="Mantieni i campi modificabili (Anteprima di macOS "
                             "li mostra male: testo ruotato, caselle vuote)")
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
        fill_character_pdf(char, template, config, output_path,
                           appiattisci=not args.editabile)

    print(f"\n✓ PDF salvati in: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
