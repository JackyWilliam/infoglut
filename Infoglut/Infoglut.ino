#include <ArduinoBLE.h>
#include <WiFiS3.h>

// 服务器端口80
WiFiServer server(80);

// 定义蓝牙服务和特征
BLEService textService("19B10000-E8F2-537E-4F6C-D104768A1214");
BLEStringCharacteristic textChar("19B10001-E8F2-537E-4F6C-D104768A1214", BLEWrite | BLERead, 100);

// --- 硬件引脚配置 ---
const int pumpPin = 4;              // 气泵继电器信号线接 D4
const int valvePin = 5;             // 电磁阀信号线接 D5
const int ledPin = LED_BUILTIN;     // 板载指示灯

void setup() {
  Serial.begin(9600);
  pinMode(pumpPin, OUTPUT);
  pinMode(valvePin, OUTPUT);
  pinMode(ledPin, OUTPUT);

  digitalWrite(pumpPin, LOW);
  digitalWrite(valvePin, LOW);
  digitalWrite(ledPin, LOW);

  delay(2000);
  Serial.println("--- 交互装置系统启动中 ---");

  if (!BLE.begin()) {
    Serial.println("BLE Error");
    while (1) {
      digitalWrite(ledPin, HIGH); delay(100);
      digitalWrite(ledPin, LOW); delay(100);
    }
  }

  BLE.setLocalName("Arduino-Pump");
  BLE.setDeviceName("Arduino-Pump");

  BLE.setAdvertisedService(textService);
  textService.addCharacteristic(textChar);
  BLE.addService(textService);

  BLE.advertise();
  Serial.println(">>> Ready, waiting for connect...");

  digitalWrite(ledPin, HIGH);
}

// 根据文字长度计算气泵持续时间
int getPumpDuration(String text) {
  int len = text.length();

  if (len <= 5) return 500;
  if (len <= 15) return 1000;
  if (len <= 30) return 1800;
  return 2500;
}

// 气泵吹气（正常内容触发）
void triggerPump(int durationMs) {
  Serial.print("Airpump starting for ");
  Serial.print(durationMs);
  Serial.println(" ms");

  digitalWrite(pumpPin, HIGH);
  delay(durationMs);
  digitalWrite(pumpPin, LOW);

  Serial.println("Airpump closed");
}

// 电磁阀放气（脏话/伤害性内容触发）
void triggerValve(int durationMs) {
  Serial.print("Valve opening for ");
  Serial.print(durationMs);
  Serial.println(" ms");

  digitalWrite(valvePin, HIGH);
  delay(durationMs);
  digitalWrite(valvePin, LOW);

  Serial.println("Valve closed");
}

// 处理来自串口的命令
void handleSerialCommand(String command) {
  command.trim();

  if (command.startsWith("PUMP:")) {
    String value = command.substring(5);
    int duration = value.toInt();

    if (duration > 0) {
      Serial.print("Received PUMP command, duration = ");
      Serial.println(duration);
      triggerPump(duration);
    } else {
      Serial.println("Invalid PUMP duration");
    }

  } else if (command.startsWith("VALVE:")) {
    String value = command.substring(6);
    int duration = value.toInt();

    if (duration > 0) {
      Serial.print("Received VALVE command, duration = ");
      Serial.println(duration);
      triggerValve(duration);
    } else {
      Serial.println("Invalid VALVE duration");
    }
  }
}

void loop() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    handleSerialCommand(command);
  }

  BLEDevice central = BLE.central();

  if (central) {
    Serial.print("📱 App connected, phone MAC address: ");
    Serial.println(central.address());
    digitalWrite(ledPin, LOW);

    while (central.connected()) {
      BLE.poll();

      if (Serial.available() > 0) {
        String command = Serial.readStringUntil('\n');
        handleSerialCommand(command);
      }

      if (textChar.written()) {
        String receivedText = textChar.value();

        Serial.print("CONTENT_FROM_PHONE:");
        Serial.println(receivedText);

        int duration = getPumpDuration(receivedText);
        triggerPump(duration);

        /*
          未来如果你想让 BLE 端也支持"伤害词吸气"，
          可以在这里加检测逻辑，再调用 triggerSuck(duration)
          目前先不启用
        */
      }
    }

    Serial.println("⚠️ Phone app disconnected");
    digitalWrite(ledPin, HIGH);
  }
}