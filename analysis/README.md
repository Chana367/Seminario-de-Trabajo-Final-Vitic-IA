# Modelo de humedad del suelo

Pronóstico de la humedad relativa de la sonda a **24 horas**, evaluado siempre contra la persistencia (la humedad dentro de 24 horas será igual a la actual). El análisis tiene tres etapas, cada una en su carpeta.

| Carpeta | Etapa | Qué hace |
| --- | --- | --- |
| `.` (esta carpeta) | Corte del 22/10/2026 | Pipeline anterior: `HistGradientBoostingRegressor` con seis variables de suelo y hora, validación de origen móvil. Se conserva para trazabilidad y para la comparación entre cortes de la tesis. |
| [cierre](cierre/README.md) | Protocolo de cierre, 28/10/2026 16:00 | Respaldo verificado, preparación horaria, bloque fijo congelado al 24/10, origen móvil, ablación de entradas y artefacto final. Protocolo fijado antes de calcular métricas. |
| [ampliacion](ampliacion/README.md) | Ampliación posterior | Escalera completa de modelos, cinco cortes de congelamiento, diagnóstico del error, interpolación de huecos, acierto en la decisión de riego y simulación declarada. |

Las tres etapas comparten las reglas del trabajo:

- Rezagos, pendientes, medias móviles y objetivo se resuelven **por marca temporal**, nunca por posición de fila. Una hora ausente queda vacía.
- El **objetivo nunca se imputa**: toda métrica compara un pronóstico con una lectura real del sensor.
- Los predictores faltantes solo se completan dentro del pipeline que se ajusta, con la mediana del entrenamiento (Ridge y bosque aleatorio). El *gradient boosting* los trata de forma nativa.
- Las series reconstruidas o simuladas no se convierten en etiquetas medidas. La simulación de la ampliación está declarada como sintética y no se mezcla con los datos reales.
- Ningún componente envía órdenes al dispositivo ni modifica producción. Los modelos no están desplegados.

No se versionan datos de campo, respaldos, salidas ni modelos entrenados.

## Corte del 22/10 (esta carpeta)

Usar Python 3.12 en un entorno separado de `satellite-api`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-lock.txt
python -B -m unittest discover -s . -p test_actualizacion.py -v
```

```powershell
# Solo lectura: consulta GET de telemetría y eventos.
python -B actualizar_modelo_real.py --backend-url https://vitialert-backend.onrender.com --output ../outputs/corte_nuevo

# Repetir un corte local sin conexión.
python -B actualizar_modelo_real.py --snapshot ../snapshots/corte_conservado/01_fuentes --output ../outputs/repeticion

# Verificar un resultado de origen confiable.
python -B verificar_resultados.py ../outputs/corte_nuevo
```

La salida debe ser nueva. Los criterios de cobertura están en [PROTOCOLO.md](PROTOCOLO.md). El pipeline preserva huecos, valida el corte y excluye registros identificados como reconstruidos.

## Interpretación

MAE y RMSE se expresan en puntos de la escala de la sonda, no en porcentaje de acierto ni contenido volumétrico de agua calibrado. La validación es retrospectiva y cronológica. No acredita una prueba futura independiente ni ahorro de agua.

Los artefactos `joblib` son experimentales y no se conectan al control de la válvula. No cargar archivos `joblib` de origen desconocido: su deserialización puede ejecutar código. Los hashes comprueban integridad respecto de un manifiesto, no prueban por sí solos autenticidad.
