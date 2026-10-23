package com.vitialert.backend.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * Toda la configuracion propia del backend, agrupada en un unico record.
 *
 * <p>Los valores viven en {@code application.yml} bajo el prefijo {@code vitialert}. Los
 * {@code @DefaultValue} garantizan que la aplicacion arranque aunque falte una clave.</p>
 */
@ConfigurationProperties(prefix = "vitialert")
public record VitiAlertProperties(
        @DefaultValue Node node,
        @DefaultValue Security security,
        @DefaultValue Quality quality,
        @DefaultValue Irrigation irrigation,
        @DefaultValue Dataset dataset,
        @DefaultValue Satellite satellite,
        @DefaultValue Ml ml
) {

    /**
     * @param autoRegister da de alta un nodo desconocido en su primer POST, de modo que el
     *                     ESP32 funcione cambiando solo la URL del servidor
     */
    public record Node(
            @DefaultValue("true") boolean autoRegister,
            @DefaultValue("-31.6550") double defaultLatitude,
            @DefaultValue("-68.5750") double defaultLongitude) {
    }

    /** Clave compartida para endpoints de escritura; vacia mantiene el modo laboratorio. */
    public record Security(@DefaultValue("") String apiKey) {
    }

    /**
     * @param flowNoiseThresholdLMin caudal por debajo del cual se considera "sin flujo".
     *                               Los caudalimetros de efecto Hall reportan pulsos espurios
     *                               cerca de cero, asi que comparar contra cero exacto daria
     *                               falsos positivos permanentes
     */
    public record Quality(@DefaultValue("0.2") double flowNoiseThresholdLMin) {
    }

    /**
     * Watchdog de la maquina de estados del riego.
     *
     * @param maxOpenHours horas que un evento puede permanecer abierto antes de darse de baja.
     *                     Un riego por goteo real dura horas, no dias; si se supera este limite
     *                     lo que hubo fue un nodo apagado con la valvula abierta o un POST de
     *                     cierre perdido, no un riego largo. Sin este limite el evento colgado
     *                     bloquea el indice unico parcial y absorbe todos los riegos siguientes
     */
    public record Irrigation(@DefaultValue("6") int maxOpenHours) {
    }

    /**
     * @param maxGapSeconds hueco maximo entre lecturas consecutivas que se acepta al integrar
     *                      el tiempo de valvula abierta. Un hueco mayor es nodo offline, no riego
     * @param maxRangeDays  rango maximo consultable de una sola vez
     */
    public record Dataset(
            @DefaultValue("120") long maxGapSeconds,
            @DefaultValue("31") int maxRangeDays) {
    }

    /**
     * Servicio satelital VitiAI (viti-alert-ds-api). Se consulta por coordenadas, no por nodo.
     *
     * @param featuresPath ruta del endpoint de features satelitales
     * @param bufferKm     radio de agregacion espacial que se le pide al servicio
     * @param timeoutMs    VitiAI corre en el plan gratuito de Render, que apaga el servicio a
     *                     los 15 minutos sin trafico y tarda alrededor de un minuto en volver.
     *                     Como la sincronizacion es diaria, VitiAI SIEMPRE esta dormido cuando
     *                     se lo llama: un timeout corto no devuelve un error, devuelve cero
     *                     observaciones todos los dias y deja las columnas satelitales del
     *                     dataset vacias para siempre, sin que nada falle a la vista
     */
    public record Satellite(
            @DefaultValue("false") boolean enabled,
            @DefaultValue("http://localhost:8000") String baseUrl,
            @DefaultValue("/api/v1/satellite/features") String featuresPath,
            @DefaultValue("5.0") double bufferKm,
            @DefaultValue("90000") int timeoutMs) {
    }

    /**
     * API Python de inferencia. Apagada por defecto: mientras lo este, la valvula sigue
     * gobernada por {@code decision_riego_local} y no se hace ninguna llamada de red.
     */
    public record Ml(
            @DefaultValue("false") boolean enabled,
            @DefaultValue("http://localhost:8002") String baseUrl,
            @DefaultValue("/predict") String predictPath,
            @DefaultValue("1500") int timeoutMs) {
    }
}
