"""
Roll20 - The One Ring 2e (Advanced) - Compilatore automatico schede
====================================================================
Scheda versione: 03-14-00

Requisiti:
    pip install playwright playwright-stealth
    playwright install chromium

Modalità disponibili:
  --mode cdp      (consigliata) Connette Playwright a Chrome già aperto via CDP.
                  1. Avvia Chrome con il flag di debug (vedi sotto).
                  2. Fai il login su Roll20 a mano nel browser.
                  3. python fill_sheets.py --mode cdp

  --mode profile  Playwright lancia Chrome con il tuo profilo reale.
                  Chrome deve essere CHIUSO prima dell'esecuzione.
                  python fill_sheets.py --mode profile

Comando per avviare Chrome in modalità CDP (copia e incolla nel terminale):
  /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
      --remote-debugging-port=9222 \
      --no-first-run \
      --no-default-browser-check
"""

import json
import time
import sys
import shutil
import tempfile
import re
from pathlib import Path
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

# ── Configurazione ─────────────────────────────────────────────────────────────
CAMPAIGN_ID     = "13540628"    # ID numerico visibile nell'URL setcampaign
CHARACTERS_FILE = Path(__file__).parent / "personaggi.json"
PAUSE           = 0.3           # pausa tra campi (secondi)
LONG_PAUSE      = 2.0           # pausa dopo apertura scheda

# Percorso della directory PADRE del profilo Chrome.
# Da chrome://version → "Percorso profilo", togli l'ultima parte (es. /Default).
CHROME_USER_DATA = "/Users/YOURNAME/Library/Application Support/Google/Chrome"

# Nome del profilo (ultima parte del percorso in chrome://version, es. "Default")
CHROME_PROFILE   = "Default"

# Se True copia il profilo in una dir temporanea (più sicuro ma più lento)
USE_PROFILE_COPY = False

# Porta CDP per la modalità --mode cdp
CDP_URL = "http://127.0.0.1:9222"

# ──────────────────────────────────────────────────────────────────────────────

# ── Helper UI ─────────────────────────────────────────────────────────────────

def _pause():
    time.sleep(PAUSE)


def fill_text(page, selector: str, value) -> None:
    """Compila un campo testo o textarea e triggera blur per forzare il salvataggio."""
    try:
        el = page.locator(selector).first
        el.click(click_count=3)
        el.fill(str(value))
        el.evaluate("el => el.dispatchEvent(new Event('blur', {bubbles: true}))")
        _pause()
    except Exception as e:
        print(f"    ⚠ fill_text({selector}): {e}")


def fill_js(page, selector: str, value, nth: int = 0) -> None:
    """
    Imposta il valore via JavaScript e scatena gli eventi input/change/blur.
    Roll20 persiste i valori via WebSocket solo dopo blur o change — entrambi
    vanno triggerati per garantire che il valore venga salvato correttamente.
    """
    try:
        el = page.locator(selector).nth(nth)
        el.evaluate(f"""el => {{
            el.value = '{value}';
            el.dispatchEvent(new Event('input',  {{bubbles: true}}));
            el.dispatchEvent(new Event('change', {{bubbles: true}}));
            el.dispatchEvent(new Event('blur',   {{bubbles: true}}));
        }}""")
        _pause()
    except Exception as e:
        print(f"    ⚠ fill_js({selector}): {e}")


def fill_number(page, attr_name: str, value) -> None:
    """Compila un campo input[type=number] tramite nome attributo via JS+change event."""
    fill_js(page, f"input[name='attr_{attr_name}']", value)


def fill_attr_text(page, attr_name: str, value) -> None:
    """Compila un input[type=text] tramite nome attributo."""
    fill_text(page, f"input[name='attr_{attr_name}']", value)


def fill_textarea(page, attr_name: str, value: str) -> None:
    """Compila una textarea tramite nome attributo."""
    fill_text(page, f"textarea[name='attr_{attr_name}']", value)


def fill_radio(page, attr_name: str, value: int) -> None:
    """Seleziona un radio button e triggera change+blur per il salvataggio."""
    try:
        el = page.locator(f"input[name='attr_{attr_name}'][value='{value}']").first
        el.check()
        el.evaluate("el => { el.dispatchEvent(new Event('change', {bubbles: true})); el.dispatchEvent(new Event('blur', {bubbles: true})); }")
        _pause()
    except Exception as e:
        print(f"    ⚠ fill_radio({attr_name}={value}): {e}")


