"""Comandi per eseguire le fasi del notebook dal terminale."""

import argparse
import os
from pathlib import Path


def _verifica_ambiente(*nomi: str) -> None:
    mancanti = [nome for nome in nomi if not os.environ.get(nome)]
    if mancanti:
        raise SystemExit(
            f"Variabili d'ambiente mancanti: {', '.join(mancanti)}. "
            "Configura .env e usa uv run --env-file .env."
        )


def _verifica_corpus(data_dir: str) -> None:
    if not (Path(data_dir) / "limiti.json").is_file():
        raise SystemExit(
            f"Corpus assente in {data_dir}. Esegui prima: uv run risk-agent corpus"
        )


def _rispondi(agente, domanda: str, config: dict) -> None:
    risposta = agente.invoke(
        {"messages": [{"role": "user", "content": domanda}]}, config=config
    )
    print(risposta["messages"][-1].content)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", default=os.environ.get("DATA_DIR", "data"),
        help="Cartella dei documenti generati (default: data o DATA_DIR)",
    )
    comandi = parser.add_subparsers(dest="comando", required=True)
    comandi.add_parser("corpus", help="Genera i 15 PDF e i tre JSON")
    chiedi = comandi.add_parser("ask", help="Pone una domanda all'agente")
    chiedi.add_argument("domanda")
    comandi.add_parser("chat", help="Avvia una conversazione interattiva")
    comandi.add_parser("test", help="Esegue le domande del notebook in sequenza")
    grafico = comandi.add_parser("dashboard", help="Mostra la dashboard")
    grafico.add_argument("--output", help="Salva il grafico nel file indicato")
    args = parser.parse_args()

    if args.comando == "corpus":
        from .corpus import genera_corpus

        risultati = genera_corpus(args.data_dir)
        print(f"Corpus generato in {args.data_dir}: {len(risultati)} documenti")
        return

    _verifica_corpus(args.data_dir)
    _verifica_ambiente("MODEL_NAME", "API_KEY")

    if args.comando == "dashboard":
        from .analysis import RiskAnalyzer
        from .dashboard import dashboard

        dashboard(RiskAnalyzer(args.data_dir), output_path=args.output)
        return

    _verifica_ambiente("EMBEDDING_MODEL")
    from .agent import crea_agente

    agente = crea_agente(args.data_dir)
    config = {"configurable": {"thread_id": "session-1"}}

    if args.comando == "ask":
        _rispondi(agente, args.domanda, config)
    elif args.comando == "test":
        from .questions import esegui_domande

        esegui_domande(agente)
    else:
        try:
            while domanda := input("Domanda (invio per terminare): ").strip():
                _rispondi(agente, domanda, config)
        except (EOFError, KeyboardInterrupt):
            print()


if __name__ == "__main__":
    main()
