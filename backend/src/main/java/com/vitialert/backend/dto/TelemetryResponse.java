package com.vitialert.backend.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;

/**
 * Respuesta que el ESP32 espera hoy. El contrato no cambia cuando en el futuro la
 * decision provenga del motor de soporte de decisiones del backend.
 */
@Schema(name = "TelemetryResponse", description = "Ordenes devueltas al nodo ESP32")
public record TelemetryResponse(

        @JsonProperty("abrir_valvula")
        @Schema(example = "true")
        boolean abrirValvula,

        @JsonProperty("encender_luz")
        @Schema(example = "true")
        boolean encenderLuz
) {
}
