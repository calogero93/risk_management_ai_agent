from .analysis import RiskAnalyzer
from .agent_tools import crea_tools
from .ingestion import Chunker
from .retrieval import ChromaDB

from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langgraph.checkpoint.memory import MemorySaver


SYSTEM_AGENTE = """Sei un assistente per il team di gestione del rischio di FinSecure Analytics.
Rispondi a domande sul dossier di rischio del cliente Banca Meridiana usando esclusivamente
i tool a disposizione.

COME PROCEDERE
- Non conosci in anticipo quali documenti esistono: usa cerca_documenti
  per individuarli, poi analizzali con gli altri tool.
- Cita sempre il documento da cui proviene ogni dato, nel formato [nome_file].
- Se i documenti riportano valori discordanti sulla stessa grandezza, riportali entrambi
  con le rispettive fonti. Non scegliere un valore e non fare medie.
- Non calcolare da solo importi, percentuali o proiezioni: usa i tool.
- Se i tool non contengono l'informazione, dillo esplicitamente invece di ipotizzare.
- Per qualsiasi domanda su criticità, limiti o valori numerici, dopo aver individuato
  i documenti devi chiamare identifica_anomalie su ciascuno. Non rispondere basandoti
  sui passaggi restituiti dalla ricerca.
- Se un documento afferma che un limite è rispettato, verificalo comunque con i tool:
  l'affermazione contenuta in un report non è una verifica.

QUANDO SEGNALI UNA CRITICITÀ
Indica sempre il valore rilevato, la soglia di riferimento e il documento che lo riporta.
"""
def crea_agente(directory_path: str = "data"):
    chunks = Chunker().documents_splitter(directory_path)
    print(f"chunk: {len(chunks)}")

    chroma = ChromaDB()
    chroma.index(chunks)
    print(f"indicizzati: {chroma.collection.count()}")

    analyzer = RiskAnalyzer(directory_path)
    tools = crea_tools(analyzer, chroma)
    checkpointer = MemorySaver()

    agente = create_agent(
        model=analyzer.model,
        tools=tools,
        system_prompt=SYSTEM_AGENTE,
        checkpointer=checkpointer,
        middleware=[SummarizationMiddleware(model=analyzer.model, max_token_before_summary=1000)]
    )
    return agente
