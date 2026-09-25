"""
Generazione del corpus documentale sintetico — FinSecure Analytics
==================================================================

Crea 15 report finanziari fittizi in PDF che compongono il dossier di rischio di
un cliente istituzionale, Banca Meridiana S.p.A., monitorato da FinSecure
Analytics.

Lo script è l'unica fonte di verità del corpus. Oltre ai documenti produce
quattro file JSON che il notebook carica direttamente:

    data/
    ├── 01_policy_limiti_rischio.pdf ... 15_nota_cro_priorita_2026.pdf
    ├── metadata.json                →  metadati per l'indicizzazione
    ├── criticita_attese.json        →  ground truth per la validazione
    └── limiti.json                  →  limiti di rischio (riferimento)

Il corpus contiene DIECI criticità deliberate, distribuite sulle quattro
categorie che il progetto richiede di individuare:

    - omissioni               (informazione dovuta da una policy e assente)
    - inesattezze             (valori che non riconciliano)
    - interpretazioni erronee (dati corretti, conclusione fuorviante)
    - fattori di rischio      (limiti superati)

Dipendenze:  fpdf2>=2.7
Uso:         uv run python -m risk_management_ai_agent.corpus
"""

import json
import os
import random
import unicodedata

from fpdf import FPDF

DATA_DIR = os.environ.get("DATA_DIR", "data")

AZIENDA = "FinSecure Analytics S.r.l."
CLIENTE = "Banca Meridiana S.p.A."

# Tassonomie canoniche: sono gli stessi valori usati nei Literal degli schemi
# Pydantic, nei filtri del retrieval e nei parametri dei tool dell'agente.
AREE = ("credit", "market", "liquidity", "capital", "governance")
DOC_TYPES = ("policy", "risk_report", "meeting_minutes", "internal_note", "register")

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
FONT_FILES = {
    "": os.path.join(FONT_DIR, "DejaVuSans.ttf"),
    "B": os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf"),
    "I": os.path.join(FONT_DIR, "DejaVuSans-Oblique.ttf"),
}
UNICODE_OK = all(os.path.exists(p) for p in FONT_FILES.values())
FAMIGLIA = "DejaVu" if UNICODE_OK else "Helvetica"

LARGHEZZA_UTILE = 180


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _sanifica(text: str) -> str:
    """Rende il testo rappresentabile in latin-1, solo se mancano i font DejaVu."""
    if UNICODE_OK:
        return text
    sostituzioni = {
        "\u20ac": "EUR", "\u2019": "'", "\u2018": "'", "\u201c": '"',
        "\u201d": '"', "\u2013": "-", "\u2014": "-", "\u2026": "...",
        "\u00a0": " ", "\u2022": "-",
    }
    for src, dst in sostituzioni.items():
        text = text.replace(src, dst)
    return unicodedata.normalize("NFC", text).encode("latin-1", "ignore").decode("latin-1")


def _data_int(data_iso: str) -> int:
    """'2026-01-15' -> 20260115. Formato numerico per i filtri sui metadati."""
    return int(data_iso.replace("-", ""))


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

