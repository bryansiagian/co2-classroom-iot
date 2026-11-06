#pragma once
// Integration EXAMPLE, not a complete replacement for the existing ESP32 firmware.
// Include <WiFiMulti.h> and <WiFiClient.h> in the existing sketch.
// Configure secrets.h (NEVER commit credentials):
//   #define DEV_WIFI_SSID "GD525-DEV"
//   #define DEV_WIFI_PASSWORD "..."
//   #define DEV_MQTT_HOST "192.168.137.1" // CONFIRM via ipconfig on Windows
//   #define DEV_MQTT_USER "gd525_dev"
//   #define DEV_MQTT_PASSWORD "..."
// Existing campus MQTT TLS credentials/settings must be retained.

#include <WiFi.h>
#include <WiFiMulti.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include "secrets.h"

WiFiMulti gd525Wifi;
WiFiClient gd525DevNet;
WiFiClientSecure gd525CampusNet;
PubSubClient gd525Mqtt;
String gd525SelectedSsid;

void gd525ConnectWifi() {
  gd525Wifi.addAP("HW-Mahasiswa");
  gd525Wifi.addAP(DEV_WIFI_SSID, DEV_WIFI_PASSWORD);
  while (gd525Wifi.run() != WL_CONNECTED) delay(500);
  gd525SelectedSsid = WiFi.SSID();
  Serial.printf("WiFi: %s, IP: %s\n", gd525SelectedSsid.c_str(), WiFi.localIP().toString().c_str());
}

void gd525SelectBroker() {
  // Assumes existing campus const declarations CAMPUS_MQTT_HOST, CAMPUS_MQTT_PORT
  // and the TLS CA setup remain in the original V4.1 sketch.
  if (gd525SelectedSsid == DEV_WIFI_SSID) {
    gd525Mqtt.setClient(gd525DevNet);
    gd525Mqtt.setServer(DEV_MQTT_HOST, 1883);
  } else if (gd525SelectedSsid == "HW-Mahasiswa") {
    // Configure CA cert and valid time before connecting (do not use setInsecure()).
    gd525Mqtt.setClient(gd525CampusNet);
    gd525Mqtt.setServer(CAMPUS_MQTT_HOST, CAMPUS_MQTT_PORT);
  }
}

void gd525ConnectMqtt() {
  // Publish topic and sensor JSON remain unchanged: classroom/gd525/sensors.
  while (!gd525Mqtt.connected()) {
    bool dev = (gd525SelectedSsid == DEV_WIFI_SSID);
    bool ok = gd525Mqtt.connect(dev ? "gd525-esp32-dev" : "gd525-esp32-campus",
                                dev ? DEV_MQTT_USER : MQTT_USERNAME,
                                dev ? DEV_MQTT_PASSWORD : MQTT_PASSWORD);
    if (!ok) delay(2500);
  }
}

// IMPORTANT: copy/select/adapt functions inside existing firmware rather than
// including blindly if it already defines WiFiClientSecure/PubSubClient instances.
// Call gd525Wifi.run() periodically, and reselect broker after any SSID change.
// The local MQTT path is plaintext only on your controlled private hotspot.
