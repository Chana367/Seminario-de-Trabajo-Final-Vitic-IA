package com.vitialert.backend.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Respuesta del servicio Python de inferencia.
 *
 * <p>{@code irrigate} es la unica variable que el backend necesita para decidir; el
 * resto se guarda para trazabilidad. Si {@code irrigate} llega null la prediccion se
 * considera no utilizable y se aplica el fallback local.</p>
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record PredictionResponse(
        @JsonProperty("irrigate") Boolean irrigate,
        @JsonProperty("probability") Double probability,
        @JsonProperty("predicted_soil_moisture_t_plus_24h") Double predictedSoilMoistureTPlus24h,
        @JsonProperty("model_version") String modelVersion
) {
}