def scrivi_pdf(path: str, titolo: str, sottotitolo: str, blocchi: list) -> None:
    pdf = FPDF()
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=18)

    if UNICODE_OK:
        for stile, file_font in FONT_FILES.items():
            pdf.add_font(FAMIGLIA, stile, file_font)

    pdf.add_page()

    pdf.set_font(FAMIGLIA, "B", 9)
    pdf.cell(0, 5, _sanifica(f"{AZIENDA}  —  Dossier di rischio {CLIENTE}"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font(FAMIGLIA, "B", 15)
    pdf.multi_cell(0, 7, _sanifica(titolo), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(FAMIGLIA, "I", 10)
    pdf.multi_cell(0, 5, _sanifica(sottotitolo), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    for tipo, contenuto in blocchi:
        if tipo == "h":
            pdf.ln(2)
            pdf.set_font(FAMIGLIA, "B", 11)
            pdf.multi_cell(0, 6, _sanifica(contenuto), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)

        elif tipo == "p":
            pdf.set_font(FAMIGLIA, "", 10)
            pdf.multi_cell(0, 5, _sanifica(contenuto), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)

        elif tipo == "li":
            pdf.set_font(FAMIGLIA, "", 10)
            for voce in contenuto:
                pdf.multi_cell(0, 5, _sanifica(f"  -  {voce}"), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)

        elif tipo == "table":
            # Larghezze esplicite per colonna: con celle uniformi le etichette
            # lunghe sbordano e l'estrazione a valle restituisce numeri
            # scollegati dalla propria riga.
            intestazione, righe, larghezze = contenuto
            assert sum(larghezze) <= LARGHEZZA_UTILE, f"tabella troppo larga: {titolo}"

            pdf.set_font(FAMIGLIA, "B", 9)
            for cella, larghezza in zip(intestazione, larghezze):
                pdf.cell(larghezza, 7, _sanifica(str(cella)), border=1)
            pdf.ln()

            pdf.set_font(FAMIGLIA, "", 9)
            for riga in righe:
                for cella, larghezza in zip(riga, larghezze):
                    pdf.cell(larghezza, 6, _sanifica(str(cella)), border=1)
                pdf.ln()
            pdf.ln(3)

    pdf.output(path)



# ---------------------------------------------------------------------------
# Serie storiche mensili — base per la stima delle sensitività
# ---------------------------------------------------------------------------
# 36 osservazioni (gennaio 2023 - dicembre 2025). I valori sono generati in modo
# deterministico da una relazione lineare più un disturbo con seed fisso, così
# che il corpus sia riproducibile e le regressioni stimabili sui dati abbiano
# coefficienti noti:
#
#     margine di interesse   ≈ +0,71 Mio per ogni punto percentuale di Euribor
#                               (≈ +8,5 Mio su base annua per +100 bp)
#     portafoglio titoli     ≈ -22 Mio per ogni punto percentuale di Euribor
#     LCR                    ≈ -0,10 pp per ogni Mio di crescita degli impieghi

def _interp(t: float, punti: list) -> float:
    """Interpolazione lineare fra punti di ancoraggio (t, valore)."""
    for (t0, v0), (t1, v1) in zip(punti, punti[1:]):
        if t0 <= t <= t1:
            return v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return punti[-1][1]


def serie_mensili() -> list:
    """Restituisce le righe della serie storica: 36 mesi, sei grandezze."""
    rnd = random.Random(42)

    ancore_euribor = [(0, 2.35), (12, 3.60), (18, 4.10), (24, 3.70),
                      (28, 3.50), (35, 3.90)]
    ancore_impieghi = [(0, 1380), (11, 1440), (23, 1520), (26, 1540),
                       (29, 1580), (32, 1630), (35, 1700)]
    ancore_lcr = [(0, 144), (26, 128), (29, 124), (32, 118), (35, 112)]

    righe = []
    for t in range(36):
        anno, mese = 2023 + t // 12, t % 12 + 1

        euribor = _interp(t, ancore_euribor) + rnd.uniform(-0.04, 0.04)
        margine = 5.34 + 0.71 * euribor + rnd.uniform(-0.06, 0.06)
        titoli = 1134 - 22 * (euribor - 2.35) + rnd.uniform(-3, 3)
        impieghi = _interp(t, ancore_impieghi) + rnd.uniform(-4, 4)
        lcr = _interp(t, ancore_lcr) + rnd.uniform(-0.4, 0.4)
        default_rate = 1.60 + 0.25 * t / 35 + rnd.uniform(-0.02, 0.02)

        righe.append([
            f"{anno}-{mese:02d}",
            f"{euribor:.2f}".replace(".", ","),
            f"{margine:.2f}".replace(".", ","),
            f"{titoli:.0f}",
            f"{impieghi:.0f}",
            f"{lcr:.1f}".replace(".", ","),
            f"{default_rate:.2f}".replace(".", ","),
        ])
    return righe


# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------

DOCUMENTI = [

    # ------------------------ AREA: GOVERNANCE ----------------------------
    dict(
        file="01_policy_limiti_rischio.pdf",
        area="governance", doc_type="policy", tipo="risk appetite framework",
        data="2025-06-30",
        titolo="Risk Appetite Framework — Sistema dei Limiti di Rischio",
        sottotitolo="Versione 4.0 — Approvata dal Consiglio di Amministrazione il 30 giugno 2025",
        blocchi=[
            ("p", "Il presente documento definisce il sistema dei limiti di rischio applicabile "
                  "al portafoglio creditizio e finanziario. I limiti sono vincolanti e il loro "
                  "superamento comporta segnalazione immediata al Comitato Rischi e attivazione "
                  "del piano di rientro entro 30 giorni."),
            ("h", "1. Limiti di rischio di credito"),
            ("table", (
                ["Indicatore", "Limite", "Frequenza"],
                [
                    ["Concentrazione settoriale", "25% del portafoglio", "Trimestrale"],
                    ["Esposizione singola controparte", "10% del patrimonio", "Mensile"],
                    ["Esposizione primi 10 clienti", "35% del portafoglio", "Trimestrale"],
                    ["NPL ratio", "6,0%", "Trimestrale"],
                ],
                [80, 55, 45],
            )),
            ("p", "La verifica del limite di esposizione per singola controparte è effettuata su "
                  "base di gruppo, aggregando le posizioni verso soggetti connessi da rapporti di "
                  "controllo o collegamento. La rilevazione su base individuale non è sufficiente "
                  "ai fini del rispetto del limite."),
            ("h", "2. Limiti di rischio di mercato"),
            ("table", (
                ["Indicatore", "Limite", "Frequenza"],
                [
                    ["VaR 1 giorno, 99%", "12,0 Mio EUR", "Giornaliera"],
                    ["Duration portafoglio titoli", "5,0 anni", "Mensile"],
                    ["Esposizione valutaria netta", "50,0 Mio EUR", "Giornaliera"],
                ],
                [80, 55, 45],
            )),
            ("p", "Il rispetto del limite di VaR è verificato sul dato puntuale di fine periodo. "
                  "L'utilizzo di medie di periodo ai fini della verifica del limite non è ammesso. "
                  "Ogni report periodico di rischio di mercato deve riportare l'esito del "
                  "backtesting, con indicazione del numero di eccezioni rilevate negli ultimi "
                  "250 giorni operativi e della zona di riferimento."),
            ("h", "3. Limiti di liquidità e patrimoniali"),
            ("table", (
                ["Indicatore", "Limite regolamentare", "Soglia interna"],
                [
                    ["LCR", "100%", "110%"],
                    ["NSFR", "100%", "105%"],
                    ["CET1 ratio", "12,5% (SREP)", "14,0%"],
                ],
                [70, 60, 50],
            )),
            ("h", "4. Obblighi di reporting"),
            ("li", [
                "Il superamento di un limite è comunicato al Comitato Rischi entro 5 giorni lavorativi",
                "I dati di sintesi riportati nei verbali devono riconciliare con i report analitici",
                "Le variazioni di perimetro sono documentate e motivate nel report di riferimento",
            ]),
        ],
    ),

    dict(
        file="11_verbale_comitato_rischi_20260210.pdf",
        area="governance", doc_type="meeting_minutes", tipo="verbale",
        data="2026-02-10",
        titolo="Verbale del Comitato Rischi",
        sottotitolo="Seduta del 10 febbraio 2026 — Esame della situazione di rischio al 31/12/2025",
        blocchi=[
            ("h", "Partecipanti"),
            ("p", "Chief Risk Officer, Chief Financial Officer, Responsabile Credit Risk, "
                  "Responsabile Market Risk, Responsabile Tesoreria, Internal Audit."),
            ("h", "1. Rischio di credito"),
            ("p", "Il Responsabile Credit Risk illustra la composizione del portafoglio al "
                  "31 dicembre 2025, pari a 1.700 milioni di euro. L'esposizione verso il comparto "
                  "real estate e costruzioni si attesta a 415 milioni di euro, corrispondenti al "
                  "24,4% del portafoglio, e risulta pertanto entro il limite del 25% previsto dal "
                  "Risk Appetite Framework."),
            ("p", "L'NPL ratio si conferma al 5,0%, in linea con il trimestre precedente e al di "
                  "sotto del limite interno del 6,0%. Il Comitato prende atto e non richiede "
                  "azioni correttive sul comparto."),
            ("h", "2. Liquidità"),
            ("p", "Il Responsabile Tesoreria riferisce che l'indicatore LCR si mantiene stabile su "
                  "livelli ampiamente superiori alla soglia interna, attestandosi al 112% a fine "
                  "dicembre. Il Comitato non ravvisa criticità sul profilo di liquidità."),
            ("h", "3. Rischio di mercato"),
            ("p", "Il Responsabile Market Risk segnala l'incremento del VaR nel corso del quarto "
                  "trimestre, riconducibile all'aumento della volatilità sui tassi. Il valore "
                  "medio del trimestre novembre-gennaio si attesta a 11,8 milioni di euro, entro "
                  "il limite di 12,0 milioni."),
            ("h", "4. Adeguatezza patrimoniale"),
            ("p", "Il CET1 ratio al 31 dicembre 2025 è pari al 15,7%, con un margine di 3,2 punti "
                  "percentuali rispetto al requisito SREP del 12,5%. Il Comitato valuta "
                  "positivamente la dotazione patrimoniale."),
            ("h", "5. Decisioni"),
            ("li", [
                "Presa d'atto della situazione di rischio al 31 dicembre 2025",
                "Richiesta di approfondimento sulla concentrazione dei primi dieci clienti entro marzo 2026",
                "Aggiornamento del Risk Appetite Framework calendarizzato per giugno 2026",
            ]),
        ],
    ),

    dict(
        file="12_registro_incidenti_operativi_2025.pdf",
        area="governance", doc_type="register", tipo="registro incidenti",
        data="2026-01-15",
        titolo="Registro degli Incidenti Operativi — Esercizio 2025",
        sottotitolo="A cura della funzione Operational Risk — Aggiornato al 15 gennaio 2026",
        blocchi=[
            ("p", "Il registro raccoglie gli eventi di rischio operativo rilevati nel corso "
                  "dell'esercizio 2025, con indicazione della perdita lorda contabilizzata e "
                  "dello stato delle azioni di rimedio."),
            ("table", (
                ["ID", "Data", "Categoria", "Perdita (k EUR)", "Stato"],
                [
                    ["OP-2025-03", "18/03/2025", "Esecuzione e processi", "420", "Chiuso"],
                    ["OP-2025-07", "22/05/2025", "Frode esterna", "1.150", "Chiuso"],
                    ["OP-2025-11", "09/08/2025", "Interruzione operatività", "680", "Chiuso"],
                    ["OP-2025-16", "14/11/2025", "Esecuzione e processi", "890", "In corso"],
                    ["OP-2025-19", "03/12/2025", "Frode esterna", "660", "In corso"],
                ],
                [32, 28, 55, 35, 30],
            )),
            ("h", "Sintesi"),
            ("p", "La perdita operativa lorda complessiva dell'esercizio 2025 ammonta a 3,8 "
                  "milioni di euro, in aumento rispetto ai 2,9 milioni del 2024. L'incremento è "
                  "concentrato nella categoria frode esterna, che passa da 0,7 a 1,8 milioni."),
            ("h", "Azioni proposte"),
            ("li", [
                "Rafforzamento dei controlli antifrode sui canali digitali entro Q2 2026",
                "Revisione del processo di autorizzazione dei bonifici di importo rilevante",
                "Estensione del monitoraggio automatico alle operazioni fuori orario",
            ]),
        ],
    ),

    dict(
        file="13_nota_audit_rilievi.pdf",
        area="governance", doc_type="internal_note", tipo="nota di audit",
        data="2026-02-24",
        titolo="Nota di Internal Audit — Rilievi Preliminari sul Sistema dei Limiti",
        sottotitolo="Verifica a campione sui report del quarto trimestre 2025 — 24 febbraio 2026",
        blocchi=[
            ("p", "La presente nota riporta i rilievi preliminari emersi dalla verifica sul "
                  "funzionamento del sistema dei limiti di rischio. Il riscontro delle funzioni "
                  "interessate è atteso entro il 15 marzo 2026 ai fini della formalizzazione."),
            ("h", "Rilievo 1 — Riconciliazione dei dati di sintesi"),
            ("p", "Il dato di esposizione settoriale riportato nel verbale del Comitato Rischi del "
                  "10 febbraio non coincide con quello del report analitico sulle esposizioni "
                  "creditizie di pari data contabile. Lo scostamento è rilevante ai fini della "
                  "verifica del limite del 25%: le due grandezze conducono a conclusioni opposte "
                  "sul rispetto del limite. Si richiede chiarimento sulla fonte utilizzata per la "
                  "predisposizione del verbale."),
            ("h", "Rilievo 2 — Perimetro di verifica della concentrazione"),
            ("p", "Il report sulla concentrazione delle controparti espone le posizioni su base "
                  "individuale. Il Risk Appetite Framework richiede la verifica su base di gruppo, "
                  "con aggregazione dei soggetti connessi. Non risulta agli atti la documentazione "
                  "della mappatura dei gruppi di clienti connessi utilizzata per il periodo."),
            ("h", "Rilievo 3 — Completezza dei report di rischio di mercato"),
            ("p", "Il report di rischio di mercato relativo al mese di gennaio 2026 non riporta "
                  "l'esito del backtesting, richiesto dal Risk Appetite Framework per ogni report "
                  "periodico. Il dato è invece presente nel report di dicembre 2025."),
        ],
    ),

    dict(
        file="15_nota_cro_priorita_2026.pdf",
        area="governance", doc_type="internal_note", tipo="nota di indirizzo",
        data="2026-03-02",
        titolo="Nota di Indirizzo del Chief Risk Officer — Priorità di Monitoraggio 2026",
        sottotitolo="Trasmessa al Comitato Rischi il 2 marzo 2026",
        blocchi=[
            ("p", "A valle dell'esame della situazione di rischio 2025 e dei rilievi formulati "
                  "dall'Internal Audit, si riepilogano le priorità di monitoraggio per "
                  "l'esercizio in corso. Il punto è proposto per l'ordine del giorno della "
                  "prossima seduta."),
            ("h", "Priorità 1 — Concentrazione del portafoglio creditizio"),
            ("p", "La dinamica del comparto real estate richiede un monitoraggio ravvicinato. Si "
                  "richiede alla funzione Credit Risk di predisporre una rilevazione mensile, in "
                  "luogo di quella trimestrale attualmente prevista, e di includere la verifica su "
                  "base di gruppo."),
            ("h", "Priorità 2 — Traiettoria dell'indicatore di liquidità"),
            ("p", "Pur restando l'LCR sopra la soglia interna, la traiettoria degli ultimi quattro "
                  "trimestri merita attenzione in sede di pianificazione del funding. Si richiede "
                  "alla Tesoreria una proiezione a dodici mesi con almeno tre scenari di deflusso."),
            ("h", "Priorità 3 — Qualità del dato nei documenti di sintesi"),
            ("p", "I rilievi dell'Audit evidenziano che il problema non è il calcolo degli "
                  "indicatori, ma la coerenza tra i documenti che li riportano. Un dato corretto "
                  "nel report analitico e disallineato nel verbale produce una decisione sbagliata "
                  "anche in presenza di un sistema di misurazione accurato."),
        ],
    ),

    # -------------------------- AREA: CREDIT ------------------------------
    dict(
        file="02_report_esposizioni_creditizie_q4_2025.pdf",
        area="credit", doc_type="risk_report", tipo="report esposizioni",
        data="2026-01-22",
        titolo="Report Esposizioni Creditizie — Q4 2025",
        sottotitolo="Dati al 31 dicembre 2025 — Importi in milioni di euro",
        blocchi=[
            ("h", "1. Composizione per settore economico"),
            ("p", "L'esposizione creditizia lorda complessiva al 31 dicembre 2025 ammonta a "
                  "1.700 milioni di euro, in aumento del 4,3% rispetto al trimestre precedente. "
                  "La composizione per settore economico è riportata di seguito."),
            ("table", (
                ["Settore", "Esposizione", "Quota", "Var. Q3"],
                [
                    ["Real estate e costruzioni", "460", "27,1%", "+8,2%"],
                    ["Retail e famiglie", "520", "30,6%", "+2,1%"],
                    ["Manifatturiero", "300", "17,6%", "+1,4%"],
                    ["Energia e utilities", "180", "10,6%", "+3,0%"],
                    ["Servizi finanziari", "140", "8,2%", "-1,2%"],
                    ["Altri settori", "100", "5,9%", "+0,5%"],
                    ["TOTALE", "1.700", "100,0%", "+4,3%"],
                ],
                [70, 38, 36, 36],
            )),
            ("p", "L'esposizione verso il comparto real estate e costruzioni ammonta a 460 milioni "
                  "di euro, pari al 27,1% del portafoglio complessivo. Si tratta del settore con "
                  "la dinamica di crescita più marcata nel trimestre."),
            ("h", "2. Composizione per classe di rating"),
            ("table", (
                ["Classe", "Esposizione", "Quota"],
                [
                    ["Investment grade (AAA-BBB)", "1.105", "65,0%"],
                    ["Sub-investment grade (BB-B)", "510", "30,0%"],
                    ["Deteriorate (CCC e inferiori)", "85", "5,0%"],
                    ["TOTALE", "1.700", "100,0%"],
                ],
                [90, 45, 45],
            )),
            ("h", "3. Qualità del credito"),
            ("p", "L'NPL ratio si attesta al 5,0%, invariato rispetto al trimestre precedente e "
                  "al di sotto del limite interno del 6,0%. Il tasso di copertura delle posizioni "
                  "deteriorate è pari al 45,0%."),
            ("h", "4. Serie storica dell'esposizione lorda"),
            ("table", (
                ["Trimestre", "Esposizione", "NPL ratio"],
                [
                    ["Q1 2025", "1.540", "5,4%"],
                    ["Q2 2025", "1.580", "5,2%"],
                    ["Q3 2025", "1.630", "5,0%"],
                    ["Q4 2025", "1.700", "5,0%"],
                ],
                [60, 60, 60],
            )),
        ],
    ),

    dict(
        file="03_report_concentrazione_controparti_q4_2025.pdf",
        area="credit", doc_type="risk_report", tipo="report concentrazione",
        data="2026-01-22",
        titolo="Report Concentrazione Controparti — Q4 2025",
        sottotitolo="Prime dieci esposizioni al 31 dicembre 2025 — Importi in milioni di euro",
        blocchi=[
            ("p", "Il presente report espone le prime dieci esposizioni creditizie rilevate su "
                  "base individuale al 31 dicembre 2025. Il patrimonio di vigilanza di riferimento "
                  "ammonta a 850 milioni di euro."),
            ("table", (
                ["#", "Controparte", "Esposizione", "% patrimonio"],
                [
                    ["1", "Gruppo Aurora Immobiliare", "92", "10,8%"],
                    ["2", "Nord Energia S.p.A.", "78", "9,2%"],
                    ["3", "Gruppo Vesta Manifatturiera", "71", "8,4%"],
                    ["4", "Delta Logistica S.p.A.", "64", "7,5%"],
                    ["5", "Compagnia Assicurativa Iride", "58", "6,8%"],
                    ["6", "Metalmeccanica Ponente", "52", "6,1%"],
                    ["7", "Sviluppi Urbani Levante S.r.l.", "49", "5,8%"],
                    ["8", "Farmaceutici Rialto", "44", "5,2%"],
                    ["9", "Trasporti Adriatico", "41", "4,8%"],
                    ["10", "Agroindustria Sud", "38", "4,5%"],
                ],
                [12, 88, 40, 40],
            )),
            ("h", "Sintesi"),
            ("p", "Le prime dieci esposizioni ammontano complessivamente a 587 milioni di euro, "
                  "pari al 34,5% del portafoglio creditizio. Il valore risulta entro il limite del "
                  "35% previsto dal Risk Appetite Framework, con un margine residuo contenuto."),
            ("h", "Note metodologiche"),
            ("p", "Le esposizioni sono rilevate su base individuale per singolo soggetto "
                  "giuridico. Gli importi sono espressi al lordo delle rettifiche di valore e "
                  "comprendono i margini disponibili su linee di credito irrevocabili."),
        ],
    ),

    dict(
        file="04_nota_ecl_stage_q4_2025.pdf",
        area="credit", doc_type="internal_note", tipo="nota tecnica",
        data="2026-01-28",
        titolo="Nota Tecnica — Perdite Attese e Classificazione per Stage",
        sottotitolo="Dati al 31 dicembre 2025 — Metodologia IFRS 9",
        blocchi=[
            ("h", "1. Classificazione per stage"),
            ("table", (
                ["Stage", "Esposizione", "ECL", "Coverage"],
                [
                    ["Stage 1", "1.360", "6,8", "0,50%"],
                    ["Stage 2", "255", "12,8", "5,02%"],
                    ["Stage 3", "85", "38,3", "45,06%"],
                    ["TOTALE", "1.700", "57,9", "3,41%"],
                ],
                [50, 45, 40, 45],
            )),
            ("h", "2. Parametri di rischio"),
            ("li", [
                "PD media a 12 mesi del portafoglio performing: 1,85%",
                "LGD media ponderata: 38,0%",
                "Esposizione media per posizione stage 3: 1,9 milioni di euro",
            ]),
            ("h", "3. Sensitività delle perdite attese"),
            ("p", "Un incremento di un punto percentuale del tasso di default atteso sul "
                  "portafoglio performing determina un aumento delle perdite attese stimato in "
                  "17,0 milioni di euro e un incremento degli attivi ponderati per il rischio "
                  "pari a 180 milioni di euro."),
            ("h", "4. Considerazioni"),
            ("p", "La quota di esposizioni classificate in stage 2 è aumentata di 0,8 punti "
                  "percentuali nel trimestre, prevalentemente per posizioni riconducibili al "
                  "comparto real estate. L'evoluzione è coerente con il deterioramento degli "
                  "indicatori anticipatori sul settore immobiliare commerciale."),
        ],
    ),

    # -------------------------- AREA: MARKET ------------------------------
    dict(
        file="05_report_var_dicembre_2025.pdf",
        area="market", doc_type="risk_report", tipo="report VaR",
        data="2026-01-08",
        titolo="Report Rischio di Mercato — Dicembre 2025",
        sottotitolo="Value at Risk giornaliero, intervallo di confidenza 99% — Milioni di euro",
        blocchi=[
            ("h", "1. Value at Risk"),
            ("p", "Il VaR giornaliero al 31 dicembre 2025 si attesta a 11,9 milioni di euro, in "
                  "aumento rispetto ai 10,4 milioni di fine novembre. L'incremento è riconducibile "
                  "all'aumento della volatilità implicita sui tassi di interesse e all'estensione "
                  "della duration del portafoglio titoli."),
            ("table", (
                ["Mese", "VaR puntuale", "VaR medio", "Limite"],
                [
                    ["Luglio 2025", "8,9", "8,7", "12,0"],
                    ["Agosto 2025", "9,2", "9,0", "12,0"],
                    ["Settembre 2025", "9,6", "9,3", "12,0"],
                    ["Ottobre 2025", "9,8", "9,7", "12,0"],
                    ["Novembre 2025", "10,4", "10,1", "12,0"],
                    ["Dicembre 2025", "11,9", "11,0", "12,0"],
                ],
                [55, 42, 42, 41],
            )),
            ("h", "2. Scomposizione per fattore di rischio"),
            ("table", (
                ["Fattore", "VaR", "Contributo"],
                [
                    ["Tasso di interesse", "9,4", "79,0%"],
                    ["Spread creditizio", "1,8", "15,1%"],
                    ["Cambio", "0,5", "4,2%"],
                    ["Azionario", "0,2", "1,7%"],
                ],
                [80, 50, 50],
            )),
            ("h", "3. Backtesting"),
            ("p", "Il backtesting condotto sugli ultimi 250 giorni operativi ha evidenziato 2 "
                  "eccezioni, entrambe registrate nel mese di ottobre in corrispondenza della "
                  "riunione della banca centrale. Il modello si colloca in zona verde secondo la "
                  "classificazione prudenziale, che prevede la zona verde fino a 4 eccezioni."),
            ("h", "4. Portafoglio titoli"),
            ("li", [
                "Valore di mercato: 1.100 milioni di euro",
                "Duration modificata: 4,2 anni (limite 5,0)",
                "Esposizione valutaria netta: 31 milioni di euro (limite 50,0)",
            ]),
        ],
    ),

    dict(
        file="06_report_var_gennaio_2026.pdf",
        area="market", doc_type="risk_report", tipo="report VaR",
        data="2026-02-06",
        titolo="Report Rischio di Mercato — Gennaio 2026",
        sottotitolo="Value at Risk giornaliero, intervallo di confidenza 99% — Milioni di euro",
        blocchi=[
            ("h", "1. Value at Risk"),
            ("p", "Il VaR giornaliero al 31 gennaio 2026 si attesta a 13,2 milioni di euro. "
                  "L'incremento rispetto al mese precedente riflette il proseguimento della fase "
                  "di volatilità sui mercati obbligazionari."),
            ("table", (
                ["Mese", "VaR puntuale", "VaR medio", "Limite"],
                [
                    ["Novembre 2025", "10,4", "10,1", "12,0"],
                    ["Dicembre 2025", "11,9", "11,0", "12,0"],
                    ["Gennaio 2026", "13,2", "12,4", "12,0"],
                ],
                [55, 42, 42, 41],
            )),
            ("p", "Il valore medio del trimestre novembre 2025 - gennaio 2026 si attesta a 11,8 "
                  "milioni di euro e risulta pertanto entro il limite di 12,0 milioni previsto dal "
                  "Risk Appetite Framework. Il profilo di rischio di mercato è da considerarsi "
                  "sotto controllo."),
            ("h", "2. Scomposizione per fattore di rischio"),
            ("table", (
                ["Fattore", "VaR", "Contributo"],
                [
                    ["Tasso di interesse", "10,7", "81,1%"],
                    ["Spread creditizio", "1,9", "14,4%"],
                    ["Cambio", "0,4", "3,0%"],
                    ["Azionario", "0,2", "1,5%"],
                ],
                [80, 50, 50],
            )),
            ("h", "3. Portafoglio titoli"),
            ("li", [
                "Valore di mercato: 1.140 milioni di euro",
                "Duration modificata: 4,6 anni (limite 5,0)",
                "Esposizione valutaria netta: 28 milioni di euro (limite 50,0)",
            ]),
            ("h", "4. Evoluzione attesa"),
            ("p", "Le attese di mercato incorporano una stabilizzazione dei tassi nel corso del "
                  "primo semestre. Non sono previste modifiche significative alla composizione del "
                  "portafoglio nel breve periodo."),
        ],
    ),

    dict(
        file="07_appendice_statistica_serie_mensili.pdf",
        area="market", doc_type="risk_report", tipo="appendice statistica",
        data="2026-02-12",
        titolo="Appendice Statistica — Serie Storiche Mensili 2023-2025",
        sottotitolo="36 osservazioni mensili — Importi in milioni di euro salvo diversa indicazione",
        blocchi=[
            ("p", "La presente appendice raccoglie le serie storiche mensili delle principali "
                  "grandezze di bilancio e di mercato per il triennio 2023-2025. I dati sono "
                  "destinati alle analisi di sensitività e alle proiezioni di scenario: le "
                  "relazioni fra le variabili sono stimabili direttamente dalla serie, senza "
                  "ricorso a coefficienti predefiniti."),
            ("h", "1. Serie storiche mensili"),
            ("table", (
                ["Mese", "Euribor 3M", "Margine int.", "Titoli", "Impieghi", "LCR", "Default rate"],
                serie_mensili(),
                [22, 26, 27, 24, 26, 22, 30],
            )),
            ("h", "2. Note metodologiche"),
            ("li", [
                "Euribor 3M: media mensile delle rilevazioni giornaliere, valori percentuali",
                "Margine di interesse: competenza del mese, al lordo delle rettifiche",
                "Titoli: valore di mercato del portafoglio a fine mese",
                "Impieghi: esposizione creditizia lorda a fine mese",
                "LCR: rilevazione di fine mese, valori percentuali",
                "Default rate: tasso di default a dodici mesi del portafoglio performing",
            ]),
            ("h", "3. Grandezze di riferimento al 31 dicembre 2025"),
            ("table", (
                ["Grandezza", "Valore"],
                [
                    ["Margine di interesse (esercizio 2025)", "96,0 Mio EUR"],
                    ["Portafoglio titoli", "1.100 Mio EUR"],
                    ["Impieghi lordi", "1.700 Mio EUR"],
                    ["Depositi clientela", "2.400 Mio EUR"],
                    ["Patrimonio di vigilanza (CET1)", "850 Mio EUR"],
                    ["Attivi ponderati per il rischio", "5.600 Mio EUR"],
                ],
                [110, 70],
            )),
            ("h", "4. Avvertenze d'uso"),
            ("p", "Le relazioni stimate sulla serie sono valide nell'intervallo di variazione "
                  "osservato nel periodo, compreso fra il 2,3% e il 4,1% per l'Euribor 3M. "
                  "L'estrapolazione al di fuori di tale intervallo non è supportata dai dati e "
                  "le stime non incorporano azioni gestionali di mitigazione."),
        ],
    ),

    # ------------------------- AREA: LIQUIDITY ----------------------------
    dict(
        file="08_report_liquidita_q4_2025.pdf",
        area="liquidity", doc_type="risk_report", tipo="report liquidità",
        data="2026-01-20",
        titolo="Report Rischio di Liquidità — Q4 2025",
        sottotitolo="Indicatori regolamentari al 31 dicembre 2025",
        blocchi=[
            ("h", "1. Liquidity Coverage Ratio"),
            ("p", "L'LCR al 31 dicembre 2025 si attesta al 112%, contro il 118% di fine settembre. "
                  "L'indicatore resta al di sopra sia del limite regolamentare del 100% sia della "
                  "soglia interna del 110%."),
            ("table", (
                ["Trimestre", "LCR", "NSFR", "Soglia interna LCR"],
                [
                    ["Q1 2025", "128%", "108%", "110%"],
                    ["Q2 2025", "124%", "107%", "110%"],
                    ["Q3 2025", "118%", "106%", "110%"],
                    ["Q4 2025", "112%", "105%", "110%"],
                ],
                [45, 40, 40, 55],
            )),
            ("h", "2. Componenti dell'LCR"),
            ("table", (
                ["Componente", "Valore (Mio EUR)"],
                [
                    ["Attività liquide di elevata qualità (HQLA)", "728"],
                    ["Deflussi di cassa attesi a 30 giorni", "910"],
                    ["Afflussi di cassa attesi a 30 giorni", "260"],
                    ["Deflussi netti", "650"],
                ],
                [115, 65],
            )),
            ("h", "3. Struttura della raccolta"),
            ("li", [
                "Depositi da clientela retail: 1.680 milioni di euro (70,0%)",
                "Depositi da clientela corporate: 480 milioni di euro (20,0%)",
                "Raccolta interbancaria e istituzionale: 240 milioni di euro (10,0%)",
            ]),
            ("h", "4. Considerazioni"),
            ("p", "La riduzione dell'LCR nel corso dell'esercizio riflette la crescita degli "
                  "impieghi a fronte di una raccolta sostanzialmente stabile. Il margine rispetto "
                  "alla soglia interna si è ridotto da 18 a 2 punti percentuali nell'arco dei "
                  "quattro trimestri."),
        ],
    ),

    dict(
        file="09_nota_tesoreria_funding_2026.pdf",
        area="liquidity", doc_type="internal_note", tipo="nota di tesoreria",
        data="2026-02-19",
        titolo="Nota di Tesoreria — Piano di Funding 2026",
        sottotitolo="Prima ipotesi — Predisposta sui dati di liquidità al 31 dicembre 2025",
        blocchi=[
            ("h", "1. Quadro di partenza"),
            ("p", "L'LCR di fine anno si attesta al 112%, con un margine di 2 punti percentuali "
                  "rispetto alla soglia interna del 110%. Nel corso del 2025 l'indicatore si è "
                  "ridotto di 16 punti percentuali, per effetto della crescita degli impieghi non "
                  "accompagnata da una crescita equivalente della raccolta."),
            ("h", "2. Fabbisogno stimato"),
            ("p", "Per riportare l'LCR in area 120% entro fine 2026, mantenendo il piano di "
                  "crescita degli impieghi, si stima un fabbisogno di raccolta aggiuntiva compreso "
                  "tra 180 e 220 milioni di euro."),
            ("h", "3. Opzioni considerate"),
            ("table", (
                ["Opzione", "Costo stimato", "Impatto margine", "Beneficio"],
                [
                    ["Raccolta retail promozionale", "2,90%", "-4,8 Mio", "LCR"],
                    ["Emissione senior preferred", "3,40%", "-6,5 Mio", "LCR e NSFR"],
                    ["Raccolta interbancaria breve", "2,10%", "-2,4 Mio", "nessuno"],
                ],
                [62, 38, 40, 40],
            )),
            ("p", "Il ricorso alla raccolta interbancaria a breve non produce beneficio sull'LCR, "
                  "data la ponderazione applicata alle scadenze inferiori a 30 giorni."),
            ("h", "4. Punto di attenzione"),
            ("p", "Un deflusso dei depositi da clientela del 10% comporterebbe una riduzione "
                  "dell'LCR di circa 14 punti percentuali, portando l'indicatore sotto la soglia "
                  "interna e a ridosso del limite regolamentare. Il margine attuale non consente "
                  "di assorbire uno shock di questa entità."),
        ],
    ),

    # -------------------------- AREA: CAPITAL -----------------------------
    dict(
        file="10_report_adeguatezza_patrimoniale_q4_2025.pdf",
        area="capital", doc_type="risk_report", tipo="report patrimoniale",
        data="2026-01-30",
        titolo="Report di Adeguatezza Patrimoniale — Q4 2025",
        sottotitolo="Dati al 31 dicembre 2025 — Importi in milioni di euro",
        blocchi=[
            ("h", "1. Fondi propri"),
            ("table", (
                ["Componente", "Valore"],
                [
                    ["Capitale primario di classe 1 (CET1)", "850"],
                    ["Capitale aggiuntivo di classe 1 (AT1)", "60"],
                    ["Capitale di classe 2 (T2)", "140"],
                    ["Totale fondi propri", "1.050"],
                ],
                [120, 60],
            )),
            ("h", "2. Attivi ponderati per il rischio"),
            ("table", (
                ["Tipologia di rischio", "RWA", "Quota"],
                [
                    ["Rischio di credito", "4.200", "75,0%"],
                    ["Rischio di mercato", "800", "14,3%"],
                    ["Rischio operativo", "600", "10,7%"],
                ],
                [90, 45, 45],
            )),
            ("p", "Gli attivi ponderati per il rischio complessivi ammontano a 5.400 milioni di "
                  "euro al 31 dicembre 2025."),
            ("h", "3. Coefficienti patrimoniali"),
            ("table", (
                ["Indicatore", "Valore", "Requisito SREP", "Margine"],
                [
                    ["CET1 ratio", "15,7%", "12,5%", "+3,2 pp"],
                    ["Tier 1 ratio", "16,9%", "14,0%", "+2,9 pp"],
                    ["Total capital ratio", "19,4%", "16,5%", "+2,9 pp"],
                ],
                [50, 40, 45, 45],
            )),
            ("h", "4. Evoluzione trimestrale del CET1 ratio"),
            ("table", (
                ["Trimestre", "CET1", "RWA", "CET1 ratio"],
                [
                    ["Q1 2025", "812", "5.050", "16,1%"],
                    ["Q2 2025", "824", "5.180", "15,9%"],
                    ["Q3 2025", "838", "5.340", "15,7%"],
                    ["Q4 2025", "850", "5.400", "15,7%"],
                ],
                [50, 42, 44, 44],
            )),
            ("h", "5. Considerazioni"),
            ("p", "La dotazione patrimoniale si mantiene su livelli adeguati, con un margine "
                  "rispetto al requisito SREP superiore a 3 punti percentuali. La crescita degli "
                  "attivi ponderati è coerente con l'espansione del portafoglio creditizio."),
        ],
    ),

    dict(
        file="14_report_stress_test_2025.pdf",
        area="capital", doc_type="risk_report", tipo="stress test",
        data="2026-02-05",
        titolo="Esercizio di Stress Test — Risultati 2025",
        sottotitolo="Scenari a tre anni — Base di calcolo: dati al 31 dicembre 2025",
        blocchi=[
            ("p", "L'esercizio di stress test valuta la tenuta patrimoniale e di liquidità in "
                  "scenari macroeconomici avversi. Gli scenari sono definiti su un orizzonte "
                  "triennale e i risultati indicano il valore minimo raggiunto nel periodo."),
            ("h", "1. Definizione degli scenari"),
            ("table", (
                ["Scenario", "PIL", "Tassi", "Prezzi immobili"],
                [
                    ["Base", "+0,8%", "invariati", "+1,0%"],
                    ["Avverso moderato", "-1,5%", "+150 bp", "-8,0%"],
                    ["Avverso severo", "-3,5%", "+250 bp", "-18,0%"],
                ],
                [55, 40, 42, 43],
            )),
            ("h", "2. Impatti sul profilo patrimoniale"),
            ("table", (
                ["Scenario", "CET1 ratio", "LCR", "ECL cumulate"],
                [
                    ["Base", "15,4%", "115%", "62 Mio"],
                    ["Avverso moderato", "13,1%", "104%", "128 Mio"],
                    ["Avverso severo", "11,2%", "96%", "241 Mio"],
                ],
                [55, 42, 40, 43],
            )),
            ("h", "3. Assunzioni sottostanti"),
            ("p", "L'esercizio assume una sensitività del margine di interesse pari a +12,0 "
                  "milioni di euro per 100 punti base di rialzo dei tassi, applicata linearmente "
                  "agli scenari avversi. L'assunzione non è stata riparametrata sulle serie "
                  "storiche del triennio."),
            ("h", "4. Considerazioni sui risultati"),
            ("p", "Nello scenario avverso severo il CET1 ratio scende all'11,2%, al di sotto del "
                  "requisito SREP del 12,5%, e l'LCR raggiunge il 96%, sotto il limite "
                  "regolamentare del 100%. Si tratta di esiti simulati in condizioni estreme e "
                  "non di valori rilevati alla data di riferimento."),
            ("p", "L'esercizio evidenzia che il fattore determinante nello scenario severo è la "
                  "concentrazione sul comparto immobiliare: la caduta dei prezzi degli immobili "
                  "del 18% spiega circa il 60% dell'incremento delle perdite attese cumulate."),
            ("h", "5. Azioni previste"),
            ("li", [
                "Predisposizione di un piano di contingenza patrimoniale entro giugno 2026",
                "Revisione dei criteri di erogazione sul comparto real estate",
                "Rafforzamento del buffer di liquidità in coerenza con il piano di funding",
            ]),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Limiti di rischio — riferimento per il rilevamento dei superamenti
# ---------------------------------------------------------------------------
# Sono gli stessi limiti dichiarati nel documento 01. Esportarli qui serve alla
# validazione: consente di verificare se il sistema li ha estratti correttamente
# dal testo, non di sostituirsi all'estrazione.

LIMITI = {
    "concentrazione_settoriale": {"valore": 25.0, "unita": "PERCENTUALE", "verso": "max",
                                  "base": "portafoglio", "area": "credit"},
    "esposizione_singola_controparte": {"valore": 10.0, "unita": "PERCENTUALE", "verso": "max",
                                        "base": "patrimonio", "area": "credit"},
    "esposizione_primi_10": {"valore": 35.0, "unita": "PERCENTUALE", "verso": "max",
                             "base": "portafoglio", "area": "credit"},
    "npl_ratio": {"valore": 6.0, "unita": "PERCENTUALE", "verso": "max", "area": "credit"},
    "var_1g": {"valore": 12.0, "unita": "MIO_EUR", "verso": "max", "area": "market"},
    "duration_titoli": {"valore": 5.0, "unita": "ANNI", "verso": "max", "area": "market"},
    "esposizione_valutaria": {"valore": 50.0, "unita": "MIO_EUR", "verso": "max", "area": "market"},
    "lcr": {"valore": 110.0, "unita": "PERCENTUALE", "verso": "min",
            "limite_regolamentare": 100.0, "area": "liquidity"},
    "nsfr": {"valore": 105.0, "unita": "PERCENTUALE", "verso": "min",
             "limite_regolamentare": 100.0, "area": "liquidity"},
    "cet1_ratio": {"valore": 14.0, "unita": "PERCENTUALE", "verso": "min",
                   "limite_regolamentare": 12.5, "area": "capital"},
}


# ---------------------------------------------------------------------------
# Ground truth: criticità deliberate
# ---------------------------------------------------------------------------
#
# `tipo` corrisponde alle quattro categorie che il progetto richiede di
# individuare:
#   - omissione               : informazione dovuta da una policy e assente
#   - inesattezza             : valori che non riconciliano tra documenti
#   - interpretazione_erronea : dati corretti, conclusione fuorviante
#   - fattore_di_rischio      : limite superato

CRITICITA_ATTESE = [
    dict(
        id="F1", tipo="fattore_di_rischio", area="credit", gravita="alta",
        chiave="concentrazione_settoriale / real estate / Q4 2025",
        descrizione="Superamento del limite di concentrazione settoriale",
        dettaglio="L'esposizione verso il comparto real estate e costruzioni è pari a 460 Mio "
                  "su un portafoglio di 1.700 Mio, ossia il 27,1%, contro un limite del 25% "
                  "previsto dal Risk Appetite Framework. Il superamento non risulta segnalato "
                  "al Comitato Rischi come richiesto dalla policy.",
        valori={"rilevato": 27.1, "limite": 25.0},
        documenti=["01_policy_limiti_rischio.pdf",
                   "02_report_esposizioni_creditizie_q4_2025.pdf"],
    ),
    dict(
        id="F2", tipo="fattore_di_rischio", area="credit", gravita="alta",
        chiave="esposizione_singola_controparte / Gruppo Aurora Immobiliare",
        descrizione="Superamento del limite di esposizione verso singola controparte",
        dettaglio="L'esposizione verso Gruppo Aurora Immobiliare è pari a 92 Mio, ossia il 10,8% "
                  "del patrimonio di vigilanza di 850 Mio, contro un limite del 10%. Il report "
                  "espone il dato ma non lo qualifica come superamento.",
        valori={"rilevato": 10.8, "limite": 10.0},
        documenti=["01_policy_limiti_rischio.pdf",
                   "03_report_concentrazione_controparti_q4_2025.pdf"],
    ),
    dict(
        id="F3", tipo="fattore_di_rischio", area="market", gravita="alta",
        chiave="var_1g / gennaio 2026",
        descrizione="Superamento del limite di VaR",
        dettaglio="Il VaR puntuale al 31 gennaio 2026 è pari a 13,2 Mio contro un limite di "
                  "12,0 Mio. La policy richiede la verifica sul dato puntuale di fine periodo.",
        valori={"rilevato": 13.2, "limite": 12.0},
        documenti=["01_policy_limiti_rischio.pdf", "06_report_var_gennaio_2026.pdf"],
    ),
    dict(
        id="I1", tipo="inesattezza", area="capital", gravita="alta",
        chiave="rwa / Q4 2025",
        descrizione="Attivi ponderati per il rischio non riconciliati",
        dettaglio="Il report dichiara RWA complessivi pari a 5.400 Mio, mentre la somma delle "
                  "componenti riportate nello stesso documento (4.200 credito + 800 mercato + "
                  "600 operativo) vale 5.600 Mio. Le quote percentuali della stessa tabella "
                  "(75,0% / 14,3% / 10,7%) sono calcolate su 5.600, il che conferma quale sia "
                  "il valore corretto. L'errore produce un CET1 ratio dichiarato del 15,7% a "
                  "fronte di un valore corretto del 15,2%, con margine sul requisito SREP "
                  "sovrastimato di circa 0,5 punti percentuali.",
        valori={"dichiarato": 5400, "somma_componenti": 5600,
                "cet1_ratio_dichiarato": 15.7, "cet1_ratio_corretto": 15.2},
        documenti=["10_report_adeguatezza_patrimoniale_q4_2025.pdf"],
    ),
    dict(
        id="I2", tipo="inesattezza", area="credit", gravita="alta",
        chiave="esposizione real estate / Q4 2025",
        descrizione="Esposizione settoriale discordante tra report e verbale",
        dettaglio="Il report analitico indica 460 Mio di esposizione real estate (27,1% del "
                  "portafoglio); il verbale del Comitato Rischi di pari data contabile indica "
                  "415 Mio (24,4%). La discordanza è determinante: sulla base del dato del "
                  "verbale il limite del 25% risulta rispettato, sulla base del report è "
                  "superato. Il Comitato ha deliberato di non richiedere azioni correttive.",
        valori={"report": 460, "verbale": 415},
        documenti=["02_report_esposizioni_creditizie_q4_2025.pdf",
                   "11_verbale_comitato_rischi_20260210.pdf"],
    ),
    dict(
        id="I3", tipo="inesattezza", area="market", gravita="alta",
        chiave="sensitività margine di interesse ai tassi",
        descrizione="Sensitività dichiarata non confermata dai dati storici",
        dettaglio="Il report di stress test assume una sensitività del margine di interesse "
                  "pari a +12,0 Mio per 100 punti base di rialzo. La regressione del margine "
                  "sull'Euribor 3M condotta sulle 36 osservazioni mensili dell'appendice "
                  "statistica restituisce un coefficiente di circa +0,71 Mio al mese, ossia "
                  "+8,5 Mio su base annua. L'assunzione sovrastima di circa il 40% il beneficio "
                  "di un rialzo dei tassi e riduce di conseguenza la severità apparente degli "
                  "scenari avversi.",
        valori={"dichiarato": 12.0, "stimato": 8.5},
        documenti=["07_appendice_statistica_serie_mensili.pdf",
                   "14_report_stress_test_2025.pdf"],
    ),
    dict(
        id="O1", tipo="omissione", area="market", gravita="media",
        chiave="backtesting / gennaio 2026",
        descrizione="Esito del backtesting non riportato",
        dettaglio="Il Risk Appetite Framework richiede che ogni report periodico di rischio di "
                  "mercato riporti l'esito del backtesting, con numero di eccezioni sugli ultimi "
                  "250 giorni e zona di riferimento. Il report di dicembre 2025 lo riporta "
                  "(2 eccezioni, zona verde); quello di gennaio 2026 lo omette, nel mese in cui "
                  "il VaR supera il limite.",
        documenti=["01_policy_limiti_rischio.pdf", "05_report_var_dicembre_2025.pdf",
                   "06_report_var_gennaio_2026.pdf"],
    ),
    dict(
        id="O2", tipo="omissione", area="credit", gravita="alta",
        chiave="concentrazione su base di gruppo",
        descrizione="Verifica della concentrazione non effettuata su base di gruppo",
        dettaglio="La policy richiede la verifica del limite per singola controparte su base di "
                  "gruppo, aggregando i soggetti connessi. Il report espone le posizioni su base "
                  "individuale e le note metodologiche lo dichiarano esplicitamente. "
                  "L'aggregazione non è documentata: due delle prime dieci posizioni "
                  "(Gruppo Aurora Immobiliare, 92 Mio, e Sviluppi Urbani Levante, 49 Mio) "
                  "appartengono al medesimo comparto e la mappatura dei gruppi connessi non "
                  "risulta agli atti.",
        documenti=["01_policy_limiti_rischio.pdf",
                   "03_report_concentrazione_controparti_q4_2025.pdf",
                   "13_nota_audit_rilievi.pdf"],
    ),
    dict(
        id="E1", tipo="interpretazione_erronea", area="market", gravita="alta",
        chiave="verifica limite VaR su media di periodo",
        descrizione="Limite di VaR verificato su media anziché su dato puntuale",
        dettaglio="Il report di gennaio 2026 e il verbale del Comitato Rischi concludono che il "
                  "profilo di rischio è entro il limite utilizzando la media del trimestre "
                  "novembre-gennaio (11,8 Mio). La policy prescrive la verifica sul dato puntuale "
                  "di fine periodo (13,2 Mio) ed esclude esplicitamente l'uso di medie. I dati "
                  "sono corretti: è la conclusione a essere fuorviante.",
        valori={"media_usata": 11.8, "puntuale_corretto": 13.2, "limite": 12.0},
        documenti=["01_policy_limiti_rischio.pdf", "06_report_var_gennaio_2026.pdf",
                   "11_verbale_comitato_rischi_20260210.pdf"],
    ),
    dict(
        id="E2", tipo="interpretazione_erronea", area="liquidity", gravita="media",
        chiave="descrizione dell'andamento LCR",
        descrizione="Andamento dell'LCR descritto come stabile a fronte di un calo continuo",
        dettaglio="Il verbale del Comitato Rischi descrive l'LCR come stabile su livelli "
                  "ampiamente superiori alla soglia. La serie mostra invece quattro trimestri di "
                  "calo consecutivo (128% → 124% → 118% → 112%), con il margine sulla soglia "
                  "interna sceso da 18 a 2 punti percentuali. Il report di liquidità e la nota "
                  "di Tesoreria segnalano correttamente la traiettoria; il verbale no.",
        valori={"serie": [128, 124, 118, 112], "soglia_interna": 110},
        documenti=["08_report_liquidita_q4_2025.pdf",
                   "11_verbale_comitato_rischi_20260210.pdf",
                   "09_nota_tesoreria_funding_2026.pdf"],
    ),
]


# ---------------------------------------------------------------------------
# Esecuzione
# ---------------------------------------------------------------------------

def costruisci_metadata() -> dict:
    """Metadati per l'indicizzazione, derivati da DOCUMENTI: unica fonte di verità."""
    metadata = {}
    for doc in DOCUMENTI:
        assert doc["area"] in AREE, f"area non canonica: {doc['area']}"
        assert doc["doc_type"] in DOC_TYPES, f"doc_type non canonico: {doc['doc_type']}"
        metadata[doc["file"]] = {
            "doc_type": doc["doc_type"],
            "tipo": doc["tipo"],
            "area": doc["area"],
            "data": _data_int(doc["data"]),
        }
    return metadata


def genera_corpus(data_dir: str = DATA_DIR) -> list:
    os.makedirs(data_dir, exist_ok=True)
    creati = []

    for doc in DOCUMENTI:
        path = os.path.join(data_dir, doc["file"])
        scrivi_pdf(path, doc["titolo"], doc["sottotitolo"], doc["blocchi"])
        creati.append(dict(
            file=doc["file"], area=doc["area"], doc_type=doc["doc_type"],
            tipo=doc["tipo"], data=doc["data"],
            kb=round(os.path.getsize(path) / 1024, 1),
        ))

    def _scrivi_json(nome, contenuto):
        with open(os.path.join(data_dir, nome), "w", encoding="utf-8") as f:
            json.dump(contenuto, f, ensure_ascii=False, indent=2)

    _scrivi_json("metadata.json", costruisci_metadata())
    _scrivi_json("criticita_attese.json", CRITICITA_ATTESE)
    _scrivi_json("limiti.json", LIMITI)

    return creati


def anteprima_estrazione(data_dir: str = DATA_DIR,
                         file_name: str = "10_report_adeguatezza_patrimoniale_q4_2025.pdf",
                         caratteri: int = 1800) -> None:
    """Mostra come il testo di un PDF arriva davvero alla pipeline.

    Da eseguire prima di scrivere i prompt di estrazione dei KPI: in questo
    corpus quasi tutti i dati stanno in tabella, e le criticità I1 e F1
    dipendono dal fatto che le righe restino associate alle proprie etichette.
    """
    path = os.path.join(data_dir, file_name)
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            testo = "\n".join((p.extract_text() or "") for p in pdf.pages)
            tabelle = [t for p in pdf.pages for t in p.extract_tables()]
    except ImportError:
        from pypdf import PdfReader
        testo = "\n".join((p.extract_text() or "") for p in PdfReader(path).pages)
        tabelle = []

    print(f"--- TESTO ESTRATTO DA {file_name} (primi {caratteri} caratteri) ---")
    print(testo[:caratteri])
    if tabelle:
        print(f"\n--- {len(tabelle)} TABELLE RICONOSCIUTE ---")
        for i, tabella in enumerate(tabelle):
            print(f"\n[tabella {i}]")
            for riga in tabella:
                print(riga)


if __name__ == "__main__":
    risultati = genera_corpus()

    print(f"Corpus generato in {DATA_DIR}: {len(risultati)} documenti")
    print(f"Font Unicode: {'DejaVu (accenti preservati)' if UNICODE_OK else 'Helvetica (fallback)'}\n")

    print(f"{'file':<50} {'area':<12} {'doc_type':<17} {'KB':>7}")
    print("-" * 90)
    for r in risultati:
        print(f"{r['file']:<50} {r['area']:<12} {r['doc_type']:<17} {r['kb']:>7}")

    print(f"\nCriticità deliberate: {len(CRITICITA_ATTESE)}")
    for c in CRITICITA_ATTESE:
        print(f"  {c['id']} [{c['tipo']:<24}] [{c['gravita']:<5}] {c['descrizione']}")

    print("\nScritti anche: metadata.json, criticita_attese.json, limiti.json")