from .analysis import RiskAnalyzer
from .ingestion import METADATA
from .retrieval import ChromaDB

from langchain_core.tools import tool
import numpy as np
from sklearn.linear_model import LinearRegression

def crea_tools(analyzer: RiskAnalyzer, chroma: ChromaDB):

  @tool
  def cerca_documenti(query: str, area: str | None = None):
    """
    Permette di cercare i documenti che fanno riferimento al contesto della query
    e di elencare i metadati di questi file in modo che altri tool posso usare
    queste informazioni per selezionari i file di interesse

    Args:
      query(str): la richiesta dell'utente che viene usata per cercare i documenti inerenti
      area(str): area tematica dei documenti (credit, market, liquidity, capital) nel caso in cui dalla query si identifica una certa area tematica

    Output:
      lista_metadata(list[dict]): è la lista dei metadati dei file scelti
    """
    where = {"area": area} if area else None
    return [{"file_name": d.metadata["file_name"],
              "area": d.metadata.get("area")}
            for d in chroma.hybrid_search(query, where=where)]

  @tool
  def identifica_anomalie(file_name: str):
    """
    Permette di estrapolare i kpi da un file e confrontarlo con i limiti di rischio
    per verificare se alcuni kpi sono o non sono stati rispettati

    Args:
      file_name(str): il nome del file da analizzare

    Output:
      lista_anomalie(list[dict]): la lista di tutte le anomalie riscontrate
    """
    if file_name not in METADATA:
        return {"errore": f"documento non trovato: {file_name}",
                "disponibili": list(METADATA)}
    kpi = analyzer.estrai_kpi(file_name)
    return {"kpi": [k.model_dump() for k in kpi],
            "superamenti": [a.model_dump() for a in analyzer.verifica_limiti(kpi)]}

  @tool
  def simula_scenario(euribor: float, impieghi: float | None = None) -> dict:
    """
    Simula l'impatto di uno scenario economico sugli indicatori di rischio. Il modello
    è stimato sulle serie storiche mensili e restituisce i valori previsti per il livello
    di Euribor indicato.

    Args:
      euribor(float): livello dell'Euribor 3M nello scenario, in percentuale (es. 5.0)
      impieghi(float): livello degli impieghi in milioni, per la previsione dell'LCR.
                      Omettere per usare l'ultimo valore osservato.

    Output:
      dict: valori previsti per margine, titoli e LCR, con il livello attuale a confronto
    """
    serie = analyzer.leggi_serie()

    X = np.array(serie["euribor"]).reshape(-1, 1)
    previsti = {
        "margine_interesse": LinearRegression().fit(X, serie["margine"]).predict([[euribor]])[0],
        "portafoglio_titoli": LinearRegression().fit(X, serie["titoli"]).predict([[euribor]])[0],
    }

    imp = impieghi if impieghi is not None else serie["impieghi"][-1]
    Xi = np.array(serie["impieghi"]).reshape(-1, 1)
    previsti["lcr"] = LinearRegression().fit(Xi, serie["lcr"]).predict([[imp]])[0]

    attuali = {"margine_interesse": serie["margine"][-1],
              "portafoglio_titoli": serie["titoli"][-1],
              "lcr": serie["lcr"][-1]}

    violazioni = [{"indicatore": n, "previsto": round(v, 2), "soglia": analyzer.limiti[n].valore}
                  for n, v in previsti.items()
                  if n in analyzer.limiti and
                  (v < analyzer.limiti[n].valore if analyzer.limiti[n].verso == "min"
                  else v > analyzer.limiti[n].valore)]

    fuori_range = not (min(serie["euribor"]) <= euribor <= max(serie["euribor"]))

    return {"scenario": {"euribor": euribor, "impieghi": round(imp, 1)},
            "attuale": {k: round(v, 2) for k, v in attuali.items()},
            "previsto": {k: round(v, 2) for k, v in previsti.items()},
            "violazioni": violazioni,
            "avvertenze": (["Euribor fuori dall'intervallo osservato (2,3%-4,1%): "
                            "il valore è un'estrapolazione."] if fuori_range else [])}
  @tool
  def leggi_documento(file_name: str) -> str:
      """Restituisce il testo integrale di un documento. Usare quando serve verificare
      cosa un documento afferma o se contiene una certa informazione.
      Args:
        file_name(str): nome del file da leggere
      Outputs:
        il testo completo del file
      """
      if file_name not in METADATA:
          return f"Documento non trovato. Disponibili: {list(METADATA)}"
      return analyzer.leggi(file_name)

  return [cerca_documenti, identifica_anomalie, simula_scenario, leggi_documento]
