# API satelital y Data Miner

FastAPI para consultar variables atmosféricas GOES-19 y los índices NDVI/NDMI de Sentinel-2. Devuelve datos y calidad por proveedor; no recibe telemetría IoT, entrena modelos ni controla la válvula.

## Instalación

Usar Python 3.11: las versiones fijadas de NumPy, PyProj y Rasterio requieren una plataforma con wheels compatibles.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --only-binary=:all: -r requirements.txt
Copy-Item .env.example .env
python -m pytest -q -p no:cacheprovider
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Completar las credenciales de Sentinel Hub en `.env` o en el entorno. GOES consulta el bucket público de NOAA. Las pruebas usan proveedores simulados y no necesitan credenciales de producción.

Documentación: `/docs`. Salud: `/health`. Rutas: `/api/v1/satellite/features`, `/api/v1/satellite/goes` y `/api/v1/satellite/sentinel`, con parámetros `lat` y `lon`. La respuesta puede ser parcial cuando una fuente no está disponible. `configured` no significa que se haya obtenido una imagen válida.

## Data Miner

`weather_collector.py` obtiene meteorología de Open-Meteo. `data_miner.py` expone:

```powershell
# Descarga meteorología a un archivo local.
python data_miner.py weather --from 2026-10-01 --to 2026-10-14 --source archive --output ../data/clima.csv

# Exportación: lectura del backend, sin importación ni refresco.
python data_miner.py dataset --backend-url https://vitialert-backend.onrender.com --node-id 1 --from 2026-10-01T00:00:00-03:00 --to 2026-10-14T18:57:00-03:00 --output ../data/dataset.csv

# Operación con escritura: importa meteorología y solicita persistencia satelital.
python data_miner.py sync
```

`sync` requiere `BACKEND_BASE_URL` y `VITIALERT_API_KEY` como variables de entorno. La carga de `.env` mediante Pydantic corresponde a la API; no asumir que el CLI Data Miner lee automáticamente ese archivo. El subcomando `weather` debe apuntar a un directorio de salida existente.

El workflow raíz `data-miner.yml` usa esos nombres como secretos de GitHub y se programa a las 03:15 UTC (00:15 de Argentina). También dispone de ejecución manual. Una ejecución puede fallar por falta de capturas satelitales aunque haya terminado la importación meteorológica.

No se incluye `web_scrapping.py`: la recolección vigente usa APIs estructuradas y el exportador del backend. La copia histórica del script queda fuera del runtime y no es necesaria para ejecutar estos componentes.
