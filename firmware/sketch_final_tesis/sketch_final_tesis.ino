// =====================================================================
// VitiAlert / Vitic-AI  -  Nodo de campo ESP32 (Modo Maqueta / Simulación)
// =====================================================================

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "DHT.h"
#include "secrets.h"

// --- ASIGNACION DE PINES ---
#define DHTPIN 4
#define DHTTYPE DHT22
#define PIN_SUELO 34
#define PIN_ANEMOMETRO 35
#define PIN_CAUDALIMETRO 14  // Pulsos sensor de flujo
#define PIN_RELE_VALVULA 27  // Control del rele de la valvula (Activo en LOW)
#define PIN_LED 2            // LED testigo en placa
#define PIN_MOTOR_VIENTO 23  // Control del motorcito simulador de viento (GPIO 23)

// --- CALIBRACION ---
const int   SUELO_SECO = 3317;
const int   SUELO_AGUA = 1104;
const int   MUESTRAS_VIENTO = 10;
const float FACTOR_CALIBRACION_CAUDAL = 7.5;

// --- UMBRALES DE DECISION ---
const float HUMEDAD_SUELO_RIEGO    = 30.0;   // por debajo de esto, regar
const float VIENTO_FUERTE_KMH      = 45.0;   // por encima de esto, cortar

// --- ESCALA DE MAQUETA Y SEGURIDAD ---
const float VOLUMEN_MAX_MAQUETA_L    = 1.50;      // 1.5 Litros equivale al riego completo de la maceta
const unsigned long PAUSA_RIEGO_MS   = 10UL * 60UL * 1000UL; // 10 minutos de reposo entre riegos simulados
const unsigned long MAX_RIEGO_MS     = 6UL * 60UL * 60UL * 1000UL;  // 6 h techo max
const unsigned long GRACIA_CAUDAL_MS = 120000UL;                  // 2 min gracia
const float CAUDAL_MINIMO_L_MIN      = 0.2;

// --- RED Y SENSORES ---
const unsigned long INTERVALO_ENVIO_MS = 30000; // Telemetría al backend cada 30 segundos
const unsigned long INTERVALO_DHT_MS   = 5000;  // Lectura del DHT22 cada 5 segundos (evita saturación)
const unsigned long MAX_EDAD_DHT_MS    = 15000; // Validez de la última lectura: 15 segundos
const uint16_t TIMEOUT_HTTP_MS         = 15000;

// --- TIEMPOS SIMULADOR DE VIENTO VARIABLE (MOTOR) ---
const unsigned long VIENTO_REPOSO_MIN_MS  = 2UL * 60UL * 1000UL;   // Reposo min: 2 minutos
const unsigned long VIENTO_REPOSO_MAX_MS  = 12UL * 60UL * 1000UL;  // Reposo max: 12 minutos
const unsigned long VIENTO_RAFAGA_MIN_MS  = 20UL * 1000UL;         // Ráfaga min: 20 segundos
const unsigned long VIENTO_RAFAGA_MAX_MS  = 3UL * 60UL * 1000UL;   // Ráfaga max: 3 minutos

DHT dht(DHTPIN, DHTTYPE);

// --- ULTIMA LECTURA DHT22 ---
float ultimaTemperaturaC = NAN;
float ultimaHumedadPct   = NAN;
unsigned long tiempoUltimoIntentoDht    = 0;
unsigned long tiempoUltimaTemperaturaOk = 0;
unsigned long tiempoUltimaHumedadOk     = 0;

void actualizarDht(unsigned long ahoraMs) {
  if (tiempoUltimoIntentoDht != 0
      && ahoraMs - tiempoUltimoIntentoDht < INTERVALO_DHT_MS) {
    return;
  }

  tiempoUltimoIntentoDht = ahoraMs;
  
  float temperatura = dht.readTemperature();
  float humedad     = dht.readHumidity();

  // Actualización con validación estricta de lectura válida
  if (!isnan(temperatura) && !isnan(humedad)) {
    ultimaTemperaturaC = temperatura;
    ultimaHumedadPct   = humedad;
    tiempoUltimaTemperaturaOk = ahoraMs;
    tiempoUltimaHumedadOk     = ahoraMs;
  } else {
    // Si la lectura falló, damos un margen de 2s extra antes de reintentar para no colgar el sensor
    tiempoUltimoIntentoDht += 2000; 
  }
}

