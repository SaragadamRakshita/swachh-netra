#include <WiFi.h>
#include <HTTPClient.h>
#include "DHTesp.h"

// WiFi Configuration
const char* ssid = "Wokwi-GUEST";
const char* password = "";

// FastAPI Backend Endpoint Configuration
// 10.0.2.2 is the special gateway IP in Wokwi to access the host's localhost (127.0.0.1)
const String backendUrl = "http://10.0.2.2:8000/api/facilities/VZ-001/readings";

// Pin Configuration
const int DHT_PIN = 15;
const int NH3_POT_PIN = 34;
const int VOC_POT_PIN = 35;
const int DOOR_BTN_PIN = 12;
const int WATER_SW_PIN = 14;

// DHT Sensor Object
DHTesp dht;

// States
int doorCount = 0;
bool lastButtonState = HIGH;

void setup() {
  Serial.begin(115200);
  Serial.println("--- SwachhNetra IoT ESP32 Node Initializing ---");

  // Initialize Sensors & Pins
  dht.setup(DHT_PIN, DHTesp::DHT22);
  pinMode(NH3_POT_PIN, INPUT);
  pinMode(VOC_POT_PIN, INPUT);
  pinMode(DOOR_BTN_PIN, INPUT_PULLUP);
  pinMode(WATER_SW_PIN, INPUT_PULLUP);

  // Connect to simulated Wokwi WiFi
  Serial.print("Connecting to WiFi: ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("");
  Serial.println("WiFi connected successfully!");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());
}

void loop() {
  // 1. Read Button State to detect door entries
  bool currentButtonState = digitalRead(DOOR_BTN_PIN);
  if (lastButtonState == HIGH && currentButtonState == LOW) {
    doorCount++;
    Serial.print("🚪 Door opened! Current count: ");
    Serial.println(doorCount);
    delay(200); // debounce
  }
  lastButtonState = currentButtonState;

  // 2. Periodic Sensor reporting (every 5 seconds)
  static unsigned long lastReportTime = 0;
  if (millis() - lastReportTime >= 5000) {
    lastReportTime = millis();

    // Read DHT22
    TempAndHumidity dhtData = dht.getTempAndHumidity();
    float temperature = dhtData.temperature;
    float humidity = dhtData.humidity;

    if (isnan(temperature) || isnan(humidity)) {
      temperature = 30.0; // fallback default
      humidity = 60.0;    // fallback default
    }

    // Read Potentiometers & Map to ppm levels
    int nh3Raw = analogRead(NH3_POT_PIN);
    int vocRaw = analogRead(VOC_POT_PIN);
    
    // Map ESP32 ADC (0-4095) to sensor ranges
    float nh3_ppm = (nh3Raw / 4095.0) * 150.0;  // 0 to 150 ppm (Critical > 50)
    float voc_ppm = (vocRaw / 4095.0) * 120.0;  // 0 to 120 ppm (Critical > 65)

    // Read Water Flow Slide Switch (LOW = normal 1.5, HIGH = zero water flow error)
    float water_flow = digitalRead(WATER_SW_PIN) == LOW ? 1.5 : 0.0;

    // Print values
    Serial.println("\n--- Sensor Readings ---");
    Serial.printf("NH3: %.1f ppm | VOC: %.1f ppm\n", nh3_ppm, voc_ppm);
    Serial.printf("Humidity: %.1f%% | Temperature: %.1fC\n", humidity, temperature);
    Serial.printf("Door entries: %d | Water flow: %.1f L/min\n", doorCount, water_flow);

    // Send HTTP POST Request to the backend API
    if (WiFi.status() == WL_CONNECTED) {
      WiFiClient client;
      HTTPClient http;
      http.begin(client, backendUrl);
      http.addHeader("Content-Type", "application/json");

      // Format JSON Payload
      String jsonPayload = "{";
      jsonPayload += "\"facility_id\":\"VZ-001\",";
      jsonPayload += "\"nh3_ppm\":" + String(nh3_ppm, 1) + ",";
      jsonPayload += "\"voc_ppm\":" + String(voc_ppm, 1) + ",";
      jsonPayload += "\"door_count\":" + String(doorCount) + ",";
      jsonPayload += "\"humidity\":" + String(humidity, 1) + ",";
      jsonPayload += "\"temperature\":" + String(temperature, 1) + ",";
      jsonPayload += "\"water_flow\":" + String(water_flow, 1);
      jsonPayload += "}";

      Serial.print("Sending POST request to FastAPI backend...");
      int httpResponseCode = http.POST(jsonPayload);

      if (httpResponseCode > 0) {
        String response = http.getString();
        Serial.print(" HTTP Response code: ");
        Serial.println(httpResponseCode);
        Serial.println("Response payload: " + response);
      } else {
        Serial.print(" Error sending POST request: ");
        Serial.println(httpResponseCode);
        Serial.println("Check if uvicorn server is running on the host machine at port 8000!");
      }
      http.end();
    } else {
      Serial.println("Error: WiFi Disconnected");
    }
  }
}