def fill_checkbox(page, attr_name: str, checked: bool) -> None:
    """Spunta o deseleziona una checkbox e triggera change+blur."""
    try:
        el = page.locator(f"input[name='attr_{attr_name}']").first
        if checked:
            el.check()
        else:
            el.uncheck()
        el.evaluate("el => { el.dispatchEvent(new Event('change', {bubbles: true})); el.dispatchEvent(new Event('blur', {bubbles: true})); }")
        _pause()
    except Exception as e:
        print(f"    ⚠ fill_checkbox({attr_name}): {e}")


def fill_select(page, attr_name: str, value) -> None:
    """Seleziona un'opzione in un <select> tramite nome attributo."""
    try:
        page.locator(f"select[name='attr_{attr_name}']").first.select_option(str(value))
        _pause()
    except Exception as e:
        print(f"    ⚠ fill_select({attr_name}={value}): {e}")


# ── Login e navigazione ───────────────────────────────────────────────────────

def login(page, email: str, password: str) -> None:
    print("→ Login su Roll20...")
    page.goto("https://app.roll20.net/login")
    page.fill("input[name='email']", email)
    page.fill("input[name='password']", password)
    page.click("button[type='submit']")
    page.wait_for_url("**/editor/**", timeout=15000)
    print("  ✓ Login effettuato")


def open_campaign(page, campaign_id: str) -> None:
    print(f"→ Impostazione campagna (ID {campaign_id})...")

    # Se siamo già sull'editor della campagna giusta, non ricaricare
    if f"setcampaign/{campaign_id}" not in page.url and "/editor" in page.url:
        print("  ✓ Editor già aperto, salto navigazione")
    else:
        page.goto(f"https://app.roll20.net/editor/setcampaign/{campaign_id}")
        page.wait_for_load_state("domcontentloaded", timeout=20000)

        if "/editor" not in page.url or "setcampaign" in page.url:
            print("→ Caricamento editor...")
            page.goto("https://app.roll20.net/editor")
            page.wait_for_load_state("domcontentloaded", timeout=20000)

    # Attiva il tab Journal se necessario
    print("→ Attivazione tab Journal...")
    try:
        page.click("[aria-controls='journal']", timeout=5000)
    except Exception:
        try:
            page.click("#ui-id-3", timeout=3000)
        except Exception:
            pass

    # Aspetta il pulsante "Personaggio" — segnale che il journal è pronto
    page.wait_for_selector("#addnewcharacter", state="visible", timeout=30000)
    time.sleep(LONG_PAUSE)
    print("  ✓ Journal pronto")


def markdown_to_html(md: str) -> str:
    """
    Converte Markdown semplice in HTML per Summernote.
    Supporta: **grassetto**, *corsivo*, # titoli, - liste, righe vuote come paragrafi.
    """
    if not md:
        return ""
    lines = md.split("\n")
    html_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Titoli
        if line.startswith("### "):
            html_lines.append(f"<h3>{_inline(line[4:])}</h3>")
        elif line.startswith("## "):
            html_lines.append(f"<h2>{_inline(line[3:])}</h2>")
        elif line.startswith("# "):
            html_lines.append(f"<h1>{_inline(line[2:])}</h1>")
        # Liste
        elif line.startswith("- ") or line.startswith("* "):
            items = []
            while i < len(lines) and (lines[i].startswith("- ") or lines[i].startswith("* ")):
                items.append(f"<li>{_inline(lines[i][2:])}</li>")
                i += 1
            html_lines.append("<ul>" + "".join(items) + "</ul>")
            continue
        # Riga vuota → paragrafo
        elif line.strip() == "":
            html_lines.append("<p><br></p>")
        # Testo normale
        else:
            html_lines.append(f"<p>{_inline(line)}</p>")
        i += 1
    return "".join(html_lines)


def _inline(text: str) -> str:
    """Converte inline Markdown: **bold**, *italic*, ~~strikethrough~~."""
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*',     r'<em>\1</em>', text)
    text = re.sub(r'~~(.+?)~~',     r'<del>\1</del>', text)
    return text


