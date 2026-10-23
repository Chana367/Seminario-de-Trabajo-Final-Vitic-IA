# services/sentinel_service.py
"""
Servicio de consulta a Sentinel-2 vía Sentinel Hub (Copernicus Data Space).

Calcula índices de vegetación y humedad a partir de imágenes Sentinel-2 L2A:

    NDVI = (B08 - B04) / (B08 + B04)
        Normalized Difference Vegetation Index
        Mide vigor y cobertura vegetal.

    NDMI = (B08 - B11) / (B08 + B11)
        Normalized Difference Moisture Index
        Sensible al contenido de humedad de la vegetación.
        Especialmente relevante para decisiones de gestión hídrica.

Bandas utilizadas:
    B04 (665 nm)  — Rojo visible
    B08 (842 nm)  — Infrarrojo cercano (NIR)
    B11 (1610 nm) — Infrarrojo de onda corta (SWIR)
    SCL           — Scene Classification Layer (filtrado de nubes)

Este servicio NO interpreta los índices ni genera recomendaciones de riego.
Devuelve valores numéricos, estadísticas y métricas de calidad que el
backend Java combinará con datos IoT y meteorológicos para tomar decisiones.
"""

import logging
import numpy as np
import requests
from io import BytesIO
from datetime import datetime, timezone, timedelta

from config import settings
from services.cache import sentinel_cache

logger = logging.getLogger(__name__)

# ── URLs de Sentinel Hub (Copernicus Data Space Ecosystem) ──
SH_AUTH_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
SH_PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"
SH_CATALOG_URL = "https://sh.dataspace.copernicus.eu/api/v1/catalog/1.0.0/search"

# ── Evalscript: NDVI + NDMI + SCL flag ──
# Este mini-programa se ejecuta DENTRO del servidor de Sentinel Hub.
# Devuelve 4 bandas por píxel: NDVI, NDMI, flag de nube (0/1), y SCL.
# Así evitamos descargar imágenes completas: solo bajan los resultados numéricos.
EVALSCRIPT_INDICES = """
//VERSION=3
function setup() {
  return {
    input: [{ bands: ["B04", "B08", "B11", "SCL"], units: "DN" }],
    output: { id: "default", bands: 4, sampleType: "FLOAT32" },
    mosaicking: "SIMPLE"
  };
}

function evaluatePixel(sample) {
  // SCL (Scene Classification Layer) de Sentinel-2 L2A:
  //   0 = no data, 1 = saturated/defective
  //   2 = dark area, 3 = cloud shadow
  //   4 = vegetation, 5 = bare soil, 6 = water
  //   7 = unclassified, 8 = cloud medium prob
  //   9 = cloud high prob, 10 = thin cirrus, 11 = snow/ice
  //
  // Consideramos "nube" a: sombra (3), cloud medium (8), cloud high (9), cirrus (10)
  // Consideramos "válido" a: vegetación (4), suelo (5), agua (6), unclassified (7)
  var scl = sample.SCL;
  var is_cloud = (scl == 3 || scl >= 8) ? 1.0 : 0.0;
  var is_nodata = (scl <= 1) ? 1.0 : 0.0;

  // Si es nube o no-dato, marcamos con -9999
  if (is_cloud > 0 || is_nodata > 0) {
    return [-9999, -9999, is_cloud, scl];
  }

  var nir = sample.B08;
  var red = sample.B04;
  var swir = sample.B11;

  // NDVI: (NIR - Red) / (NIR + Red)
  var ndvi = (nir + red != 0) ? (nir - red) / (nir + red) : -9999;

  // NDMI: (NIR - SWIR) / (NIR + SWIR)
  var ndmi = (nir + swir != 0) ? (nir - swir) / (nir + swir) : -9999;

  return [ndvi, ndmi, is_cloud, scl];
}
"""


def _obtener_token() -> str | None:
    """
    Pide un token OAuth2 a Sentinel Hub usando las credenciales del .env.
    El token dura ~10 minutos. Para uso en producción con alto tráfico
    convendría cachearlo, pero para nuestro volumen de consultas es suficiente.
    """
    if not settings.sh_client_id or not settings.sh_client_secret:
        logger.warning("Credenciales de Sentinel Hub no configuradas")
        return None

    try:
        resp = requests.post(SH_AUTH_URL, data={
            "grant_type": "client_credentials",
            "client_id": settings.sh_client_id,
            "client_secret": settings.sh_client_secret,
        }, timeout=15)
        resp.raise_for_status()
        token = resp.json()["access_token"]
        logger.info("Token de Sentinel Hub obtenido OK")
        return token

    except Exception as e:
        logger.error(f"No pude autenticar con Sentinel Hub: {e}")
        return None


