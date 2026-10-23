# tests/conftest.py
"""
Fixtures compartidas para los tests del servicio satelital.
Proporciona mocks de S3, Sentinel Hub y datasets GOES.
"""

import pytest
import numpy as np
import xarray as xr


@pytest.fixture
def sample_goes_dataset():
    """
    Crea un dataset xarray que simula un archivo NetCDF de GOES-19 CMI Band 13.
    Incluye la proyección geoestacionaria y valores de temperatura en Kelvin.
    """
    # Grilla pequeña para tests rápidos (20x20 píxeles)
    ny, nx = 20, 20

    # Valores de la grilla en radianes (simulando la proyección geoestacionaria)
    x = np.linspace(-0.1, 0.1, nx)
    y = np.linspace(-0.1, 0.1, ny)

    # Temperaturas en Kelvin (rango realista: 220K a 300K)
    np.random.seed(42)
    cmi_data = np.random.uniform(220, 300, (ny, nx)).astype(np.float32)

    ds = xr.Dataset(
        {"CMI": (["y", "x"], cmi_data)},
        coords={"x": x, "y": y},
    )

    # Agregar atributos de proyección geoestacionaria (como en los archivos reales)
    ds["goes_imager_projection"] = xr.DataArray(0)
    ds["goes_imager_projection"].attrs = {
        "perspective_point_height": 35786023.0,
        "longitude_of_projection_origin": -75.0,
        "sweep_angle_axis": "x",
    }

    return ds


@pytest.fixture
def sample_acm_dataset():
    """Dataset que simula el producto ACM (Binary Cloud Mask)."""
    ny, nx = 20, 20
    x = np.linspace(-0.1, 0.1, nx)
    y = np.linspace(-0.1, 0.1, ny)

    # Máscara binaria: 0=clear, 1=cloudy
    np.random.seed(42)
    bcm_data = np.random.choice([0, 1], size=(ny, nx), p=[0.4, 0.6]).astype(np.float32)

    ds = xr.Dataset(
        {"BCM": (["y", "x"], bcm_data)},
        coords={"x": x, "y": y},
    )
    ds["goes_imager_projection"] = xr.DataArray(0)
    ds["goes_imager_projection"].attrs = {
        "perspective_point_height": 35786023.0,
        "longitude_of_projection_origin": -75.0,
        "sweep_angle_axis": "x",
    }
    return ds


@pytest.fixture
def sample_acha_dataset():
    """Dataset que simula el producto ACHA (Cloud Top Height)."""
    ny, nx = 10, 10
    x = np.linspace(-0.1, 0.1, nx)
    y = np.linspace(-0.1, 0.1, ny)

    # Alturas en metros (0 a 15000)
    np.random.seed(42)
    ht_data = np.random.uniform(500, 12000, (ny, nx)).astype(np.float32)

    ds = xr.Dataset(
        {"HT": (["y", "x"], ht_data)},
        coords={"x": x, "y": y},
    )
    ds["goes_imager_projection"] = xr.DataArray(0)
    ds["goes_imager_projection"].attrs = {
        "perspective_point_height": 35786023.0,
        "longitude_of_projection_origin": -75.0,
        "sweep_angle_axis": "x",
    }
    return ds


@pytest.fixture
def sample_ndvi_ndmi_tiff():
    """
    Genera bytes que simulan un GeoTIFF de 4 bandas (NDVI, NDMI, cloud_flag, SCL)
    como lo devolvería Sentinel Hub.
    """
    np.random.seed(42)
    ndvi = np.random.uniform(0.2, 0.8, (64, 64)).astype(np.float32)
    ndmi = np.random.uniform(-0.1, 0.4, (64, 64)).astype(np.float32)
    cloud = np.zeros((64, 64), dtype=np.float32)
    scl = np.full((64, 64), 4, dtype=np.float32)  # 4 = vegetation

    # Agregar algunos píxeles nublados
    cloud[0:5, :] = 1.0
    ndvi[0:5, :] = -9999
    ndmi[0:5, :] = -9999
    scl[0:5, :] = 9  # cloud high prob

    return np.stack([ndvi, ndmi, cloud, scl])
