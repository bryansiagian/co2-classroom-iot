
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <time.h>
#include <sys/time.h>
#include <math.h>
#include <cstring>
#include <cstdio>

#include "secrets.h"

// ======================================
// 1. KONFIGURASI WIFI & MQTT
// ======================================

const char* WIFI_SSID = "HW-Mahasiswa";

const char* MQTT_SERVER = "172.22.44.29";
const uint16_t MQTT_PORT = 8883;

const char* MQTT_USER = "esp32_gd525";
const char* MQTT_TOPIC = "classroom/gd525/sensors";

// Sertifikat publik server MQTT H200.
// Sertifikat sama dengan firmware V3.
const char* SERVER_CERT = R"EOF(-----BEGIN CERTIFICATE-----
MIIDIDCCAgigAwIBAgIUV+lqGLjwFkFpqp018p0BEDt5RI4wDQYJKoZIhvcNAQEL
BQAwFzEVMBMGA1UEAwwMMTcyLjIyLjQ0LjI5MB4XDTI2MTEwMjEyNDQzMVoXDTI3
MTEwMjEyNDQzMVowFzEVMBMGA1UEAwwMMTcyLjIyLjQ0LjI5MIIBIjANBgkqhkiG
9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1NF4GsCFSAx1WXl0SHUeFdpd9scAssFu90rm
zgJFsQUu4b5zSSwFJPPCo2L0Tybe4gdXQAzSYrgMJA1MFZIt229GpjOfYNOu5nsT
VzuHqnaspIqND3BBBGkYC5gBtrPrnkRwkDC48F3tVPz4oddPb6BDrXxsUW1Snuuo
TZB0p+AhU511ItbYgH5X1+ewp6P2q7aw6Uc5GWEMoMkkIplCKoGLZAxJOl5wO8yR
g+1IUwDTESqMJ5fsjBS3Id20HVgClo+jl3FAdIH07V3/30fpX4swsk20VedeB00O
j4p8E5pd76UpTW5RG8H1ykBO7NQCz5FLOaPiuu9lEczrr1d2lwIDAQABo2QwYjAd
BgNVHQ4EFgQUSzpO77HpquhF5woRm9d8SCSESBYwHwYDVR0jBBgwFoAUSzpO77Hp
quhF5woRm9d8SCSESBYwDwYDVR0TAQH/BAUwAwEB/zAPBgNVHREECDAGhwSsFiwd
MA0GCSqGSIb3DQEBCwUAA4IBAQBjyQJ/J1Rp0R7McyIExV8DZ1ApJ9nvQj8Nw6+w
IT6z1PhlQdj7ehrP5ThfXor5HMrj9xSd4zqm5wS+sAwu8WZ2FzhdMshdSV9nUeDD
IaBlNSwUuhpaZdxKB47hRVNLwtRo6X7Vgo/jmygl2g/D9WlGAIieQwCUiLGtP3+Q
TFdQVUVH8CwhksNQfaSwzmIalY6NUFOs0u6TeeOHK8lA6ORIKMbTDcvFkEQdUrIt
qdyQq87vNtR0yp7tgr8VP5Bkg2if1LQjlpebwKjJwZy9ejMtJpOkACQFpejfKqks
f8Uo5C9YhpiGMUJWQn7tLIKv8rlr+kMWoIarxVX908il/+qA
-----END CERTIFICATE-----)EOF";

// ======================================
// 2. KONFIGURASI SENSOR
// ======================================

#define MH_RX_PIN 26
#define MH_TX_PIN 25

#define PIR_PIN 27

#define DHT_PIN 4
#define DHT_TYPE DHT22

DHT dht(DHT_PIN, DHT_TYPE);
HardwareSerial co2Serial(2);

WiFiClientSecure secureClient;
PubSubClient mqttClient(secureClient);

// ======================================
// 3. INTERVAL DAN STATUS
// ======================================

