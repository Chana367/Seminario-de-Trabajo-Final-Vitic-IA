"""Figuras de la version final. Paleta validada (azul, naranja; persistencia en gris de referencia).

Uso: python figuras.py [carpeta_datos] [carpeta_salida]  (los mismos argumentos que analisis_final.py,
que debe ejecutarse antes). Las figuras se guardan en <carpeta_salida>/figuras.
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
REF = "#898781"
TZ = "America/Argentina/San_Juan"
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": AXIS, "axes.linewidth": 0.8,
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "axes.titlesize": 10,
    "axes.titleweight": "bold", "axes.titlecolor": INK, "axes.titlelocation": "left",
    "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
    "legend.fontsize": 8.5, "figure.dpi": 100, "savefig.dpi": 300, "savefig.bbox": "tight",
    "figure.facecolor": "white", "axes.facecolor": "white",
})
def grid(ax, axis="y"):
    ax.grid(True, axis=axis, color=GRID, linewidth=0.6); ax.set_axisbelow(True)
    ax.tick_params(length=0)

BASE = Path(__file__).resolve().parent
DATA = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE.parent / "cierre" / "datos"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else BASE / "salidas"
(OUT / "figuras").mkdir(parents=True, exist_ok=True)
R = json.load(open(OUT / "resultados.json", encoding="utf-8"))
p = pd.read_csv(DATA / "pares_24h.csv", parse_dates=["timestamp", "target_timestamp"])
W = 6.3  # pulgadas, ~16 cm

# ------------------------------------------------------------------ A. Bloque oficial en el tiempo
s = pd.read_csv(OUT / "serie_oficial.csv", parse_dates=["objetivo"])
s["t"] = (s.objetivo.dt.tz_localize("UTC") if s.objetivo.dt.tz is None else s.objetivo).dt.tz_convert(TZ).dt.tz_localize(None)
s = s.sort_values("t")
fig, ax = plt.subplots(figsize=(W, 3.1))
# huecos visibles: cortar lineas si hay mas de 1 h entre puntos
def tramos(df):
    brk = df.t.diff().dt.total_seconds().gt(3600 * 1.5).cumsum()
    return [g for _, g in df.groupby(brk)]
for i, g in enumerate(tramos(s)):
    ax.plot(g.t, g.y, color=INK, lw=1.6, label="Observado" if i == 0 else None, zorder=5)
    ax.plot(g.t, g.per, color=REF, lw=1.4, ls=(0, (4, 2)), label="Persistencia" if i == 0 else None)
    ax.plot(g.t, g.gb, color=ORANGE, lw=1.4, label="Gradient boosting (nivel)" if i == 0 else None)
    ax.plot(g.t, g.ridge, color=BLUE, lw=1.6, label="Ridge (variación)" if i == 0 else None)
ax.axhline(30, color=MUTED, lw=0.8, ls=":")
ax.text(s.t.min(), 31.5, "umbral de riego 30", color=MUTED, fontsize=7.5)
ax.set_ylabel("Humedad del suelo (escala de la sonda)")
ax.set_ylim(0, 105); grid(ax)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m\n%H h"))
ax.set_xlabel("Momento de la respuesta (hora local)")
ax.legend(ncol=4, loc="upper left", bbox_to_anchor=(0, 1.13), handlelength=2.2)
fig.savefig(OUT / "figuras" / "fig_bloque_oficial.png"); plt.close(fig)

# ------------------------------------------------------------------ B. Cambio de regimen
FZ = pd.Timestamp("2026-10-24 19:00", tz="UTC")
tr = p[p.target_timestamp < FZ]; te = p[(p.timestamp > FZ) & (p.timestamp <= FZ + pd.Timedelta(hours=72))]
c_tr = (tr.soil_moisture_t_plus_24h - tr.soil_moisture).abs()
c_te = (te.soil_moisture_t_plus_24h - te.soil_moisture).abs()
bins = np.arange(0, 80, 2.5)
fig, axs = plt.subplots(2, 1, figsize=(W, 3.4), sharex=True)
for ax, c, col, nom in [(axs[0], c_tr, BLUE, f"Entrenamiento ({len(c_tr)} pares)"),
                        (axs[1], c_te, ORANGE, f"Prueba ({len(c_te)} pares)")]:
    ax.hist(c, bins=bins, color=col, edgecolor="white", linewidth=0.8)
    md = c.median()
    ax.axvline(md, color=INK, lw=1.0)
    lado = 1 if md < 20 else -1
    ax.text(md + lado * 1.2, ax.get_ylim()[1] * 0.80, f"mediana {md:.1f}".replace(".", ","), fontsize=8,
            color=INK, ha="left" if lado > 0 else "right")
    ax.set_title(nom, fontsize=9, pad=3); grid(ax); ax.set_ylabel("pares")
axs[1].set_xlabel("Cambio absoluto de la humedad del suelo en 24 h (puntos)")
fig.tight_layout(h_pad=0.6)
fig.savefig(OUT / "figuras" / "fig_regimen.png"); plt.close(fig)

# ------------------------------------------------------------------ C. MAE agregado en cinco cortes
ag = R["multicorte"]["agregado"]
orden = ["Ridge (variación)", "Bosque aleatorio (nivel)", "Gradient boosting (nivel)", "Ridge (nivel)",
         "Media del entrenamiento", "Bosque aleatorio (variación)", "Gradient boosting (variación)"]
vals = [ag[k]["mae"] for k in orden]; per = ag["Persistencia"]["mae"]
fig, ax = plt.subplots(figsize=(W, 3.0))
y = np.arange(len(orden))[::-1]
cols = [BLUE if k == "Ridge (variación)" else ("#86b6ef" if "Media" not in k else "#c3c2b7") for k in orden]
ax.barh(y, vals, height=0.62, color=cols)
for yi, v, k in zip(y, vals, orden):
    ax.text(v - 0.8, yi, f"{v:.1f}".replace(".", ","), va="center", ha="right", fontsize=8,
            color="white" if k == "Ridge (variación)" else INK)
    ax.text(52, yi, f"{ag[k]['gana_dias_corte']}/15", va="center", ha="center", fontsize=8, color=INK2)
ax.text(52, len(orden) - 0.35, "gana a\npersistencia", ha="center", va="bottom", fontsize=7.5, color=INK2)
ax.axvline(per, color=REF, lw=1.2, ls=(0, (4, 2)))
ax.text(per - 0.5, -0.95, f"persistencia {per:.1f}".replace(".", ","), color=REF, fontsize=8, ha="right")
ax.set_yticks(y); ax.set_yticklabels(orden); ax.set_xlim(0, 57); ax.set_ylim(-1.3, len(orden) + 0.3)
ax.set_xlabel("MAE agregado sobre 5 cortes (puntos de la escala de la sonda)"); grid(ax, "x")
fig.savefig(OUT / "figuras" / "fig_multicorte.png"); plt.close(fig)

# ------------------------------------------------------------------ D. Por dia en el bloque oficial
pdia = R["oficial"]["por_dia"]
dias = list(pdia.keys()); x = np.arange(len(dias)); w = 0.26
fig, ax = plt.subplots(figsize=(W, 2.9))
for off, k, col, nom in [(-w, "Persistencia", REF, "Persistencia"),
                         (0, "Gradient boosting (nivel)", ORANGE, "Gradient boosting (nivel)"),
                         (w, "Ridge (variación)", BLUE, "Ridge (variación)")]:
    v = [pdia[d][k] for d in dias]
    ax.bar(x + off, v, width=w - 0.03, color=col, label=nom)
    for xi, vi in zip(x + off, v):
        ax.text(xi, vi + 1, f"{vi:.0f}", ha="center", fontsize=7.5, color=INK2)
ax.set_xticks(x); ax.set_xticklabels([f"{d[8:10]}/{d[5:7]}\n(n={pdia[d]['n']})" for d in dias])
ax.set_ylabel("MAE (puntos)"); ax.set_ylim(0, 78); grid(ax)
ax.legend(ncol=3, loc="upper left", bbox_to_anchor=(0, 1.12))
fig.savefig(OUT / "figuras" / "fig_por_dia.png"); plt.close(fig)

# ------------------------------------------------------------------ E. MAE vs acierto en la decision
cv = R["decision"]["curva_mae_acierto"]
fig, ax = plt.subplots(figsize=(W, 3.1))
mx = [c["mae"] for c in cv]; my = [c["acierto_pct"] for c in cv]
ax.axvspan(0, 3, color="#cde2fb", lw=0); ax.axvspan(3, 8, color="#e8f1fc", lw=0)
for xt, t in [(1.5, "bueno"), (5.5, "usable"), (11.5, "marginal")]:
    ax.text(xt, 3, t, ha="center", fontsize=7.5, color=INK2)
ax.axvline(15, color=AXIS, lw=0.8)
ax.plot(mx, my, color=BLUE, lw=1.6, marker="o", ms=4.5)
ax.text(20.5, 84.5, "referencia: error aleatorio\nsimétrico del mismo MAE", color=BLUE, fontsize=8)
dm = R["decision"]["multicorte"]; ag = R["multicorte"]["agregado"]
for k, nom, col, dy in [("Ridge (variación)", "Ridge (variación)", ORANGE, 5),
                        ("Persistencia", "Persistencia", REF, -9)]:
    xx, yy_ = ag[k]["mae"], dm[k]["acierto_pct"]
    ax.plot([xx], [yy_], marker="o", ms=8, color=col, mec="white", mew=1.5, zorder=6)
    ax.text(xx + 0.8, yy_ + dy, f"{nom}: MAE {xx:.1f}, acierto {yy_:.0f} %".replace(".", ","),
            fontsize=8, color=INK)
ax.set_xlim(0, 47); ax.set_ylim(0, 100)
ax.set_xlabel("MAE del pronóstico (puntos)"); ax.set_ylabel("Acierto en «¿regar o no?» (%)"); grid(ax)
fig.savefig(OUT / "figuras" / "fig_mae_acierto.png"); plt.close(fig)

# ------------------------------------------------------------------ F. Simulacion (sintetica)
sm = pd.read_csv(OUT / "simulacion_muestra.csv")
h = np.arange(len(sm)) / 24
fig, ax = plt.subplots(figsize=(W, 2.6))
ax.plot(h, sm.soil_moisture, color=BLUE, lw=1.4, label="Humedad simulada")
ev = sm.riego > 0
ax.scatter(h[ev], np.full(ev.sum(), 25.5), marker="|", s=60, color=ORANGE, label="Riego simulado (1,5 L)")
ax.axhline(30, color=MUTED, lw=0.8, ls=":")
ax.text(0, 28.2, "umbral de riego (30)", color=MUTED, fontsize=7.5)
ax.set_xlabel("Días de la muestra simulada"); ax.set_ylabel("Humedad (escala de la sonda)")
ax.set_ylim(24, 50); grid(ax)
ax.legend(ncol=2, loc="upper right")
ax.set_title("DATOS SINTÉTICOS — no son mediciones de la maqueta", fontsize=8.5, color=ORANGE)
fig.savefig(OUT / "figuras" / "fig_simulacion.png"); plt.close(fig)
print("figuras ok")
