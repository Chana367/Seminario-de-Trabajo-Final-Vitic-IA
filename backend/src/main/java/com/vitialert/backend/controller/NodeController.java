package com.vitialert.backend.controller;

import com.vitialert.backend.client.SatelliteClient;
import com.vitialert.backend.domain.Node;
import com.vitialert.backend.dto.FeatureVector;
import com.vitialert.backend.dto.IrrigationEventDto;
import com.vitialert.backend.dto.NodeDto;
import com.vitialert.backend.dto.PageResponse;
import com.vitialert.backend.dto.TelemetryReadingDto;
import com.vitialert.backend.exception.ApiErrorResponse;
import com.vitialert.backend.exception.ResourceNotFoundException;
import com.vitialert.backend.service.DatasetService;
import com.vitialert.backend.service.IrrigationService;
import com.vitialert.backend.service.TelemetryService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.util.List;

/**
 * Consultas sobre nodos: telemetria, riegos, features y contexto satelital.
 *
 * <p>Los parametros {@code from} y {@code to} admiten ISO-8601 ({@code 2026-09-03T10:00:00Z})
 * o fecha suelta ({@code 2026-09-03}, comienzo del dia en UTC). Por defecto, ultimas 24 h.</p>
 */
@RestController
@RequestMapping("/api/nodes")
@Tag(name = "Nodos", description = "Consulta de telemetria, riegos y features por nodo")
public class NodeController {

    private static final int MAX_PAGE_SIZE = 500;

    private final TelemetryService telemetryService;
    private final IrrigationService irrigationService;
    private final DatasetService datasetService;
    private final SatelliteClient satelliteClient;

    public NodeController(TelemetryService telemetryService,
                          IrrigationService irrigationService,
                          DatasetService datasetService,
                          SatelliteClient satelliteClient) {
        this.telemetryService = telemetryService;
        this.irrigationService = irrigationService;
        this.datasetService = datasetService;
        this.satelliteClient = satelliteClient;
    }

    @Operation(summary = "Lista los nodos registrados")
    @GetMapping
    public List<NodeDto> findAll() {
        return telemetryService.findAllNodes().stream().map(NodeDto::from).toList();
    }

    @Operation(summary = "Ultima lectura recibida del nodo")
    @GetMapping("/{nodeId}/telemetry/latest")
    public TelemetryReadingDto latestTelemetry(@PathVariable String nodeId) {
        Node node = telemetryService.requireNode(nodeId);
        return telemetryService.findLatest(node.getId())
                .map(TelemetryReadingDto::from)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "El nodo " + nodeId + " todavia no tiene lecturas."));
    }

    @Operation(summary = "Historico de telemetria paginado")
    @GetMapping("/{nodeId}/telemetry")
    public PageResponse<TelemetryReadingDto> telemetry(@PathVariable String nodeId,
                                                       @RequestParam(required = false) String from,
                                                       @RequestParam(required = false) String to,
                                                       @RequestParam(defaultValue = "0") int page,
                                                       @RequestParam(defaultValue = "100") int size) {
        Node node = telemetryService.requireNode(nodeId);
        Instant toInstant = RequestTimes.parseOrDefault(to, "to", Instant.now());
        Instant fromInstant = RequestTimes.parseOrDefault(from, "from", RequestTimes.defaultFrom(toInstant));

        return PageResponse.of(
                telemetryService.findRange(node.getId(), fromInstant, toInstant, pageable(page, size)),
                TelemetryReadingDto::from);
    }

    @Operation(summary = "Eventos de riego reconstruidos",
            description = "Periodos reales de riego derivados de las transiciones de la electrovalvula, "
                    + "con el volumen aplicado calculado a partir del contador acumulado.")
    @GetMapping("/{nodeId}/irrigation-events")
    public PageResponse<IrrigationEventDto> irrigationEvents(@PathVariable String nodeId,
                                                             @RequestParam(required = false) String from,
                                                             @RequestParam(required = false) String to,
                                                             @RequestParam(defaultValue = "0") int page,
                                                             @RequestParam(defaultValue = "50") int size) {
        Node node = telemetryService.requireNode(nodeId);
        Instant toInstant = RequestTimes.parseOrDefault(to, "to", Instant.now());
        Instant fromInstant = RequestTimes.parseOrDefault(from, "from", RequestTimes.defaultFrom(toInstant));

        return PageResponse.of(
                irrigationService.findRange(node.getId(), fromInstant, toInstant, pageable(page, size)),
                IrrigationEventDto::from);
    }

    @Operation(summary = "Vector de features de una hora",
            description = "Devuelve exactamente la misma fila que exporta el dataset, calculada con el "
                    + "mismo codigo. Permite inspeccionar que los lags se resuelven por timestamp real: "
                    + "soil_moisture_lag_3h es el bucket de t-3h, y si ese bucket no existe llega null.")
    @GetMapping("/{nodeId}/features")
    public FeatureVector features(@PathVariable String nodeId,
                                  @RequestParam(required = false) String at) {
        Node node = telemetryService.requireNode(nodeId);
        return datasetService.features(node, RequestTimes.parseOrDefault(at, "at", Instant.now()));
    }

    @Operation(summary = "Contexto satelital del nodo (VitiAI)",
            description = "Resuelve las coordenadas del nodo y consulta VitiAI. Devuelve 503 si la "
                    + "integracion esta apagada o el servicio no responde: la telemetria nunca depende "
                    + "de que VitiAI este disponible.")
    @GetMapping("/{nodeId}/satellite")
    public ResponseEntity<Object> satellite(@PathVariable String nodeId) {
        Node node = telemetryService.requireNode(nodeId);
        if (node.getLatitud() == null || node.getLongitud() == null) {
            throw new IllegalArgumentException(
                    "El nodo " + nodeId + " no tiene coordenadas cargadas: no se puede consultar VitiAI.");
        }
        return satelliteClient.fetchFeatures(node.getLatitud(), node.getLongitud())
                .<ResponseEntity<Object>>map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                        .body(ApiErrorResponse.of(
                                HttpStatus.SERVICE_UNAVAILABLE.value(),
                                "SATELLITE_UNAVAILABLE",
                                satelliteClient.isEnabled()
                                        ? "VitiAI no respondio."
                                        : "La integracion satelital esta desactivada.",
                                "/api/nodes/" + nodeId + "/satellite")));
    }

    private static Pageable pageable(int page, int size) {
        if (page < 0) {
            throw new IllegalArgumentException("El parametro page no puede ser negativo.");
        }
        if (size <= 0 || size > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException("El parametro size debe estar entre 1 y " + MAX_PAGE_SIZE + ".");
        }
        return PageRequest.of(page, size);
    }
}
