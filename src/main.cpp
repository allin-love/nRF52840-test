#include <Arduino.h>
#include <bluefruit.h>

// ================= 配置 =================
#define MY_DEVICE_NAME   "ESP32_EEG_8Ch"
#define PACKET_SIZE      52
#define TIMER_INTERVAL   8   // 8ms

// ================= 全局变量 =================
BLEUart bleuart;
SoftwareTimer eegTimer;
uint8_t packetSeq = 0;
uint32_t sampleCounter = 0;
bool isConnected = false;
bool isStreaming = false;

// 模拟信号
const int32_t SIG_HIGH = 4000000;
const int32_t SIG_LOW  = -4000000;

// ================= 辅助函数 =================
void pack24Bit(uint8_t* buf, int& idx, int32_t val, uint8_t& csum) {
    uint8_t b1 = (val >> 16) & 0xFF;
    uint8_t b2 = (val >> 8)  & 0xFF;
    uint8_t b3 = (val)       & 0xFF;
    buf[idx++] = b1; buf[idx++] = b2; buf[idx++] = b3;
    csum += (b1 + b2 + b3);
}

// ================= 核心：连接参数动态调整 =================
// 1. 高速模式：适合传数据 (7.5ms - 15ms)
void setConnFast() {
    if (isConnected) {
        // 参数单位是 1.25ms。 6=7.5ms
        Bluefruit.Connection(0)->requestConnectionParameter(6); 
    }
}

// 2. 待机模式：适合发指令 (100ms - 200ms)
void setConnIdle() {
    if (isConnected) {
        // 80 * 1.25 = 100ms
        Bluefruit.Connection(0)->requestConnectionParameter(80); 
    }
}

// 3. 睡眠模式：适合挂机省电 (1s - 2s)
// 注意：在这个模式下，发指令可能会有 1~2秒 的延迟，这是正常的
void setConnSleep() {
    if (isConnected) {
        // 800 * 1.25 = 1000ms (1秒心跳一次)
        // 增加 Slave Latency 可以进一步省电，但在 PC 上兼容性有时不好，先只改 Interval
        Bluefruit.Connection(0)->requestConnectionParameter(800); 
    }
}

// ================= 蓝牙回调 =================
void connect_callback(uint16_t conn_handle) {
    isConnected = true;
    Serial.println("Client Connected");
    // 刚连上时先用高速，方便握手
    setConnFast();
    Bluefruit.Connection(conn_handle)->requestMtuExchange(247);
}

void disconnect_callback(uint16_t conn_handle, uint8_t reason) {
    isConnected = false;
    isStreaming = false;
    Serial.println("Client Disconnected");
}

// 指令处理
void rx_callback(uint16_t conn_handle) {
    if (bleuart.available()) {
        char cmd = (char) bleuart.read();
        Serial.printf("RX CMD: %c\n", cmd);

        if (cmd == 'b') {       // Begin (Wake up & Start)
            isStreaming = true;
            Serial.println("Mode: STREAMING (Fast)");
            setConnFast(); // 切换回高速
        } 
        else if (cmd == 's') {  // Stop (Idle)
            isStreaming = false;
            Serial.println("Mode: IDLE (Medium)");
            setConnIdle(); // 切换到中速
        }
        else if (cmd == 'd') {  // Fake Deep Sleep
            isStreaming = false;
            Serial.println("Mode: FAKE SLEEP (Slow)");
            // 切换到超低速 (假睡眠)
            // 此时功耗会大幅降低，但连接不断
            setConnSleep(); 
        }
    }
}

// ================= 发送任务 =================
void send_eeg_data(TimerHandle_t xTimerID) {
    if (!isConnected || !isStreaming) return;

    uint8_t packet[PACKET_SIZE];
    uint8_t checksum = 0;
    int idx = 0;

    packet[idx++] = 0xA0;
    packet[idx++] = packetSeq++;

    for (int f = 0; f < 2; f++) {
        sampleCounter++;
        int32_t val = ((sampleCounter / 25) % 2 == 0) ? SIG_HIGH : SIG_LOW;
        for (int ch = 0; ch < 8; ch++) {
            pack24Bit(packet, idx, (ch < 4) ? val : -val, checksum);
        }
    }

    packet[50] = checksum;
    packet[51] = 0xC0;

    bleuart.write(packet, PACKET_SIZE);
}

// ================= Setup =================
void setup() {
    Serial.begin(115200);
    // while(!Serial) delay(10); // 测功耗时注释掉

    Serial.println("\n=== nRF52840 Option 3: Fake Sleep Firmware ===");

    Bluefruit.configPrphBandwidth(BANDWIDTH_MAX);
    Bluefruit.begin();
    Bluefruit.setTxPower(4); 
    Bluefruit.setName(MY_DEVICE_NAME);
    Bluefruit.Periph.setConnectCallback(connect_callback);
    Bluefruit.Periph.setDisconnectCallback(disconnect_callback);

    bleuart.begin();
    bleuart.setRxCallback(rx_callback);

    Bluefruit.Advertising.addFlags(BLE_GAP_ADV_FLAGS_LE_ONLY_GENERAL_DISC_MODE);
    Bluefruit.Advertising.addTxPower();
    Bluefruit.Advertising.addName();
    Bluefruit.ScanResponse.addService(bleuart);
    Bluefruit.Advertising.restartOnDisconnect(true);
    Bluefruit.Advertising.setInterval(32, 244); 
    Bluefruit.Advertising.start(0);

    eegTimer.begin(TIMER_INTERVAL, send_eeg_data);
    eegTimer.start();
}

void loop() {
    // FreeRTOS handles sleep
}