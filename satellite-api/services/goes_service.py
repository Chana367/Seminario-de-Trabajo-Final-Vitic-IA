# services/goes_service.py
"""
Servicio de consulta al satélite GOES-19 para extracción de features atmosféricas.

Accede a 5 productos GOES-R ABI Level 2 desde el bucket público de NOAA en S3:

    CMI (B13, 10.3μm IR) → Temperatura de tope de nube
    ACM                   → Máscara binaria de nubes (fracción nubosa)
    ACHA                  → Altura del tope de nube (metros)
    ACTP                  → Fase termodinámica del tope (agua/hielo/mixta)
    RRQPE                 → Tasa de precipitación instantánea (mm/h)

La clasificación de nubes combina los 5 productos para producir una categorización
meteorológica basada en los géneros de nubes del WMO International Cloud Atlas,
adaptada a los productos disponibles en GOES-R.

Referencias:
    - NOAA/NESDIS GOES-R Series ABI Algorithm Theoretical Basis Documents (ATBDs)
    - WMO International Cloud Atlas (Manual on the Observation of Clouds, WMO-No. 407)
    - Schmit, T. J., et al. (2017). A Closer Look at the ABI on the GOES-R Series.
      Bull. Amer. Meteor. Soc., 98(4), 681-698.
"""

import logging
import asyncio
import numpy as np
import xarray as xr
import s3fs
from pyproj import Proj
from datetime import datetime, timezone, timedelta

from config import settings
from services.cache import goes_cache

logger = logging.getLogger(__name__)

# ── Productos GOES-R ABI Level 2 ──
# Cada producto tiene su propio directorio en S3 y variables específicas.
GOES_PRODUCTS = {
    "CMI": {
        "path": "ABI-L2-CMIPF",
        "filter": "C13_G19",
        "variable": "CMI",
    },
    "ACM": {
        "path": "ABI-L2-ACMF",
        "filter": "_G19",
        "variable": "BCM",
    },
    "ACHA": {
        "path": "ABI-L2-ACHAF",
        "filter": "_G19",
        "variable": "HT",
    },
    "ACTP": {
        "path": "ABI-L2-ACTPF",
        "filter": "_G19",
        "variable": "Phase",
    },
    "RRQPE": {
        "path": "ABI-L2-RRQPEF",
        "filter": "_G19",
        "variable": "RRQPE",
    },
}

# ── Mapeo de fases termodinámicas del producto ACTP ──
# Fuente: GOES-R ABI ATBD for Cloud Top Phase (ACTP)
PHASE_LABELS = {
    0: "CLEAR",
    1: "WATER",
    2: "SUPERCOOLED_WATER",
    3: "MIXED",
    4: "ICE",
    5: "UNKNOWN",
}

# ── Resolución aproximada de los productos (km/píxel) ──
# CMI B13, ACM y RRQPE se producen a ~2 km (Full Disk).
# ACHA y ACTP se producen a ~10 km (Full Disk).
# Estos valores se usan para calcular el radio del buffer en píxeles.
PRODUCT_RESOLUTION_KM = {
    "CMI": 2.0,
    "ACM": 2.0,
    "ACHA": 10.0,
    "ACTP": 10.0,
    "RRQPE": 2.0,
}


# ═══════════════════════════════════════════════════════════
# Funciones de procesamiento geoespacial (reutilizadas)
# ═══════════════════════════════════════════════════════════

def _latlon_a_pixel(lat: float, lon: float, ds: xr.Dataset) -> tuple[int, int]:
    """
    Convierte coordenadas geográficas (lat/lon) al píxel correspondiente
    en la grilla del satélite GOES.

    El GOES utiliza una proyección geoestacionaria (vista desde el satélite
    a 35786 km de altura). Los parámetros de proyección se leen directamente
    del archivo NetCDF para garantizar consistencia.

    Returns:
        (iy, ix): índices del píxel en la grilla (fila, columna)
    """
    proj_info = ds.goes_imager_projection
    sat_h = proj_info.perspective_point_height
    sat_lon = proj_info.longitude_of_projection_origin
    sat_sweep = proj_info.sweep_angle_axis

    proyeccion = Proj(proj='geos', h=sat_h, lon_0=sat_lon, sweep=sat_sweep)

    # Proyectamos y pasamos a radianes (que es como GOES indexa sus píxeles)
    x_metros, y_metros = proyeccion(lon, lat)
    x_rad = x_metros / sat_h
    y_rad = y_metros / sat_h

    # Buscamos el píxel más cercano en cada eje
    idx_x = int(np.abs(ds.x.values - x_rad).argmin())
    idx_y = int(np.abs(ds.y.values - y_rad).argmin())

    return idx_y, idx_x


