package com.vitialert.backend.service;

import com.vitialert.backend.TestSupport;
import com.vitialert.backend.domain.IrrigationEvent;
import com.vitialert.backend.domain.IrrigationEventStatus;
import com.vitialert.backend.domain.Node;
import com.vitialert.backend.domain.TelemetryReading;
import com.vitialert.backend.repository.NodeRepository;
import com.vitialert.backend.repository.TelemetryReadingRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.domain.PageRequest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

/** Deteccion de apertura y cierre de riego, y calculo del consumo de agua. */
@SpringBootTest
@ActiveProfiles("test")
@Transactional
class IrrigationServiceTest {

    @Autowired
    private IrrigationService irrigationService;

    @Autowired
    private TelemetryReadingRepository telemetryReadingRepository;

    @Autowired
    private NodeRepository nodeRepository;

    private Node newNode(String externalId) {
        return nodeRepository.save(new Node(externalId));
    }

    private TelemetryReading save(Node node, Instant at, boolean valveOpen, String volume) {
        return telemetryReadingRepository.save(
                TestSupport.reading(node, at, 25.0, valveOpen, new BigDecimal(volume)));
    }

    private IrrigationEvent firstEvent(Node node, Instant around) {
        return irrigationService.findRange(node.getId(), around.minusSeconds(600), around.plusSeconds(600),
                PageRequest.of(0, 10)).getContent().get(0);
    }

    @Test
    void abreUnEventoCuandoLaValvulaPasaDeCerradaAAbierta() {
        Node node = newNode("evt-1");
        Instant t0 = Instant.parse("2026-09-01T10:00:00Z");

        irrigationService.processReading(node, save(node, t0, false, "100.000"));
        assertThat(irrigationService.findCurrent(node.getId())).isEmpty();

        irrigationService.processReading(node, save(node, t0.plusSeconds(30), true, "100.000"));

        Optional<IrrigationEvent> current = irrigationService.findCurrent(node.getId());
        assertThat(current).isPresent();
        assertThat(current.get().getEstado()).isEqualTo(IrrigationEventStatus.OPEN);
        assertThat(current.get().getStartedAt()).isEqualTo(t0.plusSeconds(30));
        assertThat(current.get().getVolumenInicialL()).isEqualByComparingTo("100.000");
        assertThat(current.get().getEndedAt()).isNull();
    }

    @Test
    void cierraElEventoYCalculaVolumenDuracionYCaudalPromedio() {
        Node node = newNode("evt-2");
        Instant start = Instant.parse("2026-09-01T10:00:00Z");
        Instant end = start.plus(Duration.ofMinutes(5));

        irrigationService.processReading(node, save(node, start, true, "100.000"));
        irrigationService.processReading(node, save(node, start.plusSeconds(120), true, "115.000"));
        irrigationService.processReading(node, save(node, end, false, "137.500"));

        assertThat(irrigationService.findCurrent(node.getId())).isEmpty();

        IrrigationEvent event = firstEvent(node, start);
        assertThat(event.getEstado()).isEqualTo(IrrigationEventStatus.CLOSED);
        assertThat(event.getEndedAt()).isEqualTo(end);
        assertThat(event.getDuracionSegundos()).isEqualTo(300L);
        assertThat(event.getVolumenAplicadoL()).isEqualByComparingTo("37.500");
        // 37,5 L en 5 minutos => 7,5 L/min
        assertThat(event.getCaudalPromedioLMin()).isEqualByComparingTo("7.500");
    }

    @Test
    void detectaElReinicioDelContadorDelEsp32YLoMarcaComoAdvertencia() {
        Node node = newNode("evt-3");
        Instant start = Instant.parse("2026-09-01T12:00:00Z");
        Instant end = start.plus(Duration.ofMinutes(2));

        irrigationService.processReading(node, save(node, start, true, "980.000"));
        // El nodo se reinicio: el contador acumulado vuelve a empezar desde cero.
        irrigationService.processReading(node, save(node, end, false, "12.000"));

        IrrigationEvent event = firstEvent(node, start);
        assertThat(event.getEstado()).isEqualTo(IrrigationEventStatus.CLOSED_WITH_WARNING);
        assertThat(event.getVolumenAplicadoL()).isEqualByComparingTo("12.000");
        assertThat(event.getObservaciones()).contains("reiniciado");
    }

