package com.vitialert.backend;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

/**
 * Punto de entrada del backend VitiAlert / Vitic-AI.
 *
 * <p>El backend Java actua como ORQUESTADOR entre las tres fuentes de informacion
 * del sistema (IoT ESP32, meteorologia historica del Data Miner y el servicio
 * satelital VitiAlert) y es responsable de recibir, validar, persistir, integrar,
 * construir features temporales y devolver la decision de riego al nodo fisico.</p>
 */
@SpringBootApplication
@ConfigurationPropertiesScan
public class VitiAlertApplication {

    public static void main(String[] args) {
        SpringApplication.run(VitiAlertApplication.class, args);
    }
}
