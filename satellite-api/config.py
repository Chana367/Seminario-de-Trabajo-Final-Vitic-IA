# config.py
# Configuración centralizada del servicio satelital.
# Todo lo configurable se lee del .env o de variables de entorno.

import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """
    Configuración del servicio Viti-Alert Satellite.
    Los valores se leen del archivo .env o de variables de entorno
    del sistema (Render las inyecta directamente).
    """

    # -- Sentinel Hub --
    sh_client_id: str = Field(default="", description="Client ID de Sentinel Hub (CDSE)")
    sh_client_secret: str = Field(default="", description="Client Secret de Sentinel Hub (CDSE)")

    # -- GOES-19 --
    goes_bucket: str = Field(default="noaa-goes19", description="Bucket S3 de NOAA para GOES")
    goes_satellite_id: str = Field(default="G19", description="Identificador del satélite GOES")

    # -- Defaults de procesamiento --
    default_buffer_km: float = Field(default=5.0, description="Radio del buffer espacial en km")
    sentinel_days_back: int = Field(default=30, description="Días hacia atrás para buscar imágenes Sentinel-2")
    cache_ttl_seconds: int = Field(default=300, description="Tiempo de vida del cache en memoria (segundos)")

    # -- Logging --
    log_level: str = Field(default="INFO", description="Nivel de logging")

    # -- Server --
    port: int = Field(default=8000, description="Puerto del servidor")

    # -- Modelo / Predicción (compatibilidad) --
    model_path: str = Field(default="modelo_granizo_rf.pkl", description="Ruta al modelo .pkl")
    umbral_alerta: float = Field(default=0.40, description="Umbral de alerta de granizo")

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=(),
    )


# Instancia global — se importa desde cualquier módulo
settings = Settings()
