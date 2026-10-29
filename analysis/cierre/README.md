# Protocolo de cierre (28/10/2026, 16:00)

Código del experimento de cierre de la campaña. El protocolo está en [PROTOCOLO_CIERRE.md](PROTOCOLO_CIERRE.md) y se fijó por escrito antes de calcular cualquier métrica. Las reglas de preparación del suelo que reutiliza están en [PROTOCOLO_ANTERIOR.md](PROTOCOLO_ANTERIOR.md).

- **Corte:** inclusivo al 28/10/2026 16:00 (Argentina), equivalente a 19:00 UTC. La última lectura incluida es de las 15:59:58.
- **Datos que conserva el paquete de cierre:** 21.180 lecturas, 233 horas de suelo utilizables y 153 pares con objetivo medido a exactamente 24 horas.
- **Modelo:** `HistGradientBoostingRegressor` con los hiperparámetros heredados del corte anterior. La persistencia es la referencia.
- **Bloque fijo:** ajuste congelado al 24/10 a las 16:00 con 74 pares, y 55 pronósticos en cuatro fechas de respuesta. Es una evaluación retrospectiva.
- **También calcula:** el origen móvil, la ablación de entradas (suelo y hora; con DHT22; integración disponible con meteorología y satélite) y la aplicación del artefacto del 22/10 a las mismas filas de prueba.
- **Resultado del protocolo:** MAE de 39,73 del *gradient boosting* con la integración disponible, frente a 49,88 de la persistencia. Apoyo parcial.

## Estructura

Los scripts esperan la estructura del paquete de cierre. La carpeta raíz es `analysis/cierre` y el código está en `codigo/`. Las carpetas de datos no se versionan:

| Carpeta | Contenido | En Git |
| --- | --- | --- |
| `codigo/` | Descarga, respaldo, análisis, pruebas, inferencia e informes | Sí |
| `fuentes_api/` | Respuestas GET originales y sus hashes | No |
| `respaldo_bd/` | Respaldo nativo de PostgreSQL, respaldo al corte y tablas exportadas | No |
| `referencia_22_octubre/` | Artefacto y predicciones del corte anterior | No |
| `datos/`, `modelo/`, `graficos/` | Salidas de la evaluación | No |

## Scripts

| Script | Función |
| --- | --- |
| `respaldar_postgres.py` | Descarga un respaldo nativo con `pg_dump` en solo lectura y lo restaura en una instancia local aislada. Recibe un archivo de conexión con `--connection-file`, que debe quedar **fuera** del repositorio. Está escrito para Windows con el cliente de PostgreSQL 18. |
| `verificar_respaldo_local.py` | Repite la restauración y exporta las tablas desde el respaldo ya descargado. |
| `crear_corte_db_local.py` | Genera el respaldo filtrado al corte desde la copia local restaurada. |
| `descargar_api.py` | Descarga en solo lectura la telemetría y los eventos de la API pública y registra los hashes. |
| `protocolo_suelo.py` | Preparación horaria, cobertura, rezagos por marca temporal y pares a 24 h. Evoluciona el pipeline del corte anterior y excluye los ensayos declarados. |
| `evaluar_cierre.py` | Evaluación completa: bloque fijo, origen móvil, ablación, controles y artefacto final. |
| `predecir_cierre.py` | Ejemplo de inferencia posterior al corte, sin etiqueta observada y excluido de toda métrica. |
| `generar_informes.py`, `generar_pdf.py` | Informes en Markdown y resumen en PDF para el equipo. |
| `verificar_integridad.py`, `empaquetar_entrega.py` | Manifiesto de hashes y empaquetado sellado de la entrega. |
| `test_cierre.py` | Diez pruebas de los controles metodológicos. |

Las diez pruebas verifican:

- que el objetivo esté a exactamente 24 horas y que el último día sin respuesta quede fuera;
- que un hueco no desplace el objetivo;
- que las etiquetas de entrenamiento sean anteriores al origen;
- que la ausencia del DHT22 no elimine suelo válido;
- que muestras aisladas del DHT22 no generen cobertura horaria;
- que no se use una versión meteorológica posterior al origen;
- que no se use el resumen meteorológico del día en curso;
- que no se use una observación satelital futura;
- que un ensayo declarado se excluya sin alterar la fuente;
- que las métricas coincidan con las de scikit-learn.

## Reproducción

Python 3.12, en un entorno propio:

```powershell
cd analysis/cierre
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r codigo/requirements-lock.txt
./.venv/Scripts/python.exe -m unittest discover -s codigo -p "test_*.py" -v
# Con las carpetas de datos del paquete de cierre copiadas en analysis/cierre:
./.venv/Scripts/python.exe codigo/evaluar_cierre.py
./.venv/Scripts/python.exe codigo/predecir_cierre.py
./.venv/Scripts/python.exe codigo/generar_informes.py
```

La evaluación verifica los hashes de las respuestas y de las tablas antes de calcular métricas. No necesita conexión a Render. Reejecutar sobrescribe las salidas de esa copia: para preservar una entrega sellada, reproducir en otra carpeta. Los informes requieren además `requirements-informe.txt`.

## Límites

- **Meteorología:** el sistema no conserva un archivo de versiones de las fuentes externas. La disponibilidad histórica se aproxima de forma conservadora con `created_at` y `updated_at`.
- **Viento:** el de la maqueta fue accionado con un motor y su escala cambió durante la segunda etapa. No se usa como viento natural.
- **Caudal:** circula en un circuito cerrado, así que no se interpreta como dosis aplicada al suelo.
- **Uso:** los artefactos no están desplegados ni conectados a la válvula.
