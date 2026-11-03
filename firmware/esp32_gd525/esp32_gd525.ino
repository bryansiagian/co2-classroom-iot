
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <time.h>
#include <sys/time.h>
#include <math.h>
#include <cstring>
#include <cstdio>

// ======================================
// 1. WIFI DAN MQTT
// ======================================

const char* WIFI_SSID = "HW-Mahasiswa";

const char* MQTT_SERVER = "172.22.44.29";
const int MQTT_PORT = 8883;

const char* MQTT_USER = "esp32_gd525";
const char* MQTT_PASSWORD = "@Bryan2026!";

const char* MQTT_TOPIC = "classroom/gd525/sensors";

// PENTING:
// Ganti blok ini dengan SERVER_CERT lengkap
// dari firmware V2 yang sudah berhasil.
// Sertifikat harus sama persis.
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
// 2. PIN SENSOR
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
// 3. PENGATURAN INTERVAL
// ======================================

const unsigned long PIR_INTERVAL = 50UL;
const unsigned long PUBLISH_INTERVAL = 10000UL;
const unsigned long TEST_DURATION = 900000UL;

unsigned long testStart = 0;
unsigned long lastPublish = 0;
unsigned long lastPirCheck = 0;
unsigned long lastReconnect = 0;

bool testFinished = false;

// Motion latch:
// TRUE jika PIR pernah HIGH sejak
// pengiriman sebelumnya.
bool motionDetected = false;

unsigned int publishCount = 0;

// ======================================
// 4. WAKTU SEMENTARA UNTUK TLS
// ======================================

bool initializeTime() {
  struct tm tmBuild = {};

  char month[4] = {};
  int day, year;
  int hour, minute, second;

  const char* months[] = {
    "Jan", "Feb", "Mar", "Apr",
    "May", "Jun", "Jul", "Aug",
    "Sep", "Oct", "Nov", "Dec"
  };

  if (sscanf(__DATE__, "%3s %d %d",
             month, &day, &year) != 3 ||
      sscanf(__TIME__, "%d:%d:%d",
             &hour, &minute, &second) != 3) {
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

  // Asumsi waktu kompilasi menggunakan WIB.
  time_t buildTime = mktime(&tmBuild) - 7 * 3600;

  struct timeval tv = {};
  tv.tv_sec = buildTime;

  return settimeofday(&tv, nullptr) == 0;
}

// ======================================
// 5. BACA MH-Z19C
// ======================================

int readCO2() {
  const uint8_t command[9] = {
    0xFF, 0x01, 0x86, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x79
  };

  while (co2Serial.available()) {
    co2Serial.read();
  }

  co2Serial.write(command, 9);
  co2Serial.flush();

  uint8_t response[9] = {};
  int count = 0;

  unsigned long start = millis();

  while (count < 9 && millis() - start < 1500) {
    if (co2Serial.available()) {
      response[count++] = co2Serial.read();
    }
    delay(1);
  }

  if (count != 9) {
    Serial.println("MH-Z19C: timeout");
    return -1;
  }

  if (response[0] != 0xFF ||
      response[1] != 0x86) {
    Serial.println("MH-Z19C: respons tidak valid");
    return -1;
  }

  uint8_t checksum = 0;

  for (int i = 1; i < 8; i++) {
    checksum += response[i];
  }

  checksum = 0xFF - checksum + 1;

  if (checksum != response[8]) {
    Serial.println("MH-Z19C: checksum salah");
    return -1;
  }

  return response[2] * 256 + response[3];
}

// ======================================
// 6. PEMANTAUAN PIR (MOTION LATCH)
// ======================================

void monitorPIR() {
  unsigned long now = millis();

  if (now - lastPirCheck < PIR_INTERVAL) {
    return;
  }

  lastPirCheck = now;

  int pirState = digitalRead(PIR_PIN);

  if (pirState == HIGH) {
    motionDetected = true;
  }
}

// ======================================
// 7. KONEKSI WIFI
// ======================================

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  Serial.println("Menghubungkan WiFi...");

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID);

  unsigned long start = millis();

  while (WiFi.status() != WL_CONNECTED &&
         millis() - start < 15000) {
    monitorPIR();
    delay(10);
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("WiFi terhubung!");
    Serial.print("IP ESP32: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("WiFi gagal!");
  }
}

// ======================================
// 8. KONEKSI MQTT TLS
// ======================================

