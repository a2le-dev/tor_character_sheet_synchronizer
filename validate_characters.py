"""
TOR2e - Validazione del file personaggi
=======================================
Controlla un file JSON di personaggi contro personaggi.schema.json
e segnala anche problemi non strutturali (immagine mancante, schema vecchio).

Usato all'avvio da fill_pdf.py e fill_sheets.py; si può anche lanciare da solo:

    python validate_characters.py personaggi.json
    python validate_characters.py out_of_the_shadow.json

Requisiti:
    pip install jsonschema
"""

import json
import sys
from pathlib import Path

SCHEMA_FILE = Path(__file__).parent / "personaggi.schema.json"
BASE_DIR    = Path(__file__).parent   # base per gli image_path relativi


def _path_str(path) -> str:
    """Trasforma un percorso jsonschema (deque) in 'skills.awe.rating' / 'weapons[0].damage'."""
    out = ""
    for p in path:
        out += f"[{p}]" if isinstance(p, int) else (f".{p}" if out else str(p))
    return out or "(radice)"


def _char_label(data, index) -> str:
    try:
        return f"'{data[index]['character_name']}'"
    except (KeyError, IndexError, TypeError):
        return f"#{index + 1}"


def validate_characters(path: Path, base_dir: Path = BASE_DIR) -> tuple[list, list, list]:
    """
    Valida il file. Restituisce (personaggi, errori, avvisi).
    Gli errori bloccano l'esecuzione, gli avvisi no.
    """
    errors, warnings = [], []

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return [], [f"File non trovato: {path}"], []
    except json.JSONDecodeError as e:
        return [], [f"JSON non valido: riga {e.lineno}, colonna {e.colno}: {e.msg}"], []

    # ── Validazione strutturale con JSON Schema ───────────────────
    Validator = None
    try:
        from jsonschema import Draft202012Validator as Validator
    except ImportError:
        try:
            # jsonschema < 4: niente draft 2020-12, ripiego sul draft 7
            # (lo schema non usa costrutti specifici del 2020-12)
            from jsonschema import Draft7Validator as Validator
            warnings.append("jsonschema obsoleto: validazione con il draft 7 "
                            "(pip install -U jsonschema)")
        except ImportError:
            warnings.append("Modulo 'jsonschema' non installato: controllo dello schema saltato "
                            "(pip install jsonschema)")
    if Validator:
        with open(SCHEMA_FILE, encoding="utf-8") as f:
            schema = json.load(f)
        validator = Validator(schema)
        for err in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
            p = list(err.absolute_path)
            if p and isinstance(p[0], int):
                who = _char_label(data, p[0])
                field = _path_str(p[1:])
            else:
                who, field = "file", _path_str(p)
            errors.append(f"{who} → {field}: {_translate(err)}")

    if not isinstance(data, list):
        return [], errors or ["Il file deve contenere una lista di personaggi"], warnings

    # ── Controlli aggiuntivi (avvisi) ─────────────────────────────
    for i, c in enumerate(data):
        if not isinstance(c, dict):
            continue
        who = _char_label(data, i)
        info = c.get("info", {}) if isinstance(c.get("info"), dict) else {}

        for key in ("bio", "image_path"):
            if key in c:
                warnings.append(f"{who} → '{key}' è al primo livello: spostalo in 'info.{key}'")

        img = info.get("image_path") or c.get("image_path")
        if img:
            p = Path(img)
            if not p.is_absolute():
                p = base_dir / p
            if not p.exists():
                warnings.append(f"{who} → immagine non trovata: {p}")
        else:
            warnings.append(f"{who} → nessuna immagine (info.image_path)")

        if not (info.get("bio") or c.get("bio")):
            warnings.append(f"{who} → bio vuota")

        for j, w in enumerate(c.get("weapons") or []):
            if isinstance(w, dict) and w.get("combat_prof") == "":
                warnings.append(f"{who} → weapons[{j}] '{w.get('skill_name', '')}': "
                                "competenza (combat_prof) non impostata")

        names = [x.get("character_name") for x in data if isinstance(x, dict)]
        n = names.count(c.get("character_name"))
        if n > 1 and names.index(c.get("character_name")) == i:
            warnings.append(f"{who} → nome ripetuto {n} volte nel file: "
                            "le schede con lo stesso nome si sovrascrivono")

    chars = [c for c in data if isinstance(c, dict) and "character_name" in c]
    return chars, errors, warnings


def _translate(err) -> str:
    """Messaggi di jsonschema più leggibili, in italiano."""
    v = err.validator
    if v == "required":
        missing = err.message.split("'")[1] if "'" in err.message else err.message
        return f"manca il campo obbligatorio '{missing}'"
    if v == "additionalProperties":
        allowed = set(err.schema.get("properties", {}))
        extra = ", ".join(f"'{k}'" for k in err.instance if k not in allowed)
        return f"campo non previsto: {extra} (refuso?)"
    if v == "type":
        return f"tipo errato: {err.instance!r} non è {err.validator_value}"
    if v == "enum":
        return f"valore {err.instance!r} non ammesso, valori possibili: {err.validator_value}"
    if v == "minimum":
        return f"valore {err.instance!r} sotto il minimo {err.validator_value}"
    if v == "maximum":
        return f"valore {err.instance!r} sopra il massimo {err.validator_value}"
    if v == "minLength":
        return "stringa vuota"
    if v == "minItems":
        return "lista vuota"
    return err.message


def load_and_validate(path: Path, base_dir: Path = BASE_DIR) -> list[dict]:
    """
    Carica e valida i personaggi; stampa errori e avvisi.
    Termina il programma se ci sono errori.
    """
    chars, errors, warnings = validate_characters(Path(path), base_dir)
    print(f"→ Validazione {Path(path).name}...")
    for w in warnings:
        print(f"  ⚠ {w}")
    if errors:
        for e in errors:
            print(f"  ✗ {e}")
        print(f"✗ {len(errors)} errori: correggi il file e riprova.")
        sys.exit(1)
    print(f"  ✓ {len(chars)} personaggi validi")
    return chars


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python validate_characters.py <file_personaggi.json>")
        sys.exit(2)
    load_and_validate(Path(sys.argv[1]))
