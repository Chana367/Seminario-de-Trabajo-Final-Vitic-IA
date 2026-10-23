package com.vitialert.backend.domain;

/**
 * Calidad asignada a una lectura en el momento de la ingesta.
 *
 * <p>Los valores fisicamente imposibles ni siquiera llegan aca: los rechaza Bean Validation
 * con un HTTP 400. Esta marca cubre lo que es posible pero dudoso.</p>
 *
 * <p><b>Ninguna de estas marcas modifica la decision de riego.</b> Son metadatos de
 * trazabilidad para el analisis posterior.</p>
 */
public enum QualityFlag {

    /** Todos los valores presentes y coherentes entre si. */
    VALID,

    /** Falta al menos una variable central del payload. */
    MISSING,

    /** Valores presentes pero incoherentes: caudal con la valvula cerrada, o valvula abierta sin caudal. */
    SUSPECT
}
