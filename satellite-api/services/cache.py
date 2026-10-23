# services/cache.py
# Cache simple en memoria con TTL para evitar descargas redundantes
# de datos satelitales. Sin Redis ni dependencias externas.

import time
import logging
from typing import Any

from config import settings

logger = logging.getLogger(__name__)


class TTLCache:
    """
    Cache en memoria con Time-To-Live configurable.

    Cada entrada tiene un timestamp de creación. Al consultar,
    si la entrada tiene más de `ttl` segundos, se descarta.

    Uso principal: evitar que el backend Java descargue el mismo
    archivo GOES o Sentinel múltiples veces en un período corto.
    """

    def __init__(self, ttl_seconds: int | None = None):
        self._store: dict[str, tuple[float, Any]] = {}
        self._ttl = ttl_seconds or settings.cache_ttl_seconds

    def get(self, key: str) -> Any | None:
        """Devuelve el valor cacheado si existe y no expiró. None si no."""
        if key not in self._store:
            return None

        timestamp, value = self._store[key]
        age = time.time() - timestamp

        if age > self._ttl:
            del self._store[key]
            logger.debug(f"Cache EXPIRED: {key} (age={age:.0f}s > ttl={self._ttl}s)")
            return None

        logger.debug(f"Cache HIT: {key} (age={age:.0f}s)")
        return value

    def set(self, key: str, value: Any) -> None:
        """Almacena un valor con el timestamp actual."""
        self._store[key] = (time.time(), value)
        logger.debug(f"Cache SET: {key}")

    def clear(self) -> None:
        """Limpia todo el cache."""
        self._store.clear()

    def cleanup(self) -> int:
        """Elimina entradas expiradas. Devuelve cuántas eliminó."""
        now = time.time()
        expired = [k for k, (ts, _) in self._store.items() if now - ts > self._ttl]
        for k in expired:
            del self._store[k]
        return len(expired)

    @property
    def size(self) -> int:
        return len(self._store)


# Instancias globales por tipo de dato
goes_cache = TTLCache()
sentinel_cache = TTLCache()
