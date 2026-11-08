#include <WiFi.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <time.h>
#include <sys/time.h>
#include <esp_sntp.h>
#include <esp_system.h>
#include <math.h>
#include <cstring>
#include <cstdio>
#include "secrets.h"

// GD525 V4.3 - firmware dual-mode berdasarkan V4.2.
// DEV    : GD525-DEV -> broker Windows port 1883 (tanpa TLS).
// CAMPUS : HW-Mahasiswa -> H200 172.22.44.29:8883 (TLS).
// Jangan memasukkan password ke repositori; tetap gunakan secrets.h.
const char* DEV_SSID = "GD525-DEV";
const char* CAMPUS_SSID = "HW-Mahasiswa";
const char* CAMPUS_BROKER = "172.22.44.29";
const char* CAMPUS_USER = "esp32_gd525";
const char* DEVICE_ID = "esp32_gd525";
const char* SENSOR_TOPIC = "classroom/gd525/sensors";

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

#define MH_RX_PIN 26
#define MH_TX_PIN 25
#define PIR_PIN 27
#define DHT_PIN 4
#define DHT_TYPE DHT22

DHT dht(DHT_PIN, DHT_TYPE);
HardwareSerial co2Serial(2);
WiFiClient plainClient;
WiFiClientSecure tlsClient;
PubSubClient mqttClient(plainClient);

enum Mode { NONE, DEV, CAMPUS };
Mode mode = NONE;

const unsigned long PIR_INTERVAL = 50UL;
const unsigned long SEND_INTERVAL = 10000UL;
const unsigned long RETRY_INTERVAL = 5000UL;
const unsigned long WIFI_TIMEOUT = 12000UL;
const unsigned long CO2_TIMEOUT = 1500UL;
const unsigned long NTP_RETRY_INTERVAL = 300000UL;

unsigned long lastPIR = 0;
unsigned long lastSend = 0;
unsigned long lastWifiRetry = 0;
unsigned long lastMqttRetry = 0;
unsigned long lastNtpAttempt = 0;
unsigned long sendCount = 0;
unsigned long sendFailures = 0;
uint32_t sampleSeq = 0;
char bootId[24] = {};

bool pirLatched = false;
bool timeAvailable = false;  // Jam cukup tersedia untuk TLS; BUKAN bukti NTP.
bool ntpSynced = false;      // Hanya true setelah SNTP melaporkan sinkronisasi.

void monitorPIR() {
  if (millis() - lastPIR < PIR_INTERVAL) return;
  lastPIR = millis();
  if (digitalRead(PIR_PIN) == HIGH) pirLatched = true;
}

Mode modeForSSID(const String& ssid) {
  if (ssid == DEV_SSID) return DEV;
  if (ssid == CAMPUS_SSID) return CAMPUS;
  return NONE;
}

void generateBootId() {
  // Dua angka acak dari RNG ESP32. Sangat kecil peluang tabrakan antar boot.
  snprintf(bootId, sizeof(bootId), "%08lx%08lx",
           (unsigned long)esp_random(), (unsigned long)esp_random());
}

void configureBroker(Mode next) {
  mqttClient.disconnect();
  plainClient.stop();
  tlsClient.stop();
  mode = next;

  Serial.println("\n==================================");
  Serial.println("[DEBUG] KONFIGURASI KONEKSI V4.3");
  Serial.println("==================================");
  Serial.print("[DEBUG] SSID WiFi    : "); Serial.println(WiFi.SSID());
  Serial.print("[DEBUG] IP ESP32     : "); Serial.println(WiFi.localIP());
  Serial.print("[DEBUG] Gateway      : "); Serial.println(WiFi.gatewayIP());
  Serial.print("[DEBUG] Subnet Mask  : "); Serial.println(WiFi.subnetMask());
  Serial.print("[DEBUG] WiFi Status  : "); Serial.println(WiFi.status());

  if (mode == DEV) {
    mqttClient.setClient(plainClient);
    mqttClient.setServer(DEV_MQTT_HOST, 1883);
    Serial.println("[MODE] DEVELOPMENT | MQTT 1883 | TLS OFF");
    Serial.print("[DEBUG] MQTT Host: "); Serial.println(DEV_MQTT_HOST);
  } else if (mode == CAMPUS) {
    tlsClient.setCACert(SERVER_CERT);
    tlsClient.setHandshakeTimeout(15);
    mqttClient.setClient(tlsClient);
    mqttClient.setServer(CAMPUS_BROKER, 8883);
    Serial.println("[MODE] CAMPUS | MQTT 8883 | TLS ON");
    Serial.print("[DEBUG] MQTT Host: "); Serial.println(CAMPUS_BROKER);
  } else {
    Serial.println("[MODE] NONE");
  }

  mqttClient.setKeepAlive(30);
  mqttClient.setSocketTimeout(10);
  if (!mqttClient.setBufferSize(768)) {
    Serial.println("[ERROR] Tidak bisa alokasi buffer MQTT 768 byte");
  }
  lastMqttRetry = 0;
  Serial.println("==================================\n");
}

