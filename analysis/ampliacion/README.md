# Ampliación del análisis

Análisis realizado **después** de conocer el resultado del protocolo de cierre. Por eso se presenta como análisis de robustez y no como prueba confirmatoria. Usa los mismos 153 pares, las mismas reglas de disponibilidad temporal y, en el bloque fijo, exactamente las mismas 55 filas de prueba. No agrega ni modifica ninguna fila.

| Sección | Qué evalúa |
| --- | --- |
| Escalera de modelos | Persistencia y media del entrenamiento como referencias. Ridge, bosque aleatorio y *gradient boosting*, cada uno con objetivo de nivel y de variación (Δ a 24 h). |
| Cinco cortes | Congelamientos al 23/10 16:00, 24/10 16:00, 25/10 04:00, 25/10 16:00 y 26/10 16:00 (hora local), con ventanas de 72 h: 209 pronósticos en 15 combinaciones de corte y fecha. |
| Ablación | Suelo y hora; con DHT22; con meteorología; integración disponible. Para Ridge y GB, en el bloque fijo y en los cinco cortes. |
| Diagnóstico | Cambio de régimen entre entrenamiento y prueba, persistencia por régimen y error según la completitud de los predictores. |
| Interpolación | Huecos de 1 a 12 h interpolados **solo para construir predictores**. El objetivo sigue siendo medido. |
| Decisión de riego | Acierto en la decisión de regar por debajo del 30 % y curva de referencia MAE-acierto. |
| Simulación | 120 días sintéticos con balance hídrico anclado en la tasa de secado y la ET0 reales. **Datos sintéticos, declarados como tales.** |

Reglas propias de esta etapa:

- La intensidad α de Ridge se elige entre 0,1, 1, 3, 10, 30 y 100 por origen móvil **dentro** de cada entrenamiento, sin que intervenga la prueba.
- Ridge y el bosque aleatorio completan los rezagos faltantes con la mediana del entrenamiento dentro del pipeline. El objetivo nunca se completa.
- El *gradient boosting* conserva los hiperparámetros heredados del protocolo de cierre.

## Ejecución

Requiere las tablas `pares_24h.csv`, `serie_horaria.csv` y `meteorologia_original.csv` que genera el protocolo de cierre (por defecto se buscan en `../cierre/datos`). Usa el mismo entorno de Python 3.12 del cierre:

```powershell
python -m pip install -r ../cierre/codigo/requirements-lock.txt
python -B analisis_final.py ../cierre/datos salidas
python -B figuras.py ../cierre/datos salidas
python -B verificar_ampliacion.py salidas
```

`analisis_final.py` tarda menos de un minuto. Escribe `salidas/resultados.json`, las tablas auxiliares y el artefacto `modelo_ridge_variacion_153.joblib` (α = 30, 153 pares, **no desplegado**). `figuras.py` genera las figuras de la tesis en `salidas/figuras`. `verificar_ampliacion.py` compara los resultados con las cifras publicadas y termina con error si alguna no coincide. La carpeta `salidas` no se versiona.

Con las versiones de `requirements-lock.txt`, el artefacto Ridge reproduce el hash SHA-256 `fe91f281bdf389f274d1b18962cb736185f27bfd6cf1c8ffdf4325c52a265127`.

## Resultados publicados

| Esquema | Persistencia | Media del entrenamiento | Mejor modelo |
| --- | ---: | ---: | ---: |
| Bloque fijo (55 pronósticos) | 49,88 | 42,08 | Ridge sobre la variación: 32,85 |
| Cinco cortes (209 pronósticos) | 44,29 | 34,98 | Ridge sobre la variación: 30,24; gana en 13 de 15 combinaciones |

Las cifras son MAE en puntos de la escala relativa de la sonda.

- **Cambio de régimen:** la mediana del cambio a 24 h fue de 0,99 puntos en el entrenamiento del bloque fijo y de 51,04 en la prueba.
- **Ablación:** las fuentes externas no mejoraron la estimación. En Ridge, la meteorología la empeoró entre 8,4 y 10,7 puntos.
- **Decisión de riego:** el acierto fue del 39 % en los cinco cortes.
- **Simulación:** con datos sintéticos, Ridge obtuvo 1,55 contra 2,08 de la persistencia.

El error queda lejos de un nivel útil para decidir un riego.