def _calcular_radio_buffer(buffer_km: float, resolucion_km: float) -> int:
    """
    Convierte el radio del buffer en km a radio en píxeles,
    adaptándose a la resolución del producto GOES.

    Ejemplo:
        buffer_km=5, resolución=2km → radio=2 → ventana 5×5 píxeles (~100 km²)
        buffer_km=5, resolución=10km → radio=1 → ventana 3×3 píxeles (~900 km²)
    """
    return max(1, int(round(buffer_km / resolucion_km)))


def _extraer_estadisticas_buffer(
    ds: xr.Dataset,
    variable: str,
    iy: int,
    ix: int,
    radio: int
) -> dict | None:
    """
    Extrae estadísticas de una variable dentro del buffer espacial.

    En vez de mirar un solo píxel, tomamos una ventana de
    (2*radio+1) × (2*radio+1) píxeles y calculamos estadísticas
    descriptivas. Esto da robustez ante nubes parciales o bordes.

    Returns:
        dict con mean, median, min, max, std, valid_pixels, total_pixels
        None si no hay datos válidos en la ventana
    """
    try:
        data = ds[variable]
        ny, nx = data.shape[-2], data.shape[-1]

        # Recorte seguro (sin salirse de los bordes de la imagen)
        y_start = max(0, iy - radio)
        y_end = min(ny, iy + radio + 1)
        x_start = max(0, ix - radio)
        x_end = min(nx, ix + radio + 1)

        recorte = data[y_start:y_end, x_start:x_end].values

        # Aplanar y filtrar NaN e infinitos
        valores = recorte.flatten()
        valores_validos = valores[np.isfinite(valores)]

        total_pixels = len(valores)
        valid_pixels = len(valores_validos)

        if valid_pixels == 0:
            return None

        return {
            "mean": float(np.mean(valores_validos)),
            "median": float(np.median(valores_validos)),
            "min": float(np.min(valores_validos)),
            "max": float(np.max(valores_validos)),
            "std": float(np.std(valores_validos)),
            "valid_pixels": valid_pixels,
            "total_pixels": total_pixels,
        }

    except Exception as e:
        logger.warning(f"Error extrayendo buffer de '{variable}': {e}")
        return None


# ═══════════════════════════════════════════════════════════
# Acceso a S3 y descarga de productos
# ═══════════════════════════════════════════════════════════

def _buscar_archivos_recientes(
    fs: s3fs.S3FileSystem,
    producto_path: str,
    filtro: str,
    bucket: str | None = None,
) -> list[str]:
    """
    Busca los archivos más recientes de un producto GOES en S3.
    Prueba la hora actual y las 2 anteriores por si NOAA tiene delay.

    Args:
        fs: conexión S3 anónima
        producto_path: ej. "ABI-L2-CMIPF"
        filtro: substring para filtrar archivos, ej. "C13_G19"
        bucket: bucket S3 (default: settings.goes_bucket)

    Returns:
        Lista de rutas S3 ordenadas cronológicamente
    """
    if bucket is None:
        bucket = settings.goes_bucket

    ahora = datetime.now(timezone.utc)

    for delta_h in [0, 1, 2]:
        momento = ahora - timedelta(hours=delta_h)
        dia_del_anio = momento.timetuple().tm_yday
        ruta = f"{bucket}/{producto_path}/{momento.year}/{dia_del_anio:03d}/{momento.hour:02d}/"

        try:
            archivos = fs.ls(ruta)
            encontrados = sorted([f for f in archivos if filtro in f])

            if encontrados:
                logger.debug(f"GOES | {producto_path} | {ruta} → {len(encontrados)} archivos")
                return encontrados
        except Exception:
            continue

    logger.warning(f"GOES | No se encontraron archivos para {producto_path} en las últimas 2 horas")
    return []


