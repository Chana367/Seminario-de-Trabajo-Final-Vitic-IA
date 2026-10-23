# tests/test_goes_service.py
"""
Tests para el servicio GOES.
Valida: conversión lat/lon, extracción de buffer, estadísticas,
clasificación de nubes, y manejo de datos faltantes.
"""

import pytest
import numpy as np

from services.goes_service import (
    _latlon_a_pixel,
    _calcular_radio_buffer,
    _extraer_estadisticas_buffer,
    _clasificar_nube,
    PHASE_LABELS,
)


class TestLatLonAPixel:
    """Tests de conversión de coordenadas geográficas a píxeles GOES."""

    def test_conversion_basica(self, sample_goes_dataset):
        """Coordenadas dentro del rango producen índices válidos."""
        iy, ix = _latlon_a_pixel(-31.655, -68.575, sample_goes_dataset)
        assert isinstance(iy, int)
        assert isinstance(ix, int)
        assert 0 <= iy < sample_goes_dataset.sizes["y"]
        assert 0 <= ix < sample_goes_dataset.sizes["x"]

    def test_coordenadas_distintas_dan_pixeles_distintos(self, sample_goes_dataset):
        """Dos coordenadas suficientemente separadas dan píxeles diferentes."""
        iy1, ix1 = _latlon_a_pixel(-31.0, -68.0, sample_goes_dataset)
        iy2, ix2 = _latlon_a_pixel(-35.0, -65.0, sample_goes_dataset)
        assert (iy1, ix1) != (iy2, ix2)


class TestCalcularRadioBuffer:
    """Tests para la conversión de buffer_km a radio en píxeles."""

    def test_buffer_5km_resolucion_2km(self):
        """5 km con resolución 2 km → radio 2 → ventana 5×5."""
        radio = _calcular_radio_buffer(5.0, 2.0)
        assert radio == 2

    def test_buffer_5km_resolucion_10km(self):
        """5 km con resolución 10 km → radio 1 → ventana 3×3."""
        radio = _calcular_radio_buffer(5.0, 10.0)
        assert radio == 1

    def test_buffer_minimo_1(self):
        """El radio mínimo siempre es 1 (ventana 3×3 mínimo)."""
        radio = _calcular_radio_buffer(0.5, 10.0)
        assert radio >= 1

    def test_buffer_grande(self):
        """Buffer de 20 km con resolución 2 km → radio 10."""
        radio = _calcular_radio_buffer(20.0, 2.0)
        assert radio == 10


class TestExtraerEstadisticasBuffer:
    """Tests para la extracción de estadísticas del buffer espacial."""

    def test_estadisticas_basicas(self, sample_goes_dataset):
        """Extrae correctamente mean, min, max, std del buffer."""
        iy, ix = 10, 10  # Centro del dataset 20x20
        stats = _extraer_estadisticas_buffer(sample_goes_dataset, "CMI", iy, ix, radio=2)

        assert stats is not None
        assert "mean" in stats
        assert "min" in stats
        assert "max" in stats
        assert "std" in stats
        assert "valid_pixels" in stats
        assert "total_pixels" in stats
        assert stats["min"] <= stats["mean"] <= stats["max"]
        assert stats["std"] >= 0
        assert stats["total_pixels"] == 25  # 5×5

    def test_borde_de_imagen(self, sample_goes_dataset):
        """En el borde del dataset, recorta sin error."""
        stats = _extraer_estadisticas_buffer(sample_goes_dataset, "CMI", 0, 0, radio=2)
        assert stats is not None
        assert stats["total_pixels"] < 25  # Menos de 5×5 porque está en la esquina

    def test_radio_1(self, sample_goes_dataset):
        """Radio 1 produce ventana 3×3 = 9 píxeles."""
        stats = _extraer_estadisticas_buffer(sample_goes_dataset, "CMI", 10, 10, radio=1)
        assert stats is not None
        assert stats["total_pixels"] == 9

    def test_variable_inexistente(self, sample_goes_dataset):
        """Variable que no existe en el dataset devuelve None."""
        stats = _extraer_estadisticas_buffer(sample_goes_dataset, "NO_EXISTE", 10, 10, radio=2)
        assert stats is None

    def test_cloud_mask_fraccion(self, sample_acm_dataset):
        """La media del BCM da la fracción nubosa (valor entre 0 y 1)."""
        stats = _extraer_estadisticas_buffer(sample_acm_dataset, "BCM", 10, 10, radio=2)
        assert stats is not None
        assert 0 <= stats["mean"] <= 1


