# nRF52840 EEG Simulator & Power Profiler

A low-power Bluetooth LE (BLE) EEG simulation system based on the nRF52840 SoC. This project is designed to test BLE throughput, packet loss, and power consumption in various operating modes (Streaming, Idle, Sleep).

It includes a **Firmware** for the nRF52840 (Arduino/PlatformIO) and a **Python GUI** (PyQt5) for visualization and control.

## 🚀 Features

- **8-Channel Simulation**: Generates high-amplitude square waves to simulate EEG data (250Hz sampling rate).
- **Stream Buffering**: Implements a robust stream buffer mechanism to handle BLE packet fragmentation (MTU splitting) with 0% packet loss.
- **Power Profiling Modes**:
  - **Streaming (Active)**: High-speed connection (7.5ms interval) for data transmission.
  - **Idle**: Medium-speed connection for standby.
  - **Deep Sleep (Fake/Connection Maintained)**: Low-power mode with long connection intervals (2s) to maintain link while minimizing current.
- **Hardware Control**: Remote toggle for UART/Serial to eliminate debug power consumption.

## 🛠 Hardware Requirements

- **Microcontroller**: nRF52840 SuperMini (or Feather nRF52840, XIAO nRF52840).
- **Debugger (Optional)**: USB-TTL Adapter (e.g., CH340, CP2102) connected to Hardware UART pins for low-power debugging.
- **Power**: 3.3V LiPo Battery or Power Profiler Kit (Do not use USB power for current measurements).

## 💻 Software & Installation

### 1. Firmware (nRF52840)
The firmware is built using **PlatformIO**.

1. Open the `firmware` folder in VSCode + PlatformIO.
2. Ensure the `Adafruit nRF52` library is installed.
3. Build and Upload to your board.

*Note: The firmware uses Hardware UART (`Serial1`) by default to allow USB subsystem shutdown for power saving.*

### 2. GUI (Python)
The host application requires Python 3.8+.

1. Install dependencies:
   ```bash
   pip install PyQt5 pyqtgraph bleak qasync numpy