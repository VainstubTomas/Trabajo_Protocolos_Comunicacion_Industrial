#include <SoftwareSerial.h>

// --- Configuración de Pines ---
// Modbus (RS485)
#define RX_PIN 10
#define TX_PIN 11
#define DE_PIN 3
#define RE_PIN 2

// Sensores
#define PIN_POT A0
#define PIN_TRIG 5
#define PIN_ECHO 6
#define PIN_BTN1 8
#define PIN_BTN2 7

// Actuador (LED ÚNICO)
#define PIN_LED 9 // Pin PWM para controlar brillo

SoftwareSerial modbusSerial(RX_PIN, TX_PIN);

// Memoria Modbus
uint16_t holdingRegs[10]; // 0-3: Sensores, 4: Valor LED (0-255)
const byte SLAVE_ID = 1;
int ledBrillo = 0;

// Buffer Trama
byte buffer[32];
int len = 0;

uint16_t crc16(byte *buffer, int length) {
  uint16_t crc = 0xFFFF;
  for (int i = 0; i < length; i++) {
    crc ^= buffer[i];
    for (int j = 0; j < 8; j++) {
      if (crc & 1) crc = (crc >> 1) ^ 0xA001;
      else crc >>= 1;
    }
  }
  return crc;
}

void setup() {
  Serial.begin(9600); // Debug USB
  modbusSerial.begin(9600); // Modbus

  pinMode(DE_PIN, OUTPUT);
  pinMode(RE_PIN, OUTPUT);
  digitalWrite(DE_PIN, LOW); // Modo Escucha
  digitalWrite(RE_PIN, LOW);

  pinMode(PIN_LED, OUTPUT);
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  pinMode(PIN_BTN1, INPUT_PULLUP);
  pinMode(PIN_BTN2, INPUT_PULLUP);

  Serial.println("--- Esclavo Listo (1 LED en D9) ---");
}

void enviarRespuesta(byte* datos, int longitud) {
  digitalWrite(DE_PIN, HIGH); // Modo Transmisión
  digitalWrite(RE_PIN, HIGH);
  delay(2);
  modbusSerial.write(datos, longitud);
  modbusSerial.flush();
  digitalWrite(DE_PIN, LOW); // Volver a Escucha
  digitalWrite(RE_PIN, LOW);
}

void loop() {
  // 1. Leer Sensores
  holdingRegs[0] = analogRead(PIN_POT);
  
  // Ultrasonido simple
  digitalWrite(PIN_TRIG, LOW); delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH); delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  holdingRegs[1] = pulseIn(PIN_ECHO, HIGH, 30000) * 0.034 / 2; 
  
  holdingRegs[2] = !digitalRead(PIN_BTN1);
  holdingRegs[3] = !digitalRead(PIN_BTN2);

  // 2. Actualizar LED Físico
  analogWrite(PIN_LED, ledBrillo);

  // 3. Escuchar Modbus
  if (modbusSerial.available()) {
    byte b = modbusSerial.read();
    
    // Reset simple por timeout (si pasa mucho tiempo entre bytes)
    static unsigned long lastByteTime = 0;
    if (millis() - lastByteTime > 50) len = 0;
    lastByteTime = millis();

    if (len < 32) buffer[len++] = b;

    // Procesar si tenemos trama mínima (8 bytes)
    if (len >= 8 && buffer[0] == SLAVE_ID) {
      uint16_t crcRecibido = buffer[len-2] | (buffer[len-1] << 8);
      if (crc16(buffer, len-2) == crcRecibido) {
        procesarTrama();
        len = 0; // Reset buffer tras procesar
      }
    }
  }
}

void procesarTrama() {
  byte funcion = buffer[1];
  uint16_t addr = (buffer[2] << 8) | buffer[3];
  uint16_t val = (buffer[4] << 8) | buffer[5];

  // --- 0x03: Leer Sensores ---
  if (funcion == 0x03) {
    byte respuesta[32];
    respuesta[0] = SLAVE_ID;
    respuesta[1] = 0x03;
    respuesta[2] = val * 2; // Bytes count
    int idx = 3;
    for (int i=0; i<val; i++) {
      respuesta[idx++] = highByte(holdingRegs[addr+i]);
      respuesta[idx++] = lowByte(holdingRegs[addr+i]);
    }
    uint16_t crc = crc16(respuesta, idx);
    respuesta[idx++] = lowByte(crc);
    respuesta[idx++] = highByte(crc);
    enviarRespuesta(respuesta, idx);
  }
  
  // --- 0x05: Escribir Digital (ON/OFF) ---
  else if (funcion == 0x05) {
    if (addr == 0) { // Bobina 0
       if (val == 0xFF00) { // ON
         ledBrillo = 255;
         Serial.println("CMD: LED ON (Max)");
       } else { // OFF
         ledBrillo = 0;
         Serial.println("CMD: LED OFF");
       }
       // Echo de respuesta (misma trama recibida)
       enviarRespuesta(buffer, 8);
    }
  }

  // --- 0x06: Escribir Analógico (0-255) ---
  else if (funcion == 0x06) {
    if (addr == 4) { // Registro 4
       if (val > 255) val = 255;
       ledBrillo = val;
       Serial.print("CMD: LED Brillo "); Serial.println(val);
       // Echo de respuesta
       enviarRespuesta(buffer, 8);
    }
  }
}