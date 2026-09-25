from pydantic import BaseModel, Field
from typing import Literal

NOMI_KPI = Literal[
    "var_1g", "lcr", "nsfr", "cet1_ratio", "rwa", "npl_ratio",
    "esposizione_lorda", "ecl", "duration_titoli", "esposizione_valutaria",
    "margine_interesse", "patrimonio_vigilanza",
    "concentrazione_settoriale", "esposizione_singola_controparte",
    "esposizione_primi_10",
]

UNITA = Literal["MIO_EUR", "PERCENTUALE", "ANNI", "CONTEGGIO"]


class Periodo(BaseModel):
    anno: int = Field(
        description="Anno a cui si riferisce il dato, non l'anno di pubblicazione del documento."
    )
    trimestre: int | None = Field(
        default=None,
        description="Trimestre da 1 a 4. Lascia null se il dato si riferisce all'intero "
                    "anno o se è un dato mensile."
    )
    mese: int | None = Field(
        default=None,
        description="Mese da 1 a 12, solo per dati con cadenza mensile come il VaR. "
                    "Lascia null per dati trimestrali o annuali."
    )


class KPI(BaseModel):
    nome: NOMI_KPI = Field(
        description="Nome canonico dell'indicatore. NON includere il periodo o il segmento "
                    "nel nome: hanno campi dedicati."
    )
    dimensione: str | None = Field(
        default=None,
        description="Segmento a cui il valore si riferisce: settore economico "
                    "('real estate e costruzioni'), stage IFRS 9 ('stage 3'), nome della "
                    "controparte ('Gruppo Aurora Immobiliare'). Lascia null quando il valore "
                    "è il totale consolidato."
    )
    periodo: Periodo = Field(
        description="Periodo di riferimento del dato. Un report può citare più periodi: "
                    "associa ogni valore al proprio, non alla data del documento."
    )
    valore: float = Field(
        description="Solo il numero, senza simboli. Per '13,2 milioni di euro' scrivi 13.2 "
                    "con unita MIO_EUR; per '15,7%' scrivi 15.7 con unita PERCENTUALE."
    )
    unita: UNITA = Field(
        description="Unità di misura del valore."
    )
    natura: Literal["rilevato", "medio", "obiettivo", "scenario"] = Field(
        default="rilevato",
        description="'rilevato' per il dato puntuale di fine periodo; 'medio' per medie di "
                    "periodo; 'obiettivo' per target o soglie attese; 'scenario' per esiti "
                    "di stress test o simulazioni. Una riga che riporta sia il valore puntuale "
                    "sia quello medio produce due KPI distinti."
    )
    fonte: str = Field(
        default="",
        description="Non compilare: viene popolato automaticamente dopo l'estrazione."
    )

class Limite(BaseModel):
    nome: NOMI_KPI = Field(
        description="Nome canonico dell'indicatore a cui il limite si applica. Usa lo stesso "
                    "vocabolario dei KPI."
    )
    valore: float = Field(
        description="Soglia numerica del limite, senza simboli."
    )
    verso: Literal["max", "min"] = Field(
        description="'max' se l'indicatore non deve superare la soglia (VaR, concentrazione); "
                    "'min' se non deve scendere sotto (LCR, CET1 ratio)."
    )
    unita: UNITA = Field(
        description="Unità di misura della soglia."
    )
    base: str | None = Field(
        default=None,
        description="Grandezza su cui si calcola la percentuale, quando il limite è espresso "
                    "in percentuale: 'portafoglio' o 'patrimonio'. Lascia null per i limiti "
                    "in valore assoluto."
    )
    limite_regolamentare: float | None = Field(
        default=None,
        description="Soglia di legge, quando il documento ne indica una distinta dalla soglia "
                    "interna. Esempio: LCR con soglia interna 110% e limite regolamentare 100%."
    )

class ListaKPI(BaseModel):
    kpi: list[KPI] = Field(description="Tutti gli indicatori quantitativi presenti nel documento.")

class ListaLimiti(BaseModel):
    limiti: list[Limite] = Field(description="Tutti i limiti di rischio definiti nel documento.")

class Anomalia(BaseModel):
    tipo: Literal["fattore_di_rischio", "inesattezza", "omissione", "interpretazione_erronea"]
    descrizione: str
    kpi_coinvolti: list[KPI] = []
    valori: dict = {}
