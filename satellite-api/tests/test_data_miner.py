from __future__ import annotations

import pytest

import data_miner


def test_refresco_satelital_reintenta_un_arranque_en_frio(monkeypatch):
    responses = iter([
        {"unavailable_nodes": 1, "stored_observations": 0},
        {"unavailable_nodes": 0, "stored_observations": 1},
    ])
    waits: list[float] = []
    monkeypatch.setattr(
        data_miner,
        "refresh_satellite",
        lambda backend_url, session: next(responses),
    )

    result = data_miner.refresh_satellite_with_retry(
        "https://backend.example",
        object(),
        attempts=2,
        delay_seconds=3,
        sleeper=waits.append,
    )

    assert result["stored_observations"] == 1
    assert waits == [3]


def test_refresco_satelital_falla_visible_si_no_hay_datos(monkeypatch):
    monkeypatch.setattr(
        data_miner,
        "refresh_satellite",
        lambda backend_url, session: {
            "unavailable_nodes": 1,
            "stored_observations": 0,
        },
    )

    with pytest.raises(RuntimeError, match="termino sin datos"):
        data_miner.refresh_satellite_with_retry(
            "https://backend.example",
            object(),
            attempts=2,
            delay_seconds=0,
            sleeper=lambda seconds: None,
        )


def test_refresco_satelital_acepta_duplicado_como_resultado_valido(monkeypatch):
    monkeypatch.setattr(
        data_miner,
        "refresh_satellite",
        lambda backend_url, session: {
            "unavailable_nodes": 0,
            "stored_observations": 0,
            "skipped_duplicates": 1,
        },
    )

    result = data_miner.refresh_satellite_with_retry(
        "https://backend.example", object(), sleeper=lambda seconds: None
    )

    assert result["skipped_duplicates"] == 1
