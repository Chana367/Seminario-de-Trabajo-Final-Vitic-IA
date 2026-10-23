package com.vitialert.backend.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;

/**
 * Payload exacto que envia hoy el firmware del ESP32. NO modificar los nombres JSON:
 * el contrato con la maqueta debe seguir funcionando sin recompilar el firmware.
 *
 * <p>Solo {@code nodo_id} es obligatorio. Un campo ausente no invalida el POST: se
 * persiste igual y la lectura queda marcada con {@code MISSING} para que Ciencia de
 * Datos sepa que falta (nunca se rellena con ceros artificiales).</p>
 *
 * <p>Los rangos declarados son los limites fisicamente posibles. Los valores raros
 * pero posibles se aceptan y se marcan con {@code OUT_OF_RANGE} o {@code SUSPECT}.</p>
 */
@Schema(name = "TelemetryRequest", description = "Payload de telemetria enviado por el nodo ESP32")
public record TelemetryRequest(

        @JsonProperty("nodo_id")
        @NotBlank(message = "nodo_id es obligatorio")
        @Size(max = 64, message = "nodo_id admite hasta 64 caracteres")
        @Schema(example = "1")
        String nodoId,

        @JsonProperty("temperatura_ambiente_c")
        @DecimalMin(value = "-40.0", message = "temperatura_ambiente_c debe ser >= -40")
        @DecimalMax(value = "70.0", message = "temperatura_ambiente_c debe ser <= 70")
        @Schema(example = "28.4")
        Double temperaturaAmbienteC,

        @JsonProperty("humedad_relativa_pct")
        @DecimalMin(value = "0.0", message = "humedad_relativa_pct debe ser >= 0")
        @DecimalMax(value = "100.0", message = "humedad_relativa_pct debe ser <= 100")
        @Schema(example = "45")
        Double humedadRelativaPct,

        @JsonProperty("humedad_suelo_pct")
        @DecimalMin(value = "0.0", message = "humedad_suelo_pct debe ser >= 0")
        @DecimalMax(value = "100.0", message = "humedad_suelo_pct debe ser <= 100")
        @Schema(example = "22")
        Double humedadSueloPct,

        @JsonProperty("humedad_suelo_raw")
        @Min(value = 0, message = "humedad_suelo_raw debe ser >= 0")
        @Schema(example = "2730")
        Integer humedadSueloRaw,

        @JsonProperty("velocidad_viento_kmh")
        @DecimalMin(value = "0.0", message = "velocidad_viento_kmh debe ser >= 0")
        @DecimalMax(value = "200.0", message = "velocidad_viento_kmh debe ser <= 200")
        @Schema(example = "18.5")
        Double velocidadVientoKmh,

        @JsonProperty("caudal_l_min")
        @DecimalMin(value = "0.0", message = "caudal_l_min debe ser >= 0")
        @Schema(example = "7.80")
        BigDecimal caudalLMin,

        @JsonProperty("volumen_total_l")
        @DecimalMin(value = "0.0", message = "volumen_total_l debe ser >= 0")
        @Schema(example = "124.60")
        BigDecimal volumenTotalL,

        @JsonProperty("valvula_abierta_actual")
        @Schema(example = "true")
        Boolean valvulaAbiertaActual,

        @JsonProperty("decision_riego_local")
        @Schema(example = "true")
        Boolean decisionRiegoLocal
) {
}
