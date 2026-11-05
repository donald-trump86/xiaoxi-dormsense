#pragma once

// Copy to ignored include/secrets.h, then replace EVERY placeholder locally.
// Firmware includes secrets.h directly; this example is never an auto-fallback.
constexpr char WIFI_SSID[] = "REPLACE_WITH_YOUR_WIFI_SSID";
constexpr char WIFI_PASSWORD[] = "REPLACE_WITH_YOUR_WIFI_PASSWORD";
constexpr char MQTT_HOST[] = "mqtt.example.invalid";
constexpr char MQTT_USERNAME[] = "REPLACE_WITH_NODE01_MQTT_USERNAME";
constexpr char MQTT_PASSWORD[] = "REPLACE_WITH_NODE01_MQTT_PASSWORD";
// Deliberately invalid until replaced with the trusted broker CA PEM.
constexpr char MQTT_CA[] = R"PEM(-----BEGIN CERTIFICATE-----
REPLACE_WITH_TRUSTED_BROKER_CA_PEM
-----END CERTIFICATE-----
)PEM";
