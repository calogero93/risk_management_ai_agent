from .analysis import RiskAnalyzer

import matplotlib.pyplot as plt

def dashboard(analyzer: RiskAnalyzer, output_path: str | None = None):
    serie = analyzer.leggi_serie()
    mesi = serie["mese"]

    fig, assi = plt.subplots(2, 2, figsize=(14, 8))
    fig.suptitle("Monitoraggio esposizioni al rischio — Banca Meridiana", fontsize=13)

    pannelli = [
        (assi[0][0], "lcr", "LCR (%)", [(110, "soglia interna"), (100, "limite regolamentare")]),
        (assi[0][1], "impieghi", "Impieghi lordi (Mio EUR)", []),
        (assi[1][0], "euribor", "Euribor 3M (%)", []),
        (assi[1][1], "margine", "Margine di interesse mensile (Mio EUR)", []),
    ]

    for ax, chiave, titolo, soglie in pannelli:
        ax.plot(mesi, serie[chiave], marker="o", markersize=3, linewidth=1.5)
        for valore, etichetta in soglie:
            ax.axhline(valore, linestyle="--", linewidth=1, label=etichetta)
        ax.set_title(titolo, fontsize=10)
        ax.grid(alpha=0.3)
        ax.set_xticks(mesi[::6])
        ax.tick_params(axis="x", rotation=45, labelsize=8)
        if soglie:
            ax.legend(fontsize=8)

    plt.tight_layout()
    if output_path:
        fig.savefig(output_path)
    else:
        plt.show()