def _buscar_fecha_imagen(
    token: str,
    bbox: list,
    fecha_inicio: datetime,
    fecha_fin: datetime,
) -> str | None:
    """
    Busca la fecha de la imagen Sentinel-2 más reciente con baja nubosidad
    para el área especificada, usando la API de catálogo STAC de Sentinel Hub.

    Returns:
        Fecha en formato "YYYY-MM-DD" o None si no se encontró
    """
    try:
        payload = {
            "bbox": bbox,
            "datetime": (
                f"{fecha_inicio.strftime('%Y-%m-%dT%H:%M:%SZ')}/"
                f"{fecha_fin.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            ),
            "collections": ["sentinel-2-l2a"],
            "limit": 5,
        }

        resp = requests.post(
            SH_CATALOG_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        features = data.get("features", [])
        if features:
            # Buscar la imagen con menor cobertura de nubes
            best = None
            best_cc = 100
            for feat in features:
                props = feat.get("properties", {})
                cc = props.get("eo:cloud_cover", 100)
                if cc < best_cc:
                    best_cc = cc
                    best = feat

            if best:
                dt_str = best["properties"].get("datetime", "")
                if dt_str:
                    return dt_str[:10]

        logger.info("Catálogo Sentinel: no se encontraron imágenes en el rango")
        return None

    except Exception as e:
        logger.warning(f"Búsqueda de catálogo Sentinel falló (no crítico): {e}")
        return None


def consultar_sentinel(
    lat: float,
    lon: float,
    dias_atras: int | None = None,
    buffer_km: float | None = None,
) -> dict | None:
    """
    Consulta índices de vegetación (NDVI) y humedad (NDMI) de una zona
    usando imágenes Sentinel-2 L2A.

    Genera un bounding box centrado en las coordenadas, ejecuta el evalscript
    en el servidor de Sentinel Hub, y calcula estadísticas descriptivas
    de los píxeles válidos (no nublados).

    Args:
        lat: latitud del centro
        lon: longitud del centro
        dias_atras: rango de búsqueda en días (default: settings.sentinel_days_back)
        buffer_km: radio del buffer en km (usado para construir el bbox)

    Returns:
        dict con estadísticas NDVI, NDMI, métricas de calidad, y metadatos.
        None si la consulta falla completamente.
    """
    if dias_atras is None:
        dias_atras = settings.sentinel_days_back
    if buffer_km is None:
        buffer_km = settings.default_buffer_km

    processing_start = datetime.now(timezone.utc)

    # Cache: redondeamos coords y usamos la fecha
    hoy = processing_start.strftime("%Y-%m-%d")
    cache_key = f"sentinel_{round(lat, 3)}_{round(lon, 3)}_{hoy}_{dias_atras}"

    cached = sentinel_cache.get(cache_key)
    if cached is not None:
        logger.info(f"Sentinel desde cache para {cache_key}")
        return cached

    token = _obtener_token()
    if not token:
        return None

    # Bounding box centrado en las coordenadas
    # 1 grado de latitud ≈ 111 km; 1 grado de longitud ≈ 111 * cos(lat) km
    import math
    lat_offset = buffer_km / 111.0
    lon_offset = buffer_km / (111.0 * math.cos(math.radians(lat)))
    bbox = [
        lon - lon_offset,
        lat - lat_offset,
        lon + lon_offset,
        lat + lat_offset,
    ]

    fecha_fin = processing_start
    fecha_inicio = fecha_fin - timedelta(days=dias_atras)

    # Buscar la fecha real de la imagen más reciente
    image_date = _buscar_fecha_imagen(token, bbox, fecha_inicio, fecha_fin)

    # Consulta al servicio de procesamiento
    payload = {
        "input": {
            "bounds": {
                "bbox": bbox,
                "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"},
            },
            "data": [{
                "type": "sentinel-2-l2a",
                "dataFilter": {
                    "timeRange": {
                        "from": fecha_inicio.strftime("%Y-%m-%dT00:00:00Z"),
                        "to": fecha_fin.strftime("%Y-%m-%dT23:59:59Z"),
                    },
                    "maxCloudCoverage": 30,
                    "mosaickingOrder": "leastCC",
                },
            }],
        },
        "output": {
            "width": 64,
            "height": 64,
            "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}],
        },
        "evalscript": EVALSCRIPT_INDICES,
    }

    try:
        resp = requests.post(
            SH_PROCESS_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "image/tiff",
            },
            timeout=30,
        )
        resp.raise_for_status()

        # Parsear el GeoTIFF con 4 bandas
        try:
            import rasterio
            with rasterio.open(BytesIO(resp.content)) as src:
                all_bands = src.read()  # Shape: (4, 64, 64)
        except ImportError:
            # Fallback: interpretar bytes crudos como float32
            raw = np.frombuffer(resp.content[-64 * 64 * 4 * 4:], dtype=np.float32)
            all_bands = raw.reshape(4, 64, 64)

        ndvi_band = all_bands[0]   # Banda 0: NDVI
        ndmi_band = all_bands[1]   # Banda 1: NDMI
        cloud_band = all_bands[2]  # Banda 2: flag de nube (0/1)

        total_pixels = ndvi_band.size

        # Píxeles válidos: no marcados como -9999 y dentro de rango físico
        valid_mask_ndvi = (ndvi_band > -1) & (ndvi_band <= 1)
        valid_mask_ndmi = (ndmi_band > -1) & (ndmi_band <= 1)
        cloud_pixels = int(np.sum(cloud_band > 0.5))

        ndvi_valid = ndvi_band[valid_mask_ndvi]
        ndmi_valid = ndmi_band[valid_mask_ndmi]

        valid_pixels = len(ndvi_valid)
        valid_pixel_pct = round(valid_pixels / total_pixels * 100, 1) if total_pixels > 0 else 0.0
        cloud_pixel_pct = round(cloud_pixels / total_pixels * 100, 1) if total_pixels > 0 else 0.0

        # Calcular la antigüedad de la imagen
        image_age_days = None
        if image_date:
            try:
                img_dt = datetime.strptime(image_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                image_age_days = (processing_start - img_dt).days
            except ValueError:
                pass

        # Determinar calidad
        if valid_pixels == 0:
            quality = "CLOUD_CONTAMINATED"
        elif valid_pixel_pct < 30:
            quality = "PARTIAL"
        elif image_age_days is not None and image_age_days > 15:
            quality = "STALE"
        else:
            quality = "VALID"

        # Construir resultado
        resultado = {
            "image_date": image_date or hoy,
            "processing_time": datetime.now(timezone.utc).isoformat(),
            # NDVI
            "ndvi_mean": round(float(np.mean(ndvi_valid)), 4) if valid_pixels > 0 else None,
            "ndvi_min": round(float(np.min(ndvi_valid)), 4) if valid_pixels > 0 else None,
            "ndvi_max": round(float(np.max(ndvi_valid)), 4) if valid_pixels > 0 else None,
            "ndvi_std": round(float(np.std(ndvi_valid)), 4) if valid_pixels > 0 else None,
            # NDMI
            "ndmi_mean": round(float(np.mean(ndmi_valid)), 4) if len(ndmi_valid) > 0 else None,
            "ndmi_min": round(float(np.min(ndmi_valid)), 4) if len(ndmi_valid) > 0 else None,
            "ndmi_max": round(float(np.max(ndmi_valid)), 4) if len(ndmi_valid) > 0 else None,
            "ndmi_std": round(float(np.std(ndmi_valid)), 4) if len(ndmi_valid) > 0 else None,
            # Calidad
            "valid_pixel_pct": valid_pixel_pct,
            "cloud_pixel_pct": cloud_pixel_pct,
            "image_age_days": image_age_days,
            "quality": quality,
        }

        sentinel_cache.set(cache_key, resultado)
        logger.info(
            f"Sentinel | NDVI={resultado['ndvi_mean']}, NDMI={resultado['ndmi_mean']} | "
            f"Valid={valid_pixel_pct}%, Clouds={cloud_pixel_pct}%"
        )
        return resultado

    except requests.exceptions.HTTPError as e:
        logger.error(
            f"Sentinel Hub respondió con error: {e.response.status_code} - "
            f"{e.response.text[:200]}"
        )
        return None
    except Exception as e:
        logger.error(f"Error consultando Sentinel: {e}")
        return None
