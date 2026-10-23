package com.vitialert.backend.domain;

/** Estado del ciclo de vida de un evento de riego reconstruido a partir de la telemetria. */
public enum IrrigationEventStatus {

    /** La electrovalvula sigue abierta: el evento todavia no tiene fin ni volumen aplicado. */
    OPEN,

    /** Evento cerrado con volumen aplicado calculado de forma confiable. */
    CLOSED,

    /** Evento cerrado, pero el volumen aplicado es dudoso (reinicio del contador del ESP32 o dato faltante). */
    CLOSED_WITH_WARNING,

    /**
     * El cierre de la valvula NUNCA se observo: el evento quedo abierto mas alla del maximo
     * configurado y el watchdog lo dio de baja.
     *
     * <p>Se distingue de {@link #CLOSED_WITH_WARNING} porque ahi el volumen aplicado es
     * <em>dudoso</em> y aca es <em>desconocido</em>: no hay instante de cierre, asi que
     * duracion, volumen y caudal promedio quedan en null en vez de inventarse.</p>
     *
     * <p>Ciencia de Datos debe excluir estos eventos de cualquier metrica de agua aplicada.</p>
     */
    ABANDONED
}
