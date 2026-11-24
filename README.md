# TOR2e Character Sheet Filler

Strumenti Python per compilare automaticamente le schede personaggio di **L'Unico Anello 2a Edizione** (The One Ring 2nd Edition) su [Roll20](https://roll20.net) e in formato PDF.

---

## Indice

- [Panoramica](#panoramica)
- [Struttura del progetto](#struttura-del-progetto)
- [Requisiti](#requisiti)
- [Configurazione](#configurazione)
- [Utilizzo — Roll20](#utilizzo--roll20)
- [Utilizzo — PDF](#utilizzo--pdf)
- [Validazione del file personaggi](#validazione-del-file-personaggi)
- [Licenza](#licenza)

---

## Panoramica

Il progetto è composto da cinque script principali:

| Script | Descrizione |
|---|---|
| `fill_sheets.py` | Compila le schede personaggio su Roll20 tramite automazione browser (Playwright + CDP) |
| `dump_sheet.py` | Operazione inversa: esporta le schede Roll20 compilate in un JSON nel formato di `personaggi.json` |
| `fill_pdf.py` | Compila una scheda PDF editabile a partire da un file di configurazione |
| `parse_pdf_fields.py` | Analizza un PDF editabile e genera automaticamente il file di configurazione dei campi |
| `validate_characters.py` | Valida un file personaggi contro `personaggi.schema.json` (eseguito anche all'avvio di `fill_pdf.py` e `fill_sheets.py`) |

---

## Struttura del progetto

```
tor2e_roll20/
├── fill_sheets.py              # Automazione Roll20
├── dump_sheet.py               # Esportazione Roll20 → JSON
├── fill_pdf.py                 # Compilazione PDF
├── parse_pdf_fields.py         # Analisi campi PDF
├── validate_characters.py      # Validazione del file personaggi
├── personaggi.schema.json      # JSON Schema del file personaggi
├── personaggi.json             # Dati dei personaggi (da compilare)
├── config_scheda_editabile.json # Configurazione campi PDF
├── scheda_editabile.pdf        # Template PDF (non incluso — da procurarsi)
├── imgs/                       # Immagini dei personaggi (opzionale)
│   └── nome_cognome.png
└── output_pdf/                 # PDF compilati (generati dallo script)
```

---

## Requisiti

- Python 3.11+
- Google Chrome installato (per Roll20)

### Installazione dipendenze

```bash
pip install -r requirements.txt
playwright install chromiumx
```

---

## Configurazione

### `personaggi.json`

Il file contiene la lista dei personaggi da compilare. La struttura completa è definita in `personaggi.schema.json` (vedi [Validazione](#validazione-del-file-personaggi)); in sintesi, ogni personaggio ha questa forma:

```json
[
  {
    "character_name": "Eglantina Scarpati",
    "info": {
      "culture":            "Hobbit della Contea",
      "calling":            "Studiosa",
      "standard_of_living": "Prospero",
      "age":                "34",
      "cultural_blessing":  "Buonsenso hobbit",
      "distinctive_features": "Curiosa, Educata, Rime di sapienza",
      "flaws":              "",
      "patron":             "",
      "shadow_weakness":    "",
      "fellowship_focus":   "",
      "bio":                "**Eglantina Scarpati** è una hobbit della Contea...\n\n## Una mattina di partenza\n\n*Testo in corsivo*, **grassetto**.",
      "image_path":         "imgs/eglantina_scarpati.png"
    },
    "attributes": {
      "strength": { "rating": 2, "tn": 16 },
      "heart":    { "rating": 6, "tn": 12 },
      "wits":     { "rating": 6, "tn": 11 }
    },
    "derived": {
      "endurance": { "current": 20, "max": 20 },
      "hope":      { "current": 16, "max": 16 },
      "parry":     { "base": 8, "total": 8 },
      "fatigue":   0,
      "load":      0
    },
    "wisdom_valour": {
      "wisdom": { "rating": 1, "favoured": 0 },
      "valour":  { "rating": 1, "favoured": 0 }
    },
    "virtues":  "Prodezza (ing.)",
    "rewards":  "",
    "skills": {
      "awe":       { "rating": 0, "favoured": 0 },
      "courtesy":  { "rating": 2, "favoured": 1 },
      "...":       "tutte le 18 abilità sono obbligatorie"
    },
    "combat_skills": {
      "axes":   { "rating": 0, "favoured": 0 },
      "bows":   { "rating": 1, "favoured": 0 },
      "spears": { "rating": 0, "favoured": 0 },
      "swords": { "rating": 2, "favoured": 0 },
      "brawl":  { "rating": 0, "favoured": 0 }
    },
    "stance": 2,
    "weapons": [
      {
        "skill_name":  "Spada corta",
        "combat_prof": "swords",
        "damage": 3, "injury": 14, "load": 1
      }
    ],
    "armour": {
      "armour": { "name": "", "prot": 0, "load": 0 },
      "helm":   { "name": "", "prot": 0, "load": 0 },
      "shield": { "name": "", "parry": 0, "load": 0 }
    },
    "shadow":  { "shadow": 0, "shadowscar": 0 },
    "experience": {
      "adventurepoints": 0, "skillpoints": 0,
      "fellowship": 0, "treasure": 0
    },
    "conditions": { "weary": 0, "miserable": 0, "wounded": 0 },
    "gear": { "travellinggear": "" },
    "notes": { "notes": "", "notes2": "", "notes3": "", "notes4": "" }
  }
]
```

### Sintassi Markdown per il campo `bio`

Il campo `bio` accetta testo in Markdown semplice:

| Sintassi | Risultato |
|---|---|
| `**testo**` | **grassetto** |
| `*testo*` | *corsivo* |
| `~~testo~~` | ~~barrato~~ |
| `## Titolo` | Titolo H2 |
| `# Titolo` | Titolo H1 |
| `- elemento` | Lista puntata |
| `\n\n` | Paragrafo (riga vuota) |

---

## Utilizzo — Roll20

Lo script usa Chrome via CDP (Chrome DevTools Protocol) per compilare le schede.

### 1. Avvia Chrome in modalità debug

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
    --remote-debugging-port=9222 \
    --user-data-dir="/tmp/chrome-debug" \
    --no-first-run \
    --no-default-browser-check
```

### 2. Accedi a Roll20

Nel browser aperto, vai su [app.roll20.net](https://app.roll20.net) ed effettua il login. Apri la campagna e assicurati che il Journal sia visibile.

### 3. Configura lo script

Apri `fill_sheets.py` e imposta:

```python
CAMPAIGN_ID      = "XXXXXXXX"    # ID visibile nell'URL della campagna
CHROME_USER_DATA = "/tmp/chrome-debug"
CHROME_PROFILE   = "Default"
```

### 4. Esegui

```bash
python fill_sheets.py --mode cdp
python fill_sheets.py --mode cdp --characters out_of_the_shadow.json
```

### Note

- I personaggi vengono cercati nel Journal per nome esatto. Se non trovati, vengono creati automaticamente.
- La scheda supporta la versione **The One Ring 2e (Advanced)** di Roll20.
- Stance di combattimento: `1`=Offensiva, `2`=Aperta, `3`=Difensiva, `4`=Arretrata.

### Esportazione da Roll20 (`dump_sheet.py`)

Fa l'operazione inversa: legge le schede già compilate e crea `personaggi_dump.json` nello stesso formato di `personaggi.json`. Chrome va avviato in modalità debug e la campagna aperta come per `fill_sheets.py`.

```bash
python dump_sheet.py --names "Eglantina Scarpati" "Esmeralda Tuc"
python dump_sheet.py --names-file nomi.txt --output personaggi_dump.json
python dump_sheet.py        # usa i nomi presenti in personaggi.json
```

- I personaggi vengono cercati nel Journal per nome (esatto, poi parziale), anche dentro cartelle chiuse. Non vengono mai creati né modificati.
- La biografia viene riconvertita da HTML a Markdown e salvata in `info.bio`.
- L'avatar viene scaricato in `imgs/` e referenziato in `info.image_path`.

---

## Utilizzo — PDF

### Compilazione scheda esistente

```bash
python fill_pdf.py \
    --input scheda_editabile.pdf \
    --config config_scheda_editabile.json \
    --characters personaggi.json
```

I PDF compilati vengono salvati in `output_pdf/`.

### Supporto per schede alternative

Per usare una scheda PDF diversa (es. versione inglese o fan-made):

**1. Analizza la scheda e genera la configurazione:**

```bash
python parse_pdf_fields.py scheda_eng.pdf \
    --character personaggi.json \
    --output config_scheda_eng.json
```

**2. Rivedi `config_scheda_eng.json`** e completa i campi senza mapping automatico (marcati con `json_path: ""`).

**3. Compila:**

```bash
python fill_pdf.py \
    --input scheda_eng.pdf \
    --config config_scheda_eng.json
```

### Formato del file di configurazione PDF

Ogni campo nel file di configurazione ha questa struttura:

```json
"nome-campo-pdf": {
  "type":       "/Tx",
  "json_path":  "info.culture"
}
```

I tipi di campo sono `/Tx` (testo), `/Btn` (checkbox/radio).

La notazione `json_path` usa dot-notation per navigare il JSON del personaggio:

| json_path | Valore |
|---|---|
| `character_name` | Nome del personaggio |
| `info.culture` | Cultura eroica |
| `attributes.strength.rating` | Grado di Forza |
| `skills.awe.rating>=3` | Spunta se Intimidire ≥ 3 |
| `conditions.weary` | Checkbox Affaticato |
| `weapons[0].damage` | Danno prima arma |

### Immagine personaggio

Aggiungi il campo `image_path` in `info` nel JSON:

```json
"info": {
  "image_path": "imgs/eglantina_scarpati.png"
}
```

L'immagine deve essere in formato PNG o JPEG. Viene centrata automaticamente nello spazio disponibile mantenendo le proporzioni.

---

## Validazione del file personaggi

La struttura del file personaggi è descritta in `personaggi.schema.json`, scritto in [JSON Schema](https://json-schema.org/) (draft 2020-12): lo standard per descrivere i documenti JSON, l'analogo di XSD per l'XML.

`fill_pdf.py` e `fill_sheets.py` validano il file all'avvio, prima di compilare qualsiasi scheda o aprire il browser. Si può anche lanciare la validazione da sola:

```bash
python validate_characters.py personaggi.json
```

Gli **errori** fermano l'esecuzione: campi obbligatori mancanti, campi non previsti (spesso refusi, come `stelth` al posto di `stealth`), tipi sbagliati (`"13"` invece di `13`), valori fuori intervallo (abilità oltre 6, posizione diversa da 1-4, `combat_prof` non valido). Esempio:

```
→ Validazione personaggi.json...
  ✗ 'Svior figlio di Ulfrung' → skills: campo non previsto: 'stelth' (refuso?)
  ✗ 'Svior figlio di Ulfrung' → skills.awe.rating: valore 7 sopra il massimo 6
✗ 2 errori: correggi il file e riprova.
```

Gli **avvisi** non fermano l'esecuzione: immagine non trovata, bio vuota, arma senza competenza (`combat_prof` vuoto), nomi di personaggio ripetuti (le schede si sovrascrivono), `bio` o `image_path` al primo livello invece che in `info` (schema vecchio, ancora accettato).

Senza il modulo `jsonschema` installato, il controllo dello schema viene saltato con un avviso e restano solo gli altri controlli.

### Validazione nell'editor

Lo schema si può collegare all'editor per avere autocompletamento ed errori evidenziati mentre si scrive il JSON. In VS Code, in `.vscode/settings.json`:

```json
"json.schemas": [
  {
    "fileMatch": ["personaggi*.json", "out_of_the_shadow.json", "piromanti.json", "!personaggi.schema.json"],
    "url": "./personaggi.schema.json"
  }
]
```

---

## Licenza

<a rel="license" href="https://creativecommons.org/licenses/by-nc-sa/4.0/">
<img alt="Creative Commons License" style="border-width:0" src="https://i.creativecommons.org/l/by-nc-sa/4.0/88x31.png" /></a>

Questo progetto è distribuito sotto licenza
**[Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)](https://creativecommons.org/licenses/by-nc-sa/4.0/)**.

Sei libero di:
- **Condividere** — copiare e ridistribuire il materiale in qualsiasi formato
- **Adattare** — remixare, trasformare e sviluppare il materiale

Alle seguenti condizioni:
- **Attribuzione** — devi dare credito appropriato, fornire un link alla licenza e indicare se sono state apportate modifiche
- **NonCommerciale** — non puoi usare il materiale per scopi commerciali
- **StessaLicenza** — se remixi, trasformi o sviluppi il materiale, devi distribuire i tuoi contributi con la stessa licenza

---

> **Nota**: questo progetto non è affiliato né approvato da **Free League Publishing** (editore di The One Ring) o **Roll20**. Il nome "The One Ring" e i relativi contenuti sono proprietà dei rispettivi titolari. Il progetto automatizza solo la compilazione di schede — non distribuisce né riproduce contenuti protetti da copyright.
