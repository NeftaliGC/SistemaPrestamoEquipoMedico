/*
 * Firmware — Lector RFID RC522 para sistema de préstamo de equipo médico.
 * Proyecto PlatformIO con soporte para tres variantes de placa:
 *
 *   ESP32 Super Mini clásico (WROOM-32E)  → entorno: esp32-supermini
 *   ESP32-C3 SuperMini                    → entorno: esp32c3-supermini
 *   ESP32-S3 SuperMini                    → entorno: esp32s3-supermini  (SU PLACA)
 *
 * Conexiones al MFRC522:
 *
 *   MFRC522  │  Super Mini clásico  │  ESP32-C3 SuperMini  │  ESP32-S3 SuperMini
 *   ─────────┼──────────────────────┼──────────────────────┼────────────────────
 *   VCC      │  3V3                 │  3V3                 │  3V3
 *   GND      │  GND                 │  GND                 │  GND
 *   SCK      │  GPIO18              │  GPIO4               │  GPIO12
 *   MISO     │  GPIO19              │  GPIO5               │  GPIO13
 *   MOSI     │  GPIO23              │  GPIO6               │  GPIO11
 *   SDA (SS) │  GPIO5               │  GPIO7               │  GPIO10
 *   RST      │  GPIO4               │  GPIO10              │  GPIO9
 *
 * (En el C3 los GPIO18/19 están reservados para el USB nativo; en el S3
 *  los GPIO19/20. En el S3 se evitan también 0/3/45/46 —de arranque— y
 *  33-37 —PSRAM octal en las versiones N8R8/N16R8—.)
 *
 * Comunicación: USB serial a 115200 baud. Por cada tag leído envía:
 *   RFID:<UID>     p. ej.  RFID:A1B2C3D4
 * El dashboard Python (app.py) escucha ese formato.
 */
#include <Arduino.h>
#include <SPI.h>
#include <MFRC522.h>

#if defined(CONFIG_IDF_TARGET_ESP32S3)
// ESP32-S3 SuperMini: evitar GPIO19/20 (USB nativo), 0/3/45/46 (boot)
// y 33-37 (PSRAM octal en las variantes N8R8/N16R8)
constexpr uint8_t PIN_SCK = 12;
constexpr uint8_t PIN_MISO = 13;
constexpr uint8_t PIN_MOSI = 11;
constexpr uint8_t PIN_SS = 10;
constexpr uint8_t PIN_RST = 9;
constexpr const char* PLACA = "ESP32-S3 SuperMini";
#elif defined(CONFIG_IDF_TARGET_ESP32C3)
// ESP32-C3 SuperMini: evitar GPIO18/19 (USB nativo) y GPIO8/9 (boot)
constexpr uint8_t PIN_SCK = 4;
constexpr uint8_t PIN_MISO = 5;
constexpr uint8_t PIN_MOSI = 6;
constexpr uint8_t PIN_SS = 7;
constexpr uint8_t PIN_RST = 10;
constexpr const char* PLACA = "ESP32-C3 SuperMini";
#else
// ESP32 Super Mini clásico (WROOM-32E)
constexpr uint8_t PIN_SCK = 18;
constexpr uint8_t PIN_MISO = 19;
constexpr uint8_t PIN_MOSI = 23;
constexpr uint8_t PIN_SS = 5;
constexpr uint8_t PIN_RST = 4;
constexpr const char* PLACA = "ESP32 Super Mini";
#endif

MFRC522 mfrc522(PIN_SS, PIN_RST);

// Reenviar el mismo tag solo después de 2 s (evita lecturas duplicadas)
constexpr unsigned long INTERVALO_REPETICION_MS = 2000;

String ultimoUid;
unsigned long ultimaLecturaMs = 0;

void setup() {
  Serial.begin(115200);
  delay(200);
  SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, PIN_SS);
  mfrc522.PCD_Init();
  Serial.print("Listo para leer RFID (");
  Serial.print(PLACA);
  Serial.println(")");
}

void loop() {
  if (!mfrc522.PICC_IsNewCardPresent()) return;
  if (!mfrc522.PICC_ReadCardSerial()) return;

  String uid;
  uid.reserve(mfrc522.uid.size * 2);
  for (byte i = 0; i < mfrc522.uid.size; i++) {
    if (mfrc522.uid.uidByte[i] < 0x10) uid += '0';
    uid += String(mfrc522.uid.uidByte[i], HEX);
  }
  uid.toUpperCase();

  const unsigned long ahora = millis();
  if (uid != ultimoUid || ahora - ultimaLecturaMs >= INTERVALO_REPETICION_MS) {
    Serial.println("RFID:" + uid);
    ultimoUid = uid;
    ultimaLecturaMs = ahora;
  }

  mfrc522.PICC_HaltA();
  mfrc522.PCD_StopCrypto1();
}
