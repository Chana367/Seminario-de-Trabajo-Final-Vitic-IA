CREATE TABLE satellite_observation (
    id                          BIGSERIAL PRIMARY KEY,
    node_id                     BIGINT      NOT NULL,
    retrieved_at                TIMESTAMPTZ NOT NULL,
    goes_observation_time       TIMESTAMPTZ,
    sentinel_image_date         DATE,
    cloud_top_temperature_c     DOUBLE PRECISION,
    cloud_temperature_delta_c   DOUBLE PRECISION,
    cloud_fraction              DOUBLE PRECISION,
    rainfall_rate_mm_h          DOUBLE PRECISION,
    ndvi_mean                   DOUBLE PRECISION,
    ndmi_mean                   DOUBLE PRECISION,
    overall_quality             VARCHAR(30),
    CONSTRAINT fk_satellite_node FOREIGN KEY (node_id) REFERENCES node (id)
);

CREATE INDEX ix_satellite_node_retrieved
    ON satellite_observation (node_id, retrieved_at DESC);
