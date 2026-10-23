package com.vitialert.backend.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfig {

    @Bean
    public OpenAPI vitiAlertOpenApi() {
        return new OpenAPI().info(new Info()
                .title("VitiAlert / Vitic-AI - Backend")
                .version("0.2.0")
                .description("""
                        Recibe los datos del ESP32, los guarda, reconstruye los eventos de riego,
                        integra la meteorologia del Data Miner y el contexto satelital de VitiAI,
                        construye el dataset horario y, mas adelante, consulta el modelo de
                        Ciencia de Datos.

                        Mientras el modelo esta apagado, la valvula sigue gobernada por
                        decision_riego_local del propio ESP32.

                        La autenticacion esta fuera del alcance de este prototipo academico.
                        """));
    }
}
