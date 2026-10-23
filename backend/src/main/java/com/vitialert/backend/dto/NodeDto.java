package com.vitialert.backend.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.vitialert.backend.domain.Node;

import java.time.Instant;

/**
 * Latitud y longitud se exponen porque sirven para consultar meteorologia y satelite.
 * NO son features del modelo: en un solo nodo tienen varianza cero y con varios nodos el
 * modelo aprenderia a identificar el nodo en lugar de la fisica del suelo.
 */
public record NodeDto(
        @JsonProperty("node_id") String nodeId,
        @JsonProperty("nombre") String nombre,
        @JsonProperty("descripcion") String descripcion,
        @JsonProperty("activo") boolean activo,
        @JsonProperty("finca") String finca,
        @JsonProperty("sector") String sector,
        @JsonProperty("latitud") Double latitud,
        @JsonProperty("longitud") Double longitud,
        @JsonProperty("created_at") Instant createdAt
) {

    public static NodeDto from(Node node) {
        return new NodeDto(
                node.getExternalId(),
                node.getNombre(),
                node.getDescripcion(),
                node.isActivo(),
                node.getFinca(),
                node.getSector(),
                node.getLatitud(),
                node.getLongitud(),
                node.getCreatedAt());
    }
}
