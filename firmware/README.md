# Nodo ESP32

El programa habitual está en [sketch_final_tesis/sketch_final_tesis.ino](sketch_final_tesis/sketch_final_tesis.ino). Se conserva separado del backend para mantener una única copia del firmware en este repositorio.

## Configuración

Abrir el sketch en Arduino IDE con soporte ESP32, ArduinoJson 7 y DHT de Adafruit con Adafruit Unified Sensor. Copiar `secrets.example.h` como `secrets.h` junto al `.ino` y completar Wi-Fi, URL, API key y nodo. El archivo real de credenciales queda excluido de Git.

| Dispositivo | GPIO |
| --- | --- |
| DHT22 | 4 |
| Sonda de suelo | 34 |
| Anemómetro | 35 |
| Caudalímetro | 14 |
| Relé de válvula, activo en LOW | 27 |
| LED | 2 |

El nodo envía JSON a `POST /api/data` con `X-API-Key` cada 60 segundos o cambio de válvula. Conserva una decisión local de respaldo y comprobaciones de viento, suelo y falta de caudal. Los valores recientes del DHT se mantienen hasta 10 segundos; luego se omiten si el sensor sigue sin responder.

## Límites a comprobar físicamente

- Factor del caudalímetro: 7,5; requiere contraste con volumen recogido.
- Calibración relativa del suelo: 3317 seco y 1104 agua; debe validarse con el sustrato.
- Duración máxima configurada: 6 horas. No es un ensayo con cierre de 60 segundos.
- Corte por caudal menor de 0,2 L/min después de 2 minutos; luego espera creciente entre reintentos.
- El contador de litros se reinicia al reiniciar el ESP32.
- Las llamadas HTTP son bloqueantes; pueden retrasar las comprobaciones del bucle. El firmware no incorpora un corte físico independiente del microcontrolador.
- `setInsecure()` cifra HTTPS sin validar la identidad del servidor. La validación TLS es una mejora pendiente antes de uso productivo.

La bomba depende del circuito instalado y no tiene un canal de control independiente en este sketch. Confirmar el cableado del actuador antes de cargarlo, con bomba apagada y alimentación del actuador desconectada. Verificar apertura/cierre y mantener supervisión durante los ensayos. La compilación no certifica el firmware cargado ni el estado físico de la válvula.

Los archivos de ensayo temporal no forman parte de este componente habitual.
