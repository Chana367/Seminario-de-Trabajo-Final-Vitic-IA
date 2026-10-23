-- =====================================================================
-- VitiAlert / Vitic-AI - esquema inicial
-- Base de datos: PostgreSQL
-- Todos los instantes se guardan en UTC (timestamptz).
-- =====================================================================

CREATE TABLE node (
    id              BIGSERIAL PRIMARY KEY,
    external_id     VARCHAR(64)  NOT NULL,
    nombre          VARCHAR(120),
    descripcion     VARCHAR(500),
    activo          BOOLEAN      NOT NULL DEFAULT TRUE,
    finca           VARCHAR(120),
    sector          VARCHAR(120),
    latitud         DOUBLE PRECISION,
    longitud        DOUBLE PRECISION,
    api_key         VARCHAR(128),
    created_at      TIMESTAMPTZ  NOT NULL,
    updated_at      TIMESTAMPTZ  NOT NULL,
    CONSTRAINT ux_node_external_id UNIQUE (external_id)
);

COMMENT ON COLUMN node.latitud  IS 'Solo para resolver informacion espacial. No es feature del modelo.';
COMMENT ON COLUMN node.longitud IS 'Solo para resolver informacion espacial. No es feature del modelo.';

-- ---------------------------------------------------------------------
-- Telemetria IoT: una fila inmutable por cada POST del ESP32.
-- ---------------------------------------------------------------------
CREATE TABLE telemetry_reading (
    id                      BIGSERIAL PRIMARY KEY,
    node_id                 BIGINT       NOT NULL,
    timestamp_received      TIMESTAMPTZ  NOT NULL,
    temperatura_ambiente_c  DOUBLE PRECISION,
    humedad_relativa_pct    DOUBLE PRECISION,
    humedad_suelo_pct       DOUBLE PRECISION,
    humedad_suelo_raw       INTEGER,
    velocidad_viento_kmh    DOUBLE PRECISION,
    caudal_l_min            NUMERIC(10, 3),
    volumen_total_l         NUMERIC(12, 3),
    valvula_abierta_actual  BOOLEAN,
    decision_riego_local    BOOLEAN,
    quality_flag            VARCHAR(20)  NOT NULL,
    quality_notes           VARCHAR(500),
    created_at              TIMESTAMPTZ  NOT NULL,
    CONSTRAINT fk_telemetry_node FOREIGN KEY (node_id) REFERENCES node (id)
);

CREATE INDEX ix_telemetry_node_ts ON telemetry_reading (node_id, timestamp_received DESC);

-- Indice parcial para la resolucion de lags por timestamp real: solo interesan las
-- observaciones que efectivamente tienen humedad de suelo.
CREATE INDEX ix_telemetry_node_soil_ts
    ON telemetry_reading (node_id, timestamp_received)
    WHERE humedad_suelo_pct IS NOT NULL;

-- ---------------------------------------------------------------------
-- Eventos de riego reconstruidos a partir de las transiciones de valvula.
-- ---------------------------------------------------------------------
CREATE TABLE irrigation_event (
    id                      BIGSERIAL PRIMARY KEY,
    node_id                 BIGINT       NOT NULL,
    started_at              TIMESTAMPTZ  NOT NULL,
    ended_at                TIMESTAMPTZ,
    duracion_segundos       BIGINT,
    volumen_inicial_l       NUMERIC(12, 3),
    volumen_final_l         NUMERIC(12, 3),
    volumen_aplicado_l      NUMERIC(12, 3),
    caudal_promedio_l_min   NUMERIC(10, 3),
    estado                  VARCHAR(25)  NOT NULL,
    observaciones           VARCHAR(500),
    CONSTRAINT fk_irrigation_node FOREIGN KEY (node_id) REFERENCES node (id)
);

CREATE INDEX ix_irrigation_node_started ON irrigation_event (node_id, started_at DESC);
CREATE INDEX ix_irrigation_node_ended   ON irrigation_event (node_id, ended_at);

-- Un nodo no puede tener dos riegos abiertos simultaneamente.
CREATE UNIQUE INDEX ux_irrigation_open_per_node
    ON irrigation_event (node_id)
    WHERE estado = 'OPEN';

-- ---------------------------------------------------------------------
-- Trazabilidad de cada decision devuelta al nodo.
-- ---------------------------------------------------------------------
CREATE TABLE decision_record (
    id                  BIGSERIAL PRIMARY KEY,
    node_id             BIGINT       NOT NULL,
    decision_timestamp  TIMESTAMPTZ  NOT NULL,
    decision_local      BOOLEAN,
    decision_backend    BOOLEAN,
    decision_final      BOOLEAN      NOT NULL,
    accion              VARCHAR(15)  NOT NULL,
    motivo              VARCHAR(500),
    source              VARCHAR(25)  NOT NULL,
    model_version       VARCHAR(60),
    CONSTRAINT fk_decision_node FOREIGN KEY (node_id) REFERENCES node (id)
);

CREATE INDEX ix_decision_node_ts ON decision_record (node_id, decision_timestamp DESC);

-- ---------------------------------------------------------------------
-- Meteorologia diaria del Data Miner. Fuente distinta de la telemetria IoT.
-- ---------------------------------------------------------------------
CREATE TABLE weather_observation (
    id                      BIGSERIAL PRIMARY KEY,
    observation_date        DATE         NOT NULL,
    source                  VARCHAR(60)  NOT NULL,
    temp_max_c              DOUBLE PRECISION,
    temp_mean_c             DOUBLE PRECISION,
    humidity_mean_pct       DOUBLE PRECISION,
    humidity_min_pct        DOUBLE PRECISION,
    wind_mean_kmh           DOUBLE PRECISION,
    wind_max_kmh            DOUBLE PRECISION,
    precipitation_mm        DOUBLE PRECISION,
    solar_radiation_mj_m2   DOUBLE PRECISION,
    et0_mm                  DOUBLE PRECISION,
    vpd_max_kpa             DOUBLE PRECISION,
    created_at              TIMESTAMPTZ  NOT NULL,
    updated_at              TIMESTAMPTZ  NOT NULL,
    CONSTRAINT ux_weather_date_source UNIQUE (observation_date, source)
);

CREATE INDEX ix_weather_date ON weather_observation (observation_date);