def fill_bio(page, markdown_text: str) -> None:
    """
    Compila il campo Biografia nella dialog di modifica personaggio (fuori dall'iframe).
    Apre la dialog tramite il pulsante Edit nella titlebar, inserisce l'HTML
    nel div.note-editable di Summernote, poi salva.
    """
    if not markdown_text:
        return
    html = markdown_to_html(markdown_text)

    print("HTML generato:", html[:200])
    # Escape apici per l'inserimento in JS
    html_escaped = html.replace("'", "\\'").replace("\n", "")

    print("  [BIO] Compilazione biografia...")
    try:
        # Clicca il pulsante Edit nella titlebar della dialog scheda
        page.click(".ui-dialog button.editcharacter", timeout=5000)
        time.sleep(1)

        # Aspetta la dialog di modifica con il campo biografia
        page.wait_for_selector(".ui-dialog .note-editable", timeout=10000)
        time.sleep(0.5)

        # Usa l'API Summernote tramite jQuery per inserire HTML formattato
        page.evaluate(f"$('.ui-dialog textarea.bio').summernote('code', '{html_escaped}')")
        time.sleep(PAUSE)

        # Salva
        page.click(".ui-dialog button.save-button", timeout=5000)
        time.sleep(LONG_PAUSE)

        # Dopo il salvataggio la dialog torna alla scheda di gioco con l'iframe
        page.wait_for_selector(".ui-dialog iframe", timeout=10000)
        print("  ✓ Biografia salvata")
    except Exception as e:
        print(f"  ⚠ fill_bio: {e}")


def save_and_open_sheet(page, name: str) -> None:
    """
    Gestisce la dialog di creazione personaggio.
    Dopo 'Save Changes' la stessa dialog mostra l'iframe con i tre pulsanti
    (Eroe Giocante, Avversario, Log Rilascio) — non si apre una nuova dialog.
    """
    page.wait_for_selector(".ui-dialog input.name[data-test='character-edit-name']", timeout=10000)
    time.sleep(0.5)

    name_input = page.locator(".ui-dialog input.name[data-test='character-edit-name']").first
    name_input.click(click_count=3)
    name_input.fill(name)
    time.sleep(PAUSE)

    page.click(".ui-dialog button.save-button", timeout=5000)
    print(f"  ✓ Nome salvato: '{name}'")

    # Dopo Save Changes la stessa dialog si aggiorna mostrando l'iframe.
    # Aspettiamo che l'iframe diventi visibile nella dialog già aperta.
    page.wait_for_selector(".ui-dialog iframe", timeout=15000)
    time.sleep(1)
    print(f"  ✓ Iframe scheda rilevato")

    # Clicca "Eroe Giocante" nell'iframe per attivare la vista PG
    _click_ispc(page)
    time.sleep(LONG_PAUSE)
    print(f"  ✓ Scheda di gioco pronta")


def get_sheet_frame(page):
    """
    Restituisce il frame della scheda di gioco (dentro l'iframe del personaggio).
    La scheda TOR2e è renderizzata dentro un iframe con name="iframe_{characterid}".
    """
    # Aspetta che l'iframe sia presente e abbia il suo contenuto
    page.wait_for_selector(".ui-dialog iframe", timeout=15000)
    time.sleep(1)
    frame = page.frame_locator(".ui-dialog iframe").first
    return frame


def open_character_sheet(page, name: str, open_sheet_tab: bool = False) -> None:
    """
    Apre la scheda del personaggio dal journal (doppio click sul nome).
    Dopo l'apertura clicca "Eroe Giocante" per attivare la vista PG.
    Restituisce il frame dell'iframe della scheda.
    """
    print(f"  → Apertura scheda '{name}'...")

    chars = page.locator("#journal .journalitem.character .namecontainer")
    found = False
    for i in range(chars.count()):
        entry = chars.nth(i)
        if name.lower() in entry.inner_text().lower():
            entry.dblclick()
            found = True
            break

    if not found:
        print(f"  → '{name}' non trovato. Creazione nuovo personaggio...")
        page.click("#addnewcharacter", timeout=5000)
        time.sleep(2)
        # Aspetta la dialog di creazione con il campo nome
        page.wait_for_selector(".ui-dialog input.name[data-test='character-edit-name']", timeout=15000)
        save_and_open_sheet(page, name)
        return

    # Personaggio esistente: aspetta l'iframe della scheda di gioco
    page.wait_for_selector(".ui-dialog iframe", timeout=15000)
    time.sleep(1)
    _click_ispc(page)
    time.sleep(LONG_PAUSE)
    print(f"  ✓ Scheda di gioco aperta")


