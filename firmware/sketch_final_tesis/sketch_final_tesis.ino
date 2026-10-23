// VitiAlert: nodo ESP32 de adquisicion y control local.
// Envia telemetria y aplica la respuesta del backend con respaldo local.
// Las credenciales se definen en secrets.h, excluido de Git.
// Los campos del DHT sin lectura reciente se omiten; el backend los marca MISSING.
// Los cortes locales limitan duracion y falta de caudal. El HTTP bloqueante puede
// retrasar su evaluacion: no sustituyen un corte fisico independiente del ESP32.

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

// --- CALIBRACION ---
const int   SUELO_SECO = 3317;
const int   SUELO_AGUA = 1104;
const int   MUESTRAS_VIENTO = 10;
const float FACTOR_CALIBRACION_CAUDAL = 7.5;

// --- UMBRALES DE DECISION ---
const float HUMEDAD_SUELO_RIEGO    = 30.0;   // por debajo de esto, regar
const float VIENTO_FUERTE_KMH      = 45.0;   // por encima de esto, cortar

// --- SEGURIDAD DE LA VALVULA ---
// Un riego por goteo real dura horas, no dias. Si se pasa de aca, lo que hay es un nodo
// colgado, no un riego largo. El backend aplica el mismo criterio del lado del dataset.
const unsigned long MAX_RIEGO_MS       = 6UL * 60UL * 60UL * 1000UL;  // 6 h
// Valvula abierta y sin caudal = obstruccion, corte de suministro o electrovalvula trabada.
// Se espera un rato antes de juzgar: la linea tarda en presurizar.
const unsigned long GRACIA_CAUDAL_MS   = 120000UL;                    // 2 min
// Mismo umbral que vitialert.quality.flow-noise-threshold-l-min en el backend: los
// caudalimetros de efecto Hall reportan pulsos espurios cerca de cero.
const float CAUDAL_MINIMO_L_MIN        = 0.2;

// --- RED ---
const unsigned long INTERVALO_ENVIO_MS = 60000;
// El DHT22 admite como maximo una medicion cada ~2 s. Se usa un margen de 2,5 s y se
// conserva solamente una lectura reciente: un fallo aislado no genera un null, pero si el
// sensor lleva mas de 10 s sin responder el campo se omite y el backend lo marca MISSING.
const unsigned long INTERVALO_DHT_MS    = 2500;
const unsigned long MAX_EDAD_DHT_MS     = 10000;
// Render free tarda ~2 min en despertar, mas de lo que conviene bloquear el loop. En vez de
// esperar el arranque en frio dentro de una sola llamada, se corta antes y se reintenta en el
// ciclo siguiente: el respaldo local gobierna la valvula mientras tanto.
const uint16_t TIMEOUT_HTTP_MS         = 15000;

DHT dht(DHTPIN, DHTTYPE);

// --- ULTIMA LECTURA DHT22 ---
// Se actualiza sin bloquear el loop. Temperatura y humedad llevan tiempos separados porque
// puede fallar solo uno de los dos valores. Los NAN nunca se copian sobre un dato valido.
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
  float humedad = dht.readHumidity();

  if (!isnan(temperatura)) {
    ultimaTemperaturaC = temperatura;
    tiempoUltimaTemperaturaOk = ahoraMs;
  }
  if (!isnan(humedad)) {
    ultimaHumedadPct = humedad;
    tiempoUltimaHumedadOk = ahoraMs;
  }
}

bool datoDhtReciente(unsigned long ahoraMs, unsigned long ultimoDatoOkMs) {
  return ultimoDatoOkMs != 0 && ahoraMs - ultimoDatoOkMs <= MAX_EDAD_DHT_MS;
}

// --- ESTADO ---
bool estadoValvulaActual   = false;
bool estadoValvulaAnterior = false;

unsigned long tiempoAperturaValvula = 0;  // millis() del ultimo cambio a ABIERTA
unsigned long tiempoAnteriorCaudal  = 0;
unsigned long tiempoUltimoEnvio     = 0;

// Bloqueo de seguridad: una vez que un corte automatico actuo, no se vuelve a abrir hasta
// que la condicion que lo provoco desaparezca. Sin esto, el ciclo siguiente reabriria la
// valvula de inmediato y el corte no serviria de nada.
//
// El bloqueo por viento o por sonda invalida se levanta solo cuando la condicion desaparece:
// son transitorios y la condicion misma es la que manda. El bloqueo por falta de caudal, en
// cambio, necesita ESPERA CRECIENTE: una obstruccion o un corte de suministro no se arregla
// en un minuto, y reintentar cada minuto cicla el rele indefinidamente y lo desgasta sin
// ninguna chance de exito. Se empieza esperando 5 minutos y se duplica en cada corte
// consecutivo hasta un techo de una hora.
unsigned long bloqueoHastaMs = 0;   // 0 = sin bloqueo temporizado vigente
uint8_t       cortesSinCaudal = 0;  // cortes seguidos sin que haya circulado agua
const char*   motivoBloqueo = "";