bool datoDhtReciente(unsigned long ahoraMs, unsigned long ultimoDatoOkMs) {
  return ultimoDatoOkMs != 0 && ahoraMs - ultimoDatoOkMs <= MAX_EDAD_DHT_MS;
}

// --- ESTADO Y VOLUMEN ---
bool estadoValvulaActual   = false;
bool estadoValvulaAnterior = false;

unsigned long tiempoAperturaValvula = 0;
unsigned long tiempoAnteriorCaudal  = 0;
unsigned long tiempoUltimoEnvio     = 0;

float volumenInicioCiclo = 0.0;     // Control del volumen entregado en la sesión actual
unsigned long bloqueoHastaMs = 0;   // 0 = sin bloqueo temporizado vigente
uint8_t       cortesSinCaudal = 0;  // cortes seguidos sin que haya circulado agua
const char*   motivoBloqueo   = "";

const unsigned long ESPERA_BASE_MS = 5UL * 60UL * 1000UL;   // 5 min
const unsigned long ESPERA_MAX_MS  = 60UL * 60UL * 1000UL;  // 1 h

bool vientoFuerteActual = false;
bool sueloValidoActual  = true;

// Variables control simulación motor de viento
bool motorVientoActivo = false;
unsigned long tiempoUltimoCambioMotor = 0;
unsigned long proximoIntervaloMotor   = 0;
float factorIntensidadViento = 1.0; 

bool bloqueoVigente() {
  return bloqueoHastaMs != 0 && (long)(millis() - bloqueoHastaMs) < 0;
}

bool aperturaBloqueada() {
  return bloqueoVigente() || vientoFuerteActual || !sueloValidoActual;
}

void bloquearPor(unsigned long duracionMs, const char* motivo) {
  bloqueoHastaMs = millis() + duracionMs;
  if (bloqueoHastaMs == 0) bloqueoHastaMs = 1;
  motivoBloqueo = motivo;
}

// --- LOGICA SIMULADOR DE VIENTO ALEATORIO (RECALIBRADO SUAVE) ---
void simularVientoEsporadico(unsigned long ahoraMs) {
  if (proximoIntervaloMotor == 0) {
    randomSeed(micros() + analogRead(36)); 
    proximoIntervaloMotor = random(VIENTO_REPOSO_MIN_MS, VIENTO_REPOSO_MAX_MS);
    tiempoUltimoCambioMotor = ahoraMs;
  }

  if (ahoraMs - tiempoUltimoCambioMotor >= proximoIntervaloMotor) {
    tiempoUltimoCambioMotor = ahoraMs;
    motorVientoActivo = !motorVientoActivo;

    if (motorVientoActivo) {
      digitalWrite(PIN_MOTOR_VIENTO, LOW);  // Relé activo en LOW
      proximoIntervaloMotor = random(VIENTO_RAFAGA_MIN_MS, VIENTO_RAFAGA_MAX_MS);

      int tipoViento = random(0, 100);
      if (tipoViento < 60) {
        // 60% probabilidad: Brisa suave (12 a 22 km/h)
        factorIntensidadViento = random(11, 20) / 10.0;  
        Serial.println("\n🍃 [SIMULADOR] Brisa suave iniciada.");
      } else if (tipoViento < 85) {
        // 25% probabilidad: Viento moderado (25 a 36 km/h)
        factorIntensidadViento = random(23, 33) / 10.0;  
        Serial.println("\n💨 [SIMULADOR] Viento moderado iniciado.");
      } else {
        // 15% probabilidad: Ráfaga Zonda de prueba (46 a 50 km/h -> Fuerza corte)
        factorIntensidadViento = random(42, 46) / 10.0;  
        Serial.println("\n🌀 [SIMULADOR] ¡ALERTA! Ráfaga Zonda de prueba iniciada.");
      }

    } else {
      digitalWrite(PIN_MOTOR_VIENTO, HIGH); // Relé apagado
      factorIntensidadViento = 1.0;
      proximoIntervaloMotor = random(VIENTO_REPOSO_MIN_MS, VIENTO_REPOSO_MAX_MS);
      Serial.println("\n🍃 [SIMULADOR] Calma ambiental (Motor APAGADO).");
    }
  }
}

// --- CAUDALIMETRO ---
volatile unsigned long pulsosCaudal   = 0;
volatile unsigned long ultimoPulsoUs  = 0;
float caudalLitrosMin    = 0.0;
float volumenTotalLitros = 0.0;

const unsigned long MIN_US_ENTRE_PULSOS = 1000;

