# Investigación histórica

Herramientas offline de la campaña de octubre de 2026. Esta carpeta no es una dependencia del backend, del firmware ni de la API satelital.

| Archivo | Función |
| --- | --- |
| `collect_sources.py` | Descarga meteorología y, opcionalmente, exporta PostgreSQL con transacción de solo lectura. |
| `probe_stations.py` | Registra disponibilidad y observaciones de estaciones cercanas. |
| `probe_inta.py` | Consulta el catálogo y datos publicados por INTA. |
| `build_dataset.py` | Audita fuentes y construye por separado tablas medidas y un escenario semisintético de balance hídrico. |
| `compare_snapshots.py` | Compara experimentos Ridge del constructor histórico; no evalúa el candidato actual de `analysis`. |
| `test_research.py` | Comprueba cortes temporales, simulación y separación de fuentes. |

## Pruebas

```powershell
python -m pip install -r requirements-research.txt
python -B -m unittest discover -s . -p test_research.py -v
```

## Recolección y construcción

```powershell
python collect_sources.py --cutoff '2026-10-14T18:57:00-03:00' --output ../snapshots/corte_historico
python build_dataset.py --snapshot ../snapshots/corte_historico --output ../outputs/experimento --cutoff '2026-10-14T18:57:00-03:00'
```

La primera orden sin `--database` descarga fuentes externas pero no exporta PostgreSQL. El constructor completo espera también los archivos exportados de la base: el ejemplo solo podrá completarse cuando ese snapshot disponga de todas las entradas requeridas.

La opción `collect_sources.py --database` requiere `psql` y variables `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`. En Windows se puede indicar su ejecutable mediante `VITIALERT_PSQL`. Usar una cuenta de lectura y credenciales fuera de Git. Cada salida debe ser nueva.

Los snapshots y salidas no se incluyen. NOAA/IEM o INTA pueden publicar datos incompletos, HTML en lugar de observaciones, o relojes que requieren interpretación. Los fallos se registran; una descarga no demuestra que exista una serie válida. La meteorología de grilla o una estación cercana no certifican la lluvia exacta de la maqueta.

Las tablas semisintéticas mantienen su identificación de origen y se usan para experimentar con la metodología. No reemplazan mediciones ausentes ni validan consumo físico, ahorro o precisión de campo. El entrenamiento sobre mediciones reales está en `analysis`.
