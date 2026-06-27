# DataForge

**An AI agent that generates realistic synthetic CSV datasets from a natural language description.**

DataForge uses an agentic loop powered by Claude to read a domain document (or query Wikipedia automatically), infer an entity-aware schema with confidence scores, and produce coherent, statistically consistent data — row by row, entity by entity.

*Documentation in English. Para consultas en español, no dudes en contactarme.*

---

## See It In Action

### 1. Autonomous Wikipedia Research
DataForge decides on its own what to search, queries Wikipedia multiple times, and synthesizes the results into domain knowledge.

![Wikipedia Research](https://raw.githubusercontent.com/jarpaivan-wq/DataForge/main/screenshots/01_wikipedia_research.png)

### 2. Entity-Aware Schema with Theoretical Justification
Every column is justified. Value ranges are assigned per entity — not averaged across the dataset — with biological correlations built in.

![Entity-Aware Schema](https://raw.githubusercontent.com/jarpaivan-wq/DataForge/main/screenshots/02_entity_aware_schema.png)

### 3. Generation Summary & Token Efficiency
Full transparency on what was generated, sources used, and tokens consumed.

![Generation Summary](https://raw.githubusercontent.com/jarpaivan-wq/DataForge/main/screenshots/03_generation_summary.png)

---

## Features

- **Entity-aware schema inference** — generates value ranges per entity, not global averages. A Zergling and an Ultralisk get physically coherent stats, not blended nonsense.
- **Automatic Wikipedia fallback** — no source document? DataForge fetches domain knowledge on its own.
- **Schema cache** — inferred schemas are saved to disk. A 56% token reduction on repeated runs (43,234 → 18,893 tokens in benchmarks).
- **Confidence scoring** — entities with low data coverage receive conservative ranges and are flagged for review.
- **Dynamic temperature** — `0.7` during schema inference (creative), `0.5` during generation (consistent), `0.0` for tool routing (precise).
- **PII guard** — requests for real personal data are detected and refused, evaluated by an LLM-as-judge test.
- **Full test suite** — 4 integration tests including adversarial cases and an LLM-as-judge evaluator.

---

## How It Works

```
User describes a domain
        │
        ▼
Schema cache hit? ──YES──► Inject synthetic tool-calls ──► generar_csv
        │ NO
        ▼
leer_documento (local file) or buscar_wikipedia (auto-fetch)
        │
        ▼
inferir_esquema — entity-aware ranges + confidence scores
   └── Saves result to schemas/{key}.json
        │
        ▼
generar_csv — coherent values per entity, biological variables included
        │
        ▼
Token usage report
```

---

## Quickstart

### 1. Clone and install

```bash
git clone https://github.com/jarpaivan-wq/DataForge.git
cd DataForge
pip install -r requirements.txt
```

### 2. Configure your API key

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=your_key_here
```

> **Windows / corporate networks:** DataForge includes `truststore` for SSL certificate injection. No extra config needed.

### 3. Run

```bash
python agent/dataforge.py
```

Then describe your dataset in natural language:

```
> Describe your domain: StarCraft II Zerg units — biological characteristics
> How many rows? 500
```

DataForge will read or fetch domain knowledge, infer the schema, and produce a `.csv` file.

### Special commands

| Command | What it does |
|---|---|
| `limpiar caché` | Deletes all cached schemas in `schemas/` |
| `salir` / `exit` | Exits the agent |

---

## Running Tests

Tests require a valid `ANTHROPIC_API_KEY` in your `.env`.

```bash
# Full integration suite
pytest -m integration -s -v

# Single test
pytest test_dataforge.py::test_adversarial_refuses_real_people_data -m integration -s -v
```

### Test coverage

| Test | What it verifies |
|---|---|
| `test_happy_path_sismos` | 500-row CSV with coherent column names, Wikipedia invoked |
| `test_zerg_entity_aware_ranges` | Larva mass < Ultralisk mass, entity-aware ranges coherent |
| `test_wikipedia_empty_returns_error` | Empty Wikipedia → agent informs user instead of hallucinating |
| `test_adversarial_refuses_real_people_data` | PII request → professional refusal, evaluated by LLM-as-judge |

---

## Project Structure

```
DataForge/
├── dataforge.py          # Main agent
├── test_dataforge.py     # Integration test suite
├── pytest.ini            # Pytest marker config
├── requirements.txt
├── .gitignore
├── CHANGELOG.md
├── screenshots/          # Demo screenshots
└── README.md
```

> `schemas/` is excluded from version control — it is generated locally at runtime.

---

## Tech Stack

- [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) — agentic loop and tool use
- [Claude Haiku](https://www.anthropic.com/claude) (`claude-haiku-4-5`) — fast, cost-efficient model
- [Wikipedia REST API](https://en.wikipedia.org/api/rest_v1/) — open knowledge base
- Python standard library — `sqlite3`, `json`, `os`, `pathlib`

---

## License

MIT License — © 2026 Iván

You are free to use, modify, and distribute this project. Attribution is required — please keep the author credit in any copies or derivatives.

---

## Author

**Iván** — BI Analyst & AI developer  
Building AI agents for data and collections workflows.  
[LinkedIn](https://www.linkedin.com/in/biexcel) · [GitHub](https://github.com/jarpaivan-wq)
