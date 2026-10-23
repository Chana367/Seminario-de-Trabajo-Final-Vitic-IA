package com.vitialert.backend.controller;

import com.vitialert.backend.dto.TelemetryRequest;
import com.vitialert.backend.dto.TelemetryResponse;
import com.vitialert.backend.service.TelemetryService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/**
 * Contrato historico con el firmware del ESP32.
 *
 * <p>La ruta, el JSON de entrada y el JSON de salida NO se modifican: apuntar la maqueta
 * al backend Java solo requiere cambiar la URL del servidor.</p>
 */
@RestController
@Tag(name = "Telemetria IoT", description = "Recepcion de telemetria del ESP32")
public class TelemetryController {

    private final TelemetryService telemetryService;

    public TelemetryController(TelemetryService telemetryService) {
        this.telemetryService = telemetryService;
    }

    @Operation(summary = "Recibe una lectura del nodo y devuelve las ordenes de valvula y luz",
            description = "Persiste la lectura de forma inmutable, actualiza el evento de riego en curso "
                    + "y registra la decision. Mientras no exista un motor avanzado habilitado, "
                    + "abrir_valvula y encender_luz replican decision_riego_local.")
    @PostMapping(path = "/api/data",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public TelemetryResponse receive(@Valid @RequestBody TelemetryRequest request) {
        return telemetryService.ingest(request);
    }
}