const unsigned long PIR_INTERVAL = 50UL;
const unsigned long PUBLISH_INTERVAL = 10000UL;
const unsigned long RECONNECT_INTERVAL = 5000UL;
const unsigned long NTP_RETRY_INTERVAL = 60000UL;

const unsigned long WIFI_TIMEOUT = 15000UL;
const unsigned long CO2_TIMEOUT = 1500UL;

unsigned long lastPirCheck = 0;
unsigned long lastPublish = 0;
unsigned long lastWiFiReconnect = 0;
unsigned long lastMQTTReconnect = 0;
unsigned long lastNtpAttempt = 0;

unsigned long publishCount = 0;
unsigned long publishFailCount = 0;

bool motionDetected = false;

bool timeInitialized = false;
bool timeFromNTP = false;

// ======================================
// 4. MONITOR PIR
// ======================================

void monitorPIR() {
  unsigned long now = millis();

  if (now - lastPirCheck < PIR_INTERVAL) {
    return;
  }

  lastPirCheck = now;

  if (digitalRead(PIR_PIN) == HIGH) {
    motionDetected = true;
  }
}

// ======================================
// 5. KONEKSI WIFI
// ======================================

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  Serial.println("[WiFi] Menghubungkan...");

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID);

  unsigned long start = millis();

  while (
    WiFi.status() != WL_CONNECTED &&
    millis() - start < WIFI_TIMEOUT
  ) {
    monitorPIR();
    delay(10);
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("[WiFi] TERHUBUNG");

    Serial.print("[WiFi] IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("[WiFi] Gagal. Akan mencoba lagi.");
  }
}

// ======================================
// 6. FALLBACK WAKTU KOMPILASI
// ======================================

// Fallback ini mengasumsikan komputer yang
// mengompilasi firmware berada di WIB (UTC+7).
//
// Digunakan untuk pengujian jika NTP gagal.
// Bukan sumber waktu ideal untuk deployment
// jangka panjang.

bool initializeTimeFromBuild() {
  struct tm tmBuild = {};

  char month[4] = {};
  int day, year;
  int hour, minute, second;

  const char* months[] = {
    "Jan", "Feb", "Mar", "Apr",
    "May", "Jun", "Jul", "Aug",
    "Sep", "Oct", "Nov", "Dec"
  };

  if (
    sscanf(
      __DATE__,
      "%3s %d %d",
      month,
      &day,
      &year
    ) != 3 ||
    sscanf(
      __TIME__,
      "%d:%d:%d",
      &hour,
      &minute,
      &second
    ) != 3
  ) {
    return false;
  }

  int monthIndex = -1;

  for (int i = 0; i < 12; i++) {
    if (strcmp(month, months[i]) == 0) {
      monthIndex = i;
      break;
    }
  }

  if (monthIndex < 0) {
    return false;
  }

  tmBuild.tm_year = year - 1900;
  tmBuild.tm_mon = monthIndex;
  tmBuild.tm_mday = day;
  tmBuild.tm_hour = hour;
  tmBuild.tm_min = minute;
  tmBuild.tm_sec = second;
  tmBuild.tm_isdst = 0;

  setenv("TZ", "UTC0", 1);
  tzset();

  time_t buildTime =
    mktime(&tmBuild) - 7 * 3600;

  if (buildTime <= 0) {
    return false;
  }

  struct timeval tv = {};
  tv.tv_sec = buildTime;
  tv.tv_usec = 0;

  if (settimeofday(&tv, nullptr) == 0) {
    timeInitialized = true;
    timeFromNTP = false;

    Serial.println(
      "[TIME] Fallback waktu kompilasi berhasil."
    );

    Serial.println(
      "[TIME] Peringatan: waktu belum disinkronkan."
    );

    return true;
  }

  Serial.println(
    "[TIME] Fallback waktu kompilasi gagal."
  );

  return false;
}

// ======================================
// 7. SINKRONISASI NTP
// ======================================

