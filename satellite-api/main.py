# main.py
# Punto de entrada de la API Viti-Alert Satellite Service.
#
# Este servicio se encarga exclusivamente de extraer features satelitales
# (GOES-19 + Sentinel-2) y entregarlas como JSON estructurado al
# backend Java del sistema de soporte de decisiones hídricas.
#
# NO recibe datos IoT. NO toma decisiones de riego. NO entrena modelos.

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from config import settings
from services import goes_service, sentinel_service
from models.schemas import (
    SatelliteFeatureResponse,
    GOESFeatures,
    SentinelFeatures,
    LocationInfo,
    ErrorDetail,
    HealthResponse,
)

# ── Logging ──
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("viti-alert")


# ── Lifespan ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Arrancando Viti-Alert Satellite Service v3.0...")

    if settings.sh_client_id:
        logger.info("Sentinel Hub configurado OK")
    else:
        logger.warning("Sin credenciales de Sentinel Hub. Endpoint Sentinel no funcionará.")

    logger.info(f"GOES bucket: {settings.goes_bucket} | Buffer default: {settings.default_buffer_km} km")
    logger.info("Servicio listo para recibir consultas")

    yield

    logger.info("Apagando Viti-Alert Satellite Service...")


# ── App ──
app = FastAPI(
    title="Viti-Alert Satellite Service",
    description=(
        "Servicio de extracción de variables satelitales para el sistema de "
        "soporte de decisiones hídricas VitiAlert. Transforma datos de GOES-19 "
        "y Sentinel-2 en features estructuradas consumibles por el backend Java."
    ),
    version="3.0",
    lifespan=lifespan,
)

# CORS para clientes web; no es un mecanismo de autenticacion.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", include_in_schema=False)
async def root():
    """Redirecciona la raíz al Swagger UI (/docs)."""
    return RedirectResponse(url="/docs")


# ═══════════════════════════════════════════════════════════════
# ENDPOINT PRINCIPAL: Features satelitales combinadas
# ═══════════════════════════════════════════════════════════════

@app.get(
    "/api/v1/satellite/features",
    response_model=SatelliteFeatureResponse,
    summary="Features satelitales combinadas (GOES + Sentinel)",
    description=(
        "Endpoint principal. Consulta GOES-19 y Sentinel-2 de forma independiente "
        "y devuelve todas las features satelitales en una única respuesta. "
        "Si una fuente falla, la otra se devuelve igualmente."
    ),
)
async def get_satellite_features(
    lat: float = Query(..., ge=-90, le=90, description="Latitud del centro de consulta"),
    lon: float = Query(..., ge=-180, le=180, description="Longitud del centro de consulta"),
    buffer_km: float = Query(
        default=None, ge=0.5, le=50,
        description="Radio del buffer espacial en km (default: 5.0)",
    ),
    sentinel_days_back: int = Query(
        default=None, ge=1, le=90,
        description="Rango de búsqueda de imágenes Sentinel en días (default: 30)",
    ),
):
    if buffer_km is None:
        buffer_km = settings.default_buffer_km
    if sentinel_days_back is None:
        sentinel_days_back = settings.sentinel_days_back

    logger.info(
        f"Request features ({lat}, {lon}) | buffer={buffer_km}km | "
        f"sentinel_days_back={sentinel_days_back}"
    )

    errors = []
    goes_data = None
    sentinel_data = None

    # ── GOES (independiente) ──
    try:
        goes_raw = await goes_service.consultar_goes(lat, lon, buffer_km)
        if goes_raw and goes_raw.get("quality") != "NO_DATA":
            goes_data = GOESFeatures(**goes_raw)
        else:
            errors.append(ErrorDetail(
                source="GOES",
                message="No se obtuvieron datos GOES-19 válidos para las coordenadas",
            ))
    except Exception as e:
        logger.error(f"Error consultando GOES: {e}")
        errors.append(ErrorDetail(source="GOES", message=str(e)))

    # ── Sentinel (independiente) ──
    if settings.sh_client_id:
        try:
            sentinel_raw = sentinel_service.consultar_sentinel(
                lat, lon, sentinel_days_back, buffer_km,
            )
            if sentinel_raw:
                sentinel_data = SentinelFeatures(**sentinel_raw)
            else:
                errors.append(ErrorDetail(
                    source="SENTINEL",
                    message="No se obtuvieron datos Sentinel-2 válidos",
                ))
        except Exception as e:
            logger.error(f"Error consultando Sentinel: {e}")
            errors.append(ErrorDetail(source="SENTINEL", message=str(e)))
    else:
        errors.append(ErrorDetail(
            source="SENTINEL",
            message="Sentinel Hub no configurado (faltan credenciales)",
        ))

    # ── Calidad global ──
    if goes_data and sentinel_data:
        overall_quality = "VALID"
    elif goes_data or sentinel_data:
        overall_quality = "PARTIAL"
    else:
        overall_quality = "NO_DATA"

    return SatelliteFeatureResponse(
        timestamp=datetime.now(timezone.utc).isoformat(),
        location=LocationInfo(lat=lat, lon=lon, buffer_km=buffer_km),
        goes=goes_data,
        sentinel=sentinel_data,
        overall_quality=overall_quality,
        errors=errors,
    )


