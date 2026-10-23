package com.vitialert.backend.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.vitialert.backend.domain.IrrigationEvent;

import java.math.BigDecimal;
import java.time.Instant;

public record IrrigationEventDto(
        @JsonProperty("id") Long id,
        @JsonProperty("node_id") String nodeId,
        @JsonProperty("started_at") Instant startedAt,
        @JsonProperty("ended_at") Instant endedAt,
        @JsonProperty("duracion_segundos") Long duracionSegundos,
        @JsonProperty("volumen_inicial_l") BigDecimal volumenInicialL,
        @JsonProperty("volumen_final_l") BigDecimal volumenFinalL,
        @JsonProperty("volumen_aplicado_l") BigDecimal volumenAplicadoL,
        @JsonProperty("caudal_promedio_l_min") BigDecimal caudalPromedioLMin,
        @JsonProperty("estado") String estado,
        @JsonProperty("observaciones") String observaciones
) {

    public static IrrigationEventDto from(IrrigationEvent event) {
        return new IrrigationEventDto(
                event.getId(),
                event.getNode().getExternalId(),
                event.getStartedAt(),
                event.getEndedAt(),
                event.getDuracionSegundos(),
                event.getVolumenInicialL(),
                event.getVolumenFinalL(),
                event.getVolumenAplicadoL(),
                event.getCaudalPromedioLMin(),
                event.getEstado() == null ? null : event.getEstado().name(),
                event.getObservaciones());
    }
}
