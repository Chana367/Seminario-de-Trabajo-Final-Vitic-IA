-- =====================================================================
-- V2 - Simplificacion del prototipo
--
-- 1) Se elimina decision_record. Mientras no exista el modelo predictivo, esa tabla
--    guardaba una copia de datos que ya estan en telemetry_reading:
--      decision_local  = telemetry_reading.decision_riego_local
--      decision_final  = decision_local (no hay decision de backend)
--      decision_backend / model_version = siempre NULL
--      source          = siempre 'LOCAL_FALLBACK'
--    La trazabilidad de la decision del ESP32 se conserva intacta, fila por fila,
--    en telemetry_reading. La tabla vuelve cuando se conecte la inferencia, que es
--    cuando aparece informacion nueva que comparar.
--
-- 2) Se elimina node.api_key. La autenticacion queda fuera del alcance del
--    prototipo academico (ambiente de laboratorio).
-- =====================================================================

DROP TABLE IF EXISTS decision_record;

ALTER TABLE node DROP COLUMN IF EXISTS api_key;
