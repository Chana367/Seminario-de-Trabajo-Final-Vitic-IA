"""Prepara los documentos de cierre a partir de resultados ya calculados."""
from __future__ import annotations

import json
import importlib.metadata
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from evaluar_cierre import ROOT, CUT, TZ, FREEZE, plots, save_json


def n(value, decimals=0):
    return f"{value:,.{decimals}f}".translate(str.maketrans({",": ".", ".": ","}))


def write(name, content):
    (ROOT / name).write_text(content.strip() + "\n", encoding="utf-8")


def table_metrics(m):
    rows = ["| Evaluación sobre las mismas 55 horas | MAE (puntos) | RMSE (puntos) | R² |", "|---|---:|---:|---:|"]
    for key, label in [("old_model", "Artefacto conservado del 22/10"), ("model", "Gradient Boosting con integración disponible"), ("persistence", "Persistencia")]:
        v = m[key]
        rows.append(f"| {label} | {n(v['mae_pp'], 2)} | {n(v['rmse_pp'], 2)} | {n(v['r2'], 3)} |")
    return "\n".join(rows)


def main():
    s = json.loads((ROOT / "RESUMEN_RESULTADOS.json").read_text(encoding="utf-8"))
    m = s["fixed_holdout"]
    old = s["historical_published"]
    w = s["walk_forward_all"]
    a, b = s["quality_stages"]
    old_event, new_event = s["water_events"]
    hourly = pd.read_csv(ROOT / "datos/serie_horaria.csv", index_col=0)
    hourly.index = pd.to_datetime(hourly.index, utc=True)
    daily = pd.read_csv(ROOT / "datos/calidad_diaria.csv", index_col=0)
    test = pd.read_csv(ROOT / "datos/predicciones_bloque_fijo.csv")
    for c in ("timestamp", "target_timestamp"):
        test[c] = pd.to_datetime(test[c], utc=True)
    errors = pd.read_csv(ROOT / "datos/error_diario_origen_movil.csv")
    plots(hourly, daily, test, m, errors, ROOT / "graficos")
    fig, ax = plt.subplots(figsize=(11, 4.5), layout="constrained")
    ax.plot(hourly.index.tz_convert(TZ), hourly.soil_moisture, color="#1b6076", lw=1.5)
    ax.axvline(pd.Timestamp(old["cutoff_utc"]).tz_convert(TZ), color="#8d6f52", ls="--", label="Corte anterior (22/10)")
    ax.axhspan(s["fixed_training"]["target_min"], s["fixed_training"]["target_max"], color="#aec7bf", alpha=.22, label="Rango de etiquetas del entrenamiento congelado")
    ax.set(title="La segunda etapa contiene estados de suelo diferentes", ylabel="Escala relativa del sensor (%)", xlabel="Fecha, Argentina")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m", tz=TZ))
    ax.grid(axis="y", alpha=.18)
    fig.legend(*ax.get_legend_handles_labels(), loc="outside lower center", ncol=2, frameon=False, fontsize=9)
    fig.savefig(ROOT / "graficos/05_evolucion_del_suelo.png", dpi=180)
    plt.close(fig)
    source_weather = pd.DataFrame([json.loads(x) for x in (ROOT / "respaldo_bd/tablas/weather_observation.jsonl").read_text().splitlines()])
    source_sat = pd.DataFrame([json.loads(x) for x in (ROOT / "respaldo_bd/tablas/satellite_observation.jsonl").read_text().splitlines()])
    source_weather.to_csv(ROOT / "datos/meteorologia_original.csv", index=False)
    source_sat.to_csv(ROOT / "datos/satelite_original.csv", index=False)
    events = pd.read_csv(ROOT / "datos/eventos_auditados.csv")
    positive = events[events.ciclo_sin_advertencia_volumen_positivo]
    events["duracion_mayor_60s"] = events.duracion_segundos.gt(60)
    events["volumen_reportado_mayor_2l"] = events.volumen_circulado_reportado_l.gt(2)
    events["caudal_promedio_reportado_mayor_10"] = events.caudal_promedio_l_min.gt(10)
    events[events.duracion_mayor_60s | events.volumen_reportado_mayor_2l | events.caudal_promedio_reportado_mayor_10].to_csv(ROOT / "datos/eventos_para_revision.csv", index=False)
    water = dict(positive_closed_without_backend_warning=len(positive),
                 median_duration_seconds=float(positive.duracion_segundos.median()),
                 median_reported_counter_delta_l=float(positive.volumen_circulado_reportado_l.median()),
                 max_reported_counter_delta_l=float(positive.volumen_circulado_reportado_l.max()),
                 closed_positive_over_2l=int(positive.volumen_circulado_reportado_l.gt(2).sum()),
                 closed_positive_over_60s=int(positive.duracion_segundos.gt(60).sum()),
                 flow_liters_independently_calibrated=False, net_water_consumption_measured=False,
                 water_saved_estimated=False)
    save_json(ROOT / "datos/auditoria_hidraulica.json", water)
    fair_gain = 100 * (1 - m["model"]["mae_pp"] / m["old_model"]["mae_pp"])
    external_gain = m["soil_only"]["mae_pp"] - m["model"]["mae_pp"]
    external_pct = 100 * external_gain / m["soil_only"]["mae_pp"]
    core_current = w["soil_only"]
    days_table = "\n".join(f"| {r.fecha_objetivo_local} | {int(r.n)} | {n(r.mae_model,2)} | {n(r.mae_persistencia,2)} |" for r in pd.read_csv(ROOT / "datos/error_diario_bloque.csv").itertuples())
    verdict = "Apoyo parcial: resultado descriptivo favorable frente a persistencia, sin confirmación robusta de la hipótesis general ni precisión operativa demostrada."
    save_json(ROOT / "CONCLUSION_HIPOTESIS.json", dict(
        hypothesis_source="Tesis_ViticAI_borrador_v4.pdf, página 8",
        numerical_fixed_block_test="FAVORABLE", overall_research_conclusion="APOYO_PARCIAL_NO_CONFIRMACION_ROBUSTA",
        relative_mae_improvement_pct=m["model"]["mae_improvement_pct"], rmse_skill=m["model"]["rmse_skill"],
        absolute_accuracy_sufficient_for_actuation=False, calibrated_water_saving_demonstrated=False,
        dht_incremental_effect_demonstrated=False, multimodal_incremental_effect_robust=False,
        actual_effect_vs_soil_only_mae_pp=external_gain,
        reasons=["55 orígenes correlacionados distribuidos en cuatro fechas, sin prueba prospectiva.",
                 "MAE de 39,73 puntos y R² negativo en el bloque fijo.",
                 "El DHT aparece en un solo par del entrenamiento congelado.",
                 "Los índices Sentinel disponibles son constantes; GOES no tiene valores de entrenamiento en ese bloque.",
                 "El agua recircula y falta una calibración física independiente."]
    ))
    write("00_LEER_PRIMERO.md", f"""
# VitiAlert - cierre de la campaña

**Corte: 28/10/2026 a las 16:00, Argentina.** Última lectura incluida: 15:59:58.

La campaña permitió completar la adquisición, respaldar la base y entrenar el modelo. **El pronóstico mejora frente a persistencia en el bloque evaluado, pero su error sigue siendo demasiado alto para defenderlo como una predicción precisa de riego.**

| Resultado principal | Valor |
|---|---:|
| Lecturas conservadas, incluidas 74 de septiembre | {n(s['api_readings'])} |
| Lecturas de octubre | {n(s['october_readings'])} |
| Horas con suelo y cobertura suficiente | {s['usable_hours']} |
| Pares medidos de suelo actual y suelo a 24 horas | {s['eligible_pairs']} |
| Prueba temporal fija | {m['n']} pronósticos en {m['target_days']} fechas |
| MAE del modelo / persistencia | {n(m['model']['mae_pp'],2)} / {n(m['persistence']['mae_pp'],2)} puntos |
| Reducción relativa de MAE | {n(m['model']['mae_improvement_pct'],2)}% |

**Conclusión formal:** {verdict}

Esto significa que hay una mejora relativa observada, pero no una validación de ahorro de agua, de precisión en viñedos ni del aporte de cada fuente por separado. No corresponde presentar la reducción del error como porcentaje de acierto.

## Para compartir con el equipo

1. Leer [Resultados y conclusiones](01_RESULTADOS_Y_CONCLUSIONES.md).
2. Practicar con [Defensa oral y preguntas](02_DEFENSA_ORAL.md).
3. Consultar [Método y reproducción](03_METODO_Y_REPRODUCCION.md) para las decisiones técnicas.
4. Usar [Textos para actualizar la memoria](05_TEXTOS_PARA_LA_MEMORIA.md) como base; revisar que coincidan con la redacción final del equipo.
5. El [resumen PDF](RESUMEN_PARA_EL_EQUIPO.pdf) presenta las cifras y los gráficos principales. Las tablas, el código y el modelo acompañan la entrega.

## Dónde está cada cosa

| Carpeta | Contenido |
|---|---|
| `respaldo_bd` | Dos respaldos PostgreSQL, manifiesto y tablas originales. El archivo terminado en `1600.dump` contiene las filas del corte. |
| `fuentes_api` | Respuestas originales GET y hashes, filtradas al corte. |
| `datos` | Auditoría, serie horaria, pares y todas las predicciones evaluadas. |
| `modelo` | Artefacto final con 153 pares y artefacto congelado usado en la prueba; no están desplegados. |
| `referencia_22_octubre` | Resultados y modelo anteriores conservados; registro de intervenciones. |
| `graficos` | Figuras listas para usar, con huecos de datos visibles. |
| `codigo` | Descarga, análisis, controles, reproducción e informe. |
| `verificacion` | Resultados de controles, versiones y manifiestos. |

La carpeta se preparó aparte. No se cambiaron GitHub, la base de Render, la válvula ni el firmware. El corte es analítico: no se apagó el servidor. La copia nativa descargada a las 16:25 contenía 47 lecturas posteriores, excluidas del respaldo al corte y de todo entrenamiento o evaluación.
""")
    write("01_RESULTADOS_Y_CONCLUSIONES.md", f"""
# Resultados del cierre de VitiAlert

Fecha de corte: **28 de octubre de 2026, 16:00 (UTC-3)**. Nodo 1. Horizonte de pronóstico: 24 horas. La unidad es la escala relativa de la sonda de suelo; no es contenido volumétrico de agua calibrado.

## Resultado que podemos defender

Se obtuvo un prototipo que recibe, conserva y audita telemetría, integra fuentes externas y ejecuta un experimento predictivo reproducible. Gradient Boosting superó a persistencia en el promedio del bloque fijo. **La precisión absoluta y la evidencia del aporte multimodal son insuficientes para declarar validada una herramienta operativa de riego.**

{table_metrics(m)}

Prueba sobre **55 de 72 orígenes horarios posibles**. Se reconstruyó retrospectivamente un ajuste con corte de entrenamiento al **24/10 a las 16:00**, con **74 pares** y etiquetas conocidas hasta las 15:00 de ese día. Se evaluaron orígenes del 24/10 a las 17:00 al 27/10 a las 16:00, con respuestas observadas hasta el corte del 28/10. Los huecos no se completaron. No hubo reajustes dentro de este bloque ni registro prospectivo de estas predicciones durante la campaña.

La reducción de MAE frente a persistencia fue **{n(m['model']['mae_improvement_pct'],2)}%**. La habilidad basada en RMSE fue **{n(m['model']['rmse_skill'],4)}**, equivalente a una reducción de RMSE del **{n(100*m['model']['rmse_skill'],2)}%**. R² = **{n(m['model']['r2'],3)}** señala una capacidad explicativa deficiente en este bloque. Superar una referencia que también falla mucho no convierte el pronóstico en preciso. El MAE es un error medio de la escala del sensor, no un porcentaje de acierto.

![Comparación en el mismo período](graficos/03_comparacion_mismo_periodo.png)

## La comparación con el 22 de octubre

| Mismo protocolo de origen móvil y seis variables de suelo/horario | Corte 22/10 | Corte 28/10 |
|---|---:|---:|
| Lecturas de octubre | {n(old['october_records'])} | {n(s['october_readings'])} |
| Días con al menos una lectura | {old['october_days_with_records']} | {int(daily.lecturas.gt(0).sum())} |
| Horas de suelo con cobertura suficiente | {old['usable_hours']} | {s['usable_hours']} |
| Pares a 24 horas | {old['eligible_pairs']} | {s['eligible_pairs']} |
| Pronósticos retrospectivos | {old['evaluation_rows']} | {w['n']} |
| Fechas objetivo evaluadas | {old['evaluation_target_days']} | {w['target_days']} |
| MAE del algoritmo | {n(old['metrics']['gradient_boosting']['mae_pp'],2)} | {n(core_current['mae_pp'],2)} |
| MAE de persistencia | {n(old['metrics']['persistence']['mae_pp'],2)} | {n(w['persistence']['mae_pp'],2)} |
| R² del algoritmo | {n(old['metrics']['gradient_boosting']['r2'],3)} | {n(core_current['r2'],3)} |

El error absoluto del análisis ampliado aumentó. **Los conjuntos son distintos:** el corte anterior tenía veinte casos estables del 13/10 y solo dos casos del 20/10. El nuevo corte incorpora variaciones de suelo mucho mayores y más jornadas. La referencia de persistencia también empeora, de {n(old['metrics']['persistence']['mae_pp'],2)} a {n(w['persistence']['mae_pp'],2)} puntos. No es correcto atribuir el aumento del error a que se incorporó o faltó un sensor.

Para controlar la diferencia de dificultad, se volvió a aplicar el artefacto anterior a las mismas 55 horas del bloque nuevo. El MAE pasó de **{n(m['old_model']['mae_pp'],2)} a {n(m['model']['mae_pp'],2)} puntos**, una mejora de **{n(fair_gain,2)}%**. Esta es la comparación directa más útil entre versiones. El entrenamiento del bloque pasó de 70 a 74 pares; el artefacto final usa 153, pero no se evalúa sobre datos que ya utilizó para ajustarse.

La evaluación de origen móvil, que se reajusta a medida que nuevas respuestas se conocen, obtuvo con integración **MAE {n(w['model']['mae_pp'],2)}**, **RMSE {n(w['model']['rmse_pp'],2)}** y **R² {n(w['model']['r2'],3)}** sobre 105 pronósticos en ocho fechas. Es un resultado complementario de una estrategia adaptativa; no es la prueba de un único modelo congelado ni la métrica independiente del artefacto final de 153 pares.

## Por qué los errores siguen siendo grandes

El entrenamiento congelado conocía respuestas entre **{n(s['fixed_training']['target_min'],2)} y {n(s['fixed_training']['target_max'],2)}**. La prueba llega a **{n(m['model']['target_max'],2)}**. Además, en la maqueta se moja la tierra para provocar cortes y no hay una bitácora completa con hora y cantidad de cada intervención. Un pronóstico a 24 horas no conoce esas futuras acciones manuales.

Esto describe cambios de régimen y factores de entrada ausentes. Es una explicación compatible con los datos y el montaje informado; no demuestra qué proporción exacta del error causó cada intervención ni descarta problemas de calibración o de contacto de la sonda.

| Fecha de la respuesta | Casos | MAE modelo | MAE persistencia |
|---|---:|---:|---:|
{days_table}

El 28/10 el modelo congelado fue peor que persistencia. Si se omite el 27/10 como diagnóstico de sensibilidad, la habilidad RMSE baja de 0,0882 a aproximadamente **0,0061**. La mejora global depende mucho de esa jornada. No se eliminó ningún día de la evaluación publicada. Cuatro fechas no permiten asegurar estabilidad estadística; no se calculó un intervalo de confianza como si las 55 horas fueran independientes.

![Observación y pronósticos del bloque](graficos/02_prueba_temporal.png)

## Qué cambió en el caudal y en el DHT22

Se comparan las lecturas de octubre hasta el corte anterior y las posteriores, no meses distintos.

| Evidencia de captura | Hasta el corte del 22/10 | Después, hasta el 28/10 a las 16:00 |
|---|---:|---:|
| Lecturas | {n(a['lecturas'])} | {n(b['lecturas'])} |
| DHT con temperatura y humedad | {n(a['dht_completo'])} ({n(a['dht_disponible_pct'],2)}%) | {n(b['dht_completo'])} ({n(b['dht_disponible_pct'],2)}%) |
| Lecturas con caudal mayor a 0,2 L/min | {a['caudal_mayor_02']} | {b['caudal_mayor_02']} |
| Eventos cerrados con volumen positivo y sin advertencia del backend | {old_event['ciclos_sin_advertencia_con_volumen']} | {new_event['ciclos_sin_advertencia_con_volumen']} |
| Descensos observados del contador | {a['caidas_contador']} | {b['caidas_contador']} |

**El caudalímetro ahora aporta información de circulación:** los 333 ciclos reportan en conjunto **576,83 L de incrementos del contador**; la mediana por ciclo es **1,54 L** y la mediana de duración es **17 segundos**. Estos son valores reportados por el sistema, sin calibración independiente. Hay ciclos con valores atípicos: el máximo reportado es {n(water['max_reported_counter_delta_l'],2)} L y {water['closed_positive_over_2l']} ciclos superan 2 L. Están señalados para revisión en `datos/eventos_para_revision.csv`.

El agua recircula. Por eso esos litros no equivalen a agua consumida, dosis que absorbió el suelo ni ahorro. El caudal no entra como dosis en el modelo. Se registraron **334 lecturas posteriores al 22/10 con caudal > 0,2 y válvula cerrada**, y **16 eventos posteriores con advertencia de reinicio**. Pueden influir transiciones de estado, el intervalo de cálculo del flujo, retrasos o fallas; el log por sí solo no confirma una fuga. Los 48 descensos del contador no se atribuyeron todos a reinicios manuales.

**El DHT sí tuvo lecturas válidas.** El 28/10 estuvo presente en **1.690 de 1.690 lecturas** hasta el corte. En la serie completa aporta **42 horas** con cobertura suficiente, pero solo **3 pares supervisados a 24 horas** incluyen DHT en el origen. El entrenamiento congelado contiene uno y la prueba otro. La mejora del último día no puede convertirse en entrada de un pronóstico emitido el día anterior. Añadir DHT al contrato de suelo produjo exactamente el mismo MAE del bloque ({n(m['soil_plus_dht']['mae_pp'],2)}). No se demostró un aporte predictivo del DHT con esta campaña.

## Qué aportaron meteorología y satélite

Se descargaron **86 registros meteorológicos de 50 fechas** y **12 capturas satelitales**. Son contexto de la ubicación configurada, no mediciones del microclima de la maqueta. Se usaron solo versiones que, según sus timestamps, ya estaban disponibles en cada origen; el día en curso no se usa como resumen conocido. La meteorología admitida puede tener hasta diez días de antigüedad; su fecha efectiva queda en la tabla horaria.

Los índices Sentinel NDVI y NDMI repiten respectivamente **0,2354 y -0,0115** cuando están presentes. En el entrenamiento del bloque tienen un solo valor numérico distinto: las filas repetidas no son nuevos escenarios de vegetación. Las cuatro variables GOES no tienen valores de entrenamiento utilizables en ese bloque y se omitieron al ajustar, aunque existan capturas posteriores. La bandera global VALID del servicio no garantiza que todos los campos estén presentes.

Con las seis variables de suelo/horario, el MAE fijo fue **{n(m['soil_only']['mae_pp'],3)}**; con la integración disponible fue **{n(m['model']['mae_pp'],3)}**. La diferencia es apenas **{n(external_gain,3)} puntos ({n(external_pct,2)}%)**. En origen móvil, la versión integrada fue ligeramente peor que suelo: **{n(w['model']['mae_pp'],3)} frente a {n(w['soil_only']['mae_pp'],3)}**. Esto no demuestra una mejora multimodal consistente ni una contribución causal del satélite.

## Conclusión sobre la hipótesis

El borrador v4, página 8, propone que integrar IoT, meteorología y satélite permite predecir humedad a 24 horas con menor error que persistencia.

**{verdict}**

1. El criterio numérico de menor error se cumple en el bloque: MAE 39,73 frente a 49,88 y habilidad RMSE positiva.
2. La precisión absoluta es baja y la mejora no es uniforme entre días.
3. El aporte adicional de la integración respecto de suelo es pequeño y cambia de signo según el esquema de evaluación.
4. La disponibilidad del DHT y la variación satelital no alcanzan para demostrar su contribución.
5. El circuito permite estudiar circulación y control, pero no cuantificar ahorro ni consumo neto de agua.

La formulación defendible es: **se demostró la viabilidad del sistema y una mejora relativa de pronóstico en esta maqueta; la hipótesis general queda apoyada de forma parcial y requiere más validación para considerarse confirmada.** No corresponde afirmar ahorro ni precisión de campo. Tampoco se puede concluir que la integración nunca vaya a funcionar: esta campaña no alcanza para establecerlo.

## Artefacto final y continuidad

El artefacto final se entrenó con **153 pares**, conservando los parámetros fijados. Está guardado con sus variables, dependencias, origen y hashes. No se desplegó ni se conectó a la válvula. Sus datos de ajuste no se reutilizaron como prueba independiente.

Las mejoras prioritarias son: calibrar suelo y caudal; medir dosis realmente aplicada al sustrato; registrar las intervenciones con hora; completar ciclos húmedo-seco repetibles; capturar DHT durante varios días completos; conservar las versiones meteorológicas e identificar las imágenes satelitales efectivas; y probar un candidato congelado en un período posterior. Estas condiciones permiten estudiar eficiencia hídrica, además de circulación.

Fuentes: respaldo PostgreSQL y respuestas GET conservados en esta carpeta; modelo y resultados del 22/10; registro de intervenciones del 24/10; borrador de tesis v4, páginas 8 y 29. Método de evaluación: [validación de series temporales](https://otexts.com/fpp3/toolbox.html#time-series-cross-validation). Estimador y tratamiento de faltantes: [documentación oficial de HistGradientBoostingRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html).
""")
    write("02_DEFENSA_ORAL.md", f"""
# Defensa oral del cierre

## Explicación de dos minutos

> Desarrollamos una maqueta que recibe y guarda datos del suelo, del ambiente y del circuito de riego. Al cerrar la campaña, conservamos 21.106 lecturas de octubre. Luego aplicamos controles de cobertura: las lecturas se redujeron a 233 horas utilizables y 153 ejemplos de humedad actual con su respuesta observada a 24 horas.
>
> Usamos un modelo de Gradient Boosting porque permite representar relaciones no lineales en datos tabulares y trabajar con faltantes. Lo comparamos con una regla sencilla: que mañana el suelo estará igual que hoy. Esa regla es persistencia.
>
> En la prueba temporal fija, el modelo tuvo un error medio de 39,73 puntos y persistencia de 49,88. La mejora relativa fue del 20,35%. Sin embargo, el error absoluto sigue siendo alto y hubo días en los que el modelo fue peor. Por eso hablamos de apoyo parcial a la hipótesis y de un prototipo experimental, con precisión operativa todavía no demostrada.
>
> El caudalímetro mejoró la observación del circuito, pero el agua recircula y no tenemos una medición independiente de consumo o dosis. El DHT tuvo lecturas válidas, aunque pocas coincidieron con ejemplos completos a 24 horas. El aporte adicional de las fuentes externas fue pequeño e inestable.
>
> El resultado principal es una plataforma funcional y una evaluación trazable que permite identificar qué falta para llegar a una herramienta confiable de gestión hídrica. El modelo queda entrenado y conservado; no acciona el riego.

## Respuestas breves a preguntas del tribunal

**¿La hipótesis se confirmó?**

El contraste numérico fue favorable frente a persistencia en este bloque. La conclusión general es apoyo parcial, sin confirmación robusta: la precisión absoluta es baja, solo hay cuatro fechas de prueba y no se aisló una mejora estable de la integración multimodal.

**¿Es un 79,65% de acierto?**

No. La mejora del 20,35% es una reducción relativa del error respecto de una referencia. MAE 39,73 significa una distancia media de 39,73 puntos entre el pronóstico y la lectura del sensor.

**¿Por qué antes el error era 3,20 y ahora es mucho mayor?**

Antes había 22 pronósticos, veinte en un día bastante estable. Ahora entraron cambios de suelo mayores y más días. Para comparar justamente, aplicamos el modelo viejo al mismo bloque nuevo: dio 40,43 puntos y el reentrenado 39,73. Mejoró poco. No atribuimos ese cambio a un sensor sin una prueba controlada.

**¿Para qué sirvió arreglar el caudalímetro?**

Permitió registrar circulación y reconstruir ciclos con incrementos del contador. Hay 333 ciclos cerrados con volumen positivo sin advertencia del backend después del corte anterior. Es una mejora de instrumentación; no prueba un ahorro de agua ni entra como dosis del suelo en el modelo.

**¿Cuánta agua ahorraron?**

No se midió un ahorro. El agua recircula y falta un volumen de entrada o consumo independiente, además de una comparación controlada entre estrategias de riego.

**¿Entonces los 576,83 litros son consumo?**

Son la suma reportada de incrementos del contador en esos ciclos. La mediana es 1,54 L por ciclo. No se validaron contra un patrón físico y pueden incluir anomalías. El mismo agua puede pasar varias veces por el sensor.

**¿Se descartó todo el DHT?**

No. Se conservaron las lecturas. Hay 42 horas con cobertura suficiente, pero solo tres pares de entrenamiento completo a 24 horas tienen DHT en el origen. Recuperarlo el último día mejora la captura, pero no genera respuestas futuras ya conocidas.

**¿Por qué no se predijo el aumento de humedad?**

Hubo estados altos que no aparecían como respuestas en el entrenamiento congelado, y el suelo recibió intervenciones manuales sin una agenda completa como entrada del modelo. Esa explicación es compatible con la evidencia. No afirmamos haber identificado la causa exacta de cada salto.

**¿Por qué Gradient Boosting y no otros algoritmos?**

El objetivo es una variable continua y los datos son tabulares, escasos e incompletos. Gradient Boosting ofrece relaciones no lineales y control de complejidad. Un clasificador respondería otra pregunta; una red profunda necesitaría más diversidad de ejemplos y decisiones de ajuste. No necesitamos afirmar que se probaron todas las alternativas para justificar este punto de partida.

**¿Hay varios modelos?**

Hay una familia elegida: Gradient Boosting. Se guardaron ajustes de fechas diferentes y se comparó el mismo algoritmo con conjuntos de variables diferentes para entender el aporte de las entradas. Persistencia es una regla de referencia sin entrenamiento.

**¿El artefacto final de 153 pares tiene el error de 39,73?**

Ese error corresponde al ajuste congelado con 74 pares antes de la prueba. El artefacto final usa los 153 pares conocidos al cierre y necesita datos posteriores para una evaluación independiente. No le atribuimos el error de un experimento distinto.

**¿Se mezcló información del futuro?**

Los objetivos están exactamente a 24 horas. En cada ajuste se exigieron respuestas ya conocidas; los huecos permanecieron ausentes. La meteorología del día en curso no se usó como un resumen conocido. Los timestamps y los controles están publicados para revisarlos.

**¿Por qué tener muchos datos no alcanzó?**

Muchas lecturas cercanas describen el mismo estado. Para el modelo cuentan las horas cubiertas, sus respuestas futuras y la variedad de ciclos. El histórico climático no reemplaza las etiquetas faltantes del suelo de esta maqueta. Los índices Sentinel repetidos tampoco son ejemplos independientes de vegetación.

**¿El trabajo sirve aunque el modelo no sea preciso?**

Sirve para demostrar la adquisición, la integración, la auditoría y una evaluación temporal reproducible. Su alcance predictivo quedó delimitado con datos. El avance no equivale todavía a una recomendación agronómica validada.

**¿Qué harían primero para mejorarlo?**

Mediríamos y registraríamos la dosis realmente aplicada al suelo, con calibración y horarios de intervención. Después repetiríamos ciclos de riego y secado, manteniendo el DHT continuo y reservando un período posterior para evaluar un candidato congelado.

## Expresiones que conviene evitar

- “Logramos ahorrar 576 litros”: no se midió ahorro.
- “El modelo tiene 80% de precisión”: esa cifra no se calculó.
- “La bomba/DHT mejoró el modelo en 20%”: no hay aislamiento causal de ese efecto.
- “El satélite confirmó el estado de la maqueta”: su escala espacial y sus valores disponibles no permiten esa afirmación.
- “Validamos el modelo final con 153 datos”: son sus pares de ajuste; la prueba congelada es otro artefacto.

Conviene defender cifras, alcance y limitaciones con la misma claridad.
""")
    write("03_METODO_Y_REPRODUCCION.md", f"""
# Método, fuentes y reproducción

## Contrato del experimento

- Nodo externo: `1`.
- Corte inclusivo: `2026-10-28T16:00:00-03:00` = `2026-10-28T19:00:00Z`.
- Modelo: `HistGradientBoostingRegressor`, misma familia y parámetros del análisis anterior.
- Objetivo: media horaria observada de humedad del suelo, a exactamente 24 horas del origen.
- Escala: relativa de la sonda; no VWC ni potencial hídrico calibrados.
- Ningún componente de este análisis envía órdenes al dispositivo.

## Respaldo y preservación

Se descargó un archivo nativo PostgreSQL mediante `pg_dump`, en modo de conexión de solo lectura, y se restauró en una instancia local aislada. La restauración recuperó 21.227 lecturas, 483 eventos, 86 registros de meteorología, 12 capturas satelitales, un nodo y cinco migraciones Flyway. El archivo completo es una copia consistente al momento de descarga, aproximadamente 16:25; no es una recuperación PITR de las 16:00.

Desde esa copia local se excluyeron las 47 lecturas posteriores al corte y se generó `respaldo_bd/vitialert_corte_2026-10-28_1600.dump`. Este segundo archivo también se restauró y verificó: 21.180 lecturas; máximo timestamp 15:59:58.027751 de Argentina. No había eventos atravesando el corte; no se debió reconstruir un cierre futuro. No se alteró producción. Las versiones meteorológicas sobreescritas antes de la descarga no pueden recuperarse con este procedimiento.

La API devolvió exactamente las mismas 21.180 lecturas al corte. Se compararon IDs y valores de suelo, DHT, caudal y contador con PostgreSQL. Se recuperaron 828 contextos de adquisición almacenados: el backend actual no los devuelve en el DTO. No se detectaron filas explícitamente marcadas como ENSAYO en este snapshot. La ausencia de contexto en el resto no prueba ausencia de intervención: se conserva el registro del montaje.

## Preparación de suelo y DHT

Se mantuvo el protocolo anterior: suelo estrictamente entre 0 y 100, seis o más muestras por hora, al menos 45 minutos cubiertos y hueco interno máximo de diez minutos. Las horas representan el intervalo `(t-1h, t]`; no incluyen datos posteriores al origen. Se excluyeron once lecturas de suelo ausentes o extremas con ese criterio. Las fuentes originales permanecen intactas.

Los rezagos se resuelven por timestamp a -6 y -24 horas; una hora ausente no se sustituye por la fila anterior. La media móvil requiere 24 horas completas. Las etiquetas se unen a `t+24h` exacto y solo se conservan cuando ese resultado se observó dentro del corte.

Para el DHT se aplicó cobertura equivalente, rango de temperatura -40 a 80 °C y humedad ambiental 0 a 100. Sus ausencias no eliminan suelo válido ni se sustituyen por cero. Hay 42 horas con DHT suficiente, tres pares con DHT, un par en el entrenamiento congelado y uno en los orígenes de la prueba.

## Fuentes externas y alineación

La meteorología procede del punto configurado en San Juan y está agregada por día local. Se conserva cada fuente por separado en el respaldo. Para cada origen se selecciona el día más reciente anterior al día local del origen, cuya versión actual ya existía según `max(created_at, updated_at)`. En empate se prefiere ERA5. Se permite una antigüedad máxima de diez días, informada en `weather_age_days` y `weather_observation_date`.

Esto es una aproximación conservadora de disponibilidad usando la versión conservada. Si una fila fue actualizada después de un origen, no se usa retroactivamente su valor actual. No se reconstruyen versiones perdidas ni se descargan ahora valores históricos para fingir que estaban disponibles antes. La falta de archivo de vintages limita el contraste multimodal.

Para satélite se exige disponibilidad del timestamp de respuesta más cinco minutos y observación no futura. GOES se considera vigente por seis horas y Sentinel por catorce días. `retrieved_at` procede del timestamp de respuesta de VitiAI; no es una columna independiente de recepción en PostgreSQL. El margen es conservador y la falta de una marca de ingesta separada queda como limitación. Los índices repetidos no se cuentan como imágenes físicamente independientes. El procesamiento Sentinel local usa un mosaico de un intervalo con selección por nubosidad; la fecha de catálogo no garantiza que todos los píxeles provengan de esa escena.

El viento de la maqueta fue accionado con un motor y tuvo cambios de firmware y campos ausentes. No se usa como viento natural calibrado. La meteorología externa contiene viento del proveedor como contexto regional; es otra fuente y otra escala. El caudal recirculado no se convierte en dosis al suelo.

## Modelo y configuraciones comparadas

Se eligió una sola familia de regresión. Se compararon sus entradas: seis variables de suelo/horario; esas seis más DHT; e integración disponible con meteorología y satélite. Los parámetros y las filas de prueba son iguales. La comparación de entradas es una ablación para revisar el aporte de información; no es una búsqueda de cinco algoritmos ni selección por una prueba repetida de hiperparámetros.

Parámetros conservados:

```json
{json.dumps(s['final_model']['params'],ensure_ascii=False,indent=2)}
```

El estimador admite valores ausentes. Una columna completamente vacía se omite en ese ajuste, usando solamente el entrenamiento. Las cuatro columnas GOES se omiten en el bloque fijo por esa razón. El artefacto final tiene sus propias columnas disponibles al cierre.

La persistencia no se ajusta: `pronóstico(t+24h) = humedad(t)`. Se conserva porque cualquier método complejo debe demostrar utilidad frente a una regla sencilla. No se entrenaron familias adicionales para este cierre.

## Validación y unidades

El bloque fijo reconstruye un ajuste con corte de entrenamiento al 24/10 a las 16:00. Entrena con 74 pares cuyas respuestas son estrictamente anteriores a ese momento. Evalúa 55 orígenes de los últimos 72 posibles. Las respuestas corresponden a cuatro fechas del 25 al 28/10. Es retrospectivo: tanto el ajuste como las predicciones se calcularon durante este análisis del 28/10, no se presentan como pronósticos registrados durante la operación.

También se repitió el protocolo de origen móvil del análisis anterior: cada ajuste usa solo respuestas anteriores a su origen y al menos 24 pares. Sus 105 resultados no son réplicas independientes y el modelo cambia con el tiempo. Las 22 predicciones antiguas del contrato de suelo se reprodujeron numéricamente.

- `MAE = media(abs(pronóstico - observado))`, en puntos.
- `RMSE = raíz(media(error²))`, en puntos.
- `R² = 1 - suma(error²)/suma((observado-media_observado)²)`.
- `Habilidad_RMSE = 1 - RMSE_modelo/RMSE_persistencia`.
- `Mejora_MAE_% = 100 × (1 - MAE_modelo/MAE_persistencia)`.

Un R² negativo describe una mala explicación de la variabilidad respecto de una media calculada sobre el conjunto evaluado. Esa media no se utiliza como pronóstico desplegable, porque se calcula con respuestas de prueba. El modelo puede superar persistencia y aun así tener R² negativo.

Se contrastaron MAE, RMSE y R² con scikit-learn. No se estimó un intervalo inferencial para cuatro días de prueba fija. El remuestreo por días de los ocho días de origen móvil es un diagnóstico exploratorio, no prueba prospectiva ni certificado de independencia.

## Reproducción offline

Python utilizado: entorno 3.12. Las versiones exactas están en `codigo/requirements-lock.txt`. El modelo está serializado con joblib y debe abrirse con dependencias compatibles.

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r codigo/requirements-lock.txt
./.venv/Scripts/python.exe -m unittest discover -s codigo -p "test_*.py" -v
./.venv/Scripts/python.exe codigo/evaluar_cierre.py
./.venv/Scripts/python.exe codigo/predecir_cierre.py
./.venv/Scripts/python.exe codigo/generar_informes.py
```

La evaluación verifica hashes de las respuestas y las tablas. Reejecutar sobrescribe únicamente los resultados de esta copia de la carpeta; para preservar la entrega sellada, reproducir en otra carpeta. No hace falta conectarse a Render. El ejemplo de inferencia para el 29/10 es una demostración calculada después del corte, sin etiqueta observada y excluida de las métricas.

Los scripts de respaldo son herramientas de adquisición, no requisitos del entrenamiento offline. La base local de verificación quedó detenida. Las credenciales temporales se retiraron de la entrega y del archivo temporal utilizado.

Referencias: [PostgreSQL, pg_dump](https://www.postgresql.org/docs/18/app-pgdump.html); [scikit-learn, HistGradientBoostingRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html); [Forecasting: Principles and Practice, validación temporal](https://otexts.com/fpp3/toolbox.html#time-series-cross-validation). La documentación respalda el método; los resultados numéricos provienen de las tablas de esta entrega.
""")
    write("04_BITACORA_DEL_CIERRE.md", """
# Bitácora del cierre

28/10/2026. Corte analítico: 16:00 de Argentina.

| Acción | Evidencia conservada |
|---|---|
| Fijar corte y plan de evaluación antes de calcular métricas | `codigo/PROTOCOLO_CIERRE.md` |
| Descargar telemetría y eventos por GET con paginación estable | `fuentes_api/MANIFIESTO_FUENTES.json` y respuestas originales |
| Descargar respaldo nativo de Render con conexión de solo lectura | `respaldo_bd/vitialert_respaldo_nativo_2026-10-28.dump` |
| Restaurar y exportar todas las tablas en PostgreSQL local | `respaldo_bd/MANIFIESTO_RESPALDO.json` |
| Crear y restaurar el respaldo filtrado al corte en la copia local | `respaldo_bd/vitialert_corte_2026-10-28_1600.dump` |
| Reconciliar lecturas API y base; recuperar contexto almacenado | `RESUMEN_RESULTADOS.json`, sección `acquisition_audit` |
| Auditar disponibilidad, eventos, contador y alertas | `datos/calidad_diaria.csv`, `calidad_por_etapa.json`, `eventos_auditados.csv` |
| Repetir evaluación anterior y comparar el artefacto viejo sobre las mismas horas | `referencia_22_octubre`, `datos/predicciones_bloque_fijo.csv` |
| Validar horizonte, cobertura y disponibilidad temporal | `codigo/test_cierre.py`, `verificacion` |
| Entrenar y verificar recarga del artefacto final | `modelo`, manifiestos y hashes |
| Preparar conclusiones, defensa y textos de memoria | Documentos principales de esta carpeta |

Se mantuvieron los parámetros del modelo anterior. Se usó una familia de regresión y se compararon conjuntos de entradas. No se ajustaron hiperparámetros para mejorar el resultado de la prueba.

El respaldo integral conserva 47 lecturas posteriores al corte por haber sido descargado a las 16:25. No entran en los resultados; el respaldo filtrado conserva 21.180. La eliminación de esas filas se hizo solo en una base local creada para verificar la copia. Render no recibió DELETE, UPDATE ni migraciones de este cierre.

La primera descarga del archivo nativo fue correcta. La herramienta de inicio de PostgreSQL local retuvo una salida de proceso en Windows; se recuperó la comprobación usando la misma instancia aislada. La restauración completa y la del corte finalizaron correctamente. Ambas verificaciones dejaron el servidor local detenido. No se modificó el contenido del respaldo nativo para resolver ese problema.

No se modificaron GitHub, el backend desplegado, sus variables, los secretos de Actions, los workflows, el firmware ni los actuadores. La carpeta pública existente tenía cambios locales previos; no se mezclaron con este cierre. El modelo y los resultados del 22/10 permanecieron intactos y fueron copiados como referencia.

El registro de intervenciones conserva los dos reinicios manuales informados y la condición de agua recirculada. No se inventaron horarios ni cantidades para las intervenciones no registradas. Los cambios de estado no se atribuyeron automáticamente a riego físico o fallas de hardware sin evidencia independiente.
""")
    write("05_TEXTOS_PARA_LA_MEMORIA.md", f"""
# Textos propuestos para actualizar la memoria

Estos párrafos describen el cierre real. Deben revisarse junto con el resto de la tesis para mantener consistencia de fechas, unidades y alcance. El borrador original no fue sobrescrito.

## Resultados de captura

La campaña se cerró el 28 de octubre de 2026 a las 16:00 (Argentina). Se conservaron 21.106 lecturas de octubre del nodo 1. La última lectura incluida fue recibida a las 15:59:58. La preparación temporal, con criterios de cobertura y continuidad, produjo 233 horas utilizables de humedad de suelo y 153 pares con objetivo observado a exactamente 24 horas. Los días sin transmisión permanecieron ausentes.

La incorporación de circulación mediante bomba permitió registrar 333 eventos posteriores al corte anterior con volumen positivo y sin advertencias del backend. La mediana del incremento reportado por ciclo fue de 1,54 L y la mediana de duración, 17 segundos. Dado que el circuito recircula agua y no se realizó una calibración independiente, estos valores se interpretan como incrementos del contador del circuito, sin equivalencia demostrada con consumo neto ni dosis aplicada al sustrato.

El DHT22 presentó funcionamiento intermitente. Su disponibilidad conjunta de temperatura y humedad aumentó de 14,71% a 22,80% al comparar las etapas anterior y posterior al corte del 22/10. El último día estuvo presente en las 1.690 lecturas recibidas hasta el cierre. No obstante, solo tres pares supervisados incluyeron DHT con cobertura horaria suficiente en el origen, lo que limitó la evaluación de su aporte predictivo.

## Algoritmo elegido

Se utilizó regresión por Gradient Boosting, implementada con HistGradientBoostingRegressor. La elección responde a la estructura tabular de los datos, al carácter continuo del objetivo y a la necesidad de representar relaciones no lineales y tratar valores ausentes. Se mantuvo una configuración de baja profundidad y regularización fijada en el análisis anterior. No se requiere comparar exhaustivamente otras familias para justificar este punto de partida; los clasificadores responderían una pregunta diferente y modelos de mayor complejidad exigirían más diversidad de ejemplos y decisiones de ajuste.

## Resultados predictivos

La evaluación principal reconstruyó retrospectivamente un ajuste con corte de entrenamiento al 24/10 a las 16:00, con 74 pares y etiquetas anteriores a ese momento. No existió un registro prospectivo de esas predicciones durante la campaña. Sobre 55 pronósticos a 24 horas, distribuidos en cuatro fechas de respuesta, el modelo con integración disponible obtuvo MAE de 39,73 puntos, RMSE de 46,70 y R² de -2,345. La persistencia obtuvo MAE de 49,88 y RMSE de 51,21. La reducción relativa de MAE fue de 20,35% y la habilidad RMSE de 0,0882. Estas métricas no representan porcentaje de acierto y no acreditan precisión operativa.

El artefacto conservado del 22/10, aplicado a exactamente el mismo bloque, obtuvo MAE de 40,43 puntos. La mejora directa del nuevo ajuste fue de 1,72%. Las métricas históricas de 3,20 puntos del corte anterior correspondían a otro período: veinte de sus veintidós pronósticos pertenecían a una jornada estable. Por ello no se interpretó el aumento del error absoluto como efecto causal de incorporar o de perder un sensor.

La evaluación complementaria de origen móvil, que incorpora nuevas etiquetas a medida que se conocen, obtuvo MAE de 18,19, RMSE de 28,40 y R² de -0,015 sobre 105 pronósticos en ocho fechas. Su referencia de persistencia obtuvo MAE de 29,91. Esta evaluación describe una estrategia que se reajusta; no se confunde con la de un único modelo fijo ni con una validación independiente del artefacto final.

## Discusión y contraste de la hipótesis

La hipótesis recibió apoyo parcial. El contraste descriptivo frente a persistencia fue favorable en el bloque temporal, pero la magnitud absoluta del error, su variación entre días y la escasa diversidad de fuentes adicionales impiden declararla confirmada de manera robusta. La versión de suelo obtuvo MAE de 39,836 frente a 39,731 con integración, una diferencia de 0,105 puntos. La diferencia no fue consistente entre esquemas de evaluación. El DHT aportó un solo par al entrenamiento congelado; los índices Sentinel presentes tuvieron un único valor numérico distinto y las variables GOES no contaron con ejemplos utilizables para ese ajuste.

Los cambios de humedad de la segunda etapa incluyeron estados fuera del rango de respuestas conocido al entrenar el modelo congelado. El montaje también recibió intervenciones manuales sin una agenda cuantificada que pudiera utilizarse como entrada del pronóstico. Ambos factores son compatibles con las limitaciones observadas, sin que el diseño permita aislar su contribución causal al error.

## Conclusión

El trabajo demostró la viabilidad de una plataforma de adquisición, persistencia, integración y evaluación temporal para una maqueta de riego. El modelo superó a persistencia en el promedio del bloque estudiado, con errores que todavía impiden considerarlo una herramienta precisa para decidir riego. No se demostró ahorro de agua, calibración agronómica ni generalización a un viñedo. La hipótesis general queda apoyada parcialmente, con validación adicional necesaria.

El artefacto final se ajustó con los 153 pares conocidos al cierre y se conservó sin desplegarlo en los actuadores. Su evaluación independiente requiere observaciones posteriores. Las líneas prioritarias son la medición contrastada de la dosis aplicada al suelo, el registro de intervenciones, una captura ambiental continua, la identificación de versiones de fuentes externas y la evaluación de un candidato congelado en una campaña posterior.

## Consistencia con el borrador v4

- Actualizar los apartados de resultados y conclusiones que todavía contienen “COMPLETAR”.
- Mantener la hipótesis original y distinguir su contraste numérico del alcance de confirmación.
- Describir el caudal como circulación reportada en el montaje recirculante, donde corresponda.
- Corregir cualquier redacción que dé por implementado el mismo pipeline de variables en backend e inferencia: este cierre incorpora un pipeline offline reproducible; su integración operativa en el servidor no se realizó.
- Evitar llamar “validación prospectiva” al bloque calculado retrospectivamente.
- Distinguir el modelo congelado de 74 pares del artefacto final de 153.
- No presentar la mejora frente a persistencia como exactitud, porcentaje de agua ahorrada ni eficiencia agronómica.
""")
    packages = list(s["packages"]) + ["scipy", "threadpoolctl", "contourpy", "cycler", "fonttools", "kiwisolver", "packaging", "pillow", "pyparsing", "python-dateutil", "six", "tzdata"]
    write("codigo/requirements-lock.txt", "\n".join(f"{k}=={importlib.metadata.version(k)}" for k in packages))
    write("codigo/requirements-informe.txt", "reportlab==4.4.9")
    print("Documentos de cierre generados; cifras tomadas de los resultados conservados.")


if __name__ == "__main__":
    main()
