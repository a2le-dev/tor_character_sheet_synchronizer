"""
The One Ring 2e - Utility analisi campi PDF
============================================
Analizza un PDF editabile e genera un file di configurazione JSON
con tutti i campi trovati, pronti da mappare con i dati del personaggio.

Requisiti:
    pip install pypdf --break-system-packages

Utilizzo:
    python parse_pdf_fields.py scheda.pdf
    python parse_pdf_fields.py scheda.pdf --output config_scheda.json
    python parse_pdf_fields.py scheda.pdf --character personaggi.json
"""

import json
import argparse
import sys
from pathlib import Path
from pypdf import PdfReader


# Valori JSON del personaggio disponibili per il mapping (dot-notation)
AVAILABLE_JSON_PATHS = [
    "character_name",
    "info.culture",
    "info.calling",
    "info.standard_of_living",
    "info.shadow_weakness",
    "info.patron",
    "info.fellowship_focus",
    "info.age",
    "info.cultural_blessing",
    "info.distinctive_features",
    "info.flaws",
    "attributes.strength.rating",
    "attributes.strength.tn",
    "attributes.heart.rating",
    "attributes.heart.tn",
    "attributes.wits.rating",
    "attributes.wits.tn",
    "derived.endurance.current",
    "derived.endurance.max",
    "derived.hope.current",
    "derived.hope.max",
    "derived.parry.base",
    "derived.parry.total",
    "derived.fatigue",
    "derived.load",
    "derived.treasureload",
    "wisdom_valour.wisdom.rating",
    "wisdom_valour.wisdom.favoured",
    "wisdom_valour.valour.rating",
    "wisdom_valour.valour.favoured",
    "virtues",
    "rewards",
    "conditions.weary",
    "conditions.miserable",
    "conditions.wounded",
    "conditions.daunted",
    "conditions.injury",
    "shadow.shadow",
    "shadow.taint",
    "shadow.shadowscar",
    "skills.awe.rating",
    "skills.awe.favoured",
    "skills.athletics.rating",
    "skills.athletics.favoured",
    "skills.awareness.rating",
    "skills.awareness.favoured",
    "skills.hunting.rating",
    "skills.hunting.favoured",
    "skills.song.rating",
    "skills.song.favoured",
    "skills.craft.rating",
    "skills.craft.favoured",
    "skills.enhearten.rating",
    "skills.enhearten.favoured",
    "skills.travel.rating",
    "skills.travel.favoured",
    "skills.insight.rating",
    "skills.insight.favoured",
    "skills.healing.rating",
    "skills.healing.favoured",
    "skills.courtesy.rating",
    "skills.courtesy.favoured",
    "skills.battle.rating",
    "skills.battle.favoured",
    "skills.persuade.rating",
    "skills.persuade.favoured",
    "skills.stealth.rating",
    "skills.stealth.favoured",
    "skills.scan.rating",
    "skills.scan.favoured",
    "skills.explore.rating",
    "skills.explore.favoured",
    "skills.riddle.rating",
    "skills.riddle.favoured",
    "skills.lore.rating",
    "skills.lore.favoured",
    "combat_skills.axes.rating",
    "combat_skills.bows.rating",
    "combat_skills.spears.rating",
    "combat_skills.swords.rating",
    "combat_skills.brawl.rating",
    "experience.adventurepoints",
    "experience.totaladventurepoints",
    "experience.skillpoints",
    "experience.totalskillpoints",
    "experience.fellowship",
    "experience.treasure",
    "armour.armour.name",
    "armour.armour.prot",
    "armour.armour.load",
    "armour.helm.name",
    "armour.helm.prot",
    "armour.helm.load",
    "armour.other.name",
    "armour.other.prot",
    "armour.other.load",
    "armour.shield.name",
    "armour.shield.parry",
    "armour.shield.load",
    "weapons[0].skill_name",
    "weapons[0].damage",
    "weapons[0].injury",
    "weapons[0].load",
    "weapons[0].note",
    "weapons[1].skill_name",
    "weapons[1].damage",
    "weapons[1].injury",
    "weapons[1].load",
    "weapons[1].note",
    "weapons[2].skill_name",
    "weapons[2].damage",
    "weapons[2].injury",
    "weapons[2].load",
    "weapons[2].note",
    "weapons[3].skill_name",
    "weapons[3].damage",
    "weapons[3].injury",
    "weapons[3].load",
    "weapons[3].note",
    "gear.travellinggear",
    "notes.notes",
    "notes.notes2",
    "notes.notes3",
    "notes.notes4",
    "stance",
]


def get_nested(obj: dict, path: str):
    """Naviga un dizionario con dot-notation e array[N]."""
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


