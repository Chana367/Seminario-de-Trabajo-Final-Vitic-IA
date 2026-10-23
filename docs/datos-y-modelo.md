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

## Modelo vigente

`analysis` utiliza solo suelo medido e historial horario. La elección de Gradient Boosting es una hipótesis de trabajo para relaciones no lineales con una serie pequeña. La precisión se verifica con evaluación temporal, no por cantidad de registros descargados.

La incorporación de lluvia, evapotranspiración, temperatura, litros o índices satelitales requiere alinear fuentes y conservar cuándo estaban disponibles. No usar información del día completo o capturas posteriores a la hora de predicción para explicar retrospectivamente una respuesta que aún no se conocía.

Los datos de prueba simulados en `tests` sirven para comprobar código. No son resultados experimentales. Los escenarios del constructor histórico tampoco se presentan como telemetría real.

## Conservación

Mantener originales inmutables, derivados separados y respaldos periódicos. El repositorio contiene herramientas, no bases de datos, datasets privados ni modelos binarios. Publicar datos o resultados requiere revisar privacidad, fuentes y licencias, y acompañarlos de su corte y método.