def _click_ispc(page) -> None:
    """
    Clicca il pulsante "Eroe Giocante" (act_isPC) nella scheda TOR2e.
    Il pulsante si trova dentro l'iframe della scheda, in fondo alla pagina.
    """
    try:
        frame = page.frame_locator(".ui-dialog iframe").first
        frame.locator("button[name='act_isPC']").click(timeout=5000)
        print("  ✓ Modalità Eroe Giocante attivata")
        time.sleep(0.5)
    except Exception as e:
        print(f"  ⚠ Impossibile cliccare Eroe Giocante: {e}")


def close_character_sheet(page) -> None:
    try:
        # Prima prova il pulsante Cancel nella dialog
        page.click(".ui-dialog button:has-text('Cancel')", timeout=3000)
    except Exception:
        try:
            page.click(".ui-dialog-titlebar-close", timeout=3000)
        except Exception:
            pass
    time.sleep(1)


# ── Compilazione scheda ───────────────────────────────────────────────────────

def fill_character(page, char: dict) -> None:
    name = char["character_name"]
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")

    # Tutti i campi della scheda sono dentro l'iframe del personaggio
    frame = get_sheet_frame(page)

    # ── Nome ──────────────────────────────────────────────────────
    fill_attr_text(frame, "character_name", name)

    # ── Informazioni generali ─────────────────────────────────────
    print("  [INFO] Informazioni generali...")
    info = char.get("info", {})
    fill_attr_text(frame, "culture",             info.get("culture", ""))
    fill_attr_text(frame, "calling",             info.get("calling", ""))
    fill_attr_text(frame, "standard_of_living",  info.get("standard_of_living", ""))
    fill_attr_text(frame, "shadow_weakness",     info.get("shadow_weakness", ""))
    fill_attr_text(frame, "patron",              info.get("patron", ""))
    fill_attr_text(frame, "fellowship_focus",    info.get("fellowship_focus", ""))
    fill_attr_text(frame, "age",                 info.get("age", ""))
    fill_attr_text(frame, "cultural_blessing",   info.get("cultural_blessing", ""))
    fill_attr_text(frame, "distinctive_features",info.get("distinctive_features", ""))
    fill_attr_text(frame, "flaws",               info.get("flaws", ""))

    # ── Biografia (compilata nella dialog Edit, fuori dall'iframe) ──
    if char.get("bio"):
        fill_bio(page, char["bio"])

    # ── Attributi base (campi number, non radio) ──────────────────
    print("  [ATTR] Attributi base...")
    for attr_name, vals in char.get("attributes", {}).items():
        fill_number(frame, attr_name,          vals.get("rating", 0))
        fill_number(frame, f"{attr_name}tn",   vals.get("tn", 14))

    # ── Derivati ─────────────────────────────────────────────────
    print("  [DERIV] Valori derivati...")
    d = char.get("derived", {})
    end = d.get("endurance", {})
    fill_number(frame, "endurance_max", end.get("max", 0))
    # endurance: nth(0) è visibile, nth(1) è hidden
    fill_js(frame, "input[name='attr_endurance']", end.get("current", 0), nth=0)
    hope = d.get("hope", {})
    fill_number(frame, "hope_max",      hope.get("max", 0))
    # hope: nth(0) è readonly/hidden, nth(1) è quello editabile visibile
    fill_js(frame, "input[name='attr_hope']", hope.get("current", 0), nth=1)
    fill_number(frame, "parry",      d.get("parry", {}).get("base", 0))
    fill_number(frame, "totalparry", d.get("parry", {}).get("total", 0))
    fill_number(frame, "fatigue",       d.get("fatigue", 0))
    fill_number(frame, "treasureload",  d.get("treasureload", 0))

    # ── Saggezza e Valore (campi number + checkbox favoured) ──────
    print("  [WIS/VAL] Saggezza e Valore...")
    wv = char.get("wisdom_valour", {})
    for attr in ("wisdom", "valour"):
        vals = wv.get(attr, {})
        fill_number(frame,   attr,              vals.get("rating", 1))
        fill_checkbox(frame, f"{attr}_favoured", bool(vals.get("favoured", 0)))

    # ── Virtù e Ricompense (textarea) ────────────────────────────
    print("  [VIR] Virtù e Ricompense...")
    fill_textarea(frame, "virtues", char.get("virtues", ""))
    fill_textarea(frame, "rewards", char.get("rewards", ""))

    # ── Condizioni ────────────────────────────────────────────────
    print("  [COND] Condizioni...")
    cond = char.get("conditions", {})
    fill_checkbox(frame, "weary",     bool(cond.get("weary", 0)))
    fill_checkbox(frame, "miserable", bool(cond.get("miserable", 0)))
    fill_checkbox(frame, "wounded",   bool(cond.get("wounded", 0)))
    fill_checkbox(frame, "daunted",   bool(cond.get("daunted", 0)))
    fill_attr_text(frame, "injury",   cond.get("injury", ""))

    # ── Ombra ─────────────────────────────────────────────────────
    print("  [SHADOW] Ombra...")
    sh = char.get("shadow", {})
    fill_number(frame, "shadow",     sh.get("shadow", 0))
    fill_number(frame, "taint",      sh.get("taint", 0))
    fill_number(frame, "shadowscar", sh.get("shadowscar", 0))

    # ── Abilità (tutte radio 0-6 + checkbox favoured) ─────────────
    print("  [SKILL] Abilità...")
    for skill_name, vals in char.get("skills", {}).items():
        fill_radio(frame,    skill_name,              vals.get("rating", 0))
        fill_checkbox(frame, f"{skill_name}_favoured", bool(vals.get("favoured", 0)))

    # ── Competenze di combattimento (radio 0-6 + checkbox) ────────
    print("  [COMBAT_SKILL] Competenze combattimento...")
    for skill_name, vals in char.get("combat_skills", {}).items():
        fill_radio(frame,    skill_name,              vals.get("rating", 0))
        fill_checkbox(frame, f"{skill_name}_favoured", bool(vals.get("favoured", 0)))

    # ── Stance (radio 1-4) ────────────────────────────────────────
    fill_radio(frame, "stance", char.get("stance", 2))

    # ── Armi (slot fissi 1-6) ─────────────────────────────────────
    print("  [WEAPONS] Armi...")
    for i, wpn in enumerate(char.get("weapons", []), start=1):
        fill_attr_text(frame, f"weapon_skill_name_{i}", wpn.get("skill_name", ""))
        fill_select(frame,    f"weapon_combat_prof_{i}", wpn.get("combat_prof", ""))
        fill_number(frame,    f"weapon_damage_{i}",      wpn.get("damage", 0))
        fill_number(frame,    f"weapon_injury_{i}",      wpn.get("injury", 0))
        fill_number(frame,    f"weapon_load_{i}",        wpn.get("load", 0))
        fill_select(frame,    f"weapon_fell_val_{i}",    wpn.get("fell_val", 0))
        fill_select(frame,    f"weapon_grievous_val_{i}",wpn.get("grievous_val", 0))
        fill_select(frame,    f"weapon_keen_val_{i}",    wpn.get("keen_val", 10))
        fill_attr_text(frame, f"weapon_note_{i}",        wpn.get("note", ""))

    # ── Armatura ─────────────────────────────────────────────────
    print("  [ARMOUR] Armatura...")
    arm = char.get("armour", {})

    a = arm.get("armour", {})
    fill_checkbox(frame, "armourprot_active", bool(a.get("active", 1)))
    fill_attr_text(frame,"armour",            a.get("name", ""))
    fill_number(frame,   "armourprot",        a.get("prot", 0))
    fill_number(frame,   "armourload",        a.get("load", 0))
    fill_select(frame,   "armourcf_val",      a.get("cf_val", 0))
    fill_select(frame,   "armourcm_val",      a.get("cm_val", 0))

    h = arm.get("helm", {})
    fill_checkbox(frame, "helmprot_active",   bool(h.get("active", 1)))
    fill_attr_text(frame,"helm",              h.get("name", ""))
    fill_number(frame,   "helmprot",          h.get("prot", 0))
    fill_number(frame,   "helmload",          h.get("load", 0))
    fill_select(frame,   "helmetcf_val",      h.get("cf_val", 0))
    fill_select(frame,   "helmetcm_val",      h.get("cm_val", 0))

    o = arm.get("other", {})
    fill_checkbox(frame, "otherprot_active",  bool(o.get("active", 1)))
    fill_attr_text(frame,"otherprot_name",    o.get("name", ""))
    fill_number(frame,   "otherprot",         o.get("prot", 0))
    fill_number(frame,   "otherload",         o.get("load", 0))
    fill_select(frame,   "othercf_val",       o.get("cf_val", 0))
    fill_select(frame,   "othercm_val",       o.get("cm_val", 0))

    s = arm.get("shield", {})
    fill_checkbox(frame, "shieldparry_active",bool(s.get("active", 1)))
    fill_attr_text(frame,"shield",            s.get("name", ""))
    fill_number(frame,   "shieldparry",       s.get("parry", 0))
    fill_number(frame,   "shieldload",        s.get("load", 0))
    fill_select(frame,   "shieldreinf_val",   s.get("reinf_val", 0))
    fill_select(frame,   "shieldcm_val",      s.get("cm_val", 0))

    # ── Cavalcatura ───────────────────────────────────────────────
    print("  [MOUNT] Cavalcatura...")
    mt = char.get("mount", {})
    fill_attr_text(frame,"mount",          mt.get("name", ""))
    fill_number(frame,   "mountvigour",    mt.get("vigour", 0))
    fill_number(frame,   "mounttreasure",  mt.get("treasure", 0))

    # ── Esperienza / Tesoro ───────────────────────────────────────
    print("  [EXP] Esperienza...")
    exp = char.get("experience", {})
    fill_number(frame, "adventurepoints",      exp.get("adventurepoints", 0))
    fill_number(frame, "skillpoints",          exp.get("skillpoints", 0))
    fill_number(frame, "fellowship",           exp.get("fellowship", 0))
    fill_number(frame, "totaladventurepoints", exp.get("totaladventurepoints", 0))
    fill_number(frame, "totalskillpoints",     exp.get("totalskillpoints", 0))
    fill_number(frame, "treasure",             exp.get("treasure", 0))

    # ── Equipaggiamento da viaggio (textarea) ─────────────────────
    print("  [GEAR] Equipaggiamento...")
    fill_textarea(frame, "travellinggear", char.get("gear", {}).get("travellinggear", ""))

    # ── Note (4 textarea) ─────────────────────────────────────────
    notes = char.get("notes", {})
    if isinstance(notes, str):
        fill_textarea(frame, "notes", notes)
    else:
        for i, key in enumerate(("notes", "notes2", "notes3", "notes4"), start=1):
            val = notes.get(key, "")
            if val:
                fill_textarea(frame, key, val)

    print(f"  ✓ '{name}' completato!")

