# Modelo de humedad del suelo

Pipeline experimental para predecir la humedad relativa de la sonda a **24 horas**. El candidato es `HistGradientBoostingRegressor`. Usa suelo actual, antecedentes de 6 y 24 horas, media de 24 horas y codificación cíclica de la hora.

El árbol de boosting permite relaciones no lineales y antecedentes faltantes sin requerir una arquitectura de secuencias. Se parte de un modelo acotado porque la cantidad de pares medidos y la cobertura temporal son limitadas. La persistencia se utiliza como referencia de evaluación, no como otro modelo desplegado.

## Instalar y probar

Usar Python 3.12 en un entorno separado de `satellite-api`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-lock.txt
python -B -m unittest discover -s . -p test_actualizacion.py -v
```

## Ejecutar

```powershell
# Solo lectura: consulta GET de telemetría y eventos.
python -B actualizar_modelo_real.py --backend-url https://vitialert-backend.onrender.com --output ../outputs/corte_nuevo

# Repetir un corte local sin conexión.
python -B actualizar_modelo_real.py --snapshot ../snapshots/corte_conservado/01_fuentes --output ../outputs/repeticion

# Verificar un resultado de origen confiable.
python -B verificar_resultados.py ../outputs/corte_nuevo
```

La salida debe ser nueva. No se incluyen snapshots ni resultados privados en Git. El período de investigación comienza en octubre de 2026 y el descargador incluye antecedentes desde septiembre para resolver retardos; no es un CLI genérico para cualquier campaña o nodo.

Consultar [PROTOCOLO.md](PROTOCOLO.md) para los criterios de cobertura. Las series reconstruidas o simuladas no se convierten en etiquetas medidas. El pipeline preserva huecos, valida el corte y excluye registros identificados como reconstruidos.

## Interpretación

MAE y RMSE se expresan en puntos de la escala de la sonda, no en porcentaje de acierto ni contenido volumétrico de agua calibrado. La validación es retrospectiva y cronológica. No acredita una prueba futura independiente ni ahorro de agua.

El artefacto `joblib` es exclusivamente experimental y no se conecta automáticamente al control de la válvula. No cargar archivos `joblib` de origen desconocido: su deserialización puede ejecutar código. Los hashes comprueban integridad respecto de un manifiesto, no prueban por sí solos autenticidad.
