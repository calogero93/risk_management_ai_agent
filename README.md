# Risk Management AI Agent

Agente conversazionale per l'analisi del dossier di rischio di **Banca Meridiana S.p.A.**, cliente istituzionale fittizio monitorato da FinSecure Analytics. Il sistema cerca nei documenti, estrae KPI, confronta i valori rilevati con i limiti, simula alcuni scenari e visualizza l'andamento delle esposizioni.

L'obiettivo è aiutare un analista a individuare presto superamenti e incoerenze, verificare la conformità al Risk Appetite Framework e interrogare il dossier in linguaggio naturale. Le conclusioni dell'agente vanno comunque controllate sulle fonti: la valutazione descritta sotto mostra sia risultati utili sia omissioni.

## Il dossier e il problema

Il corpus comprende **15 documenti PDF sintetici**, datati da giugno 2025 a marzo 2026, nelle aree credito, mercato, liquidità, patrimonio e governance. L'appendice statistica contiene serie mensili da gennaio 2023. Il documento di riferimento è il **Risk Appetite Framework**: stabilisce le soglie senza le quali non sarebbe possibile definire in modo verificabile un superamento. Gli altri documenti riportano valori osservati, decisioni, note tecniche e rilievi di audit.

Ho inserito deliberatamente **dieci criticità** nel dossier, suddivise in quattro categorie:

| Categoria | Casi | Esempio |
| --- | ---: | --- |
| Fattori di rischio | 3 | Concentrazione real estate al 27,1% rispetto al limite del 25%. |
| Inesattezze | 3 | RWA dichiarati pari a 5.400 Mio EUR, mentre le componenti sommano a 5.600. |
| Omissioni | 2 | Esito del backtesting assente nel report di gennaio, benché richiesto dalla policy. |
| Interpretazioni erronee | 2 | Limite VaR verificato sulla media anziché sul dato puntuale. |

I PDF sono generati da [corpus.py](src/risk_management_ai_agent/corpus.py). Nella cartella `data/` vengono prodotti anche `metadata.json`, `limiti.json` e `criticita_attese.json`. Quest'ultimo contiene la soluzione attesa per la valutazione; **non viene indicizzato né messo a disposizione dell'agente**. Anche i limiti sono conservati in JSON per il confronto deterministico, mentre i documenti PDF costituiscono il materiale interrogabile.

## Scelte progettuali

Ho organizzato il lavoro in tre fasi: preparazione del corpus e della pipeline di ingestione e ricerca; sviluppo degli schemi, degli strumenti e dell'agente; valutazione delle risposte e visualizzazione dei dati. La prima fase ha richiesto particolare attenzione alla lettura dei PDF, alla suddivisione del testo e alla qualità del recupero dei passaggi.

### Lettura e suddivisione dei documenti

Uso **LlamaIndex `SimpleDirectoryReader`** per leggere i PDF e ricavare testo e metadati, tra cui il nome del file necessario per citare la fonte. Le pagine dello stesso documento vengono riunite prima della suddivisione. I chunk conservano nome, indice progressivo, area, tipo e data del documento.

Il testo viene diviso con `RecursiveCharacterTextSplitter`, con chunk di 1.000 caratteri e sovrapposizione di 200. I separatori privilegiano paragrafi e righe prima di arrivare a spazi e caratteri. La dimensione è un compromesso: chunk troppo piccoli frammentano il contesto, chunk troppo grandi diluiscono l'informazione utile e aggiungono rumore alla risposta. Nei documenti regolatori è particolarmente importante mantenere insieme articoli, commi e relativi valori.

Per questo corpus considero il testo estratto dai PDF e un'unica strategia di suddivisione. Su documenti reali andrebbero esaminati tabelle, immagini, separatori e possibili strategie diverse per tipo di file. La mappa dei metadati usata dall'ingestione è fissa: è pratica per un esercizio con 15 documenti, ma non sarebbe una soluzione adeguata per un flusso documentale in produzione.

### Embedding e ricerca ibrida

Ho scelto l'embedder multilingua **`intfloat/multilingual-e5-small`** perché i documenti e le domande sono in italiano e il modello è abbastanza leggero per l'uso locale. Un modello più grande potrebbe migliorare la qualità, ma richiederebbe più risorse; il cambio ha senso solo dopo una misura del retrieval. Lo stesso modello deve essere usato per documenti e query, con i prefissi `passage:` e `query:` previsti dalla sua modalità d'uso.

I vettori sono indicizzati in **ChromaDB**, con distanza coseno. Per le dimensioni attuali del corpus, un archivio locale è sufficiente e non ci sono requisiti stringenti di latenza. Chroma usa l'indicizzazione HNSW; su migliaia di documenti, invece, valuterei qualità, tempi, memoria e persistenza con misure dedicate prima di confermare questa scelta. L'indice viene costruito all'avvio dell'agente.

