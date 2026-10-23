# tests/test_cache.py
"""
Tests para el cache TTL en memoria.
"""

import time
import pytest

from services.cache import TTLCache


class TestTTLCache:
    """Tests del cache con Time-To-Live."""

    def test_set_and_get(self):
        cache = TTLCache(ttl_seconds=60)
        cache.set("key1", {"value": 42})
        assert cache.get("key1") == {"value": 42}

    def test_miss(self):
        cache = TTLCache(ttl_seconds=60)
        assert cache.get("nonexistent") is None

    def test_ttl_expiry(self):
        """Entradas expiradas devuelven None."""
        cache = TTLCache(ttl_seconds=1)
        cache.set("key1", "valor")
        assert cache.get("key1") == "valor"

        time.sleep(1.1)
        assert cache.get("key1") is None

    def test_size(self):
        cache = TTLCache(ttl_seconds=60)
        assert cache.size == 0
        cache.set("a", 1)
        cache.set("b", 2)
        assert cache.size == 2

    def test_clear(self):
        cache = TTLCache(ttl_seconds=60)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.size == 0
        assert cache.get("a") is None

    def test_overwrite(self):
        cache = TTLCache(ttl_seconds=60)
        cache.set("key", "old")
        cache.set("key", "new")
        assert cache.get("key") == "new"

    def test_cleanup(self):
        """cleanup() elimina entradas expiradas."""
        cache = TTLCache(ttl_seconds=1)
        cache.set("a", 1)
        cache.set("b", 2)
        time.sleep(1.1)
        cache.set("c", 3)  # Esta no expira

        removed = cache.cleanup()
        assert removed == 2
        assert cache.size == 1
        assert cache.get("c") == 3

    def test_different_types(self):
        """El cache puede almacenar distintos tipos de datos."""
        cache = TTLCache(ttl_seconds=60)
        cache.set("dict", {"a": 1})
        cache.set("list", [1, 2, 3])
        cache.set("str", "hello")
        cache.set("float", 3.14)
        cache.set("none", None)

        assert cache.get("dict") == {"a": 1}
        assert cache.get("list") == [1, 2, 3]
        assert cache.get("str") == "hello"
        assert cache.get("float") == 3.14
        # None como valor es distinto de "no encontrado"
        # El cache devuelve None para ambos casos, lo cual es una limitación conocida
