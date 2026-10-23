package com.vitialert.backend.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.vitialert.backend.domain.TelemetryReading;

import java.math.BigDecimal;
import java.time.Instant;

public record TelemetryReadingDto(
        @JsonProperty("id") Long id,
        @JsonProperty("node_id") String nodeId,
        @JsonProperty("timestamp") Instant timestamp,
        @JsonProperty("temperatura_ambiente_c") Double temperaturaAmbienteC,
        @JsonProperty("humedad_relativa_pct") Double humedadRelativaPct,
        @JsonProperty("humedad_suelo_pct") Double humedadSueloPct,
        @JsonProperty("humedad_suelo_raw") Integer humedadSueloRaw,
        @JsonProperty("velocidad_viento_kmh") Double velocidadVientoKmh,
        @JsonProperty("caudal_l_min") BigDecimal caudalLMin,
        @JsonProperty("volumen_total_l") BigDecimal volumenTotalL,
        @JsonProperty("valvula_abierta_actual") Boolean valvulaAbiertaActual,
        @JsonProperty("decision_riego_local") Boolean decisionRiegoLocal,
        @JsonProperty("quality_flag") String qualityFlag,
        @JsonProperty("quality_notes") String qualityNotes
) {

    public static TelemetryReadingDto from(TelemetryReading reading) {
        return new TelemetryReadingDto(
                reading.getId(),
                reading.getNode().getExternalId(),
                reading.getTimestampReceived(),
                reading.getTemperaturaAmbienteC(),
                reading.getHumedadRelativaPct(),
                reading.getHumedadSueloPct(),
                reading.getHumedadSueloRaw(),
                reading.getVelocidadVientoKmh(),
                reading.getCaudalLMin(),
                reading.getVolumenTotalL(),
                reading.getValvulaAbiertaActual(),
                reading.getDecisionRiegoLocal(),
                reading.getQualityFlag() == null ? null : reading.getQualityFlag().name(),
                reading.getQualityNotes());
    }
}
