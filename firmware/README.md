# Nodo ESP32

El programa del nodo está en [sketch_final_tesis/sketch_final_tesis.ino](sketch_final_tesis/sketch_final_tesis.ino). Es la versión **Modo Maqueta** que operó en la segunda etapa de la campaña, con bomba de recirculación y motor simulador de viento. Según la serie de viento registrada, opera desde el 24/10/2026 hacia las 10:50 (hora de San Juan). Ese es el momento en que el máximo de la serie pasa a ser exactamente 65 km/h, el techo que fija este firmware.

## Configuración

Abrir el sketch en Arduino IDE con soporte ESP32, ArduinoJson 7 y DHT de Adafruit con Adafruit Unified Sensor. Copiar `secrets.example.h` como `secrets.h` junto al `.ino` y completar Wi-Fi, URL, API key y nodo. El archivo real de credenciales queda excluido de Git.

| Dispositivo | GPIO |
| --- | --- |
| DHT22 | 4 |
| Sonda de suelo | 34 |
| Anemómetro | 35 |
| Caudalímetro | 14 |
| Relé de válvula, activo en LOW | 27 |
| Relé del motor simulador de viento, activo en LOW | 23 |
| LED | 2 |

## Comportamiento

- **Telemetría:** JSON a `POST /api/data` con `X-API-Key` cada 30 segundos y de inmediato ante un cambio de válvula. Tiempo máximo de espera HTTP de 15 segundos.
- **DHT22:**
  - se consulta cada 5 segundos;
  - una lectura se acepta solo si temperatura y humedad son válidas a la vez;
  - la última lectura válida se conserva 15 segundos y, pasado ese plazo, sus campos no se envían;
  - después de una falla espera 2 segundos más antes de reintentar.
- **Decisión local:** regar si la sonda es válida, la humedad del suelo es menor que 30 %, el viento es menor que 45 km/h y no hay un bloqueo vigente. La decisión viaja al backend y gobierna la válvula ante una falla de red.
- **Cortes de seguridad:**
  - ráfaga de 45 km/h o más con la válvula abierta;
  - sonda de suelo fuera de rango;
  - 1,5 L entregados en el ciclo, seguido de una pausa de 10 minutos;
  - duración máxima de 6 horas;
  - caudal menor que 0,2 L/min después de 2 minutos de gracia, con espera creciente desde 5 minutos hasta 1 hora.
- **Simulador de viento:** reposos aleatorios de 2 a 12 minutos y ráfagas de 20 segundos a 3 minutos. En cada ráfaga, el firmware sortea un factor de intensidad que **multiplica** la lectura del anemómetro:
  - brisa (60 %): ×1,1 a ×1,9;
  - viento moderado (25 %): ×2,3 a ×3,2;
  - ráfaga de prueba del corte por Zonda (15 %): ×4,2 a ×4,5.

  El valor resultante tiene un techo de 65 km/h.

## Lectura de los datos

- **Escala del suelo:** relativa, mapeada entre 3317 (seco) y 1104 (agua). No es contenido volumétrico de agua.
- **Viento:** desde que opera esta versión, la velocidad informada es la lectura del anemómetro, movido por el motor, multiplicada por un factor que elige el propio firmware. Ese factor no se transmite. El valor sirve para ejercitar el corte por viento y **no es una medición de viento natural**. Entre el 23 y el 24/10 la escala del anemómetro se ajustó más de una vez, de modo que la serie de viento de la segunda etapa no es homogénea. Ningún modelo del trabajo usa esta variable.
- **Caudalímetro:** factor 7,5 pulsos por segundo por L/min, sin contrastar con un volumen conocido. El contador de litros se reinicia al reiniciar el ESP32, y el circuito recircula: los litros describen circulación, no consumo.

## Límites a comprobar físicamente

- Las llamadas HTTP son bloqueantes y pueden retrasar las comprobaciones del bucle. El firmware no incorpora un corte físico independiente del microcontrolador.
- `setInsecure()` cifra HTTPS sin validar la identidad del servidor. La validación TLS es una mejora pendiente antes de un uso productivo.
- El backend registra la hora de recepción, no la de medición.

Confirmar el cableado de la válvula, la bomba y el motor antes de cargar el programa, con la alimentación de los actuadores desconectada, y mantener supervisión durante los ensayos. La compilación no certifica el firmware cargado ni el estado físico de la válvula.

La versión anterior, con envío cada 60 segundos y sin simulador de viento, queda en el historial de Git.