bool tryWiFi(const char* ssid, const char* password) {
  WiFi.disconnect();
  delay(100);
  Serial.print("[WiFi] Mencoba "); Serial.println(ssid);
  WiFi.begin(ssid, password);
  unsigned long started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < WIFI_TIMEOUT) {
    monitorPIR();
    delay(20);
  }
  return WiFi.status() == WL_CONNECTED;
}

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    Mode next = modeForSSID(WiFi.SSID());
    if (next != mode && next != NONE) configureBroker(next);
    return;
  }
  if (mode != NONE) {
    mqttClient.disconnect();
    mode = NONE;
  }
  WiFi.mode(WIFI_STA);
  bool connected = tryWiFi(DEV_SSID, DEV_WIFI_PASSWORD);
  if (!connected) connected = tryWiFi(CAMPUS_SSID, nullptr);
  if (connected) {
    Serial.print("[WiFi] Connected: "); Serial.println(WiFi.SSID());
    Serial.print("[WiFi] ESP32 IP: "); Serial.println(WiFi.localIP());
    configureBroker(modeForSSID(WiFi.SSID()));
  } else {
    Serial.println("[WiFi] Keduanya tidak tersedia. Mencoba lagi nanti.");
  }
}

bool initializeTimeFromBuild() {
  // Fallback untuk validasi sertifikat TLS seperti V4.2.
  // TIDAK boleh dipakai sebagai measured_at_utc.
  struct tm build = {};
  char month[4] = {};
  int day, year, hour, minute, second;
  const char* months[] = {
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
  };
  if (sscanf(__DATE__, "%3s %d %d", month, &day, &year) != 3 ||
      sscanf(__TIME__, "%d:%d:%d", &hour, &minute, &second) != 3) return false;
  int m = -1;
  for (int i = 0; i < 12; ++i) {
    if (strcmp(month, months[i]) == 0) { m = i; break; }
  }
  if (m < 0) return false;
  build.tm_year = year - 1900;
  build.tm_mon = m;
  build.tm_mday = day;
  build.tm_hour = hour;
  build.tm_min = minute;
  build.tm_sec = second;
  build.tm_isdst = 0;
  setenv("TZ", "UTC0", 1);
  tzset();
  // Dipertahankan dari V4.2: waktu build PC diasumsikan WIB (UTC+7).
  time_t t = mktime(&build) - 7 * 3600;
  if (t <= 0) return false;
  struct timeval tv = {};
  tv.tv_sec = t;
  if (settimeofday(&tv, nullptr) != 0) return false;
  timeAvailable = true;
  ntpSynced = false;
  Serial.println("[TIME] WARNING: jam dari waktu kompilasi (BUKAN NTP).");
  return true;
}

bool syncTimeNTP() {
  if (WiFi.status() != WL_CONNECTED) return false;
  lastNtpAttempt = millis();
  Serial.println("[NTP] Menyinkronkan waktu...");
  configTime(0, 0, "pool.ntp.org", "time.google.com");
  unsigned long started = millis();
  while (millis() - started < 8000UL) {
    monitorPIR();
    if (sntp_get_sync_status() == SNTP_SYNC_STATUS_COMPLETED) {
      ntpSynced = true;
      timeAvailable = true;
      Serial.println("[NTP] Sinkronisasi berhasil. Timestamp valid.");
      return true;
    }
    delay(100);
  }
  Serial.println("[NTP] Belum berhasil; measured_at_utc tetap null.");
  return false;
}