const unsigned long ESPERA_BASE_MS = 5UL * 60UL * 1000UL;   // 5 min
const unsigned long ESPERA_MAX_MS  = 60UL * 60UL * 1000UL;  // 1 h

// Condiciones del ciclo actual. Se actualizan al principio de cada loop y las consultan
// tanto los cortes como la decision de apertura.
bool vientoFuerteActual = false;
bool sueloValidoActual  = true;

// La resta en aritmetica con signo es lo que mantiene esto correcto cuando millis() da la
// vuelta a los 49 dias. Comparar "millis() < bloqueoHastaMs" fallaria justo en ese momento.
bool bloqueoVigente() {
  return bloqueoHastaMs != 0 && (long)(millis() - bloqueoHastaMs) < 0;
}

bool aperturaBloqueada() {
  return bloqueoVigente() || vientoFuerteActual || !sueloValidoActual;
}

void bloquearPor(unsigned long duracionMs, const char* motivo) {
  bloqueoHastaMs = millis() + duracionMs;
  if (bloqueoHastaMs == 0) bloqueoHastaMs = 1;  // 0 significa "sin bloqueo"
  motivoBloqueo = motivo;
}

// --- CAUDALIMETRO ---
volatile unsigned long pulsosCaudal   = 0;
volatile unsigned long ultimoPulsoUs  = 0;
float caudalLitrosMin    = 0.0;
float volumenTotalLitros = 0.0;

// Un caudalimetro YF-S201 a 30 L/min ronda los 225 Hz, o sea ~4,4 ms entre pulsos. Todo lo
// que llegue mas rapido que 1 ms es rebote del reed/Hall o ruido inducido por el cable, no
// agua. Sin este filtro el volumen acumulado sube solo con la valvula cerrada.
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
    return;  // ya esta en ese estado: no repetir el log ni reiniciar el cronometro
  }
  if (abrir) {
    digitalWrite(PIN_RELE_VALVULA, LOW);
    estadoValvulaActual = true;
    tiempoAperturaValvula = millis();
    Serial.println(" -> RELE FISICO: ACTIVADO [ABIERTO]");
  } else {
    digitalWrite(PIN_RELE_VALVULA, HIGH);
    estadoValvulaActual = false;
    Serial.println(" -> RELE FISICO: DESACTIVADO [CERRADO]");
  }
}

// ---------------------------------------------------------------------
// Cortes locales, evaluados antes de la siguiente operacion de red.
// Una operacion HTTP ya iniciada puede retrasar la siguiente comprobacion.
// ---------------------------------------------------------------------
void aplicarCortesDeSeguridad() {
  if (vientoFuerteActual && estadoValvulaActual) {
    Serial.println("CORTE: rafaga de viento. La deriva desperdicia el agua y moja la hoja.");
    controlarValvula(false);
    motivoBloqueo = "viento fuerte";
    return;
  }

  // Se evalua aunque la valvula ya este cerrada: sin medicion de suelo confiable tampoco se
  // obedece una orden de apertura del backend.
  if (!sueloValidoActual) {
    if (estadoValvulaActual) {
      Serial.println("CORTE: sonda de suelo fuera de rango. Sin medicion confiable no se riega.");
      controlarValvula(false);
    }
    motivoBloqueo = "sonda de suelo invalida";
    return;
  }

  if (!estadoValvulaActual) {
    return;
  }

  unsigned long abiertaHace = millis() - tiempoAperturaValvula;

  // Si esta circulando agua, el riego es real: se limpia la racha de cortes en seco para que
  // la proxima obstruccion vuelva a empezar la espera desde los 5 minutos.
  if (caudalLitrosMin >= CAUDAL_MINIMO_L_MIN) {
    cortesSinCaudal = 0;
  }

  if (abiertaHace > MAX_RIEGO_MS) {
    Serial.println("CORTE: duracion maxima de riego alcanzada.");
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

    Serial.print("CORTE: valvula abierta sin caudal (obstruccion o falta de suministro). Corte #");
    Serial.print(cortesSinCaudal);
    Serial.print(", reintento en ");
    Serial.print(espera / 60000UL);
    Serial.println(" min.");

    controlarValvula(false);
    bloquearPor(espera, "sin caudal");
  }
}