def guess_mapping(field_name: str, field_type: str) -> str:
    """
    Tenta di indovinare il mapping JSON dal nome del campo PDF.
    Restituisce il path suggerito o stringa vuota se non riesce.
    """
    name = field_name.lower()

    # Abilità con suffisso _N (radio/checkbox per livello)
    skill_map = {
        "intimorire": "skills.awe",
        "atletica": "skills.athletics",
        "allerta": "skills.awareness",
        "caccia": "skills.hunting",
        "canzoni": "skills.song",
        "manualita": "skills.craft",
        "incoraggiare": "skills.enhearten",
        "viaggio": "skills.travel",
        "perspicacia": "skills.insight",
        "guarigione": "skills.healing",
        "cortesia": "skills.courtesy",
        "battaglia": "skills.battle",
        "convincere": "skills.persuade",
        "furtivita": "skills.stealth",
        "scrutare": "skills.scan",
        "esplorazione": "skills.explore",
        "indovinelli": "skills.riddle",
        "sapienza": "skills.lore",
        "asce": "combat_skills.axes",
        "archi": "combat_skills.bows",
        "lance": "combat_skills.spears",
        "spade": "combat_skills.swords",
        # English
        "awe": "skills.awe",
        "athletics": "skills.athletics",
        "awareness": "skills.awareness",
        "hunting": "skills.hunting",
        "song": "skills.song",
        "craft": "skills.craft",
        "enhearten": "skills.enhearten",
        "travel": "skills.travel",
        "insight": "skills.insight",
        "healing": "skills.healing",
        "courtesy": "skills.courtesy",
        "battle": "skills.battle",
        "persuade": "skills.persuade",
        "stealth": "skills.stealth",
        "scan": "skills.scan",
        "explore": "skills.explore",
        "riddle": "skills.riddle",
        "lore": "skills.lore",
        "axes": "combat_skills.axes",
        "bows": "combat_skills.bows",
        "spears": "combat_skills.spears",
        "swords": "combat_skills.swords",
    }

    # Campi radio abilità: nome_N → skills.xxx.rating (level N)
    for skill_pdf, skill_json in skill_map.items():
        if name.startswith(skill_pdf + "_") and name.split("_")[-1].isdigit():
            level = int(name.split("_")[-1])
            return f"{skill_json}.rating>={level}"  # "compila se rating >= N"
        if name == f"spunta-{skill_pdf}":
            return f"{skill_json}.favoured"

    # Condizioni
    if "affaticato" in name or "weary" in name:
        return "conditions.weary"
    if "oppresso" in name or "miserable" in name:
        return "conditions.miserable"
    if "ferito" in name or "wounded" in name:
        return "conditions.wounded"

    # Campi testo comuni
    text_map = {
        "nome": "character_name",
        "name": "character_name",
        "cultura": "info.culture",
        "culture": "info.culture",
        "vocazione": "info.calling",
        "calling": "info.calling",
        "vantaggio": "info.cultural_blessing",
        "cultural_blessing": "info.cultural_blessing",
        "eta": "info.age",
        "age": "info.age",
        "tenore": "info.standard_of_living",
        "patrono": "info.patron",
        "patron": "info.patron",
        "discesa": "info.shadow_weakness",
        "shadow_weakness": "info.shadow_weakness",
        "tratti": "info.distinctive_features",
        "distinctive_features": "info.distinctive_features",
        "difetti": "info.flaws",
        "flaws": "info.flaws",
        "tesoro": "experience.treasure",
        "treasure": "experience.treasure",
        "virtu_saggezza": "wisdom_valour.wisdom.rating",
        "wisdom": "wisdom_valour.wisdom.rating",
        "ricompense_valore": "wisdom_valour.valour.rating",
        "valour": "wisdom_valour.valour.rating",
        "virtu": "virtues",
        "ricompense": "rewards",
        "rewards": "rewards",
        "lesioni": "conditions.injury",
        "injury": "conditions.injury",
        "forza_grado": "attributes.strength.rating",
        "forza_tn": "attributes.strength.tn",
        "forza_resistenza": "derived.endurance.max",
        "cuore_grado": "attributes.heart.rating",
        "cuore_tn": "attributes.heart.tn",
        "cuore_speranza": "derived.hope.max",
        "ingegno_tn": "attributes.wits.tn",
        "ingegno_difesa": "derived.parry.base",
        "res-attuale": "derived.endurance.current",
        "spe-attuale": "derived.hope.current",
        "punti-avventura": "experience.adventurepoints",
        "punti-abilita": "experience.skillpoints",
        "valore-compagnia": "experience.fellowship",
        "equip-viaggio": "gear.travellinggear",
        "armatura_protezione": "armour.armour.prot",
        "armatura_ingombro": "armour.armour.load",
        "elmo_protezione": "armour.helm.prot",
        "elmo_ingombro": "armour.helm.load",
        "scudo_protezione": "armour.shield.parry",
        "scudo_ingombro": "armour.shield.load",
    }

    for key, path in text_map.items():
        if key in name:
            return path

    # Armi con suffisso _N
    weapon_map = {
        "equipaggiamento": "skill_name",
        "danno": "damage",
        "ferire": "injury",
        "ingombro": "load",
        "note": "note",
    }
    for key, wpn_field in weapon_map.items():
        if name.startswith(key + "_") and name.split("_")[-1].isdigit():
            idx = int(name.split("_")[-1]) - 1
            return f"weapons[{idx}].{wpn_field}"

    return ""


