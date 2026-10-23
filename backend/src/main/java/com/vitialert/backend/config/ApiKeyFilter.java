package com.vitialert.backend.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/** Proteccion liviana para las escrituras publicas sin incorporar sesiones de usuario. */
@Component
public class ApiKeyFilter extends OncePerRequestFilter {
    private final byte[] configuredKey;

    public ApiKeyFilter(VitiAlertProperties properties) {
        this.configuredKey = properties.security().apiKey().getBytes(StandardCharsets.UTF_8);
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return configuredKey.length == 0 || !"POST".equalsIgnoreCase(request.getMethod());
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        byte[] supplied = request.getHeader("X-API-Key") == null
                ? new byte[0]
                : request.getHeader("X-API-Key").getBytes(StandardCharsets.UTF_8);
        if (!MessageDigest.isEqual(configuredKey, supplied)) {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.getWriter().write("{\"status\":401,\"error\":\"UNAUTHORIZED\","
                    + "\"message\":\"X-API-Key invalida o ausente.\"}");
            return;
        }
        filterChain.doFilter(request, response);
    }
}