// Una orden de apertura solo se obedece si ningun bloqueo esta activo.
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

// ---------------------------------------------------------------------
// Transmision al backend
// ---------------------------------------------------------------------
void enviarTelemetriaBackend(float temp, bool tempValida,
                             float hum, bool humValida,
                             int sueloPct, int sueloRaw, bool sueloValido,
                             float viento, float caudal, float volumenTotal,
                             bool decisionLocal) {

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi desconectado. Reconectando. Gobierna la decision local.");
    WiFi.reconnect();
    abrirSiEstaPermitido(decisionLocal);
    return;
  }

  WiFiClientSecure secureClient;
  // Sin validacion de certificado: el ESP32 no tiene el almacen de raices y fijar el
  // certificado de Render obligaria a reflashear cada rotacion. El trafico igual viaja
  // cifrado; lo que se resigna es autenticar al servidor. Aceptable para el prototipo,
  // pero es una limitacion que hay que declarar en la tesis.
  secureClient.setInsecure();

  HTTPClient http;
  http.begin(secureClient, VITIALERT_URL);
  http.setConnectTimeout(TIMEOUT_HTTP_MS);
  http.setTimeout(TIMEOUT_HTTP_MS);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", VITIALERT_API_KEY);

  JsonDocument jsonDoc;
  jsonDoc["nodo_id"] = VITIALERT_NODO_ID;

  // Campos condicionales: si el sensor fallo, el campo NO va. El backend lo guarda como
  // null y marca la lectura MISSING. Nunca se manda un valor inventado.
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

  // Solo 200 es exito. Un 401 o un 500 tambien devuelven un codigo positivo, y tomarlos
  // por buenos dejaria la valvula gobernada por una respuesta que no existe.
  if (httpCode != 200) {
    Serial.print("Error HTTP: ");
    Serial.print(httpCode);
    if (httpCode == 401) {
      Serial.println("  -> X-API-Key rechazada. Revisar secrets.h contra Render.");
    } else if (httpCode < 0) {
      Serial.println("  -> sin respuesta (probable arranque en frio de Render). Se reintenta.");
    } else {
      Serial.println("");
    }
    abrirSiEstaPermitido(decisionLocal);
    http.end();
    return;
  }

  JsonDocument respuestaDoc;
  DeserializationError error = deserializeJson(respuestaDoc, http.getString());
  http.end();

  if (error) {
    Serial.println("Respuesta ilegible del backend. Gobierna la decision local.");
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

// ---------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  dht.begin();
  // Da tiempo al DHT22 para estabilizarse antes del primer intento de lectura.
  tiempoUltimoIntentoDht = millis();
  analogSetAttenuation(ADC_11db);

  pinMode(PIN_RELE_VALVULA, OUTPUT);
  pinMode(PIN_LED, OUTPUT);
  pinMode(PIN_CAUDALIMETRO, INPUT_PULLUP);

  // Estado inicial seguro: valvula CERRADA, LED apagado.
  digitalWrite(PIN_RELE_VALVULA, HIGH);
  digitalWrite(PIN_LED, LOW);

  attachInterrupt(digitalPinToInterrupt(PIN_CAUDALIMETRO), contarPulsos, RISING);

  Serial.println("\n[VITIC-AI] Iniciando nodo...");
  Serial.print("Nodo: ");
  Serial.println(VITIALERT_NODO_ID);
  Serial.print("Conectando a: ");
  Serial.println(WIFI_SSID);

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int intentos = 0;
  while (WiFi.status() != WL_CONNECTED && intentos < 30) {
    delay(500);
    Serial.print(".");
    intentos++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi conectado.");
    Serial.print("IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\nSin WiFi. El nodo sigue funcionando con la decision local.");
  }

  // El contador de volumen arranca de cero en cada reinicio. El backend lo detecta al
  // cerrar el evento de riego (volumen final menor que el inicial) y lo marca
  // CLOSED_WITH_WARNING en vez de calcular un consumo negativo.
  tiempoAnteriorCaudal = millis();
  tiempoUltimoEnvio    = millis();
}

