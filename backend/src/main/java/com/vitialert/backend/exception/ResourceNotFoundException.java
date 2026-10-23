package com.vitialert.backend.exception;

/** Recurso inexistente (nodo, evento, etc.). Se traduce a HTTP 404. */
public class ResourceNotFoundException extends RuntimeException {

    public ResourceNotFoundException(String message) {
        super(message);
    }
}
