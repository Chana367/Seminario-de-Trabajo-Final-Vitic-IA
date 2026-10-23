package com.vitialert.backend.service;

import com.vitialert.backend.domain.Node;
import com.vitialert.backend.domain.QualityFlag;
import com.vitialert.backend.domain.TelemetryReading;
import com.vitialert.backend.repository.NodeRepository;
import com.vitialert.backend.repository.TelemetryReadingRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * La agregacion se apoya solo en timestamps: nunca se asume "una fila = una hora".
 * Tambien se comprueba la integracion del tiempo de valvula abierta y del consumo de agua.
 */
@SpringBootTest
@ActiveProfiles("test")
@Transactional
class AggregationServiceTest {

    private static final Instant START = Instant.parse("2026-09-02T10:00:00Z");

    @Autowired
    private AggregationService aggregationService;

    @Autowired
    private TelemetryReadingRepository telemetryReadingRepository;

    @Autowired
    private NodeRepository nodeRepository;

    @Test
    void agrupaPorHoraEIntegraValvulaAbiertaYConsumo() {
        Node node = nodeRepository.save(new Node("agg-1"));

        // Hora 1: valvula abierta, el contador sube 1 L por minuto (100 -> 160).
        for (int minute = 0; minute < 60; minute++) {
            save(node, START.plus(Duration.ofMinutes(minute)), 30.0, 20.0 + minute * 0.1,
                    true, new BigDecimal(100 + minute + ".000"));
        }
        // Hora 2: valvula cerrada, el contador se mantiene en 160.
        for (int minute = 0; minute < 60; minute++) {
            save(node, START.plus(Duration.ofMinutes(60 + minute)), 45.0, 25.0,
                    false, new BigDecimal("160.000"));
        }

        Map<Instant, HourlyPoint> series =
                aggregationService.hourlySeries(node.getId(), START, START.plus(Duration.ofHours(2)));

        assertThat(series).hasSize(2);

        HourlyPoint first = series.get(START);
        assertThat(first).isNotNull();
        assertThat(first.sampleCount()).isEqualTo(60);
        assertThat(first.soilMoistureMean()).isCloseTo(30.0, within(1e-9));
        assertThat(first.soilMoistureMin()).isCloseTo(30.0, within(1e-9));
        // 60 intervalos de 60 s con la valvula abierta (incluye el salto 10:59 -> 11:00).
        assertThat(first.valveOpenSeconds()).isEqualTo(3600L);
        assertThat(first.waterVolumeUsed()).isEqualByComparingTo("60.000");

        HourlyPoint second = series.get(START.plus(Duration.ofHours(1)));
        assertThat(second).isNotNull();
        assertThat(second.sampleCount()).isEqualTo(60);
        assertThat(second.soilMoistureMean()).isCloseTo(45.0, within(1e-9));
        assertThat(second.valveOpenSeconds()).isZero();
        assertThat(second.waterVolumeUsed()).isEqualByComparingTo("0.000");
    }

    @Test
    void noContabilizaRiegoDuranteLosHuecosEnQueElNodoEstuvoOffline() {
        Node node = nodeRepository.save(new Node("agg-2"));

        // Dos lecturas con la valvula abierta separadas por 30 minutos: el nodo estuvo caido.
        save(node, START, 30.0, 20.0, true, new BigDecimal("10.000"));
        save(node, START.plus(Duration.ofMinutes(30)), 30.0, 20.0, true, new BigDecimal("400.000"));

        Map<Instant, HourlyPoint> series =
                aggregationService.hourlySeries(node.getId(), START, START.plus(Duration.ofHours(1)));

        assertThat(series).hasSize(1);
        assertThat(series.get(START).valveOpenSeconds()).isZero();
        assertThat(series.get(START).waterVolumeUsed()).isNull();
    }

    @Test
    void rechazaRangosInvalidos() {
        Node node = nodeRepository.save(new Node("agg-3"));

        assertThrows(IllegalArgumentException.class,
                () -> aggregationService.hourlySeries(node.getId(), START, START));
        assertThrows(IllegalArgumentException.class,
                () -> aggregationService.hourlySeries(node.getId(), START, START.plus(Duration.ofDays(60))));
    }

    private void save(Node node, Instant at, Double soil, Double temp, boolean valveOpen, BigDecimal volume) {
        telemetryReadingRepository.save(TelemetryReading.builder()
                .node(node)
                .timestampReceived(at)
                .temperaturaAmbienteC(temp)
                .humedadRelativaPct(55.0)
                .humedadSueloPct(soil)
                .humedadSueloRaw(2500)
                .velocidadVientoKmh(12.0)
                .caudalLMin(valveOpen ? new BigDecimal("1.000") : BigDecimal.ZERO)
                .volumenTotalL(volume)
                .valvulaAbiertaActual(valveOpen)
                .decisionRiegoLocal(valveOpen)
                .quality(QualityFlag.VALID, null)
                .build());
    }
}