// ---------------------------------------------------------------------
void loop() {
  unsigned long tiempoActual = millis();

  // 1. TEMPERATURA Y HUMEDAD AMBIENTE
  actualizarDht(tiempoActual);
  float tempAire = ultimaTemperaturaC;
  float humAire  = ultimaHumedadPct;
  bool tempValida = datoDhtReciente(tiempoActual, tiempoUltimaTemperaturaOk);
  bool humValida  = datoDhtReciente(tiempoActual, tiempoUltimaHumedadOk);

  // 2. HUMEDAD DE SUELO.
  // Una lectura pegada a cualquiera de los dos extremos del ADC significa sonda
  // desconectada o cable cortado, no suelo saturado ni suelo seco. Tomarla por buena daria
  // 0 % de humedad y el nodo regaria indefinidamente contra un sensor que no existe.
  int lecturaSuelo = analogRead(PIN_SUELO);
  bool sueloValido = (lecturaSuelo > 20 && lecturaSuelo < 4075);
  sueloValidoActual = sueloValido;
  int humSuelo = constrain(map(lecturaSuelo, SUELO_SECO, SUELO_AGUA, 0, 100), 0, 100);

  // 3. ANEMOMETRO
  long sumaViento = 0;
  for (int i = 0; i < MUESTRAS_VIENTO; i++) {
    sumaViento += analogRead(PIN_ANEMOMETRO);
    delay(5);
  }
  float vientoCrudo = sumaViento / (float)MUESTRAS_VIENTO;
  float voltPin   = (vientoCrudo / 4095.0) * 3.3;
  float voltMotor = voltPin * 3.12;

  float velocidadViento = 0.0;
  if (voltMotor < 0.005) {
    velocidadViento = 0.0;
  } else if (voltMotor < 0.33) {
    velocidadViento = 5.0 + ((voltMotor - 0.005) * (45.0 / 0.325));
  } else {
    velocidadViento = 40.0 + (voltMotor * 30.0);
  }
  if (velocidadViento > 120.0) velocidadViento = 120.0;

  bool vientoFuerte = (velocidadViento >= VIENTO_FUERTE_KMH);
  vientoFuerteActual = vientoFuerte;

  // 4. CAUDAL Y VOLUMEN ACUMULADO
  unsigned long dt = tiempoActual - tiempoAnteriorCaudal;
  if (dt >= 1000) {
    noInterrupts();
    unsigned long pulsosEnIntervalo = pulsosCaudal;
    pulsosCaudal = 0;
    interrupts();

    // La integracion usa dt real, asi que sigue siendo correcta aunque una llamada HTTP
    // haya demorado varios segundos el ciclo.
    float frecuenciaHz = (pulsosEnIntervalo * 1000.0) / dt;
    caudalLitrosMin = frecuenciaHz / FACTOR_CALIBRACION_CAUDAL;
    volumenTotalLitros += (caudalLitrosMin / 60.0) * (dt / 1000.0);

    tiempoAnteriorCaudal = tiempoActual;
  }

  // 5. CORTES DE SEGURIDAD. Van antes que todo lo demas.
  aplicarCortesDeSeguridad();

  // 6. AVISO CUANDO VENCE EL BLOQUEO TEMPORIZADO.
  // No hace falta "levantarlo": bloqueoVigente() ya devuelve false sola cuando vence. Esto
  // es solo para que quede en el monitor serie.
  static bool bloqueoAvisado = false;
  if (bloqueoHastaMs != 0 && !bloqueoVigente() && !bloqueoAvisado) {
    Serial.print("Bloqueo vencido, se puede volver a abrir. Era: ");
    Serial.println(motivoBloqueo);
    bloqueoAvisado = true;
  }
  if (bloqueoVigente()) {
    bloqueoAvisado = false;
  }

  // 7. DECISION LOCAL DE RESPALDO.
  // Sin medicion de suelo confiable no se riega: es la opcion segura.
  bool decisionLocalRiego = sueloValido
                            && (humSuelo < HUMEDAD_SUELO_RIEGO)
                            && !vientoFuerte
                            && !bloqueoVigente();

  // 8. TRANSMISION: cada 60 s, o en cuanto cambie el estado fisico de la valvula.
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

    // El estado que efectivamente viaja en el JSON. Se captura ANTES del envio porque la
    // respuesta del backend puede cambiar la valvula dentro de esa misma llamada.
    bool estadoReportado = estadoValvulaActual;

    enviarTelemetriaBackend(tempAire, tempValida, humAire, humValida,
                            humSuelo, lecturaSuelo, sueloValido,
                            velocidadViento, caudalLitrosMin, volumenTotalLitros,
                            decisionLocalRiego);

    tiempoUltimoEnvio = tiempoActual;

    // Se guarda el estado REPORTADO, no el actual. Si el backend ordeno abrir y la valvula
    // cambio durante el envio, la vuelta siguiente detecta la diferencia y manda de inmediato
    // un POST confirmando la apertura. Guardar el estado actual perdia esa confirmacion y el
    // backend no se enteraba hasta 60 s despues: el evento de riego arrancaba tarde y su
    // duracion quedaba subestimada en hasta un intervalo entero.
    estadoValvulaAnterior = estadoReportado;
  }

  delay(100);
}