class TestClasificacionNubes:
    """
    Tests para la clasificación meteorológica de nubes.
    Verifica que la lógica de decisión funciona con distintas combinaciones
    de variables de entrada.
    """

    def test_cielo_despejado(self):
        """Fracción nubosa baja → CLEAR."""
        result = _clasificar_nube(
            cloud_fraction=0.05,
            temp_tope_c=15.0,
            height_m=None,
            phase_code=0,
            rainfall_rate=0.0,
        )
        assert result["cloud_type"] == "CLEAR"
        assert result["precipitation_potential"] == "NONE"

    def test_cumulonimbus_con_precipitacion(self):
        """Precipitación activa + tope alto → CUMULONIMBUS."""
        result = _clasificar_nube(
            cloud_fraction=0.95,
            temp_tope_c=-55.0,
            height_m=12000,
            phase_code=4,  # ICE
            rainfall_rate=8.5,
        )
        assert result["cloud_type"] == "CUMULONIMBUS"
        assert result["precipitation_potential"] == "HIGH"

    def test_nimbostratus_precipitacion_sin_conveccion(self):
        """Precipitación activa pero sin tope alto → NIMBOSTRATUS."""
        result = _clasificar_nube(
            cloud_fraction=0.90,
            temp_tope_c=-15.0,
            height_m=4000,
            phase_code=3,  # MIXED
            rainfall_rate=2.0,
        )
        assert result["cloud_type"] == "NIMBOSTRATUS"
        assert result["precipitation_potential"] == "HIGH"

    def test_estratocumulo_bajo(self):
        """Nube baja de agua líquida → STRATOCUMULUS."""
        result = _clasificar_nube(
            cloud_fraction=0.70,
            temp_tope_c=5.0,
            height_m=1500,
            phase_code=1,  # WATER
            rainfall_rate=0.0,
        )
        assert result["cloud_type"] == "STRATOCUMULUS"
        assert result["cloud_category"] == "LOW"
        assert result["precipitation_potential"] == "LOW"

    def test_cirrus_alto_hielo(self):
        """Nube alta de hielo con temp no extrema → CIRRUS."""
        result = _clasificar_nube(
            cloud_fraction=0.40,
            temp_tope_c=-30.0,
            height_m=9000,
            phase_code=4,  # ICE
            rainfall_rate=0.0,
        )
        assert result["cloud_type"] == "CIRRUS"
        assert result["precipitation_potential"] == "NONE"

    def test_conveccion_profunda(self):
        """Tope muy alto y muy frío → DEEP_CONVECTIVE."""
        result = _clasificar_nube(
            cloud_fraction=0.95,
            temp_tope_c=-62.0,
            height_m=13000,
            phase_code=4,  # ICE
            rainfall_rate=0.0,
        )
        assert result["cloud_type"] == "DEEP_CONVECTIVE"
        assert result["precipitation_potential"] == "HIGH"

    def test_altocumulo_nivel_medio(self):
        """Nube de nivel medio de agua → ALTOCUMULUS."""
        result = _clasificar_nube(
            cloud_fraction=0.50,
            temp_tope_c=-5.0,
            height_m=4500,
            phase_code=1,  # WATER
            rainfall_rate=0.0,
        )
        assert result["cloud_type"] == "ALTOCUMULUS"
        assert result["cloud_category"] == "MID"

    def test_altostratus_fase_mixta(self):
        """Nube media con fase mixta → ALTOSTRATUS."""
        result = _clasificar_nube(
            cloud_fraction=0.60,
            temp_tope_c=-10.0,
            height_m=5000,
            phase_code=3,  # MIXED
            rainfall_rate=0.0,
        )
        assert result["cloud_type"] == "ALTOSTRATUS"
        assert result["precipitation_potential"] == "MODERATE"

    def test_fallback_sin_altura(self):
        """Sin dato de altura, usa temperatura como proxy."""
        result = _clasificar_nube(
            cloud_fraction=0.60,
            temp_tope_c=-45.0,
            height_m=None,
            phase_code=None,
            rainfall_rate=None,
        )
        assert result["cloud_type"] == "TOWERING_CUMULUS"
        assert "sin altura disponible" in result["classification_criteria"][0]

    def test_unknown_sin_datos(self):
        """Sin ningún dato → UNKNOWN."""
        result = _clasificar_nube(
            cloud_fraction=None,
            temp_tope_c=None,
            height_m=None,
            phase_code=None,
            rainfall_rate=None,
        )
        assert result["cloud_type"] == "UNKNOWN"
        assert result["precipitation_potential"] == "UNKNOWN"

    def test_criterios_trazabilidad(self):
        """La clasificación incluye criterios que permiten trazabilidad."""
        result = _clasificar_nube(
            cloud_fraction=0.05,
            temp_tope_c=15.0,
            height_m=1000,
            phase_code=0,
            rainfall_rate=0.0,
        )
        assert len(result["classification_criteria"]) > 0
        assert isinstance(result["classification_criteria"][0], str)

    def test_precipitacion_con_temp_fria_sin_altura(self):
        """Precipitación activa + tope frío pero sin altura → CUMULONIMBUS."""
        result = _clasificar_nube(
            cloud_fraction=0.90,
            temp_tope_c=-55.0,
            height_m=None,
            phase_code=4,
            rainfall_rate=5.0,
        )
        assert result["cloud_type"] == "CUMULONIMBUS"
        assert result["precipitation_potential"] == "HIGH"


class TestPhaseLabels:
    """Verifica el mapeo de códigos de fase a etiquetas."""

    def test_todos_los_codigos(self):
        """Todos los códigos 0-5 tienen etiqueta."""
        for code in range(6):
            assert code in PHASE_LABELS
            assert isinstance(PHASE_LABELS[code], str)

    def test_clear_es_cero(self):
        assert PHASE_LABELS[0] == "CLEAR"

    def test_ice_es_cuatro(self):
        assert PHASE_LABELS[4] == "ICE"