void maintainTime() {
  if (WiFi.status() != WL_CONNECTED) return;
  if (sntp_get_sync_status() == SNTP_SYNC_STATUS_COMPLETED && !ntpSynced) {
    ntpSynced = true;
    timeAvailable = true;
    Serial.println("[NTP] Sinkronisasi asinkron berhasil.");
  }
  if (!ntpSynced && millis() - lastNtpAttempt >= NTP_RETRY_INTERVAL) {
    syncTimeNTP();
    if (mode == CAMPUS && !timeAvailable) initializeTimeFromBuild();
  }
}

void connectMQTT() {
  if (WiFi.status() != WL_CONNECTED || mode == NONE || mqttClient.connected()) return;
  if (mode == CAMPUS && !timeAvailable) return;
  String id = "ESP32-GD525-" + WiFi.macAddress();
  id.replace(":", "");
  const char* user = (mode == DEV) ? DEV_MQTT_USER : CAMPUS_USER;
  const char* password = (mode == DEV) ? DEV_MQTT_PASSWORD : MQTT_PASSWORD;
  Serial.print("[MQTT] Connecting ");
  Serial.println(mode == DEV ? "DEV" : "CAMPUS TLS");
  if (mqttClient.connect(id.c_str(), user, password)) {
    Serial.println("[MQTT] TERHUBUNG!");
  } else {
    Serial.print("[MQTT] Gagal, state: "); Serial.println(mqttClient.state());
    if (mode == CAMPUS) {
      char errBuf[128] = {};
      int err = tlsClient.lastError(errBuf, sizeof(errBuf));
      Serial.print("[TLS] "); Serial.print(err); Serial.print(" "); Serial.println(errBuf);
    }
  }
}

int readCO2() {
  const uint8_t command[9] = {0xFF, 0x01, 0x86, 0, 0, 0, 0, 0, 0x79};
  while (co2Serial.available()) co2Serial.read();
  co2Serial.write(command, 9);
  co2Serial.flush();
  uint8_t result[9] = {};
  int n = 0;
  unsigned long started = millis();
  while (n < 9 && millis() - started < CO2_TIMEOUT) {
    monitorPIR();
    if (co2Serial.available()) result[n++] = co2Serial.read();
    delay(1);
  }
  if (n != 9) { Serial.println("[CO2] Timeout"); return -1; }
  if (result[0] != 0xFF || result[1] != 0x86) {
    Serial.println("[CO2] Respons tidak valid"); return -1;
  }
  uint8_t checksum = 0;
  for (int i = 1; i < 8; ++i) checksum += result[i];
  checksum = 0xFF - checksum + 1;
  if (checksum != result[8]) { Serial.println("[CO2] Checksum salah"); return -1; }
  return result[2] * 256 + result[3];
}

