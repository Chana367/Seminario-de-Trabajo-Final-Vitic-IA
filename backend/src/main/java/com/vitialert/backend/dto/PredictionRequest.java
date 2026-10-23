package com.vitialert.backend.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.time.Instant;
import java.util.Map;

/**
 * Peticion al servicio Python de inferencia. Las features viajan como mapa
 * nombre -&gt; valor, con los mismos nombres que las columnas del CSV de entrenamiento.
 * Un valor faltante viaja como {@code null} explicito: Python decide como imputarlo.
 */
public record PredictionRequest(
        @JsonProperty("node_id") String nodeId,
        @JsonProperty("timestamp") Instant timestamp,
        @JsonProperty("features") Map<String, Double> features
) {
}
