"""Verifiche locali del corpus e delle regole deterministiche del notebook."""

import json
import tempfile
import unittest
from pathlib import Path

from risk_management_ai_agent.analysis import RiskAnalyzer
from risk_management_ai_agent.corpus import genera_corpus
from risk_management_ai_agent.ingestion import Chunker, METADATA
from risk_management_ai_agent.schemas import KPI, Limite, Periodo


class PipelineTest(unittest.TestCase):
    def test_corpus_e_chunk(self):
        with tempfile.TemporaryDirectory() as directory:
            risultati = genera_corpus(directory)
            data = Path(directory)
            self.assertEqual(len(risultati), 15)
            self.assertEqual(len(list(data.glob("*.pdf"))), 15)
            self.assertEqual(json.loads((data / "metadata.json").read_text()), METADATA)
            self.assertEqual(len(json.loads((data / "criticita_attese.json").read_text())), 10)

            chunks = Chunker().documents_splitter(directory)
            self.assertEqual({chunk["file_name"] for chunk in chunks}, set(METADATA))
            self.assertTrue(all(chunk["payload"] for chunk in chunks))

    def test_verifica_limiti_solo_su_valori_rilevati(self):
        analyzer = RiskAnalyzer.__new__(RiskAnalyzer)
        analyzer.limiti = {
            "var_1g": Limite(nome="var_1g", valore=12, verso="max", unita="MIO_EUR"),
            "lcr": Limite(nome="lcr", valore=110, verso="min", unita="PERCENTUALE"),
        }
        periodo = Periodo(anno=2026, mese=1)
        kpi = [
            KPI(nome="var_1g", periodo=periodo, valore=13.2, unita="MIO_EUR"),
            KPI(nome="var_1g", periodo=periodo, valore=11.8, unita="MIO_EUR", natura="medio"),
            KPI(nome="lcr", periodo=periodo, valore=109, unita="PERCENTUALE"),
            KPI(nome="lcr", periodo=periodo, valore=112, unita="PERCENTUALE"),
        ]
        anomalie = analyzer.verifica_limiti(kpi)
        self.assertEqual([a.kpi_coinvolti[0].valore for a in anomalie], [13.2, 109])


if __name__ == "__main__":
    unittest.main()
