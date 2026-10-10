#!/usr/bin/env python3

import json
import csv
import sys

INPUT_FILE = "personaggi.json"
OUTPUT_FILE = "personaggi_sintesi.csv"

with open(INPUT_FILE, "r", encoding="utf-8") as f:
    characters = json.load(f)

# intestazione
header = ["Caratteristica"] + [
    c["character_name"] for c in characters
]

rows = []

# vocazione
rows.append(
    ["Vocazione"] +
    [c["info"]["calling"] for c in characters]
)

# attributi
rows.append(
    ["Forza"] +
    [c["attributes"]["strength"]["rating"] for c in characters]
)

rows.append(
    ["Cuore"] +
    [c["attributes"]["heart"]["rating"] for c in characters]
)

rows.append(
    ["Ingegno"] +
    [c["attributes"]["wits"]["rating"] for c in characters]
)

# tratti distintivi
for idx in range(3):
    riga = [f"Tratto {idx+1}"]

    for c in characters:
        tratti = [
            t.strip()
            for t in c["info"]["distinctive_features"].split(",")
        ]

        riga.append(tratti[idx] if idx < len(tratti) else "")

    rows.append(riga)

# skill favorite
skill_labels = {
    "awe": "Awe",
    "athletics": "Athletics",
    "awareness": "Awareness",
    "hunting": "Hunting",
    "song": "Song",
    "craft": "Craft",
    "enhearten": "Enhearten",
    "travel": "Travel",
    "insight": "Insight",
    "healing": "Healing",
    "courtesy": "Courtesy",
    "battle": "Battle",
    "persuade": "Persuade",
    "stealth": "Stealth",
    "scan": "Scan",
    "explore": "Explore",
    "riddle": "Riddle",
    "lore": "Lore"
}

favoured_row = ["Skill favorite"]

for c in characters:
    favoured = []

    for skill, data in c["skills"].items():
        if data.get("favoured", 0):
            favoured.append(skill_labels.get(skill, skill))

    favoured_row.append("; ".join(favoured))

rows.append(favoured_row)

# altre caratteristiche significative
rows.append(
    ["Cultura"] +
    [c["info"]["culture"] for c in characters]
)

rows.append(
    ["Età"] +
    [c["info"]["age"] for c in characters]
)

rows.append(
    ["Debolezza dell'Ombra"] +
    [c["info"]["shadow_weakness"] for c in characters]
)

rows.append(
    ["Benedizione culturale"] +
    [c["info"]["cultural_blessing"] for c in characters]
)

rows.append(
    ["Virtù"] +
    [c.get("virtues", "") for c in characters]
)

rows.append(
    ["Saggezza"] +
    [c["wisdom_valour"]["wisdom"]["rating"] for c in characters]
)

rows.append(
    ["Valore"] +
    [c["wisdom_valour"]["valour"]["rating"] for c in characters]
)

rows.append(
    ["Speranza"] +
    [c["derived"]["hope"]["max"] for c in characters]
)

rows.append(
    ["Resistenza"] +
    [c["derived"]["endurance"]["max"] for c in characters]
)

with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f, delimiter=";")
    writer.writerow(header)
    writer.writerows(rows)

print(f"Creato: {OUTPUT_FILE}")