bool syncTimeNTP() {
  if (WiFi.status() != WL_CONNECTED) {
    return false;
  }

  Serial.println("[NTP] Sinkronisasi waktu...");

  configTime(
    0,
    0,
    "pool.ntp.org",
    "time.google.com"
  );

  unsigned long start = millis();

  while (millis() - start < 10000UL) {
    monitorPIR();

    time_t now = time(nullptr);

    // Tahun minimal 2025.
    if (now >= 1735689600) {
      timeInitialized = true;
      timeFromNTP = true;

      Serial.println(
        "[NTP] Waktu tersedia."
      );

      return true;
    }

    delay(100);
  }

  Serial.println("[NTP] Gagal.");

  return false;
}

// ======================================
// 8. KONEKSI MQTT TLS
// ======================================

void connectMQTT() {
  if (
    WiFi.status() != WL_CONNECTED ||
    !timeInitialized ||
    mqttClient.connected()
  ) {
    return;
  }

  String clientId = "ESP32-GD525-";
  clientId += WiFi.macAddress();
  clientId.replace(":", "");

  Serial.println("[MQTT] Menghubungkan TLS...");

  bool connected = mqttClient.connect(
    clientId.c_str(),
    MQTT_USER,
    MQTT_PASSWORD
  );

  if (connected) {
    Serial.println("[MQTT] TERHUBUNG!");
  } else {
    Serial.print("[MQTT] Gagal, state: ");
    Serial.println(mqttClient.state());

    char errorBuffer[128] = {};

    int error = secureClient.lastError(
      errorBuffer,
      sizeof(errorBuffer)
    );

    Serial.print("[TLS] Error: ");
    Serial.println(error);
    Serial.println(errorBuffer);
  }
}

// ======================================
// 9. BACA SENSOR MH-Z19C
// ======================================

int readCO2() {
  const uint8_t command[9] = {
    0xFF, 0x01, 0x86,
    0x00, 0x00, 0x00,
    0x00, 0x00, 0x79
  };

  while (co2Serial.available()) {
    co2Serial.read();
  }

  co2Serial.write(command, 9);
  co2Serial.flush();

  uint8_t response[9] = {};
  int count = 0;

  unsigned long start = millis();

  while (
    count < 9 &&
    millis() - start < CO2_TIMEOUT
  ) {
    monitorPIR();

    if (co2Serial.available()) {
      response[count++] = co2Serial.read();
    }

    delay(1);
  }

  if (count != 9) {
    Serial.println("[CO2] Timeout");
    return -1;
  }

  if (
    response[0] != 0xFF ||
    response[1] != 0x86
  ) {
    Serial.println("[CO2] Respons tidak valid");
    return -1;
  }

  uint8_t checksum = 0;

  for (int i = 1; i < 8; i++) {
    checksum += response[i];
  }

  checksum = 0xFF - checksum + 1;

  if (checksum != response[8]) {
    Serial.println("[CO2] Checksum salah");
    return -1;
  }

  return response[2] * 256 + response[3];
}

// ======================================
// 10. BACA DAN KIRIM SENSOR
// ======================================