void IRAM_ATTR contarPulsos() {
  unsigned long ahora = micros();
  if (ahora - ultimoPulsoUs >= MIN_US_ENTRE_PULSOS) {
    pulsosCaudal++;
    ultimoPulsoUs = ahora;
  }
}

// --- CONTROL DEL RELE (activo en LOW) ---
void controlarValvula(bool abrir) {
  if (abrir == estadoValvulaActual) {
    return;
  }
  if (abrir) {
    digitalWrite(PIN_RELE_VALVULA, LOW);
    estadoValvulaActual = true;
    tiempoAperturaValvula = millis();
    volumenInicioCiclo = volumenTotalLitros; // Guarda el contador al abrir
    Serial.println(" -> RELE FISICO: ACTIVADO [ABIERTO]");
  } else {
    digitalWrite(PIN_RELE_VALVULA, HIGH);
    estadoValvulaActual = false;
    Serial.println(" -> RELE FISICO: DESACTIVADO [CERRADO]");
  }
}

// --- CORTES AUTOMATICOS Y CICLO MAQUETA ---
void aplicarCortesDeSeguridad() {
  if (vientoFuerteActual && estadoValvulaActual) {
    Serial.println("CORTE: ráfaga de viento detectada.");
    controlarValvula(false);
    motivoBloqueo = "viento fuerte";
    return;
  }

  if (!sueloValidoActual) {
    if (estadoValvulaActual) {
      Serial.println("CORTE: sonda de suelo fuera de rango.");
      controlarValvula(false);
    }
    motivoBloqueo = "sonda de suelo invalida";
    return;
  }

  if (!estadoValvulaActual) {
    return;
  }

  // 1. CORTE POR VOLUMEN COMPLETADO DE MAQUETA (1.5 Litros)
  float volumenConsumidoSesion = volumenTotalLitros - volumenInicioCiclo;
  if (volumenConsumidoSesion >= VOLUMEN_MAX_MAQUETA_L) {
    Serial.print("CORTE PROGRAMADO: Riego completado (");
    Serial.print(volumenConsumidoSesion, 2);
    Serial.println(" L). Entrando en pausa de infiltración.");
    
    controlarValvula(false);
    bloquearPor(PAUSA_RIEGO_MS, "riego de maqueta completado");
    return;
  }

  unsigned long abiertaHace = millis() - tiempoAperturaValvula;

  if (caudalLitrosMin >= CAUDAL_MINIMO_L_MIN) {
    cortesSinCaudal = 0;
  }

  if (abiertaHace > MAX_RIEGO_MS) {
    Serial.println("CORTE: duración máxima de riego alcanzada.");
    controlarValvula(false);
    bloquearPor(ESPERA_BASE_MS, "duracion maxima");
    return;
  }

  if (abiertaHace > GRACIA_CAUDAL_MS && caudalLitrosMin < CAUDAL_MINIMO_L_MIN) {
    if (cortesSinCaudal < 255) cortesSinCaudal++;

    unsigned long espera = ESPERA_BASE_MS;
    for (uint8_t i = 1; i < cortesSinCaudal; i++) {
      if (espera >= ESPERA_MAX_MS) break;
      espera *= 2;
    }
    if (espera > ESPERA_MAX_MS) espera = ESPERA_MAX_MS;

    Serial.print("CORTE: válvula abierta sin caudal. Corte #");
    Serial.print(cortesSinCaudal);
    Serial.print(", reintento en ");
    Serial.print(espera / 60000UL);
    Serial.println(" min.");

    controlarValvula(false);
    bloquearPor(espera, "sin caudal");
  }
}

void abrirSiEstaPermitido(bool quiereAbrir) {
  if (!quiereAbrir) {
    controlarValvula(false);
    return;
  }
  if (aperturaBloqueada()) {
    Serial.print(" -> APERTURA BLOQUEADA (");
    Serial.print(bloqueoVigente() ? motivoBloqueo : (vientoFuerteActual ? "viento fuerte" : "sonda invalida"));
    if (bloqueoVigente()) {
      Serial.print(", quedan ");
      Serial.print((bloqueoHastaMs - millis()) / 1000UL);
      Serial.print(" s");
    }
    Serial.println(")");
    return;
  }
  controlarValvula(true);
}

