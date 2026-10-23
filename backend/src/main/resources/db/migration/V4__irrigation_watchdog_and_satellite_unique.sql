-- =====================================================================
-- V4 - Watchdog de riego e idempotencia satelital
--
-- 1) satellite_observation no tenia clave natural. weather_observation si la tiene
--    (ux_weather_date_source) y por eso reimportar el mismo CSV actualiza en vez de
--    duplicar. Aca cada llamada a POST /api/satellite/refresh insertaba una fila nueva
--    aunque GOES y Sentinel devolvieran exactamente la misma captura, de modo que un
--    reintento del workflow diario duplicaba la observacion.
--
-- 2) Un evento de riego solo se cerraba en la transicion valvula true -> false. Si el
--    nodo se apagaba con la valvula abierta, o se perdia el POST del cierre, el evento
--    quedaba en OPEN indefinidamente. Como ux_irrigation_open_per_node admite un solo
--    evento abierto por nodo, ese evento colgado impedia crear cualquier riego posterior
--    y se los tragaba a todos: el historial habria terminado siendo una unica fila de
--    semanas de duracion. El watchdog vive en IrrigationService; esta migracion limpia
--    los eventos que ya quedaron colgados antes de que existiera.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Clave natural de una captura satelital: (nodo, instante de captura).
-- ---------------------------------------------------------------------

-- Primero hay que quitar los duplicados que pudieran existir, o el indice no se crea.
-- Se conserva la fila de menor id de cada grupo, que es la primera que se guardo.
DELETE FROM satellite_observation s
      USING satellite_observation d
      WHERE s.node_id     = d.node_id
        AND s.retrieved_at = d.retrieved_at
        AND s.id           > d.id;

CREATE UNIQUE INDEX IF NOT EXISTS ux_satellite_node_retrieved
    ON satellite_observation (node_id, retrieved_at);

-- ---------------------------------------------------------------------
-- 2. Baja de los eventos de riego que quedaron abiertos.
--
-- El filtro por antiguedad es imprescindible: si en el momento del deploy hay un nodo
-- regando de verdad, su evento es legitimo y no debe tocarse. Seis horas es el mismo
-- limite que aplica el watchdog (vitialert.irrigation.max-open-hours).
--
-- ended_at, duracion_segundos, volumen_final_l, volumen_aplicado_l y
-- caudal_promedio_l_min quedan en NULL a proposito: no se sabe cuando cerro la valvula
-- y el invariante del proyecto es que un dato desconocido nunca se reemplaza por un
-- valor inventado.
-- ---------------------------------------------------------------------
UPDATE irrigation_event
   SET estado        = 'ABANDONED',
       observaciones = 'Watchdog (migracion V4): el evento quedo abierto sin que se observara '
                    || 'el cierre de la valvula. Duracion, volumen aplicado y caudal promedio '
                    || 'quedan sin calcular porque se desconoce el instante de cierre.'
 WHERE estado     = 'OPEN'
   AND started_at < now() - INTERVAL '6 hours';
