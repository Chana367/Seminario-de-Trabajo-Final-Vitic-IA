package com.vitialert.backend.controller;

import com.vitialert.backend.client.PredictionClient;
import com.vitialert.backend.client.SatelliteClient;
import com.vitialert.backend.domain.Node;
import com.vitialert.backend.dto.WeatherImportResultDto;
import com.vitialert.backend.service.DatasetService;
import com.vitialert.backend.service.SatelliteObservationService;
import com.vitialert.backend.service.TelemetryService;
import com.vitialert.backend.service.WeatherService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

/** Importacion del historico meteorologico, exportacion del dataset y estado del backend. */
@RestController
@Tag(name = "Datos", description = "Meteorologia, dataset y salud del backend")
public class DataController {

    private final WeatherService weatherService;
    private final DatasetService datasetService;
    private final TelemetryService telemetryService;
    private final SatelliteClient satelliteClient;
    private final PredictionClient predictionClient;
    private final SatelliteObservationService satelliteObservationService;

    public DataController(WeatherService weatherService,
                          DatasetService datasetService,
                          TelemetryService telemetryService,
                          SatelliteClient satelliteClient,
                          PredictionClient predictionClient,
                          SatelliteObservationService satelliteObservationService) {
        this.weatherService = weatherService;
        this.datasetService = datasetService;
        this.telemetryService = telemetryService;
        this.satelliteClient = satelliteClient;
        this.predictionClient = predictionClient;
        this.satelliteObservationService = satelliteObservationService;
    }

    @Operation(summary = "Importa el CSV diario del Data Miner",
            description = "Idempotente por (fecha, fuente): reimportar el mismo archivo actualiza las "
                    + "filas existentes. Las celdas vacias se guardan como null, nunca como cero.")
    @PostMapping(path = "/api/weather/import", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public WeatherImportResultDto importWeather(@RequestParam("file") MultipartFile file,
                                                @RequestParam(value = "source", required = false) String source)
            throws IOException {
        if (file == null || file.isEmpty()) {
            throw new IllegalArgumentException("Se requiere un archivo CSV en el campo 'file'.");
        }
        return weatherService.importCsv(file.getInputStream(), source);
    }

    @Operation(summary = "Consulta VitiAI y persiste una captura por nodo con coordenadas")
    @PostMapping("/api/satellite/refresh")
    public Map<String, Object> refreshSatellite() {
        return satelliteObservationService.refreshAll();
    }

    @Operation(summary = "Exporta el dataset horario en CSV",
            description = "Lags, medias moviles y target t+24h se resuelven por timestamp real sobre la "
                    + "serie horaria. Un hueco de datos produce una celda vacia, nunca un cero ni un "
                    + "valor corrido.")
    @GetMapping(path = "/api/dataset/export", produces = "text/csv")
    public ResponseEntity<byte[]> exportDataset(@RequestParam("nodeId") String nodeId,
                                                @RequestParam("from") String from,
                                                @RequestParam("to") String to) {
        Node node = telemetryService.requireNode(nodeId);
        String csv = datasetService.exportCsv(node,
                RequestTimes.parse(from, "from"),
                RequestTimes.parse(to, "to"));

        String filename = "vitialert_dataset_node" + node.getExternalId() + "_hourly.csv";
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"" + filename + "\"")
                .contentType(new MediaType("text", "csv", StandardCharsets.UTF_8))
                .body(csv.getBytes(StandardCharsets.UTF_8));
    }

    @Operation(summary = "Estado del backend y de las integraciones opcionales")
    @GetMapping("/health")
    public Map<String, Object> health() {
        Map<String, Object> integrations = new LinkedHashMap<>();
        integrations.put("satellite_enabled", satelliteClient.isEnabled());
        integrations.put("ml_enabled", predictionClient.isEnabled());

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("status", "UP");
        body.put("timestamp", Instant.now());
        body.put("integrations", integrations);
        return body;
    }
}
