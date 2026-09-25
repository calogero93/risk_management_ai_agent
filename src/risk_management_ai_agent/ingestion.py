from collections import defaultdict

from langchain_text_splitters import RecursiveCharacterTextSplitter
from llama_index.core import SimpleDirectoryReader

METADATA = {
  "01_policy_limiti_rischio.pdf": {
    "doc_type": "policy",
    "tipo": "risk appetite framework",
    "area": "governance",
    "data": 20250630
  },
  "11_verbale_comitato_rischi_20260210.pdf": {
    "doc_type": "meeting_minutes",
    "tipo": "verbale",
    "area": "governance",
    "data": 20260210
  },
  "12_registro_incidenti_operativi_2025.pdf": {
    "doc_type": "register",
    "tipo": "registro incidenti",
    "area": "governance",
    "data": 20260115
  },
  "13_nota_audit_rilievi.pdf": {
    "doc_type": "internal_note",
    "tipo": "nota di audit",
    "area": "governance",
    "data": 20260224
  },
  "15_nota_cro_priorita_2026.pdf": {
    "doc_type": "internal_note",
    "tipo": "nota di indirizzo",
    "area": "governance",
    "data": 20260302
  },
  "02_report_esposizioni_creditizie_q4_2025.pdf": {
    "doc_type": "risk_report",
    "tipo": "report esposizioni",
    "area": "credit",
    "data": 20260122
  },
  "03_report_concentrazione_controparti_q4_2025.pdf": {
    "doc_type": "risk_report",
    "tipo": "report concentrazione",
    "area": "credit",
    "data": 20260122
  },
  "04_nota_ecl_stage_q4_2025.pdf": {
    "doc_type": "internal_note",
    "tipo": "nota tecnica",
    "area": "credit",
    "data": 20260128
  },
  "05_report_var_dicembre_2025.pdf": {
    "doc_type": "risk_report",
    "tipo": "report VaR",
    "area": "market",
    "data": 20260108
  },
  "06_report_var_gennaio_2026.pdf": {
    "doc_type": "risk_report",
    "tipo": "report VaR",
    "area": "market",
    "data": 20260206
  },
  "07_appendice_statistica_serie_mensili.pdf": {
    "doc_type": "risk_report",
    "tipo": "appendice statistica",
    "area": "market",
    "data": 20260212
  },
  "08_report_liquidita_q4_2025.pdf": {
    "doc_type": "risk_report",
    "tipo": "report liquidità",
    "area": "liquidity",
    "data": 20260120
  },
  "09_nota_tesoreria_funding_2026.pdf": {
    "doc_type": "internal_note",
    "tipo": "nota di tesoreria",
    "area": "liquidity",
    "data": 20260219
  },
  "10_report_adeguatezza_patrimoniale_q4_2025.pdf": {
    "doc_type": "risk_report",
    "tipo": "report patrimoniale",
    "area": "capital",
    "data": 20260130
  },
  "14_report_stress_test_2025.pdf": {
    "doc_type": "risk_report",
    "tipo": "stress test",
    "area": "capital",
    "data": 20260205
  }
}

class Chunker():
  """
  Prende i documenti presenti in una cartella, estrapola il testo e i metadati
  e crea i chunks. Al momento è prevista una sola strategia di chunking.
  """
  def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
    self.chunk_size = chunk_size
    self.chunk_overlap = chunk_overlap

  def _chunk_testo(self, testo: str, file_name: str) -> list[dict]:
    """
    Applica la strategia di chunking al testo di un documento e restituisce i
    chunk arricchiti con i metadati.
    Args:
      testo(str): testo completo del documento, già ricomposto da tutte le pagine
      file_name(str): nome del file, per i metadati e per l'id del chunk
    Output:
      list[dict]: lista dei chunk con payload e metadati
    """
    text_splitter = RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n", "; ", " ", ""],
        chunk_size=self.chunk_size,
        chunk_overlap=self.chunk_overlap,
    )
    chunks = text_splitter.split_text(text=testo)
    return [{"file_name": file_name, "chunk_index": i, "payload": c,
             **METADATA.get(file_name, {})}
            for i, c in enumerate(chunks)]

  def documents_splitter(self, directory_path: str = "./data"):
    """
    Orchestra la pipeline di chunking:
    1. legge i documenti ed estrapola il testo
    2. raggruppa le pagine dello stesso file, così il chunk_index resta progressivo
    3. splitta e restituisce i chunk arricchiti con i metadati
    Args:
      directory_path(str): cartella con i documenti da elaborare
    Output:
      list[dict]: lista completa di tutti i chunk di tutti i documenti
    """
    documents = SimpleDirectoryReader(directory_path, required_exts=[".pdf"]).load_data()

    testi = defaultdict(list)
    for d in documents:
      testi[d.metadata.get("file_name", "unknown")].append(d.text)

    documents_chunks = []
    for file_name, parti in testi.items():
      try:
        documents_chunks.extend(self._chunk_testo("\n".join(parti), file_name))
      except Exception as e:
        print(f"Skippo {file_name}: {e}")

    if not documents_chunks:
      raise RuntimeError(f"Nessun chunk prodotto da {directory_path}")

    return documents_chunks