void publishSensorData() {
  // Ambil status gerakan sejak pengiriman
  // terakhir yang berhasil.
  int pir = motionDetected ? 1 : 0;

  int co2 = readCO2();

  monitorPIR();

  float temperature = dht.readTemperature();
  float humidity = dht.readHumidity();

  monitorPIR();

  Serial.println();
  Serial.println("===== GD525 SENSOR V4.1 =====");

  Serial.print("CO2        : ");
  Serial.print(co2);
  Serial.println(" ppm");

  Serial.print("Suhu       : ");
  Serial.print(temperature);
  Serial.println(" C");

  Serial.print("Kelembapan : ");
  Serial.print(humidity);
  Serial.println(" %");

  Serial.print("PIR latch  : ");
  Serial.println(pir);

  if (
    co2 < 0 ||
    isnan(temperature) ||
    isnan(humidity)
  ) {
    Serial.println(
      "[SENSOR] Pembacaan gagal."
    );

    publishFailCount++;
    return;
  }

  char payload[192];

  snprintf(
    payload,
    sizeof(payload),
    "{\"co2\":%d,"
    "\"temperature\":%.2f,"
    "\"humidity\":%.2f,"
    "\"pir\":%d}",
    co2,
    temperature,
    humidity,
    pir
  );

  Serial.print("[MQTT] Payload: ");
  Serial.println(payload);

  if (!mqttClient.connected()) {
    Serial.println(
      "[MQTT] Tidak terhubung."
    );

    publishFailCount++;
    return;
  }

  bool success = mqttClient.publish(
    MQTT_TOPIC,
    payload
  );

  if (success) {
    publishCount++;

    Serial.print(
      "[MQTT] Publish berhasil #"
    );

    Serial.println(publishCount);

    // Reset latch setelah publish berhasil.
    motionDetected = false;

    // Jika PIR masih HIGH, catat kembali.
    if (digitalRead(PIR_PIN) == HIGH) {
      motionDetected = true;
    }

  } else {
    publishFailCount++;

    Serial.println(
      "[MQTT] Publish gagal."
    );
  }
}

// ======================================
// 11. SETUP
// ======================================

void setup() {
  Serial.begin(115200);
  delay(1500);

  Serial.println();
  Serial.println("==================================");
  Serial.println(" GD525 SENSOR V4.1");
  Serial.println(" CONTINUOUS MONITORING");
  Serial.println("==================================");

  pinMode(PIR_PIN, INPUT);

  dht.begin();

  co2Serial.begin(
    9600,
    SERIAL_8N1,
    MH_RX_PIN,
    MH_TX_PIN
  );

  Serial.println("PIR sampling : 50 ms");
  Serial.println("MQTT publish : 10 detik");
  Serial.println("Durasi       : Continuous");

  lastPirCheck = millis();

  secureClient.setCACert(SERVER_CERT);
  secureClient.setHandshakeTimeout(15);

  mqttClient.setServer(
    MQTT_SERVER,
    MQTT_PORT
  );

  mqttClient.setKeepAlive(30);
  mqttClient.setSocketTimeout(10);

  // Wi-Fi
  connectWiFi();

  // Coba NTP, lalu fallback jika gagal.
  if (WiFi.status() == WL_CONNECTED) {
    lastNtpAttempt = millis();

    if (!syncTimeNTP()) {
      Serial.println(
        "[TIME] Menggunakan fallback..."
      );

      initializeTimeFromBuild();
    }

    if (timeInitialized) {
      connectMQTT();
    }
  }

  lastPublish = millis();

  Serial.println(
    "[SYSTEM] Monitoring dimulai."
  );
}

// ======================================
// 12. LOOP CONTINUOUS MONITORING
// ======================================

void loop() {
  monitorPIR();

  unsigned long now = millis();

  // A. Reconnect Wi-Fi
  if (WiFi.status() != WL_CONNECTED) {
    if (
      now - lastWiFiReconnect >=
      RECONNECT_INTERVAL
    ) {
      lastWiFiReconnect = now;
      connectWiFi();
    }

    delay(10);
    return;
  }

  // B. Jika belum memiliki waktu valid,
  // coba NTP atau fallback.
  if (!timeInitialized) {
    if (
      now - lastNtpAttempt >=
      NTP_RETRY_INTERVAL
    ) {
      lastNtpAttempt = now;

      if (!syncTimeNTP()) {
        initializeTimeFromBuild();
      }
    }

    delay(10);
    return;
  }

  // C. Reconnect MQTT
  if (!mqttClient.connected()) {
    if (
      now - lastMQTTReconnect >=
      RECONNECT_INTERVAL
    ) {
      lastMQTTReconnect = now;
      connectMQTT();
    }
  } else {
    mqttClient.loop();
  }

  // D. Kirim sensor setiap 10 detik
  if (
    millis() - lastPublish >=
    PUBLISH_INTERVAL
  ) {
    lastPublish = millis();
    publishSensorData();
  }

  delay(10);
}