def analyze_pdf(pdf_path: Path, char_sample: dict = None) -> dict:
    """Analizza il PDF e costruisce il file di configurazione."""
    reader = PdfReader(str(pdf_path))
    fields = reader.get_fields()

    config = {
        "_meta": {
            "pdf": pdf_path.name,
            "total_fields": len(fields),
            "note": (
                "Ogni campo ha: 'type' (/Tx=testo, /Btn=checkbox/radio), "
                "'json_path' (path nel JSON personaggio, da compilare), "
                "'sample_value' (valore di esempio dal personaggio di test se fornito). "
                "Per i campi radio abilità il json_path usa la sintassi "
                "'skills.xxx.rating>=N' che significa: spunta se rating >= N."
            )
        },
        "fields": {}
    }

    for field_name, field in sorted(fields.items()):
        ft = field.get('/FT', '/Tx')
        ft_str = str(ft)

        guessed = guess_mapping(field_name, ft_str)

        entry = {
            "type": ft_str,
            "json_path": guessed,
        }

        # Valore di esempio dal personaggio sample
        if char_sample and guessed:
            try:
                if ">=" in guessed:
                    # Campo radio abilità: skills.xxx.rating>=N
                    path, threshold = guessed.split(">=")
                    val = get_nested(char_sample, path)
                    entry["sample_value"] = "✓" if (val or 0) >= int(threshold) else ""
                else:
                    val = get_nested(char_sample, guessed)
                    entry["sample_value"] = str(val) if val is not None else ""
            except Exception:
                entry["sample_value"] = ""

        config["fields"][field_name] = entry

    return config


def main():
    parser = argparse.ArgumentParser(
        description="Analizza campi PDF e genera configurazione per fill_pdf.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  python parse_pdf_fields.py scheda_ita.pdf
  python parse_pdf_fields.py scheda_eng.pdf --output config_eng.json
  python parse_pdf_fields.py scheda_ita.pdf --character personaggi.json
        """
    )
    parser.add_argument("pdf", help="PDF da analizzare")
    parser.add_argument(
        "--output", default=None,
        help="File di output JSON (default: config_{nome_pdf}.json)"
    )
    parser.add_argument(
        "--character", default=None,
        help="File personaggi.json per popolare sample_value"
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"✗ File non trovato: {pdf_path}")
        sys.exit(1)

    output_path = Path(args.output) if args.output else \
        pdf_path.parent / f"config_{pdf_path.stem}.json"

    # Carica personaggio sample se fornito
    char_sample = None
    if args.character:
        char_file = Path(args.character)
        if char_file.exists():
            with open(char_file, encoding="utf-8") as f:
                chars = json.load(f)
            char_sample = next((c for c in chars if "character_name" in c), None)
            if char_sample:
                print(f"  Personaggio di esempio: {char_sample['character_name']}")

    print(f"→ Analisi PDF: {pdf_path.name}")
    config = analyze_pdf(pdf_path, char_sample)
    print(f"  Campi trovati: {config['_meta']['total_fields']}")

    # Conta campi con mapping automatico
    mapped = sum(1 for f in config["fields"].values() if f["json_path"])
    print(f"  Mapping automatico: {mapped}/{config['_meta']['total_fields']}")
    unmapped = config["_meta"]["total_fields"] - mapped
    if unmapped:
        print(f"  ⚠ Campi senza mapping: {unmapped} (da completare manualmente)")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"  ✓ Configurazione salvata: {output_path}")

    # Mostra campi senza mapping
    if unmapped:
        print("\nCampi senza mapping automatico:")
        for name, field in config["fields"].items():
            if not field["json_path"]:
                print(f"  [{field['type']}] {name}")


if __name__ == "__main__":
    main()
