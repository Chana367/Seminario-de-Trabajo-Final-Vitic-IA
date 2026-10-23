# models/schemas.py
# Modelos Pydantic para validación y tipado de las respuestas JSON.
# Estos schemas definen el contrato de la API con el backend Java.

from pydantic import BaseModel, Field
from typing import Optional


# ── Ubicación ──

class LocationInfo(BaseModel):
    """Información de ubicación de la consulta."""
    lat: float = Field(..., description="Latitud del centro de consulta")
    lon: float = Field(..., description="Longitud del centro de consulta")
    buffer_km: float = Field(..., description="Radio del buffer espacial en km")


# ── GOES Features ──

class CloudClassification(BaseModel):
    """
    Clasificación meteorológica de la nube basada en múltiples
    productos GOES-R ABI Level 2.
    """
    cloud_type: str = Field(
        ...,
        description=(
            "Tipo de nube clasificado. Valores posibles: CLEAR, STRATOCUMULUS, "
            "LOW_CLOUD, ALTOCUMULUS, ALTOSTRATUS, MID_CLOUD, CIRRUS, HIGH_CLOUD, "
            "TOWERING_CUMULUS, DEEP_CONVECTIVE, NIMBOSTRATUS, CUMULONIMBUS, UNKNOWN"
        ),
    )
    cloud_category: Optional[str] = Field(
        None,
        description="Categoría vertical: LOW, MID, HIGH, o null si despejado",
    )
    precipitation_potential: str = Field(
        ...,
        description="Potencial de precipitación estimado: NONE, LOW, MODERATE, HIGH, UNKNOWN",
    )
    description: str = Field(
        ...,
        description="Descripción meteorológica del estado de nubosidad",
    )
    classification_criteria: list[str] = Field(
        default_factory=list,
        description="Criterios utilizados para la clasificación (trazabilidad)",
    )


class GOESFeatures(BaseModel):
    """Features atmosféricas extraídas de GOES-19."""
    satellite: str = Field(default="GOES-19")
    observation_time: Optional[str] = Field(None, description="Timestamp de la observación GOES")
    processing_time: Optional[str] = Field(None, description="Timestamp del procesamiento")

    # Temperatura de tope de nube (CMI Band 13)
    cloud_top_temperature_c: Optional[float] = Field(
        None, description="Temperatura media del tope de nube en el buffer (°C)",
    )
    cloud_top_temp_min_c: Optional[float] = Field(
        None, description="Temperatura mínima del tope de nube en el buffer (°C)",
    )
    cloud_top_temp_max_c: Optional[float] = Field(
        None, description="Temperatura máxima del tope de nube en el buffer (°C)",
    )
    cloud_top_temp_std_c: Optional[float] = Field(
        None, description="Desviación estándar de temperatura en el buffer (°C)",
    )
    cloud_temperature_delta_c: Optional[float] = Field(
        None, description="Cambio de temperatura del tope respecto a ~10 min antes (°C)",
    )

    # Cloud Mask (ACM)
    cloud_fraction: Optional[float] = Field(
        None, description="Fracción nubosa en el buffer (0.0 a 1.0)",
    )

    # Cloud Top Height (ACHA)
    cloud_top_height_m: Optional[float] = Field(
        None, description="Altura media del tope de nube en metros (ACHA)",
    )

    # Cloud Top Phase (ACTP)
    cloud_top_phase: Optional[str] = Field(
        None, description="Fase termodinámica del tope: CLEAR, WATER, SUPERCOOLED_WATER, MIXED, ICE, UNKNOWN",
    )

    # Rainfall Rate (RRQPE)
    rainfall_rate_mm_h: Optional[float] = Field(
        None, description="Tasa de precipitación instantánea en mm/h (RRQPE). null = dato no disponible, NO equivale a 0",
    )

    # Clasificación de nube
    cloud_classification: Optional[CloudClassification] = Field(
        None, description="Clasificación meteorológica basada en múltiples productos GOES",
    )

    # Metadatos
    buffer_pixels: Optional[int] = Field(None, description="Cantidad de píxeles en la ventana del buffer")
    data_age_minutes: Optional[float] = Field(None, description="Antigüedad del dato en minutos")
    quality: str = Field(
        default="NO_DATA",
        description="Calidad del dato: VALID, PARTIAL, STALE, NO_DATA, ERROR",
    )


# ── Sentinel Features ──

class SentinelFeatures(BaseModel):
    """Features de vegetación y humedad extraídas de Sentinel-2 L2A."""
    image_date: Optional[str] = Field(None, description="Fecha de la imagen Sentinel-2 utilizada (YYYY-MM-DD)")
    processing_time: Optional[str] = Field(None, description="Timestamp del procesamiento")

    # NDVI
    ndvi_mean: Optional[float] = Field(None, description="NDVI promedio de píxeles válidos")
    ndvi_min: Optional[float] = Field(None, description="NDVI mínimo")
    ndvi_max: Optional[float] = Field(None, description="NDVI máximo")
    ndvi_std: Optional[float] = Field(None, description="Desviación estándar del NDVI")

    # NDMI
    ndmi_mean: Optional[float] = Field(None, description="NDMI promedio (humedad de vegetación)")
    ndmi_min: Optional[float] = Field(None, description="NDMI mínimo")
    ndmi_max: Optional[float] = Field(None, description="NDMI máximo")
    ndmi_std: Optional[float] = Field(None, description="Desviación estándar del NDMI")

    # Calidad
    valid_pixel_pct: Optional[float] = Field(None, description="Porcentaje de píxeles válidos")
    cloud_pixel_pct: Optional[float] = Field(None, description="Porcentaje de píxeles nublados")
    image_age_days: Optional[int] = Field(None, description="Antigüedad de la imagen en días")
    quality: str = Field(
        default="NO_DATA",
        description="Calidad: VALID, PARTIAL, STALE, CLOUD_CONTAMINATED, NO_DATA, ERROR",
    )


# ── Errores ──

class ErrorDetail(BaseModel):
    """Detalle de error por fuente de datos."""
    source: str = Field(..., description="Fuente que falló: GOES, SENTINEL")
    message: str = Field(..., description="Descripción del error")


# ── Respuesta principal ──

class SatelliteFeatureResponse(BaseModel):
    """
    Respuesta completa del endpoint /satellite/features.
    Combina GOES y Sentinel en una única respuesta estructurada.
    """
    timestamp: str = Field(..., description="Timestamp de la respuesta")
    location: LocationInfo
    goes: Optional[GOESFeatures] = Field(
        None,
        description="Features atmosféricas GOES-19. null si el servicio no pudo obtener datos.",
    )
    sentinel: Optional[SentinelFeatures] = Field(
        None,
        description="Features de vegetación Sentinel-2. null si el servicio no pudo obtener datos.",
    )
    overall_quality: str = Field(
        ...,
        description="Calidad global: VALID (ambas fuentes OK), PARTIAL (una fuente), NO_DATA (ninguna)",
    )
    errors: list[ErrorDetail] = Field(
        default_factory=list,
        description="Lista de errores por fuente, vacía si todo OK",
    )


# ── Health Check ──

class HealthResponse(BaseModel):
    """Respuesta del health check."""
    status: str = Field(..., description="ok / degraded / error")
    goes_configured: bool = Field(..., description="True si el acceso a GOES está disponible")
    sentinel_configured: bool = Field(..., description="True si Sentinel Hub tiene credenciales")
    timestamp: str
    version: str