def _extraer_producto(
    fs: s3fs.S3FileSystem,
    producto_key: str,
    lat: float,
    lon: float,
    buffer_km: float,
) -> dict | None:
    """
    Descarga y procesa un producto GOES individual.

    Args:
        producto_key: clave del producto en GOES_PRODUCTS (ej. "ACM")

    Returns:
        dict con estadísticas del buffer, o None si falla
    """
    config = GOES_PRODUCTS[producto_key]
    archivos = _buscar_archivos_recientes(fs, config["path"], config["filter"])

    if not archivos:
        return None

    try:
        archivo = archivos[-1]  # El más reciente
        resolucion = PRODUCT_RESOLUTION_KM.get(producto_key, 2.0)
        radio = _calcular_radio_buffer(buffer_km, resolucion)

        with fs.open(archivo) as f:
            ds = xr.open_dataset(f, engine='h5netcdf')

            iy, ix = _latlon_a_pixel(lat, lon, ds)
            stats = _extraer_estadisticas_buffer(ds, config["variable"], iy, ix, radio)

            ds.close()

            return stats

    except Exception as e:
        logger.warning(f"GOES | Error procesando {producto_key}: {e}")
        return None


# ═══════════════════════════════════════════════════════════
# Clasificación de nubes
# ═══════════════════════════════════════════════════════════