Accanto alla ricerca semantica uso **BM25**. Nel lessico finanziario, sigle come LCR, NSFR, CET1, RWA e VaR, codici di protocollo e nomi di controparti possono beneficiare della corrispondenza lessicale. La ricerca densa resta utile per domande formulate con parole diverse da quelle del documento, per esempio «esposizione immobiliare» rispetto a «real estate e costruzioni». I risultati vengono fusi con **Reciprocal Rank Fusion (RRF)**: conta la posizione nelle due liste, non il valore assoluto dei rispettivi score; `alpha` permette di regolarne il peso relativo.

### Estrazione, limiti e agente

L'estrazione dei KPI usa un modello Anthropic con output strutturato secondo schemi **Pydantic**. Per ogni indicatore vengono conservati nome canonico, eventuale segmento, periodo, valore, unità, natura e fonte. La natura distingue un valore **rilevato** da una media, un obiettivo o uno scenario: solo il dato rilevato viene confrontato con una soglia per segnalare un superamento in essere. Il vocabolario dei nomi KPI è chiuso per limitare nomi inventati e facilitare il confronto fra documenti. Su un corpus reale lo definirei dopo aver esaminato un campione rappresentativo, anziché fissarlo a priori.

I limiti vengono letti da `limiti.json`, generato insieme alla policy e quindi coerente con essa per costruzione. Ho preferito un confronto **deterministico** tra KPI estratti e soglie: evita un'ulteriore chiamata al modello e riduce gli errori nel controllo numerico. La dipendenza dall'estrazione resta, però, e se cambia la policy il JSON dei limiti deve essere aggiornato. Il confronto copre i superamenti; non equivale a un controllo automatico di tutte le inesattezze, omissioni e interpretazioni presenti nel dossier.

L'agente è orchestrato con **LangChain** e può scegliere tra quattro strumenti: ricerca dei documenti, estrazione dei KPI e verifica dei limiti, lettura integrale di un documento, simulazione di scenario. Una factory passa agli strumenti gli oggetti di analisi e ricerca, che il modello non può fornire come argomenti serializzati. Il flusso è iterativo: il modello riceve la domanda, invoca uno o più strumenti e usa i risultati per rispondere. Il prompt chiede di citare i file, riportare entrambi i valori in caso di discordanza e verificare i dati numerici con lo strumento di analisi. Un checkpointer in memoria e un riepilogo della conversazione aiutano a gestire domande successive nello stesso thread.

La scelta iniziale del modello è **Anthropic Haiku**: per questo perimetro mi aspetto che sia sufficiente e meno costoso di un modello più grande. Il modello effettivo si imposta con `MODEL_NAME`, quindi si può provare un altro modello Anthropic senza cambiare il codice. Non considero questa scelta convalidata per corpus o domande più complessi: servirebbe confrontare qualità, costo e tempo di risposta.

### Scenari e dashboard

Lo strumento di simulazione legge le serie storiche mensili e adatta semplici **regressioni lineari**: Euribor 3M per margine di interesse e portafoglio titoli, impieghi per LCR. Restituisce valori attuali, previsioni e possibili violazioni dei limiti. Quando l'Euribor richiesto esce dall'intervallo osservato, aggiunge un'avvertenza sull'estrapolazione. È una simulazione esplorativa basata sulle serie sintetiche, non una previsione validata per decisioni finanziarie.

La dashboard mostra LCR, impieghi lordi, Euribor 3M e margine di interesse nel tempo; per l'LCR visualizza anche la soglia interna e quella regolamentare.

## Avvio