    @Test
    void noCreaEventosMientrasLaValvulaSigueCerrada() {
        Node node = newNode("evt-4");
        Instant t0 = Instant.parse("2026-09-01T14:00:00Z");

        irrigationService.processReading(node, save(node, t0, false, "10.000"));
        irrigationService.processReading(node, save(node, t0.plusSeconds(30), false, "10.000"));
        irrigationService.processReading(node, save(node, t0.plusSeconds(60), false, "10.000"));

        assertThat(irrigationService.findCurrent(node.getId())).isEmpty();
        assertThat(irrigationService.findRange(node.getId(), t0.minusSeconds(60), t0.plusSeconds(600),
                PageRequest.of(0, 10)).getTotalElements()).isZero();
    }

    @Test
    void mantieneUnUnicoEventoAbiertoMientrasLaValvulaSigueAbierta() {
        Node node = newNode("evt-5");
        Instant t0 = Instant.parse("2026-09-01T16:00:00Z");

        // El ESP32 informa el estado de la valvula en CADA POST, no solo cuando cambia.
        irrigationService.processReading(node, save(node, t0, true, "0.000"));
        irrigationService.processReading(node, save(node, t0.plusSeconds(20), true, "2.500"));
        irrigationService.processReading(node, save(node, t0.plusSeconds(40), true, "5.000"));

        assertThat(irrigationService.findRange(node.getId(), t0.minusSeconds(60), t0.plusSeconds(600),
                PageRequest.of(0, 10)).getTotalElements()).isEqualTo(1);
        assertThat(irrigationService.findCurrent(node.getId())).isPresent();
    }

    @Test
    void elWatchdogDaDeBajaUnRiegoQueQuedoAbiertoYDejaEmpezarElSiguiente() {
        Node node = newNode("evt-6");
        Instant t0 = Instant.parse("2026-09-01T18:00:00Z");

        // El nodo abre la valvula y despues se apaga: nunca llega el POST que informa el cierre.
        irrigationService.processReading(node, save(node, t0, true, "40.000"));
        assertThat(irrigationService.findCurrent(node.getId())).isPresent();

        // Vuelve al dia siguiente, muy pasado el limite de 6 h, informando la valvula abierta.
        Instant regreso = t0.plus(Duration.ofHours(20));
        irrigationService.processReading(node, save(node, regreso, true, "0.000"));

        var eventos = irrigationService.findRange(node.getId(), t0.minusSeconds(60),
                regreso.plusSeconds(60), PageRequest.of(0, 10)).getContent();

        assertThat(eventos).hasSize(2);

        IrrigationEvent nuevo = eventos.get(0);
        IrrigationEvent colgado = eventos.get(1);

        // El colgado se dio de baja y NO se le invento un cierre.
        assertThat(colgado.getStartedAt()).isEqualTo(t0);
        assertThat(colgado.getEstado()).isEqualTo(IrrigationEventStatus.ABANDONED);
        assertThat(colgado.getEndedAt()).isNull();
        assertThat(colgado.getDuracionSegundos()).isNull();
        assertThat(colgado.getVolumenAplicadoL()).isNull();
        assertThat(colgado.getCaudalPromedioLMin()).isNull();
        assertThat(colgado.getObservaciones()).contains("Watchdog");

        // Y el riego que empieza ahora si pudo abrirse: es esto lo que el evento colgado bloqueaba.
        assertThat(nuevo.getStartedAt()).isEqualTo(regreso);
        assertThat(nuevo.getEstado()).isEqualTo(IrrigationEventStatus.OPEN);
        assertThat(irrigationService.findCurrent(node.getId()).orElseThrow().getId())
                .isEqualTo(nuevo.getId());
    }

    @Test
    void noDaDeBajaUnRiegoLargoPeroTodaviaDentroDelLimite() {
        Node node = newNode("evt-7");
        Instant t0 = Instant.parse("2026-09-01T06:00:00Z");

        irrigationService.processReading(node, save(node, t0, true, "0.000"));
        // Cinco horas de goteo es un riego real, no un evento colgado.
        Instant cierre = t0.plus(Duration.ofHours(5));
        irrigationService.processReading(node, save(node, cierre, false, "1200.000"));

        IrrigationEvent event = firstEvent(node, t0);
        assertThat(event.getEstado()).isEqualTo(IrrigationEventStatus.CLOSED);
        assertThat(event.getEndedAt()).isEqualTo(cierre);
        assertThat(event.getVolumenAplicadoL()).isEqualByComparingTo("1200.000");
    }
}
