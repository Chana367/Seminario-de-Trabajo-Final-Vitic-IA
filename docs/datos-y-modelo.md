# Datos y modelo

## Tipos de registro

- Telemetría: mediciones reportadas por el ESP32, con timestamp de recepción y calidad.
- Eventos: intervalos derivados de estados de válvula, no una certificación de movimiento mecánico.
- Meteorología: observaciones o estimaciones de proveedores, con fuente y período propios.
- Satélite: fecha de captura, fecha de consulta, índices y calidad del área.
- Simulación: escenario de investigación identificado, separado de mediciones de campo.

Los valores ausentes no equivalen a cero. `MISSING` en temperatura no invalida automáticamente una lectura de suelo disponible. El cambio de bomba, posición de sonda o factor de calibración debe anotarse con fecha y hora.

## Medición del agua

El contador del nodo se acumula desde el arranque. Un reinicio no equivale a consumo negativo; los eventos afectados requieren interpretar sus advertencias. Contrastar el sensor con un recipiente y registrar el factor, configuración y período de validez de la calibración.

En un circuito recirculado el volumen que atraviesa el sensor no equivale a agua consumida. Para vincular riego y suelo, el agua debe llegar al mismo sustrato donde está la sonda.

## Modelos evaluados

`analysis` usa solo humedad de suelo medida e historial horario como entrada principal y la compara siempre con la persistencia. Sus tres etapas (corte del 22/10, protocolo de cierre y ampliación) se describen en [analysis/README.md](../analysis/README.md).

- **Protocolo de cierre:** un `HistGradientBoostingRegressor` con hiperparámetros heredados.
- **Ampliación:** agrega la escalera completa de modelos, con Ridge, bosque aleatorio y *gradient boosting*, cada uno con objetivo de nivel y de variación, y cinco cortes de congelamiento.
- **Artefactos:** se conservan dos, fuera de Git: el *gradient boosting* del cierre y Ridge sobre la variación (α = 30). Ninguno está desplegado.

Reglas de datos:

- **Objetivo:** es la media horaria medida a exactamente 24 horas y nunca se imputa.
- **Predictores faltantes:** los rezagos y la media móvil que faltan se completan solo dentro del pipeline, con la mediana del entrenamiento.
- **Interpolación:** completar huecos de la serie se ensayó únicamente para construir predictores y no modificó los resultados.
- **Fuentes externas:** incorporar lluvia, evapotranspiración, temperatura, litros o índices satelitales requiere alinear las fuentes y conservar cuándo estaban disponibles. No usar información del día completo ni capturas posteriores a la hora de predicción para explicar retrospectivamente una respuesta que aún no se conocía.
- **Viento de la maqueta:** lo acciona un motor, y desde el 24/10 el firmware multiplica la lectura del anemómetro por un factor de intensidad que sortea en cada ráfaga. No es una medición de viento natural y ningún modelo lo usa.

Los datos de prueba simulados en `tests` sirven para comprobar código y no son resultados experimentales. Tampoco se presentan como telemetría real los escenarios del constructor histórico ni la simulación de la ampliación, que está declarada como sintética.

## Conservación

Mantener originales inmutables, derivados separados y respaldos periódicos. El repositorio contiene herramientas, no bases de datos, datasets privados ni modelos binarios. Publicar datos o resultados requiere revisar privacidad, fuentes y licencias, y acompañarlos de su corte y método.
