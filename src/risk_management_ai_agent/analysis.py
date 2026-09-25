import json
import os

from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from llama_index.core import SimpleDirectoryReader

from .schemas import Anomalia, KPI, Limite, ListaKPI

import re

SYSTEM_KPI = """
Estrai dal documento tutti gli indicatori di KPI, seguendo lo schema fornito.

Estrapola solo i dati scritti senza provare a calcolare o rielaborare,
se trovi lo stesso KPI in periodi diversi indicali entrambi come KPI separati
in periodi diversi.
Se i dati riportato valori sullo stesso KPI che fanno riferimento a misure diverse
indicali entrambi come KPI separati con diversa "natura".
"""


class RiskAnalyzer:
    def __init__(self, directory_path: str):
        self.model = ChatAnthropic(
            model=os.environ["MODEL_NAME"],
            api_key=os.environ["API_KEY"],
            temperature=0,
        )
        self.documents = SimpleDirectoryReader(directory_path, required_exts=[".pdf"]).load_data()
        with open(f"{directory_path}/limiti.json", encoding="utf-8") as f:
          grezzi = json.load(f)

        campi = set(Limite.model_fields)
        self.limiti = {
            nome: Limite(nome=nome,
                        **{k: v for k, v in dati.items() if k in campi})
            for nome, dati in grezzi.items()
        }

    def leggi(self, file_name: str) -> str:
        parti = [d.text for d in self.documents
                 if d.metadata.get("file_name") == file_name]
        if not parti:
            raise ValueError(f"Documento non trovato: {file_name}")
        return "\n".join(parti)

    def estrai_kpi(self, file_name: str) -> list[KPI]:
        """
        Funzione che estrae i kpi di un report finanziario e restituisce
        un dato strutturato con tutte le informazioni utili definite nello schema
        Args:
          file_name(str): nome del file dal quale estrarre i KPI
        Output:
          lista_kpi(list[KPI]): lista dei KPI trovate per il documento
        """
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_KPI),
            ("human", "{documento}"),
        ])
        model = self.model.with_structured_output(ListaKPI)

        chain = prompt | model

        risultato = chain.invoke({"documento": self.leggi(file_name)})
        for k in risultato.kpi:
            k.fonte = file_name
        lista_kpi = risultato.kpi

        return lista_kpi

    def verifica_limiti(self, kpi: list[KPI]) -> list[Anomalia]:
        """
        Funzione che identifica la violazione dei limiti per ogni kpi estratto
        da un file, dato che lo si può confrontare deterministicamente ho preferito
        non delegare ad un LLM che potrebbe portare imprecisioni o richiedere un modello
        più costoso per performare bene
        Args:
          kpi(list[KPI]): i KPI estratti da un documento
        Output:
          list[Anomalia]: le violazioni di limite riscontrate
        """
        anomalie = []
        for k in kpi:
            limite = self.limiti.get(k.nome)
            # i KPI di natura diversa da 'rilevato' non si confrontano con i limiti:
            # medie, target e valori di scenario non sono violazioni in essere
            if limite is None or k.natura != "rilevato":
                continue

            violato = (k.valore > limite.valore if limite.verso == "max"
                       else k.valore < limite.valore)
            if violato:
                anomalie.append(Anomalia(
                    tipo="fattore_di_rischio",
                    descrizione=f"{k.nome} ({k.dimensione or 'totale'}) a {k.valore} "
                                f"{limite.unita} contro un limite di {limite.valore}",
                    kpi_coinvolti=[k],
                    valori={"rilevato": k.valore, "limite": limite.valore,
                            "verso": limite.verso},
                ))
        return anomalie

    def leggi_serie(self, path="07_appendice_statistica_serie_mensili.pdf"):
      """
      Questa funzione è creata ad hoc per leggere il file delle serie storiche, in modo da
      fornire uno storico per l'addestramento di un modello a prevedere scenari simulati,
      tramite algoritmi di ML (LinearRegression Semplice)
      """
      testo = self.leggi(path)

      f = lambda s: float(s.replace(".", "").replace(",", "."))
      righe = []
      for riga in testo.split("\n"):
          campi = riga.split()
          if len(campi) == 7 and re.fullmatch(r"\d{4}-\d{2}", campi[0]):
              righe.append(campi)

      return {
          "mese":     [r[0] for r in righe],
          "euribor":  [f(r[1]) for r in righe],
          "margine":  [f(r[2]) for r in righe],
          "titoli":   [f(r[3]) for r in righe],
          "impieghi": [f(r[4]) for r in righe],
          "lcr":      [f(r[5]) for r in righe],
          "default":  [f(r[6]) for r in righe],
      }