Servono Python 3.11 o 3.12, [`uv`](https://docs.astral.sh/uv/), una chiave API Anthropic per le richieste all'agente e una connessione a Hugging Face al primo caricamento dell'embedder. Su Linux il lockfile usa la variante CPU di PyTorch.

```bash
uv sync --locked
cp .env.example .env
```

Inserire in `.env` un `MODEL_NAME` Anthropic valido, `API_KEY` e `EMBEDDING_MODEL`. L'esempio usa `intfloat/multilingual-e5-small`. Il file `.env` è escluso da Git.

```bash
uv run risk-agent corpus
uv run --env-file .env risk-agent ask "Quali documenti abbiamo sul rischio di mercato?"
uv run --env-file .env risk-agent chat
uv run --env-file .env risk-agent test
uv run --env-file .env risk-agent dashboard --output dashboard.png
```

`corpus` genera i PDF e i tre JSON in `data/`, una cartella esclusa da Git e rigenerabile. `ask` pone una domanda; `chat` conserva il contesto tra domande nella stessa esecuzione. `test` invia in sequenza **18 domande di prova** e comporta chiamate all'API. La dashboard può essere aperta a schermo omettendo `--output` in un ambiente grafico. Per scegliere un'altra cartella dati, impostare `DATA_DIR` oppure passare `--data-dir PERCORSO` prima del comando.

Per le verifiche locali del corpus e delle regole deterministiche, senza chiamate all'API:

```bash
uv run python -m unittest discover -s tests
```

## Valutazione

Ho confrontato le risposte dell'agente con le dieci criticità deliberate, usando domande per area che non suggerivano la criticità da cercare. In quella esecuzione l'agente ne ha **rilevate 7 su 10**; un'ulteriore omissione è stata colta solo parzialmente. Le risposte dipendono dal modello configurato e possono variare tra esecuzioni.

| ID | Categoria | Esito | Osservazione |
| --- | --- | --- | --- |
| F1 | Fattore di rischio | Rilevata | Concentrazione real estate 27,1% contro 25%, qualificata correttamente. |
| F2 | Fattore di rischio | Non rilevata | Riporta 92 Mio EUR e 10,8%, ma non li confronta con il limite. |
| F3 | Fattore di rischio | Rilevata | VaR puntuale 13,2 Mio EUR contro 12,0. |
| I1 | Inesattezza | Non rilevata | Riporta RWA 5.400 e componenti senza verificarne la somma. |
| I2 | Inesattezza | Rilevata | Riporta 460 e 415 Mio EUR con le rispettive fonti. |
| I3 | Inesattezza | Rilevata | Nota la divergenza nella sensitività, ma tramite un calcolo manuale e non con la regressione. |
| O1 | Omissione | Rilevata | Riconosce il backtesting assente nel report di gennaio. |
| O2 | Omissione | Parziale | Nota le due posizioni real estate, senza collegarle alla verifica su base di gruppo richiesta dalla policy. |
| E1 | Interpretazione erronea | Rilevata | Riconosce che la policy vieta di usare la media per verificare il limite VaR. |
| E2 | Interpretazione erronea | Rilevata | Contesta la descrizione dell'LCR come «ampiamente superiore» alla soglia, a fronte di un margine di 2 punti percentuali. |

Il confronto con la soluzione attesa è stato fatto con l'ausilio di Claude e poi verificato manualmente. Per un corpus più ampio andrebbe automatizzato con criteri espliciti di valutazione.

L'agente ha gestito bene diversi confronti semantici tra affermazioni e dati, comprese entrambe le interpretazioni erronee e la discordanza tra verbale e report analitico. I due insuccessi principali hanno cause diverse. **I1** richiede di riconciliare aritmeticamente il totale RWA con le sue componenti, controllo per cui non esiste uno strumento dedicato. In **F2** il valore compare nella risposta, ma l'agente usa il testo letto senza passare dal confronto strutturato con il limite. Ho mitigato questo comportamento nel prompt, chiedendo la verifica dei numeri, ma la prova non dimostra che sia risolto.

## Limiti e sviluppi

Il corpus sintetico permette di sapere quali problemi ci si aspetta di trovare, ma non misura da solo la qualità su documenti reali. Prima di estendere il sistema valuterei:

- una verifica aritmetica delle tabelle, dei totali e delle componenti, per intercettare casi come I1;
- un controllo del flusso che renda affidabile la verifica dei limiti quando l'agente ha già letto il testo del documento;
- parsing e chunking su tabelle, immagini e documenti eterogenei, insieme a metadati prodotti senza una mappa fissa;
- prove di retrieval e prestazioni su corpus grandi, confrontando embedder e configurazioni dell'indice;
- schemi KPI definiti su campioni reali, invece che su un elenco chiuso deciso in anticipo;
- misure di costo e latenza delle chiamate al modello, con eventuale accorpamento delle richieste e limiti più precisi sulle ripetizioni degli strumenti. Il `recursion_limit` di default è 25 passi complessivi, ma non limita da solo la ripetizione della stessa chiamata;
- una valutazione ripetibile delle risposte, prima di considerare affidabile il supporto all'audit.

## Struttura del progetto

```text
src/risk_management_ai_agent/
  corpus.py        Generazione dei 15 PDF e dei tre JSON
  ingestion.py     Lettura PDF, metadati e chunking
  retrieval.py     Embedding, ChromaDB, BM25 e RRF
  schemas.py       Schemi Pydantic per KPI e limiti
  analysis.py      Estrazione KPI, verifica dei limiti e serie storiche
  agent_tools.py   Strumenti di ricerca, analisi, simulazione e lettura
  agent.py         Prompt e composizione dell'agente
  dashboard.py     Grafici delle esposizioni
  questions.py     Domande di prova
  cli.py           Comandi da terminale
tests/             Verifiche deterministiche
```