// --- TRANSMISION AL BACKEND ---
void enviarTelemetriaBackend(float temp, bool tempValida,
                             float hum, bool humValida,
                             int sueloPct, int sueloRaw, bool sueloValido,
                             float viento, float caudal, float volumenTotal,
                             bool decisionLocal) {

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi desconectado. Reconectando.");
    WiFi.reconnect();
    abrirSiEstaPermitido(decisionLocal);
    return;
  }

  WiFiClientSecure secureClient;
  secureClient.setInsecure();

  HTTPClient http;
  http.begin(secureClient, VITIALERT_URL);
  http.setConnectTimeout(TIMEOUT_HTTP_MS);
  http.setTimeout(TIMEOUT_HTTP_MS);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", VITIALERT_API_KEY);

  JsonDocument jsonDoc;
  jsonDoc["nodo_id"] = VITIALERT_NODO_ID;

  if (tempValida)  jsonDoc["temperatura_ambiente_c"] = round(temp * 10.0) / 10.0;
  if (humValida)   jsonDoc["humedad_relativa_pct"]   = int(round(hum));
  if (sueloValido) {
    jsonDoc["humedad_suelo_pct"] = sueloPct;
    jsonDoc["humedad_suelo_raw"] = sueloRaw;
  }

  jsonDoc["velocidad_viento_kmh"]   = round(viento * 10.0) / 10.0;
  jsonDoc["caudal_l_min"]           = round(caudal * 100.0) / 100.0;
  jsonDoc["volumen_total_l"]        = round(volumenTotal * 100.0) / 100.0;
  jsonDoc["valvula_abierta_actual"] = estadoValvulaActual;
  jsonDoc["decision_riego_local"]   = decisionLocal;

  String payload;
  serializeJson(jsonDoc, payload);

  int httpCode = http.POST(payload);

  if (httpCode != 200) {
    Serial.print("Error HTTP: ");
    Serial.println(httpCode);
    abrirSiEstaPermitido(decisionLocal);
    http.end();
    return;
  }

  JsonDocument respuestaDoc;
  DeserializationError error = deserializeJson(respuestaDoc, http.getString());
  http.end();

  if (error) {
    Serial.println("Respuesta ilegible del backend.");
    abrirSiEstaPermitido(decisionLocal);
    return;
  }

  Serial.println("Transmision exitosa (HTTP 200)");

  bool ordenBackend = respuestaDoc["abrir_valvula"] | decisionLocal;
  Serial.print(" -> Orden servidor: ");
  Serial.println(ordenBackend ? "ABRIR" : "CERRAR");

  bool encenderLuz = respuestaDoc["encender_luz"] | false;
  digitalWrite(PIN_LED, encenderLuz ? HIGH : LOW);

  abrirSiEstaPermitido(ordenBackend);
}

void setup() {
  Serial.begin(115200);
  dht.begin();
  tiempoUltimoIntentoDht = millis();
  analogSetAttenuation(ADC_11db);

  pinMode(PIN_RELE_VALVULA, OUTPUT);
  pinMode(PIN_LED, OUTPUT);
  pinMode(PIN_MOTOR_VIENTO, OUTPUT);
  pinMode(PIN_CAUDALIMETRO, INPUT_PULLUP);

  digitalWrite(PIN_RELE_VALVULA, HIGH);
  digitalWrite(PIN_LED, LOW);
  digitalWrite(PIN_MOTOR_VIENTO, HIGH); // Apagado en HIGH (Relé activo en LOW)

  attachInterrupt(digitalPinToInterrupt(PIN_CAUDALIMETRO), contarPulsos, RISING);

  Serial.println("\n[VITIC-AI] Iniciando nodo...");

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int intentos = 0;
  while (WiFi.status() != WL_CONNECTED && intentos < 30) {
    delay(500);
    Serial.print(".");
    intentos++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi conectado.");
  } else {
    Serial.println("\nSin WiFi. Decisión local activa.");
  }

  tiempoAnteriorCaudal = millis();
  tiempoUltimoEnvio    = millis();
}