# ── Main ─────────────────────────────────────────────────────────────────────

def load_characters(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        chars = json.load(f)
    return [c for c in chars if "character_name" in c]


def run_session(page, characters: list[dict]) -> None:
    """Logica comune: verifica sessione, apre campagna, compila schede."""
    print("→ Verifica sessione Roll20...")

    # Se non siamo già su Roll20, naviga
    if "roll20.net" not in page.url:
        page.goto("https://app.roll20.net/")
        page.wait_for_load_state("domcontentloaded", timeout=15000)

    if "login" in page.url:
        print("  ⚠ Non sei loggato su Roll20.")
        print("  Effettua il login a mano nel browser, poi premi INVIO qui.")
        input("  [INVIO per continuare dopo il login] ")

    print("  ✓ Sessione attiva")
    open_campaign(page, CAMPAIGN_ID)

    for char in characters:
        open_character_sheet(page, char["character_name"], open_sheet_tab=True)
        fill_character(page, char)
        close_character_sheet(page)

    print("\n" + "="*60)
    print("  ✓ Tutti i personaggi compilati!")
    print("="*60)


def mode_cdp(p, characters: list[dict]) -> None:
    """
    Connette Playwright a Chrome già in esecuzione via CDP.
    Prima di usare questa modalità:
      1. Avvia Chrome con --remote-debugging-port=9222 (vedi docstring in cima)
      2. Fai il login su Roll20 a mano nel browser
      3. Avvia lo script con --mode cdp
    """
    import subprocess
    result = subprocess.run(["pgrep", "-x", "Google Chrome"], capture_output=True)
    if result.returncode != 0:
        print("✗ Chrome non sembra essere in esecuzione.")
        print("  Avvialo prima con il comando indicato nella docstring dello script.")
        sys.exit(1)

    print(f"→ Connessione a Chrome via CDP su {CDP_URL} ...")
    try:
        browser = p.chromium.connect_over_cdp(CDP_URL)
    except Exception as e:
        print(f"✗ Impossibile connettersi a Chrome: {e}")
        print(f"  Assicurati di aver avviato Chrome con --remote-debugging-port=9222")
        sys.exit(1)

    context = browser.contexts[0] if browser.contexts else browser.new_context()
    page = context.pages[0] if context.pages else context.new_page()
    Stealth().apply_stealth_sync(page)

    try:
        print("  ✓ Connesso a Chrome")
        run_session(page, characters)

    except Exception as e:
        print(f"\n✗ Errore: {e}")
        import traceback; traceback.print_exc()
    finally:
        input("\nPremi INVIO per disconnettersi (il browser rimane aperto)...")
        browser.close()


def mode_profile(p, characters: list[dict]) -> None:
    """
    Playwright lancia Chrome con il profilo reale (launch_persistent_context).
    Chrome deve essere CHIUSO prima dell'esecuzione.
    """
    user_data = Path(CHROME_USER_DATA)
    tmp_dir   = None

    if not user_data.exists():
        print(f"✗ Directory profilo Chrome non trovata: {user_data}")
        print("  Verifica CHROME_USER_DATA nello script.")
        sys.exit(1)

    import subprocess
    result = subprocess.run(["pgrep", "-x", "Google Chrome"], capture_output=True)
    if result.returncode == 0:
        print("\n✗ Chrome sembra essere ancora in esecuzione.")
        print("  Chiudilo completamente con Cmd+Q, poi riavvia lo script.")
        sys.exit(1)

    if USE_PROFILE_COPY:
        tmp_dir  = tempfile.mkdtemp(prefix="chrome_playwright_")
        dest     = Path(tmp_dir) / "chrome"
        print("  Copia profilo in corso... ", end="", flush=True)
        shutil.copytree(str(user_data), str(dest))
        user_data = dest
        print(f"fatto → {user_data}")

    print(f"  Profilo Chrome: {user_data / CHROME_PROFILE}")
    print("  Avvio Chrome... ", end="", flush=True)

    context = p.chromium.launch_persistent_context(
        user_data_dir=str(user_data),
        channel="chrome",
        headless=False,
        slow_mo=80,
        viewport={"width": 1440, "height": 900},
        args=[f"--profile-directory={CHROME_PROFILE}"],
        timeout=30000,
    )
    print("fatto")
    page = context.pages[0] if context.pages else context.new_page()
    Stealth().apply_stealth_sync(page)

    try:
        run_session(page, characters)
    except Exception as e:
        print(f"\n✗ Errore: {e}")
        import traceback; traceback.print_exc()
    finally:
        input("\nPremi INVIO per chiudere il browser...")
        context.close()
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="Compila schede Roll20 TOR 2e Advanced tramite Chrome",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modalità:
  cdp      Connette Playwright a Chrome già aperto (consigliata).
           Avvia prima Chrome con --remote-debugging-port=9222,
           fai il login su Roll20 a mano, poi esegui lo script.

  profile  Playwright lancia Chrome con il profilo reale.
           Chrome deve essere CHIUSO prima dell'esecuzione.
        """
    )
    parser.add_argument(
        "--mode", choices=["cdp", "profile"], default="cdp",
        help="Modalità di connessione (default: cdp)"
    )
    args = parser.parse_args()

    characters = load_characters(CHARACTERS_FILE)
    if not characters:
        print("Nessun personaggio trovato in personaggi.json")
        sys.exit(1)

    print(f"Modalità: {args.mode}")
    print(f"Personaggi da compilare: {len(characters)}")
    for c in characters:
        print(f"  - {c['character_name']}")
    print()

    with sync_playwright() as p:
        if args.mode == "cdp":
            mode_cdp(p, characters)
        else:
            mode_profile(p, characters)


if __name__ == "__main__":
    main()
