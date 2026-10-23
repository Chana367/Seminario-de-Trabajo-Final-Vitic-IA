package com.vitialert.backend.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;

public record WeatherImportResultDto(
        @JsonProperty("source") String source,
        @JsonProperty("rows_read") int rowsRead,
        @JsonProperty("inserted") int inserted,
        @JsonProperty("updated") int updated,
        @JsonProperty("skipped") int skipped,
        @JsonProperty("errors") List<String> errors
) {
}