void loop() {
  unsigned long tiempoActual = millis();

  // 0. SIMULACION DE VIENTO VARIABLE
  simularVientoEsporadico(tiempoActual);

  actualizarDht(tiempoActual);
  float tempAire = ultimaTemperaturaC;
  float humAire  = ultimaHumedadPct;
  bool tempValida = datoDhtReciente(tiempoActual, tiempoUltimaTemperaturaOk);
  bool humValida  = datoDhtReciente(tiempoActual, tiempoUltimaHumedadOk);

  int lecturaSuelo = analogRead(PIN_SUELO);
  bool sueloValido = (lecturaSuelo > 20 && lecturaSuelo < 4075);
  sueloValidoActual = sueloValido;
  int humSuelo = constrain(map(lecturaSuelo, SUELO_SECO, SUELO_AGUA, 0, 100), 0, 100);

  // ANEMÓMETRO REESCALADO PARA POLEA GRANDE
  long sumaViento = 0;
  for (int i = 0; i < MUESTRAS_VIENTO; i++) {
    sumaViento += analogRead(PIN_ANEMOMETRO);
    delay(5);
  }
  float vientoCrudo = sumaViento / (float)MUESTRAS_VIENTO;
  float voltPin   = (vientoCrudo / 4095.0) * 3.3;

  float velocidadViento = 0.0;
  if (voltPin < 0.05) {
    velocidadViento = 0.0;
  } else {
    // Escala base directa ajustada a tu polea (11 km/h crudos)
    float velocidadBase = (voltPin - 0.05) * (11.0 / 0.15); 
    velocidadViento = velocidadBase * factorIntensidadViento;
  }
  if (velocidadViento > 65.0) velocidadViento = 65.0; // Techo máximo razonable

  bool vientoFuerte = (velocidadViento >= VIENTO_FUERTE_KMH);
  vientoFuerteActual = vientoFuerte;

  unsigned long dt = tiempoActual - tiempoAnteriorCaudal;
  if (dt >= 1000) {
    noInterrupts();
    unsigned long pulsosEnIntervalo = pulsosCaudal;
    pulsosCaudal = 0;
    interrupts();

    float frecuenciaHz = (pulsosEnIntervalo * 1000.0) / dt;
    caudalLitrosMin = frecuenciaHz / FACTOR_CALIBRACION_CAUDAL;
    volumenTotalLitros += (caudalLitrosMin / 60.0) * (dt / 1000.0);

    tiempoAnteriorCaudal = tiempoActual;
  }

  aplicarCortesDeSeguridad();

  static bool bloqueoAvisado = false;
  if (bloqueoHastaMs != 0 && !bloqueoVigente() && !bloqueoAvisado) {
    Serial.print("Pausa finalizada, nodo listo para siguiente riego. Era: ");
    Serial.println(motivoBloqueo);
    bloqueoAvisado = true;
  }
  if (bloqueoVigente()) {
    bloqueoAvisado = false;
  }

  bool decisionLocalRiego = sueloValido
                            && (humSuelo < HUMEDAD_SUELO_RIEGO)
                            && !vientoFuerte
                            && !bloqueoVigente();

  bool cambioEstadoValvula = (estadoValvulaActual != estadoValvulaAnterior);
  bool tiempoCumplido      = (tiempoActual - tiempoUltimoEnvio >= INTERVALO_ENVIO_MS);

  if (tiempoCumplido || cambioEstadoValvula) {
    Serial.println("\n--- CICLO DE TRANSMISION ---");
    Serial.print("Ambiente: ");
    if (tempValida) { Serial.print(tempAire, 1); Serial.print(" C"); } else Serial.print("SIN DATO");
    Serial.print(" | Hum: ");
    if (humValida)  { Serial.print(humAire, 0);  Serial.println(" %"); } else Serial.println("SIN DATO");

    Serial.print("Suelo: ");
    if (sueloValido) {
      Serial.print(humSuelo); Serial.print(" % (raw "); Serial.print(lecturaSuelo); Serial.println(")");
    } else {
      Serial.print("SONDA INVALIDA (raw "); Serial.print(lecturaSuelo); Serial.println(")");
    }

    Serial.print("Viento: ");  Serial.print(velocidadViento, 1); Serial.println(" km/h");
    Serial.print("Caudal: ");  Serial.print(caudalLitrosMin, 2);
    Serial.print(" L/min | Total: "); Serial.print(volumenTotalLitros, 2); Serial.println(" L");
    Serial.print("Valvula: "); Serial.println(estadoValvulaActual ? "ABIERTA" : "CERRADA");

    bool estadoReportado = estadoValvulaActual;

    enviarTelemetriaBackend(tempAire, tempValida, humAire, humValida,
                            humSuelo, lecturaSuelo, sueloValido,
                            velocidadViento, caudalLitrosMin, volumenTotalLitros,
                            decisionLocalRiego);

    tiempoUltimoEnvio = tiempoActual;
    estadoValvulaAnterior = estadoReportado;
  }

  delay(100);
}