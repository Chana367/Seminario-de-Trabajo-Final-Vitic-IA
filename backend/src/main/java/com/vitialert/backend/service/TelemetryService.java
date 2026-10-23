package com.vitialert.backend.service;

import com.vitialert.backend.client.PredictionClient;
import com.vitialert.backend.config.VitiAlertProperties;
import com.vitialert.backend.domain.Node;
import com.vitialert.backend.domain.QualityFlag;
import com.vitialert.backend.domain.TelemetryReading;
import com.vitialert.backend.dto.PredictionResponse;
import com.vitialert.backend.dto.TelemetryRequest;
import com.vitialert.backend.dto.TelemetryResponse;
import com.vitialert.backend.exception.ResourceNotFoundException;
import com.vitialert.backend.repository.NodeRepository;
import com.vitialert.backend.repository.TelemetryReadingRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * Recepcion de telemetria y consultas sobre nodos y lecturas.
 *
 * <p>El camino del POST esta acotado a proposito: resolver el nodo, evaluar la calidad sin
 * tocar la base, guardar la lectura, actualizar como mucho un evento de riego y responder.
 * Son dos consultas y una escritura, y ese numero no crece con el historico acumulado. El
 * prototipo Python recalculaba todo el historico en cada recepcion.</p>
 */
@Service
public class TelemetryService {

    private static final Logger log = LoggerFactory.getLogger(TelemetryService.class);

    private final TelemetryReadingRepository telemetryReadingRepository;
    private final NodeRepository nodeRepository;
    private final IrrigationService irrigationService;
    private final DatasetService datasetService;
    private final PredictionClient predictionClient;
    private final VitiAlertProperties properties;

    public TelemetryService(TelemetryReadingRepository telemetryReadingRepository,
                            NodeRepository nodeRepository,
                            IrrigationService irrigationService,
                            DatasetService datasetService,
                            PredictionClient predictionClient,
                            VitiAlertProperties properties) {
        this.telemetryReadingRepository = telemetryReadingRepository;
        this.nodeRepository = nodeRepository;
        this.irrigationService = irrigationService;
        this.datasetService = datasetService;
        this.predictionClient = predictionClient;
        this.properties = properties;
    }

    /**
     * Procesa un POST del ESP32 y devuelve las ordenes para el nodo.
     *
     * <p>El timestamp lo genera el backend en UTC al recibir el payload: el ESP32 no tiene
     * reloj confiable y su contador se reinicia con el nodo.</p>
     */
    @Transactional
    public TelemetryResponse ingest(TelemetryRequest request) {
        Instant receivedAt = Instant.now();

        Node node = resolveNode(request.nodoId());
        Quality quality = evaluateQuality(request);

        TelemetryReading reading = telemetryReadingRepository.save(TelemetryReading.builder()
                .node(node)
                .timestampReceived(receivedAt)
                .temperaturaAmbienteC(request.temperaturaAmbienteC())
                .humedadRelativaPct(request.humedadRelativaPct())
                .humedadSueloPct(request.humedadSueloPct())
                .humedadSueloRaw(request.humedadSueloRaw())
                .velocidadVientoKmh(request.velocidadVientoKmh())
                .caudalLMin(request.caudalLMin())
                .volumenTotalL(request.volumenTotalL())
                .valvulaAbiertaActual(request.valvulaAbiertaActual())
                .decisionRiegoLocal(request.decisionRiegoLocal())
                .quality(quality.flag(), quality.notes())
                .build());

        irrigationService.processReading(node, reading);
        boolean decision = resolveIrrigationDecision(node, reading);

        log.info("Telemetria nodo={} ts={} humedadSuelo={}% viento={} km/h caudal={} L/min "
                        + "valvula={} decisionLocal={} decisionFinal={} calidad={}",
                node.getExternalId(), receivedAt, request.humedadSueloPct(), request.velocidadVientoKmh(),
                request.caudalLMin(), request.valvulaAbiertaActual(), request.decisionRiegoLocal(),
                decision, quality.flag());

        return new TelemetryResponse(decision, decision);
    }

    /**
     * <b>Punto de extension del motor de decision.</b>
     *
     * <p>Prioridad definida para el proyecto: si existe una decision confiable del backend se
     * usa; si no, se replica {@code decision_riego_local} del ESP32.</p>
     *
     * <p>Hoy el modelo esta apagado, asi que la valvula sigue gobernada por el firmware y la
     * maqueta se comporta exactamente igual que antes. No se implementa ninguna IA ficticia ni
     * logica meteorologica inventada: cuando exista el modelo, la unica linea que cambia es la
     * de abajo.</p>
     *
     * <p>Con el modelo apagado NO se calculan features ni se hace ninguna llamada de red: el
     * costo de tener la integracion preparada es cero.</p>
     */
    private boolean resolveIrrigationDecision(Node node, TelemetryReading reading) {
        boolean localDecision = reading.isLocalIrrigationDecision();
        if (!predictionClient.isEnabled()) {
            return localDecision;
        }
        // Optional.map ya descarta un irrigate nulo: una respuesta sin decision utilizable
        // (modelo no cargado, confianza baja) cae al fallback local, no a "no regar".
        return predictionClient.predict(datasetService.features(node, reading.getTimestampReceived()))
                .map(PredictionResponse::irrigate)
                .orElse(localDecision);
    }

    // ------------------------------------------------------------------ nodos