void sampleAndPublish() {
  // Capture metadata SEBELUM baca sensor agar timestamp mencerminkan saat sampel.
  const uint32_t seq = ++sampleSeq;
  const uint32_t uptimeMs = millis();
  char measuredJson[32] = "null";
  if (ntpSynced) {
    time_t nowUtc = time(nullptr);
    struct tm utc = {};
    if (gmtime_r(&nowUtc, &utc) != nullptr && utc.tm_year + 1900 >= 2025) {
      char iso[24] = {};
      strftime(iso, sizeof(iso), "%Y-%m-%dT%H:%M:%SZ", &utc);
      snprintf(measuredJson, sizeof(measuredJson), "\"%s\"", iso);
    }
  }

  int pir = pirLatched ? 1 : 0;
  int co2 = readCO2();
  monitorPIR();
  float temperature = dht.readTemperature();
  float humidity = dht.readHumidity();
  monitorPIR();

  char co2Json[16] = "null";
  char tempJson[24] = "null";
  char humJson[24] = "null";
  bool co2OK = co2 >= 0;
  bool tempOK = isfinite(temperature);
  bool humOK = isfinite(humidity);
  if (co2OK) snprintf(co2Json, sizeof(co2Json), "%d", co2);
  if (tempOK) snprintf(tempJson, sizeof(tempJson), "%.2f", temperature);
  if (humOK) snprintf(humJson, sizeof(humJson), "%.2f", humidity);

  char faultsJson[64] = "[";
  bool first = true;
  if (!co2OK) { strcat(faultsJson, "\"co2\""); first = false; }
  if (!tempOK) { if (!first) strcat(faultsJson, ","); strcat(faultsJson, "\"temperature\""); first = false; }
  if (!humOK) { if (!first) strcat(faultsJson, ","); strcat(faultsJson, "\"humidity\""); }
  strcat(faultsJson, "]");

  char payload[512];
  int len = snprintf(
    payload, sizeof(payload),
    "{\"device_id\":\"%s\",\"boot_id\":\"%s\",\"seq\":%lu,"
    "\"uptime_ms\":%lu,\"measured_at_utc\":%s,\"co2_ppm\":%s,"
    "\"temp_in_c\":%s,\"hum_in_pct\":%s,\"pir\":%d,"
    "\"rssi\":%ld,\"faults\":%s}",
    DEVICE_ID, bootId, (unsigned long)seq, (unsigned long)uptimeMs,
    measuredJson, co2Json, tempJson, humJson, pir,
    (long)(WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0), faultsJson
  );

  Serial.println("\n===== GD525 SENSOR V4.3 =====");
  Serial.print("BOOT: "); Serial.println(bootId);
  Serial.print("SEQ: "); Serial.print(seq);
  Serial.print(" | uptime_ms: "); Serial.println(uptimeMs);
  Serial.print("CO2: "); Serial.println(co2Json);
  Serial.print("Temperature: "); Serial.println(tempJson);
  Serial.print("Humidity: "); Serial.println(humJson);
  Serial.print("PIR latch: "); Serial.println(pir);
  Serial.print("NTP synced: "); Serial.println(ntpSynced ? "YES" : "NO");

  if (len < 0 || len >= (int)sizeof(payload)) {
    Serial.println("[MQTT] Payload JSON melampaui buffer lokal");
    ++sendFailures;
    return;
  }
  Serial.print("[MQTT] Payload: "); Serial.println(payload);
  if (!mqttClient.connected()) {
    Serial.println("[MQTT] Belum terhubung; sampel tidak dikirim, seq tetap bertambah.");
    ++sendFailures;
    return;
  }
  if (mqttClient.publish(SENSOR_TOPIC, payload)) {
    ++sendCount;
    Serial.print("[MQTT] Publish berhasil #"); Serial.println(sendCount);
    pirLatched = false;
    if (digitalRead(PIR_PIN) == HIGH) pirLatched = true;
  } else {
    Serial.println("[MQTT] Publish gagal; seq tetap bertambah.");
    ++sendFailures;
  }
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  Serial.println("\nGD525 SENSOR V4.3 - MULTI WIFI/MQTT");
  pinMode(PIR_PIN, INPUT);
  dht.begin();
  co2Serial.begin(9600, SERIAL_8N1, MH_RX_PIN, MH_TX_PIN);
  generateBootId();
  Serial.print("[BOOT] ID: "); Serial.println(bootId);
  lastPIR = millis();

  connectWiFi();
  if (WiFi.status() == WL_CONNECTED) {
    if (!syncTimeNTP() && mode == CAMPUS) initializeTimeFromBuild();
  }
  connectMQTT();
  lastSend = millis();
  Serial.println("[SYSTEM] Monitoring dimulai");
}

void loop() {
  monitorPIR();
  unsigned long now = millis();

  if (WiFi.status() != WL_CONNECTED) {
    if (now - lastWifiRetry >= RETRY_INTERVAL) {
      lastWifiRetry = now;
      connectWiFi();
    }
  } else {
    Mode next = modeForSSID(WiFi.SSID());
    if (next != mode) configureBroker(next);
    maintainTime();
    if (mode == CAMPUS && !timeAvailable) {
      // Fallback hanya bagi TLS; tidak dianggap waktu pengukuran valid.
      initializeTimeFromBuild();
    }
    if (!mqttClient.connected()) {
      if (millis() - lastMqttRetry >= RETRY_INTERVAL) {
        lastMqttRetry = millis();
        connectMQTT();
      }
    } else {
      mqttClient.loop();
    }
  }

  // Usahakan pengukuran berkala, termasuk saat MQTT sedang offline.
  // Blocking Wi-Fi/NTP/TLS masih dapat menambah jitter.
  if (millis() - lastSend >= SEND_INTERVAL) {
    lastSend = millis();
    sampleAndPublish();
  }
  delay(10);
}
