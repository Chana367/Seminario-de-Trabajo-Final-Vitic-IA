package com.vitialert.backend.exception;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.time.Instant;
import java.util.Map;

/** Cuerpo JSON uniforme para todos los errores de la API. */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record ApiErrorResponse(
        @JsonProperty("timestamp") Instant timestamp,
        @JsonProperty("status") int status,
        @JsonProperty("error") String error,
        @JsonProperty("message") String message,
        @JsonProperty("path") String path,
        @JsonProperty("details") Map<String, String> details
) {

    public static ApiErrorResponse of(int status, String error, String message, String path) {
        return new ApiErrorResponse(Instant.now(), status, error, message, path, null);
    }

    public static ApiErrorResponse of(int status, String error, String message, String path, Map<String, String> details) {
        return new ApiErrorResponse(Instant.now(), status, error, message, path, details);
    }
}
