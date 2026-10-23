# tests/test_endpoints.py
"""
Tests de integración para los endpoints de la API.
Usa FastAPI TestClient para verificar rutas, respuestas y manejo de errores.
Las llamadas a servicios externos (S3, Sentinel Hub) están mockeadas.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


class TestHealthEndpoint:
    """Tests del endpoint /health."""

    def test_health_returns_200(self):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_structure(self):
        resp = client.get("/health")
        data = resp.json()
        assert "status" in data
        assert "goes_configured" in data
        assert "sentinel_configured" in data
        assert "timestamp" in data
        assert "version" in data

    def test_health_version(self):
        resp = client.get("/health")
        assert resp.json()["version"] == "3.0"

    def test_health_no_modelo_cargado(self):
        """El health check NO incluye 'modelo_cargado'."""
        resp = client.get("/health")
        data = resp.json()
        assert "modelo_cargado" not in data

    def test_health_goes_always_configured(self):
        """GOES usa S3 público, siempre está 'configured'."""
        resp = client.get("/health")
        assert resp.json()["goes_configured"] is True


class TestSatelliteFeaturesEndpoint:
    """Tests del endpoint /api/v1/satellite/features."""

    @pytest.fixture(autouse=True)
    def sentinel_configured_for_mocked_tests(self, monkeypatch):
        # Los proveedores estan simulados. No depender del .env de una persona.
        from config import settings
        monkeypatch.setattr(settings, "sh_client_id", "sentinel-test-client")

    @patch("services.goes_service.consultar_goes")
    @patch("services.sentinel_service.consultar_sentinel")
    def test_unconfigured_sentinel_is_not_called(self, mock_sentinel, mock_goes, monkeypatch):
        from config import settings
        monkeypatch.setattr(settings, "sh_client_id", "")
        mock_goes.return_value = {"quality": "NO_DATA"}
        resp = client.get("/api/v1/satellite/features?lat=-31.655&lon=-68.575")
        assert resp.status_code == 200
        assert resp.json()["sentinel"] is None
        assert resp.json()["overall_quality"] == "NO_DATA"
        mock_sentinel.assert_not_called()

    def test_missing_lat_lon(self):
        """Sin lat/lon → 422."""
        resp = client.get("/api/v1/satellite/features")
        assert resp.status_code == 422

    def test_invalid_lat(self):
        """Latitud fuera de rango → 422."""
        resp = client.get("/api/v1/satellite/features?lat=999&lon=-68.575")
        assert resp.status_code == 422

    def test_invalid_lon(self):
        """Longitud fuera de rango → 422."""
        resp = client.get("/api/v1/satellite/features?lat=-31.655&lon=999")
        assert resp.status_code == 422

    def test_invalid_buffer(self):
        """Buffer negativo → 422."""
        resp = client.get("/api/v1/satellite/features?lat=-31.655&lon=-68.575&buffer_km=-1")
        assert resp.status_code == 422

    @patch("services.goes_service.consultar_goes")
    @patch("services.sentinel_service.consultar_sentinel")
    def test_both_sources_ok(self, mock_sentinel, mock_goes):
        """Con ambas fuentes OK → VALID."""
        mock_goes.return_value = {
            "satellite": "GOES-19",
            "observation_time": "2026-09-03T20:00:00Z",
            "processing_time": "2026-09-03T20:01:00Z",
            "cloud_top_temperature_c": -34.6,
            "cloud_top_temp_min_c": -42.1,
            "cloud_top_temp_max_c": -28.3,
            "cloud_top_temp_std_c": 4.2,
            "cloud_temperature_delta_c": -2.1,
            "cloud_fraction": 0.62,
            "cloud_top_height_m": 6500,
            "cloud_top_phase": "ICE",
            "rainfall_rate_mm_h": 0.0,
            "cloud_classification": {
                "cloud_type": "HIGH_CLOUD",
                "cloud_category": "HIGH",
                "precipitation_potential": "LOW",
                "description": "Nube alta",
                "classification_criteria": ["height=6500m"],
            },
            "buffer_pixels": 25,
            "data_age_minutes": 8.0,
            "quality": "VALID",
        }
        mock_sentinel.return_value = {
            "image_date": "2026-08-30",
            "processing_time": "2026-09-03T20:01:00Z",
            "ndvi_mean": 0.61,
            "ndvi_min": 0.42,
            "ndvi_max": 0.78,
            "ndvi_std": 0.09,
            "ndmi_mean": 0.22,
            "ndmi_min": 0.10,
            "ndmi_max": 0.35,
            "ndmi_std": 0.06,
            "valid_pixel_pct": 91.2,
            "cloud_pixel_pct": 8.8,
            "image_age_days": 4,
            "quality": "VALID",
        }

        resp = client.get("/api/v1/satellite/features?lat=-31.655&lon=-68.575")
        assert resp.status_code == 200
        data = resp.json()

        assert data["overall_quality"] == "VALID"
        assert data["goes"] is not None
        assert data["sentinel"] is not None
        assert data["goes"]["cloud_top_temperature_c"] == -34.6
        assert data["sentinel"]["ndvi_mean"] == 0.61
        assert data["sentinel"]["ndmi_mean"] == 0.22
        assert data["location"]["lat"] == -31.655
        assert data["location"]["lon"] == -68.575
        assert len(data["errors"]) == 0

    @patch("services.goes_service.consultar_goes")
    @patch("services.sentinel_service.consultar_sentinel")
    def test_goes_fail_sentinel_ok(self, mock_sentinel, mock_goes):
        """GOES falla, Sentinel OK → PARTIAL + goes null."""
        mock_goes.return_value = {"quality": "NO_DATA"}
        mock_sentinel.return_value = {
            "image_date": "2026-08-30",
            "processing_time": "2026-09-03T20:01:00Z",
            "ndvi_mean": 0.55,
            "ndvi_min": 0.30,
            "ndvi_max": 0.75,
            "ndvi_std": 0.10,
            "ndmi_mean": 0.18,
            "ndmi_min": 0.05,
            "ndmi_max": 0.30,
            "ndmi_std": 0.07,
            "valid_pixel_pct": 85.0,
            "cloud_pixel_pct": 15.0,
            "image_age_days": 3,
            "quality": "VALID",
        }

        resp = client.get("/api/v1/satellite/features?lat=-31.655&lon=-68.575")
        data = resp.json()

        assert resp.status_code == 200
        assert data["overall_quality"] == "PARTIAL"
        assert data["goes"] is None
        assert data["sentinel"] is not None
        assert len(data["errors"]) >= 1

    @patch("services.goes_service.consultar_goes")
    @patch("services.sentinel_service.consultar_sentinel")
    def test_goes_ok_sentinel_fail(self, mock_sentinel, mock_goes):
        """Sentinel falla, GOES OK → PARTIAL + sentinel null."""
        mock_goes.return_value = {
            "satellite": "GOES-19",
            "observation_time": None,
            "processing_time": None,
            "cloud_top_temperature_c": -20.0,
            "cloud_top_temp_min_c": -25.0,
            "cloud_top_temp_max_c": -15.0,
            "cloud_top_temp_std_c": 3.0,
            "cloud_temperature_delta_c": 1.0,
            "cloud_fraction": 0.40,
            "cloud_top_height_m": None,
            "cloud_top_phase": None,
            "rainfall_rate_mm_h": None,
            "cloud_classification": {
                "cloud_type": "MID_CLOUD",
                "cloud_category": "MID",
                "precipitation_potential": "LOW",
                "description": "Nube de nivel medio",
                "classification_criteria": [],
            },
            "buffer_pixels": 25,
            "data_age_minutes": None,
            "quality": "PARTIAL",
        }
        mock_sentinel.return_value = None

        resp = client.get("/api/v1/satellite/features?lat=-31.655&lon=-68.575")
        data = resp.json()

        assert resp.status_code == 200
        assert data["overall_quality"] == "PARTIAL"
        assert data["goes"] is not None
        assert data["sentinel"] is None

    @patch("services.goes_service.consultar_goes")
    @patch("services.sentinel_service.consultar_sentinel")
    def test_null_rainfall_not_zero(self, mock_sentinel, mock_goes):
        """rainfall_rate_mm_h = null ≠ 0 (ausencia de dato ≠ ausencia de lluvia)."""
        mock_goes.return_value = {
            "satellite": "GOES-19",
            "observation_time": None,
            "processing_time": None,
            "cloud_top_temperature_c": -30.0,
            "cloud_top_temp_min_c": -35.0,
            "cloud_top_temp_max_c": -25.0,
            "cloud_top_temp_std_c": 3.0,
            "cloud_temperature_delta_c": -1.0,
            "cloud_fraction": 0.50,
            "cloud_top_height_m": None,
            "cloud_top_phase": None,
            "rainfall_rate_mm_h": None,  # No hay dato, no es que no llueve
            "cloud_classification": None,
            "buffer_pixels": 25,
            "data_age_minutes": None,
            "quality": "PARTIAL",
        }
        mock_sentinel.return_value = None

        resp = client.get("/api/v1/satellite/features?lat=-31.655&lon=-68.575")
        data = resp.json()
        assert data["goes"]["rainfall_rate_mm_h"] is None


class TestDeprecatedNDVIEndpoint:
    """Tests del endpoint deprecated /finca/{id}/ndvi."""

    @patch("services.sentinel_service.consultar_sentinel")
    def test_deprecated_ndvi_returns_data(self, mock_sentinel):
        mock_sentinel.return_value = {
            "ndvi_mean": 0.55,
            "ndvi_min": 0.30,
            "ndvi_max": 0.75,
            "image_date": "2026-08-30",
        }

        resp = client.get("/api/v1/finca/pocito-01/ndvi?lat=-31.655&lon=-68.575")
        data = resp.json()

        assert resp.status_code == 200
        assert data["finca_id"] == "pocito-01"
        assert data["ndvi"]["ndvi_promedio"] == 0.55
        assert "_deprecated" in data

    @patch("services.sentinel_service.consultar_sentinel")
    def test_deprecated_ndvi_no_recomendacion(self, mock_sentinel):
        """El endpoint deprecated NO devuelve recomendación de riego."""
        mock_sentinel.return_value = {
            "ndvi_mean": 0.42,
            "ndvi_min": 0.20,
            "ndvi_max": 0.60,
            "image_date": "2026-08-30",
        }

        resp = client.get("/api/v1/finca/pocito-01/ndvi?lat=-31.655&lon=-68.575")
        data = resp.json()

        assert "recomendacion" not in data
        assert "Riego actual" not in str(data)


class TestClimaEspacialRemoved:
    """Verifica que el endpoint viejo de granizo NO existe."""

    def test_clima_espacial_not_found(self):
        """El viejo endpoint /clima-espacial no existe."""
        resp = client.get(
            "/api/v1/finca/pocito-01/clima-espacial"
            "?lat=-31.655&lon=-68.575&temp_superficie=35&viento_superficie=22"
        )
        assert resp.status_code == 404 or resp.status_code == 405


class TestParameterValidation:
    """Tests de validación de parámetros de entrada."""

    def test_buffer_km_default(self):
        """Sin buffer_km explícito, usa el default."""
        # Solo verificamos que no falle la validación
        # (la llamada real a GOES fallará pero eso es esperado)
        with patch("services.goes_service.consultar_goes") as mock:
            mock.return_value = {"quality": "NO_DATA"}
            resp = client.get("/api/v1/satellite/features?lat=-31.655&lon=-68.575")
            assert resp.status_code == 200

    def test_buffer_km_too_large(self):
        """Buffer > 50 km → 422."""
        resp = client.get("/api/v1/satellite/features?lat=-31.655&lon=-68.575&buffer_km=100")
        assert resp.status_code == 422

    def test_sentinel_days_back_too_large(self):
        """Más de 90 días → 422."""
        resp = client.get("/api/v1/satellite/features?lat=-31.655&lon=-68.575&sentinel_days_back=200")
        assert resp.status_code == 422