    /**
     * Resuelve el nodo del payload y lo da de alta la primera vez que aparece, de modo que
     * apuntar la maqueta al backend solo requiera cambiar la URL del servidor.
     *
     * <p>El alta ocurre una sola vez por nodo, por lo que no se agrega bloqueo: en el peor
     * caso dos POST simultaneos de un nodo nuevo chocan contra la restriccion de unicidad y el
     * ESP32 reintenta segundos despues.</p>
     */
    private Node resolveNode(String externalId) {
        return nodeRepository.findByExternalId(externalId).orElseGet(() -> {
            if (!properties.node().autoRegister()) {
                throw new ResourceNotFoundException("Nodo desconocido: " + externalId);
            }
            Node node = new Node(externalId);
            node.setNombre("Nodo " + externalId);
            node.setDescripcion("Alta automatica en la primera recepcion de telemetria.");
            node.setLatitud(properties.node().defaultLatitude());
            node.setLongitud(properties.node().defaultLongitude());
            Node saved = nodeRepository.save(node);
            log.info("Nodo dado de alta automaticamente: {}", externalId);
            return saved;
        });
    }

    /** Busca el nodo o lanza 404. Nunca lo crea: un GET no debe dar de alta nada. */
    @Transactional(readOnly = true)
    public Node requireNode(String externalId) {
        return nodeRepository.findByExternalId(externalId)
                .orElseThrow(() -> new ResourceNotFoundException("No existe el nodo " + externalId));
    }

    @Transactional(readOnly = true)
    public List<Node> findAllNodes() {
        return nodeRepository.findAllByOrderByExternalIdAsc();
    }

    // ------------------------------------------------------------------ consultas

    @Transactional(readOnly = true)
    public Optional<TelemetryReading> findLatest(Long nodeId) {
        List<TelemetryReading> latest = telemetryReadingRepository.findLatest(nodeId, PageRequest.of(0, 1));
        return latest.isEmpty() ? Optional.empty() : Optional.of(latest.get(0));
    }

    @Transactional(readOnly = true)
    public Page<TelemetryReading> findRange(Long nodeId, Instant from, Instant to, Pageable pageable) {
        if (!from.isBefore(to)) {
            throw new IllegalArgumentException("El parametro from debe ser anterior a to.");
        }
        return telemetryReadingRepository.findRange(nodeId, from, to, pageable);
    }

    // ------------------------------------------------------------------ calidad

    /**
     * Control de calidad de la lectura, sin ninguna consulta a la base.
     *
     * <p>Lo fisicamente imposible ya fue rechazado por Bean Validation con un HTTP 400. Aca se
     * detecta lo que es posible pero dudoso: faltantes e incoherencias entre caudal y valvula.
     * La deteccion de sensor congelado se hace en el preprocesamiento del dataset en Python,
     * con {@code diff()}, que es donde corresponde y donde no genera falsos positivos.</p>
     *
     * <p><b>La calidad nunca modifica la decision de riego.</b> Es metadato para el analisis.</p>
     */
    private Quality evaluateQuality(TelemetryRequest request) {
        List<String> notes = new ArrayList<>();

        boolean missing = false;
        if (request.temperaturaAmbienteC() == null) {
            notes.add("MISSING:temperatura_ambiente_c");
            missing = true;
        }
        if (request.humedadRelativaPct() == null) {
            notes.add("MISSING:humedad_relativa_pct");
            missing = true;
        }
        if (request.humedadSueloPct() == null) {
            notes.add("MISSING:humedad_suelo_pct");
            missing = true;
        }
        if (request.humedadSueloRaw() == null) {
            notes.add("MISSING:humedad_suelo_raw");
            missing = true;
        }
        if (request.valvulaAbiertaActual() == null) {
            notes.add("MISSING:valvula_abierta_actual");
            missing = true;
        }
        if (request.decisionRiegoLocal() == null) {
            notes.add("MISSING:decision_riego_local");
            missing = true;
        }

        boolean suspect = false;
        BigDecimal caudal = request.caudalLMin();
        Boolean valvula = request.valvulaAbiertaActual();
        if (caudal != null && valvula != null) {
            // Los caudalimetros de efecto Hall reportan pulsos espurios cerca de cero, asi que
            // se compara contra un umbral de ruido y no contra cero exacto.
            boolean flowing = caudal.compareTo(
                    BigDecimal.valueOf(properties.quality().flowNoiseThresholdLMin())) > 0;
            if (flowing && !valvula) {
                notes.add("SUSPECT:caudal=" + caudal.toPlainString()
                        + " L/min con la valvula cerrada (posible fuga)");
                suspect = true;
            } else if (!flowing && valvula) {
                notes.add("SUSPECT:valvula abierta sin caudal (posible obstruccion o falta de suministro)");
                suspect = true;
            }
        }

        QualityFlag flag = missing ? QualityFlag.MISSING
                : suspect ? QualityFlag.SUSPECT
                : QualityFlag.VALID;

        String joined = notes.isEmpty() ? null : truncate(String.join(" | ", notes));
        if (flag != QualityFlag.VALID) {
            log.warn("Calidad degradada nodo={} flag={} detalle={}", request.nodoId(), flag, joined);
        }
        return new Quality(flag, joined);
    }

    private static String truncate(String value) {
        return value.length() <= 500 ? value : value.substring(0, 497) + "...";
    }

    /** Resultado del control de calidad. Solo existe dentro de la ingesta. */
    private record Quality(QualityFlag flag, String notes) {
    }
}