def _clasificar_nube(
    cloud_fraction: float | None,
    temp_tope_c: float | None,
    height_m: float | None,
    phase_code: int | None,
    rainfall_rate: float | None,
) -> dict:
    """
    Clasificación meteorológica de nubes basada en múltiples productos
    GOES-R ABI Level 2.

    Metodología:
        Combina 5 variables de entrada para asignar una categoría de nube
        basada en los géneros del WMO International Cloud Atlas, adaptados
        a la resolución y productos disponibles de GOES-R ABI.

    Criterios de clasificación (aplicados en orden de prioridad):

        1. Fracción nubosa (ACM): discrimina cielo despejado
        2. Precipitación activa (RRQPE): identifica nubes precipitantes
        3. Altura del tope (ACHA): estratificación vertical
           - Baja: < 2000 m
           - Media: 2000 - 6000 m
           - Alta: > 6000 m
        4. Fase termodinámica (ACTP): discrimina agua/hielo/mixta
        5. Temperatura del tope (CMI B13): intensidad del desarrollo convectivo

    La precipitación potencial se evalúa independientemente del tipo de nube
    para no confundir "tipo de nube" con "predicción de lluvia". El campo
    precipitation_potential es una estimación basada en la combinación de
    características, NO una predicción meteorológica.

    References:
        - WMO-No. 407: International Cloud Atlas
        - Pavolonis, M. J. (2010). GOES-R ABI Cloud Type/Phase Algorithm (ATBD)
        - Heidinger, A. K. (2011). GOES-R ABI Cloud Height Algorithm (ATBD)

    Args:
        cloud_fraction: fracción nubosa (0.0-1.0) del producto ACM
        temp_tope_c: temperatura media del tope de nube en °C (CMI B13)
        height_m: altura media del tope de nube en metros (ACHA)
        phase_code: código de fase termodinámica 0-5 (ACTP)
        rainfall_rate: tasa de precipitación en mm/h (RRQPE)

    Returns:
        dict con cloud_type, cloud_category, precipitation_potential,
        description, classification_criteria
    """
    # Valores por defecto cuando no hay datos suficientes
    result = {
        "cloud_type": "UNKNOWN",
        "cloud_category": None,
        "precipitation_potential": "UNKNOWN",
        "description": "Datos insuficientes para clasificación",
        "classification_criteria": [],
    }

    criteria = []

    # ── Paso 1: Verificar si hay cielo despejado ──
    if cloud_fraction is not None and cloud_fraction < 0.10:
        result["cloud_type"] = "CLEAR"
        result["cloud_category"] = None
        result["precipitation_potential"] = "NONE"
        result["description"] = (
            "Cielo despejado o con nubosidad insignificante (fracción < 10%). "
            "Sin bloqueo de radiación solar significativo."
        )
        criteria.append(f"cloud_fraction={cloud_fraction:.2f} < 0.10 → despejado")
        result["classification_criteria"] = criteria
        return result

    # ── Paso 2: Verificar precipitación activa ──
    has_precipitation = rainfall_rate is not None and rainfall_rate > 0.5

    if has_precipitation:
        criteria.append(f"rainfall_rate={rainfall_rate:.1f} mm/h > 0.5 → precipitación activa")

        # Distinguir entre precipitación convectiva y estratiforme
        if height_m is not None and height_m > 8000:
            result["cloud_type"] = "CUMULONIMBUS"
            result["cloud_category"] = "HIGH"
            result["precipitation_potential"] = "HIGH"
            result["description"] = (
                "Cumulonimbo: desarrollo convectivo profundo con precipitación activa. "
                "Tope de nube por encima de 8 km, posible tormenta con lluvias intensas. "
                "Aporte hídrico significativo probable."
            )
            criteria.append(f"height={height_m:.0f}m > 8000m → convección profunda")
        elif temp_tope_c is not None and temp_tope_c < -50:
            result["cloud_type"] = "CUMULONIMBUS"
            result["cloud_category"] = "HIGH"
            result["precipitation_potential"] = "HIGH"
            result["description"] = (
                "Cumulonimbo: tope de nube extremadamente frío con precipitación. "
                "Desarrollo convectivo intenso. Aporte hídrico significativo probable."
            )
            criteria.append(f"temp_tope={temp_tope_c:.1f}°C < -50°C → convección profunda")
        else:
            result["cloud_type"] = "NIMBOSTRATUS"
            result["cloud_category"] = "MID"
            result["precipitation_potential"] = "HIGH"
            result["description"] = (
                "Nimboestrato: nube estratiforme gruesa con precipitación activa. "
                "Lluvia sostenida de intensidad leve a moderada. "
                "Aporte hídrico sostenido."
            )
            criteria.append("precipitación sin convección profunda → nimboestrato")

        result["classification_criteria"] = criteria
        return result

    # ── Paso 3: Clasificación por altura, fase y temperatura ──
    # Usamos altura si está disponible; si no, usamos temperatura como proxy
    phase_label = PHASE_LABELS.get(phase_code) if phase_code is not None else None

    if phase_label:
        criteria.append(f"phase={phase_label}")

    if height_m is not None:
        criteria.append(f"height={height_m:.0f}m")

        if height_m < 2000:
            # Nubes bajas
            result["cloud_category"] = "LOW"

            if phase_label in ("WATER", "SUPERCOOLED_WATER"):
                result["cloud_type"] = "STRATOCUMULUS"
                result["precipitation_potential"] = "LOW"
                result["description"] = (
                    "Estratocúmulo: nube baja de agua líquida (< 2 km). "
                    "Puede producir llovizna ligera. Bloqueo parcial de radiación solar. "
                    "Generalmente no aporta precipitación significativa."
                )
                criteria.append("agua líquida + baja altitud → estratocúmulo")
            else:
                result["cloud_type"] = "LOW_CLOUD"
                result["precipitation_potential"] = "LOW"
                result["description"] = (
                    "Nube baja (< 2 km). Bloqueo parcial de radiación solar. "
                    "Aporte hídrico mínimo esperado."
                )
                criteria.append("baja altitud sin fase específica → nube baja genérica")

        elif height_m < 6000:
            # Nubes medias
            result["cloud_category"] = "MID"

            if phase_label == "MIXED":
                result["cloud_type"] = "ALTOSTRATUS"
                result["precipitation_potential"] = "MODERATE"
                result["description"] = (
                    "Altoestrato: nube de nivel medio (2-6 km) con fase mixta "
                    "(agua y hielo coexistiendo). Puede ser precursora de "
                    "precipitación si se espesa. Bloqueo moderado de radiación."
                )
                criteria.append("nivel medio + fase mixta → altoestrato")
            elif phase_label in ("WATER", "SUPERCOOLED_WATER"):
                result["cloud_type"] = "ALTOCUMULUS"
                result["precipitation_potential"] = "LOW"
                result["description"] = (
                    "Altocúmulo: nube de nivel medio (2-6 km) de agua líquida. "
                    "Generalmente no precipitante. Bloqueo moderado de radiación."
                )
                criteria.append("nivel medio + agua → altocúmulo")
            else:
                result["cloud_type"] = "MID_CLOUD"
                result["precipitation_potential"] = "LOW"
                result["description"] = (
                    "Nube de nivel medio (2-6 km). Bloqueo parcial de radiación."
                )
                criteria.append("nivel medio genérico")

        else:
            # Nubes altas (≥ 6000 m)
            result["cloud_category"] = "HIGH"

            if temp_tope_c is not None and temp_tope_c < -55:
                result["cloud_type"] = "DEEP_CONVECTIVE"
                result["precipitation_potential"] = "HIGH"
                result["description"] = (
                    "Convección profunda: tope de nube muy alto (> 6 km) y "
                    f"extremadamente frío ({temp_tope_c:.0f}°C). "
                    "Desarrollo convectivo intenso, posible tormenta. "
                    "Alto potencial de aporte hídrico si hay precipitación asociada."
                )
                criteria.append(f"alto + temp={temp_tope_c:.1f}°C < -55°C → convección profunda")

            elif temp_tope_c is not None and temp_tope_c < -40:
                if phase_label == "ICE":
                    result["cloud_type"] = "TOWERING_CUMULUS"
                    result["precipitation_potential"] = "MODERATE"
                    result["description"] = (
                        "Cúmulo en torre: nube alta en desarrollo vertical activo. "
                        "Fase de hielo con temperatura moderadamente fría. "
                        "Puede evolucionar a cumulonimbo. Potencial de lluvias."
                    )
                    criteria.append("alto + hielo + temp moderada → cúmulo en torre")
                else:
                    result["cloud_type"] = "HIGH_CLOUD"
                    result["precipitation_potential"] = "LOW"
                    result["description"] = (
                        "Nube alta (> 6 km) con tope frío. "
                        "Bloqueo significativo de radiación solar."
                    )
                    criteria.append("alto + temp fría sin fase hielo confirmada")
            else:
                if phase_label == "ICE":
                    result["cloud_type"] = "CIRRUS"
                    result["precipitation_potential"] = "NONE"
                    result["description"] = (
                        "Cirro: nube alta delgada de cristales de hielo. "
                        "No precipitante. Efecto mínimo sobre radiación directa. "
                        "Sin aporte hídrico."
                    )
                    criteria.append("alto + hielo + temp no extrema → cirro")
                else:
                    result["cloud_type"] = "HIGH_CLOUD"
                    result["precipitation_potential"] = "NONE"
                    result["description"] = (
                        "Nube alta (> 6 km). Generalmente no precipitante."
                    )
                    criteria.append("alto genérico")

    elif temp_tope_c is not None:
        # Fallback: sin altura disponible, usamos temperatura como proxy
        # La relación altura-temperatura sigue la tasa de lapse rate estándar
        criteria.append(f"sin altura disponible, usando temp_tope={temp_tope_c:.1f}°C como proxy")

        if temp_tope_c > 0:
            result["cloud_type"] = "LOW_CLOUD"
            result["cloud_category"] = "LOW"
            result["precipitation_potential"] = "LOW"
            result["description"] = (
                "Nube baja estimada por temperatura de tope cálida (> 0°C). "
                "Clasificación basada en temperatura sin dato de altura."
            )
        elif temp_tope_c > -20:
            result["cloud_type"] = "MID_CLOUD"
            result["cloud_category"] = "MID"
            result["precipitation_potential"] = "LOW"
            result["description"] = (
                "Nube de nivel medio estimada por temperatura de tope (-20 a 0°C). "
                "Clasificación basada en temperatura sin dato de altura."
            )
        elif temp_tope_c > -40:
            result["cloud_type"] = "HIGH_CLOUD"
            result["cloud_category"] = "HIGH"
            result["precipitation_potential"] = "LOW"
            result["description"] = (
                "Nube alta estimada por temperatura de tope fría (-40 a -20°C). "
                "Clasificación basada en temperatura sin dato de altura."
            )
        elif temp_tope_c > -55:
            result["cloud_type"] = "TOWERING_CUMULUS"
            result["cloud_category"] = "HIGH"
            result["precipitation_potential"] = "MODERATE"
            result["description"] = (
                "Cúmulo en torre estimado por temperatura de tope muy fría (-55 a -40°C). "
                "Posible desarrollo convectivo activo. "
                "Clasificación basada en temperatura sin dato de altura."
            )
        else:
            result["cloud_type"] = "DEEP_CONVECTIVE"
            result["cloud_category"] = "HIGH"
            result["precipitation_potential"] = "HIGH"
            result["description"] = (
                f"Convección profunda estimada por tope extremadamente frío ({temp_tope_c:.0f}°C). "
                "Alta probabilidad de desarrollo convectivo intenso. "
                "Clasificación basada en temperatura sin dato de altura."
            )

    # Si cloud_fraction está disponible pero no entramos por "CLEAR",
    # agregar el dato a los criterios
    if cloud_fraction is not None:
        criteria.append(f"cloud_fraction={cloud_fraction:.2f}")

    result["classification_criteria"] = criteria
    return result


