package com.vitialert.backend;

import com.vitialert.backend.domain.Node;
import com.vitialert.backend.domain.QualityFlag;
import com.vitialert.backend.domain.TelemetryReading;

import java.math.BigDecimal;
import java.time.Instant;

/** Construccion de lecturas con timestamps controlados. */
public final class TestSupport {

    private TestSupport() {
    }

    public static TelemetryReading reading(Node node,
                                           Instant timestamp,
                                           Double soilMoisture,
                                           boolean valveOpen,
                                           BigDecimal volume) {
        return TelemetryReading.builder()
                .node(node)
                .timestampReceived(timestamp)
                .temperaturaAmbienteC(25.0)
                .humedadRelativaPct(50.0)
                .humedadSueloPct(soilMoisture)
                .humedadSueloRaw(2500)
                .velocidadVientoKmh(10.0)
                .caudalLMin(valveOpen ? new BigDecimal("7.500") : BigDecimal.ZERO)
                .volumenTotalL(volume)
                .valvulaAbiertaActual(valveOpen)
                .decisionRiegoLocal(valveOpen)
                .quality(QualityFlag.VALID, null)
                .build();
    }

    public static TelemetryReading reading(Node node, Instant timestamp, Double soilMoisture) {
        return reading(node, timestamp, soilMoisture, false, new BigDecimal("100.000"));
    }
}
