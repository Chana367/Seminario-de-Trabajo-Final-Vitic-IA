package com.vitialert.backend.service;

import java.util.ArrayList;
import java.util.List;

/**
 * Parser CSV minimo (RFC 4180 simplificado) suficiente para los datasets del Data Miner:
 * separador coma o punto y coma, comillas dobles opcionales y comillas escapadas duplicando.
 *
 * <p>Se evita una dependencia externa para no agregar complejidad al prototipo.</p>
 */
final class SimpleCsvParser {

    private SimpleCsvParser() {
    }

    /** Detecta el separador mirando la linea de cabecera. */
    static char detectDelimiter(String headerLine) {
        int commas = count(headerLine, ',');
        int semicolons = count(headerLine, ';');
        return semicolons > commas ? ';' : ',';
    }

    static List<String> parseLine(String line, char delimiter) {
        List<String> fields = new ArrayList<>();
        StringBuilder current = new StringBuilder();
        boolean inQuotes = false;

        for (int i = 0; i < line.length(); i++) {
            char c = line.charAt(i);
            if (inQuotes) {
                if (c == '"') {
                    if (i + 1 < line.length() && line.charAt(i + 1) == '"') {
                        current.append('"');
                        i++;
                    } else {
                        inQuotes = false;
                    }
                } else {
                    current.append(c);
                }
            } else if (c == '"') {
                inQuotes = true;
            } else if (c == delimiter) {
                fields.add(current.toString().trim());
                current.setLength(0);
            } else {
                current.append(c);
            }
        }
        fields.add(current.toString().trim());
        return fields;
    }

    private static int count(String value, char c) {
        int total = 0;
        for (int i = 0; i < value.length(); i++) {
            if (value.charAt(i) == c) {
                total++;
            }
        }
        return total;
    }
}
