package com.vitialert.backend.controller;

import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

/**
 * Conversion de los parametros temporales de la API. Todo el backend trabaja en UTC.
 * Se aceptan instantes ISO-8601 ({@code 2026-09-03T10:00:00Z}), fechas-hora con offset
 * y fechas sueltas ({@code 2026-09-03}, interpretada como el comienzo del dia en UTC).
 */
final class RequestTimes {

    private RequestTimes() {
    }

    static Instant parse(String value, String parameterName) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("El parametro " + parameterName + " es obligatorio.");
        }
        String raw = value.trim();
        try {
            if (raw.length() == 10) {
                return LocalDate.parse(raw).atStartOfDay(ZoneOffset.UTC).toInstant();
            }
            if (raw.endsWith("Z")) {
                return Instant.parse(raw);
            }
            return OffsetDateTime.parse(raw).toInstant();
        } catch (RuntimeException ex) {
            throw new IllegalArgumentException("El parametro " + parameterName
                    + " no es una fecha/hora ISO-8601 valida: " + value);
        }
    }

    static Instant parseOrDefault(String value, String parameterName, Instant fallback) {
        return (value == null || value.isBlank()) ? fallback : parse(value, parameterName);
    }

    static Instant defaultFrom(Instant to) {
        return to.minus(Duration.ofHours(24));
    }
}
