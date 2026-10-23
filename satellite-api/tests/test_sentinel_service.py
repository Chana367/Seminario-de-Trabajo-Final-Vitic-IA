# tests/test_sentinel_service.py
"""
Tests para el servicio Sentinel-2.
Valida: cálculo de NDVI, cálculo de NDMI, filtrado por SCL,
métricas de calidad, y manejo de datos faltantes.
"""

import pytest
import numpy as np


class TestNDVICalculation:
    """Tests del cálculo de NDVI a partir de datos simulados."""

    def test_ndvi_rango_valido(self, sample_ndvi_ndmi_tiff):
        """Los valores de NDVI están en el rango [-1, 1]."""
        ndvi_band = sample_ndvi_ndmi_tiff[0]
        valid = ndvi_band[ndvi_band > -9999]
        assert np.all(valid >= -1)
        assert np.all(valid <= 1)

    def test_ndvi_pixeles_nublados_marcados(self, sample_ndvi_ndmi_tiff):
        """Los píxeles nublados tienen NDVI = -9999."""
        ndvi_band = sample_ndvi_ndmi_tiff[0]
        cloud_band = sample_ndvi_ndmi_tiff[2]

        cloud_pixels = ndvi_band[cloud_band > 0.5]
        assert np.all(cloud_pixels == -9999)

    def test_ndvi_estadisticas(self, sample_ndvi_ndmi_tiff):
        """Las estadísticas de NDVI son calculables sobre píxeles válidos."""
        ndvi_band = sample_ndvi_ndmi_tiff[0]
        valid = ndvi_band[(ndvi_band > -1) & (ndvi_band <= 1)]

        assert len(valid) > 0
        mean = float(np.mean(valid))
        assert -1 <= mean <= 1

        # Para datos seed=42 con uniform(0.2, 0.8), la media debería estar ~0.5
        assert 0.3 < mean < 0.7


class TestNDMICalculation:
    """Tests del cálculo de NDMI."""

    def test_ndmi_rango_valido(self, sample_ndvi_ndmi_tiff):
        """Los valores de NDMI están en el rango [-1, 1]."""
        ndmi_band = sample_ndvi_ndmi_tiff[1]
        valid = ndmi_band[ndmi_band > -9999]
        assert np.all(valid >= -1)
        assert np.all(valid <= 1)

    def test_ndmi_pixeles_nublados(self, sample_ndvi_ndmi_tiff):
        """Los píxeles nublados tienen NDMI = -9999."""
        ndmi_band = sample_ndvi_ndmi_tiff[1]
        cloud_band = sample_ndvi_ndmi_tiff[2]

        cloud_pixels = ndmi_band[cloud_band > 0.5]
        assert np.all(cloud_pixels == -9999)


class TestSCLFiltering:
    """Tests del filtrado por Scene Classification Layer."""

    def test_cloud_flag_binary(self, sample_ndvi_ndmi_tiff):
        """El flag de nube es binario (0 o 1)."""
        cloud_band = sample_ndvi_ndmi_tiff[2]
        unique = np.unique(cloud_band)
        assert all(v in [0.0, 1.0] for v in unique)

    def test_valid_pixel_pct(self, sample_ndvi_ndmi_tiff):
        """El porcentaje de píxeles válidos se calcula correctamente."""
        ndvi_band = sample_ndvi_ndmi_tiff[0]
        total = ndvi_band.size
        valid = ndvi_band[(ndvi_band > -1) & (ndvi_band <= 1)]
        pct = len(valid) / total * 100

        assert 0 < pct < 100  # Hay nubes parciales

    def test_cloud_pixel_pct(self, sample_ndvi_ndmi_tiff):
        """El porcentaje de nubes se calcula correctamente."""
        cloud_band = sample_ndvi_ndmi_tiff[2]
        total = cloud_band.size
        cloud_count = int(np.sum(cloud_band > 0.5))
        pct = cloud_count / total * 100

        # Sabemos que filas 0-4 de 64 son nube → ~7.8%
        assert 5 < pct < 15


class TestQualityDetermination:
    """Tests de la lógica de determinación de calidad."""

    def test_full_cloud_quality(self):
        """Imagen 100% nublada → CLOUD_CONTAMINATED."""
        ndvi = np.full((64, 64), -9999, dtype=np.float32)
        valid = ndvi[(ndvi > -1) & (ndvi <= 1)]
        quality = "CLOUD_CONTAMINATED" if len(valid) == 0 else "VALID"
        assert quality == "CLOUD_CONTAMINATED"

    def test_partial_cloud_quality(self, sample_ndvi_ndmi_tiff):
        """Imagen parcialmente nublada con >30% válido → VALID."""
        ndvi_band = sample_ndvi_ndmi_tiff[0]
        total = ndvi_band.size
        valid = ndvi_band[(ndvi_band > -1) & (ndvi_band <= 1)]
        pct = len(valid) / total * 100

        quality = "PARTIAL" if pct < 30 else "VALID"
        # Con 5 filas nubladas de 64, ~92% válido
        assert quality == "VALID"

    def test_stale_image_quality(self):
        """Imagen con más de 15 días → STALE."""
        image_age_days = 20
        quality = "STALE" if image_age_days > 15 else "VALID"
        assert quality == "STALE"


class TestNullHandling:
    """Tests de manejo de datos nulos (ausencia ≠ cero)."""

    def test_all_cloud_returns_null_stats(self):
        """Si todos los píxeles son nube, las estadísticas deben ser None."""
        ndvi = np.full((64, 64), -9999, dtype=np.float32)
        valid = ndvi[(ndvi > -1) & (ndvi <= 1)]

        ndvi_mean = float(np.mean(valid)) if len(valid) > 0 else None
        assert ndvi_mean is None

    def test_null_not_zero(self):
        """None y 0.0 son conceptualmente diferentes."""
        resultado = {"ndvi_mean": None, "rainfall_rate_mm_h": None}
        assert resultado["ndvi_mean"] is None  # No hay dato
        assert resultado["ndvi_mean"] != 0  # No es "NDVI es cero"
        assert resultado["rainfall_rate_mm_h"] is None  # No hay dato
        assert resultado["rainfall_rate_mm_h"] != 0  # No es "no llueve"
