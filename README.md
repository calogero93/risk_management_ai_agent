# Risk Management AI Agent

Versione Python del [notebook originale](notebooks/Agente%20AI%20per%20la%20Gestione%20del%20Rischio%20Finanziario%20e%20Audit%20Interattivi.ipynb). Il progetto conserva il corpus sintetico, i prompt, gli schemi KPI, la ricerca ibrida ChromaDB/BM25, la verifica dei limiti, la simulazione e le 18 domande di prova del notebook.

## Requisiti

- Python 3.11 o 3.12
- [`uv`](https://docs.astral.sh/uv/)
- Una chiave API Anthropic per le domande all'agente
- Connessione a Hugging Face al primo uso del modello di embedding

Su Linux, il lockfile installa PyTorch nella variante CPU. Il corpus viene salvato in `data/`, che è esclusa da Git e può essere rigenerata.

## Avvio

```bash
uv sync --locked
cp .env.example .env
```

Inserire in `.env` un `MODEL_NAME` Anthropic valido, `API_KEY` e `EMBEDDING_MODEL`. Il modello di embedding usato nel notebook è `intfloat/multilingual-e5-small`, già indicato nell'esempio. La chiave resta locale: `.env` è escluso da Git.

```bash
uv run risk-agent corpus
uv run --env-file .env risk-agent ask "Quali documenti abbiamo sul rischio di mercato?"
uv run --env-file .env risk-agent chat
uv run --env-file .env risk-agent test
uv run --env-file .env risk-agent dashboard --output dashboard.png
```

`chat` mantiene lo stesso thread tra le domande. `test` ripropone in sequenza le 18 domande del notebook e comporta chiamate all'API. La dashboard può anche essere aperta a schermo omettendo `--output` in un ambiente grafico. Per usare un'altra cartella dati, specificare `--data-dir PERCORSO` prima del comando oppure impostare `DATA_DIR`.

Per verificare il corpus e le regole locali senza chiamate all'API:

```bash
uv run python -m unittest discover -s tests
```

## Struttura

```text
src/risk_management_ai_agent/
  corpus.py        Generazione dei 15 PDF e dei tre JSON
  ingestion.py     Lettura PDF, metadati e chunking
  retrieval.py     Embedding, ChromaDB, BM25 e RRF
  schemas.py       Schemi Pydantic dei KPI e dei limiti
  analysis.py      Estrazione KPI, verifica dei limiti e serie storiche
  agent_tools.py   Tool di ricerca, analisi, simulazione e lettura
  agent.py         Prompt e composizione dell'agente
  dashboard.py     Grafici delle esposizioni
  questions.py     Domande di prova del notebook
  cli.py           Comandi da terminale
notebooks/         Notebook originale conservato come riferimento
tests/             Verifiche deterministiche
```

Il corpus è volutamente sintetico. La valutazione riportata nel notebook ha rilevato 7 delle 10 criticità deliberate; le risposte dell'agente dipendono dal modello configurato e non sono garantite identiche tra esecuzioni.