void connectMQTT() {
  if (WiFi.status() != WL_CONNECTED ||
      mqttClient.connected()) {
    return;
  }

  String clientId = "ESP32-GD525-";
  clientId += WiFi.macAddress();
  clientId.replace(":", "");

  Serial.println("Menghubungkan MQTT TLS...");

  if (mqttClient.connect(
        clientId.c_str(),
        MQTT_USER,
        MQTT_PASSWORD
      )) {
    Serial.println("MQTT TERHUBUNG!");
  } else {
    Serial.print("MQTT gagal, state: ");
    Serial.println(mqttClient.state());

    char errorBuffer[128] = {};

    int error = secureClient.lastError(
      errorBuffer,
      sizeof(errorBuffer)
    );

    Serial.print("TLS error: ");
    Serial.println(error);
    Serial.println(errorBuffer);
  }
}

// ======================================
// 9. BACA DAN KIRIM SENSOR
// ======================================

void publishSensorData() {
  // Ambil status aktivitas yang tercatat
  // selama interval sebelumnya.
  int pir = motionDetected ? 1 : 0;

  int co2 = readCO2();

  // Periksa PIR lagi setelah pembacaan CO2.
  monitorPIR();

  float temperature = dht.readTemperature();
  float humidity = dht.readHumidity();

  // Periksa PIR lagi setelah pembacaan DHT.
  monitorPIR();

  Serial.println();
  Serial.println("===== SENSOR V3 =====");

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

  if (co2 < 0 ||
      isnan(temperature) ||
      isnan(humidity)) {
    Serial.println(
      "Pembacaan sensor gagal. Data dilewati."
    );
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

  Serial.println("DATA MQTT:");
  Serial.println(payload);

  if (!mqttClient.connected()) {
    Serial.println(
      "MQTT terputus. Data belum terkirim."
    );
    return;
  }

  bool success = mqttClient.publish(
    MQTT_TOPIC,
    payload
  );

  if (success) {
    publishCount++;

    Serial.println("Publish berhasil!");

    // Reset hanya setelah pengiriman berhasil.
    // Aktivitas yang terdeteksi selama pembacaan
    // sensor tetap dipertahankan.
    motionDetected = motionDetected && (pir == 0);
  } else {
    Serial.println("Publish gagal!");
  }
}

// ======================================
// 10. SETUP
// ======================================

void setup() {
  Serial.begin(115200);
  delay(1500);

  pinMode(PIR_PIN, INPUT);

  dht.begin();

  co2Serial.begin(
    9600,
    SERIAL_8N1,
    MH_RX_PIN,
    MH_TX_PIN
  );

  Serial.println();
  Serial.println(
    "=== GD525 SENSOR V3 - MOTION LATCH ==="
  );

  Serial.println(
    "PIR sampling: 50 ms"
  );

  Serial.println(
    "MQTT publish: 10 detik"
  );

  Serial.println(
    "Durasi: 15 menit"
  );

  testStart = millis();
  lastPirCheck = millis();

  // Mulai mencatat status PIR.
  monitorPIR();

  connectWiFi();

  if (!initializeTime()) {
    Serial.println(
      "Gagal inisialisasi waktu TLS."
    );
    testFinished = true;
    return;
  }

  secureClient.setCACert(SERVER_CERT);
  secureClient.setHandshakeTimeout(15);

  mqttClient.setServer(
    MQTT_SERVER,
    MQTT_PORT
  );

  mqttClient.setKeepAlive(30);
  mqttClient.setSocketTimeout(10);

  connectMQTT();

  lastPublish = millis();
}

// ======================================
// 11. LOOP
// ======================================

void loop() {
  if (testFinished) {
    delay(1000);
    return;
  }

  // Pantau PIR sesering mungkin.
  monitorPIR();

  if (millis() - testStart >= TEST_DURATION) {
    testFinished = true;

    Serial.println();
    Serial.println(
      "=== UJI COBA 15 MENIT SELESAI ==="
    );

    Serial.print("Total publish berhasil: ");
    Serial.println(publishCount);

    mqttClient.disconnect();
    return;
  }

  if (WiFi.status() != WL_CONNECTED) {
    if (millis() - lastReconnect >= 5000) {
      lastReconnect = millis();
      connectWiFi();
    }

    delay(10);
    return;
  }

  if (!mqttClient.connected()) {
    if (millis() - lastReconnect >= 5000) {
      lastReconnect = millis();
      connectMQTT();
    }
  } else {
    mqttClient.loop();
  }

  if (millis() - lastPublish >= PUBLISH_INTERVAL) {
    lastPublish = millis();
    publishSensorData();
  }

  delay(10);
}