# ═══════════════════════════════════════════════════════════
# Función principal de consulta GOES
# ═══════════════════════════════════════════════════════════

def _consultar_goes_sync(lat: float, lon: float, buffer_km: float) -> dict:
    """
    Función sincrónica que consulta todos los productos GOES-R ABI Level 2
    y produce un conjunto de features atmosféricas estructuradas.

    Accede a 5 productos de forma independiente. Si alguno falla,
    el campo correspondiente será null pero los demás se devuelven.

    Returns:
        dict con todas las features GOES y metadatos de calidad
    """
    processing_start = datetime.now(timezone.utc)

    # Verificar cache
    cache_key = f"goes_{round(lat, 2)}_{round(lon, 2)}_{buffer_km}_{processing_start.strftime('%Y%m%d%H')}"
    cached = goes_cache.get(cache_key)
    if cached is not None:
        return cached

    result = {
        "satellite": "GOES-19",
        "observation_time": None,
        "processing_time": None,
        "cloud_top_temperature_c": None,
        "cloud_top_temp_min_c": None,
        "cloud_top_temp_max_c": None,
        "cloud_top_temp_std_c": None,
        "cloud_temperature_delta_c": None,
        "cloud_fraction": None,
        "cloud_top_height_m": None,
        "cloud_top_phase": None,
        "rainfall_rate_mm_h": None,
        "cloud_classification": None,
        "buffer_pixels": None,
        "data_age_minutes": None,
        "quality": "NO_DATA",
    }

    try:
        fs = s3fs.S3FileSystem(anon=True)

        # ── 1. CMI Band 13: Temperatura de tope de nube ──
        cmi_config = GOES_PRODUCTS["CMI"]
        archivos_b13 = _buscar_archivos_recientes(fs, cmi_config["path"], cmi_config["filter"])

        if len(archivos_b13) < 2:
            logger.warning("GOES | No hay suficientes archivos CMI B13 para calcular delta")
            result["quality"] = "NO_DATA"
            return result

        archivo_actual = archivos_b13[-1]
        archivo_previo = archivos_b13[-2]
        radio_cmi = _calcular_radio_buffer(buffer_km, PRODUCT_RESOLUTION_KM["CMI"])

        logger.info(f"GOES | CMI B13: {archivo_actual.split('/')[-1]}")

        with fs.open(archivo_actual) as f_act, fs.open(archivo_previo) as f_prev:
            ds_actual = xr.open_dataset(f_act, engine='h5netcdf')
            ds_previo = xr.open_dataset(f_prev, engine='h5netcdf')

            iy, ix = _latlon_a_pixel(lat, lon, ds_actual)

            # Estadísticas del buffer actual
            stats_actual = _extraer_estadisticas_buffer(ds_actual, "CMI", iy, ix, radio_cmi)
            stats_previo = _extraer_estadisticas_buffer(ds_previo, "CMI", iy, ix, radio_cmi)

            if stats_actual:
                # Convertir Kelvin a Celsius
                result["cloud_top_temperature_c"] = round(stats_actual["mean"] - 273.15, 2)
                result["cloud_top_temp_min_c"] = round(stats_actual["min"] - 273.15, 2)
                result["cloud_top_temp_max_c"] = round(stats_actual["max"] - 273.15, 2)
                result["cloud_top_temp_std_c"] = round(stats_actual["std"], 2)
                result["buffer_pixels"] = stats_actual["total_pixels"]

                # Delta térmico (evolución temporal)
                if stats_previo:
                    delta = (stats_actual["mean"] - 273.15) - (stats_previo["mean"] - 273.15)
                    result["cloud_temperature_delta_c"] = round(delta, 2)

                # Tiempo de observación (del nombre del archivo GOES)
                try:
                    # Los archivos GOES tienen timestamp en el nombre: _s{YYYYDDDHHMMSSs}
                    nombre = archivo_actual.split('/')[-1]
                    idx_s = nombre.index('_s') + 2
                    ts_str = nombre[idx_s:idx_s + 13]
                    obs_time = datetime.strptime(ts_str, "%Y%j%H%M%S").replace(tzinfo=timezone.utc)
                    result["observation_time"] = obs_time.isoformat()
                    result["data_age_minutes"] = round((processing_start - obs_time).total_seconds() / 60, 1)
                except Exception:
                    pass

                result["quality"] = "VALID"

            ds_actual.close()
            ds_previo.close()

        # ── 2. ACM: Fracción nubosa ──
        try:
            stats_acm = _extraer_producto(fs, "ACM", lat, lon, buffer_km)
            if stats_acm:
                # BCM: 0=clear, 1=cloudy → mean = fracción nubosa
                result["cloud_fraction"] = round(stats_acm["mean"], 3)
                logger.info(f"GOES | ACM cloud_fraction={result['cloud_fraction']}")
        except Exception as e:
            logger.warning(f"GOES | ACM falló: {e}")

        # ── 3. ACHA: Altura del tope de nube ──
        try:
            stats_acha = _extraer_producto(fs, "ACHA", lat, lon, buffer_km)
            if stats_acha:
                result["cloud_top_height_m"] = round(stats_acha["mean"], 0)
                logger.info(f"GOES | ACHA height={result['cloud_top_height_m']}m")
        except Exception as e:
            logger.warning(f"GOES | ACHA falló: {e}")

        # ── 4. ACTP: Fase termodinámica del tope ──
        try:
            stats_actp = _extraer_producto(fs, "ACTP", lat, lon, buffer_km)
            if stats_actp:
                # La fase es categórica; usamos la moda (valor más frecuente) del buffer
                # Como stats da mean, usamos round para aproximar la categoría dominante
                phase_code = int(round(stats_actp["median"]))
                result["cloud_top_phase"] = PHASE_LABELS.get(phase_code, "UNKNOWN")
                logger.info(f"GOES | ACTP phase={result['cloud_top_phase']}")
        except Exception as e:
            logger.warning(f"GOES | ACTP falló: {e}")

        # ── 5. RRQPE: Tasa de precipitación ──
        try:
            stats_rrqpe = _extraer_producto(fs, "RRQPE", lat, lon, buffer_km)
            if stats_rrqpe:
                result["rainfall_rate_mm_h"] = round(stats_rrqpe["mean"], 2)
                logger.info(f"GOES | RRQPE rainfall={result['rainfall_rate_mm_h']} mm/h")
        except Exception as e:
            logger.warning(f"GOES | RRQPE falló: {e}")

        # ── 6. Clasificación de nubes ──
        # Determinar phase_code para la clasificación
        phase_for_class = None
        if result["cloud_top_phase"]:
            # Invertir el mapeo para obtener el código
            inv_map = {v: k for k, v in PHASE_LABELS.items()}
            phase_for_class = inv_map.get(result["cloud_top_phase"])

        cloud_class = _clasificar_nube(
            cloud_fraction=result["cloud_fraction"],
            temp_tope_c=result["cloud_top_temperature_c"],
            height_m=result["cloud_top_height_m"],
            phase_code=phase_for_class,
            rainfall_rate=result["rainfall_rate_mm_h"],
        )
        result["cloud_classification"] = cloud_class

        # Determinar calidad global de GOES
        fields_present = sum(1 for f in [
            result["cloud_top_temperature_c"],
            result["cloud_fraction"],
            result["cloud_top_height_m"],
            result["cloud_top_phase"],
            result["rainfall_rate_mm_h"],
        ] if f is not None)

        if fields_present == 5:
            result["quality"] = "VALID"
        elif fields_present >= 2:
            result["quality"] = "PARTIAL"
        elif fields_present >= 1:
            result["quality"] = "PARTIAL"
        else:
            result["quality"] = "NO_DATA"

    except Exception as e:
        logger.error(f"GOES | Error general: {e}")
        result["quality"] = "ERROR"

    result["processing_time"] = datetime.now(timezone.utc).isoformat()

    # Guardar en cache
    if result["quality"] != "ERROR":
        goes_cache.set(cache_key, result)

    return result


async def consultar_goes(lat: float, lon: float, buffer_km: float) -> dict:
    """
    Wrapper async para no bloquear el event loop de FastAPI.
    Las consultas a S3 son I/O intensivas, se ejecutan en un thread aparte.
    """
    return await asyncio.to_thread(_consultar_goes_sync, lat, lon, buffer_km)