# ═══════════════════════════════════════════════════════════════
# ENDPOINT: GOES individual
# ═══════════════════════════════════════════════════════════════

@app.get(
    "/api/v1/satellite/goes",
    response_model=GOESFeatures,
    summary="Features atmosféricas GOES-19",
    description="Devuelve únicamente las features GOES-19 (temperatura, nubosidad, clasificación).",
)
async def get_goes_features(
    lat: float = Query(..., ge=-90, le=90, description="Latitud"),
    lon: float = Query(..., ge=-180, le=180, description="Longitud"),
    buffer_km: float = Query(
        default=None, ge=0.5, le=50,
        description="Radio del buffer en km",
    ),
):
    if buffer_km is None:
        buffer_km = settings.default_buffer_km

    logger.info(f"Request GOES ({lat}, {lon}) | buffer={buffer_km}km")

    goes_raw = await goes_service.consultar_goes(lat, lon, buffer_km)
    return GOESFeatures(**goes_raw)


# ═══════════════════════════════════════════════════════════════
# ENDPOINT: Sentinel individual
# ═══════════════════════════════════════════════════════════════

@app.get(
    "/api/v1/satellite/sentinel",
    response_model=SentinelFeatures,
    summary="Features de vegetación Sentinel-2",
    description="Devuelve únicamente los índices NDVI y NDMI de Sentinel-2.",
)
async def get_sentinel_features(
    lat: float = Query(..., ge=-90, le=90, description="Latitud"),
    lon: float = Query(..., ge=-180, le=180, description="Longitud"),
    dias_atras: int = Query(
        default=None, ge=1, le=90,
        description="Rango de búsqueda en días",
    ),
    buffer_km: float = Query(
        default=None, ge=0.5, le=50,
        description="Radio del buffer en km",
    ),
):
    if dias_atras is None:
        dias_atras = settings.sentinel_days_back
    if buffer_km is None:
        buffer_km = settings.default_buffer_km

    logger.info(f"Request Sentinel ({lat}, {lon}) | dias_atras={dias_atras} | buffer={buffer_km}km")

    sentinel_raw = sentinel_service.consultar_sentinel(lat, lon, dias_atras, buffer_km)
    if sentinel_raw:
        return SentinelFeatures(**sentinel_raw)
    return SentinelFeatures(quality="NO_DATA")


# ═══════════════════════════════════════════════════════════════
# ENDPOINT: NDVI (deprecated, compatibilidad con el viejo endpoint)
# ═══════════════════════════════════════════════════════════════

@app.get(
    "/api/v1/finca/{finca_id}/ndvi",
    summary="[DEPRECATED] NDVI de la finca",
    description=(
        "Endpoint mantenido para compatibilidad. Usar /api/v1/satellite/sentinel "
        "en su lugar. Ya no devuelve recomendaciones de riego."
    ),
    deprecated=True,
)
async def obtener_ndvi_deprecated(
    finca_id: str,
    lat: float = Query(..., ge=-90, le=90, description="Latitud de la finca"),
    lon: float = Query(..., ge=-180, le=180, description="Longitud de la finca"),
    dias_atras: int = Query(default=30, ge=1, le=90, description="Rango de búsqueda en días"),
):
    """
    Endpoint deprecated que mantiene la ruta anterior /finca/{finca_id}/ndvi
    pero delega al nuevo SentinelService. Ya no devuelve 'recomendacion'.
    """
    logger.info(f"[DEPRECATED] Request NDVI finca '{finca_id}' ({lat}, {lon})")

    sentinel_raw = sentinel_service.consultar_sentinel(lat, lon, dias_atras)

    ndvi_data = {}
    if sentinel_raw:
        ndvi_data = {
            "ndvi_promedio": sentinel_raw.get("ndvi_mean"),
            "ndvi_minimo": sentinel_raw.get("ndvi_min"),
            "ndvi_maximo": sentinel_raw.get("ndvi_max"),
            "fecha_imagen": sentinel_raw.get("image_date"),
        }

    return {
        "finca_id": finca_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "coordenadas": {"lat": lat, "lon": lon},
        "ndvi": ndvi_data,
        "_deprecated": "Usar /api/v1/satellite/sentinel en su lugar",
    }


# ═══════════════════════════════════════════════════════════════
# ENDPOINT: Health Check
# ═══════════════════════════════════════════════════════════════

@app.get("/health", response_model=HealthResponse, summary="Estado del servicio")
async def health_check():
    """
    Verifica que el servicio satelital esté operativo.
    Render usa esto para determinar si el servicio está vivo.
    """
    sentinel_ok = bool(settings.sh_client_id and settings.sh_client_secret)

    # GOES no requiere credenciales (S3 público), siempre está "configurado"
    goes_ok = True

    if goes_ok and sentinel_ok:
        status = "ok"
    elif goes_ok or sentinel_ok:
        status = "degraded"
    else:
        status = "error"

    return HealthResponse(
        status=status,
        goes_configured=goes_ok,
        sentinel_configured=sentinel_ok,
        timestamp=datetime.now(timezone.utc).isoformat(),
        version="3.0",
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=True)
