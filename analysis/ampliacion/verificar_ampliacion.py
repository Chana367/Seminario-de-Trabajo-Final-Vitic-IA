"""Compara salidas/resultados.json con las cifras publicadas en la tesis.

Uso: python verificar_ampliacion.py [carpeta_salida]   (por defecto ./salidas)
Termina con código 1 si alguna cifra no coincide al redondeo publicado.
"""
import json
import sys
from pathlib import Path

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "salidas"
R = json.loads((OUT / "resultados.json").read_text(encoding="utf-8"))

ESPERADO = [
    # (descripción, ruta en resultados.json, valor publicado, decimales)
    ("Bloque fijo: MAE persistencia", ("oficial", "modelos", "Persistencia", "mae"), 49.88, 2),
    ("Bloque fijo: MAE media del entrenamiento", ("oficial", "modelos", "Media del entrenamiento", "mae"), 42.08, 2),
    ("Bloque fijo: MAE Ridge (variación)", ("oficial", "modelos", "Ridge (variación)", "mae"), 32.85, 2),
    ("Bloque fijo: MAE gradient boosting (nivel)", ("oficial", "modelos", "Gradient boosting (nivel)", "mae"), 39.84, 2),
    ("Bloque fijo: R² Ridge (variación)", ("oficial", "modelos", "Ridge (variación)", "r2"), -1.162, 3),
    ("Cinco cortes: MAE persistencia", ("multicorte", "agregado", "Persistencia", "mae"), 44.29, 2),
    ("Cinco cortes: MAE media del entrenamiento", ("multicorte", "agregado", "Media del entrenamiento", "mae"), 34.98, 2),
    ("Cinco cortes: MAE Ridge (variación)", ("multicorte", "agregado", "Ridge (variación)", "mae"), 30.24, 2),
    ("Cinco cortes: combinaciones que Ridge gana a la persistencia", ("multicorte", "agregado", "Ridge (variación)", "gana_dias_corte"), 13, 0),
    ("Cinco cortes: combinaciones evaluadas", ("multicorte", "n_dias_corte"), 15, 0),
    ("Diagnóstico: mediana del cambio en 24 h, entrenamiento", ("diagnostico", "cambio_entrenamiento_oficial", "mediana"), 0.99, 2),
    ("Diagnóstico: mediana del cambio en 24 h, prueba", ("diagnostico", "cambio_prueba_oficial", "mediana"), 51.04, 2),
    ("Decisión de riego: acierto de Ridge en cinco cortes (%)", ("decision", "multicorte", "Ridge (variación)", "acierto_pct"), 39.2, 1),
    ("Artefacto: α de Ridge", ("artefacto", "alpha"), 30, 0),
]
HASH = "fe91f281bdf389f274d1b18962cb736185f27bfd6cf1c8ffdf4325c52a265127"


def valor(ruta):
    v = R
    for k in ruta:
        v = v[k]
    return v


fallas = 0
for nombre, ruta, publicado, dec in ESPERADO:
    obtenido = valor(ruta)
    ok = round(float(obtenido), dec) == round(publicado, dec)
    fallas += not ok
    print(f"{'OK ' if ok else 'ERR'}  {nombre}: {round(float(obtenido), dec)} (publicado {publicado})")
h = R["artefacto"]["sha256"]
print(f"{'OK ' if h == HASH else 'AVISO'}  SHA-256 del artefacto Ridge: {h}")
if h != HASH:
    print("       El hash depende de las versiones exactas de las bibliotecas (ver requirements-lock.txt).")
sys.exit(1 if fallas else 0)
