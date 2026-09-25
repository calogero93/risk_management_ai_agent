DOMANDE_TEST = [
    # --- selezione del tool corretto ---
    "Quali documenti abbiamo sul rischio di mercato?",
    "Chi è responsabile del presidio ICT risk?",
    "Analizza il report di adeguatezza patrimoniale del Q4 2025",
    "Cosa succederebbe se l'Euribor salisse al 5%?",

    # --- criticità, una per area ---
    "Ci sono criticità sull'area credito?",
    "Ci sono superamenti di limite sul rischio di mercato?",
    "Ci sono criticità sulla liquidità?",
    "L'adeguatezza patrimoniale presenta problemi?",

    # --- concatenamento fra tool ---
    "Il verbale del Comitato Rischi è coerente con i report analitici?",
    "L'esposizione sul real estate rispetta il limite di concentrazione?",
    "Il report di gennaio sul VaR contiene tutto quello che la policy richiede?",
    "La sensitività assunta nello stress test è confermata dai dati storici?",

    # --- memoria conversazionale (da eseguire in sequenza) ---
    "Qual è la situazione della liquidità?",
    "E come si è mossa negli ultimi trimestri?",
    "Cosa succede se i depositi calano del 10%?",

    # --- robustezza ---
    "Qual è il fatturato del 2027?",
    "Analizza il file report_2030.pdf",
    "Cosa succede se l'Euribor arriva al 12%?",
]


def esegui_domande(agente):
    # Il notebook usa un thread fisso per tutta la sequenza di domande.
    config = {"configurable": {"thread_id": "session-1"}}
    for d in DOMANDE_TEST:
        print(f"\n{'='*70}\n{d}\n{'='*70}")
        risposta = agente.invoke({"messages": [{"role": "user", "content": d}]}, config=config)
        print(risposta["messages"][-1].content)
