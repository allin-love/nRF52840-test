import sys
import asyncio
import time
from collections import deque
import numpy as np
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                             QWidget, QPushButton, QLabel, QGroupBox, QFrame, QMessageBox)
from PyQt5.QtCore import QTimer
import pyqtgraph as pg
from bleak import BleakScanner, BleakClient
from qasync import QEventLoop

# ================= 配置 =================
DEVICE_NAME = "ESP32_EEG_8Ch" 
RX_UUID      = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
TX_UUID      = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
SCALE_FACTOR = (4.5 / 8388607 / 24.0) * 1000000 

# ================= 样式表 =================
STYLESHEET = """
QMainWindow { background-color: #1e1e1e; color: #fff; }
QGroupBox { border: 1px solid #444; border-radius: 6px; margin-top: 6px; padding-top: 10px; font-weight: bold; color: #bbb; }
QPushButton { background-color: #333; border: 1px solid #555; border-radius: 4px; padding: 10px; color: #fff; font-size: 13px; }
QPushButton:hover { background-color: #444; border-color: #00E676; }
QPushButton:pressed { background-color: #00E676; color: #000; }
QPushButton:disabled { background-color: #222; color: #555; border-color: #333; }
QLabel { color: #ddd; }
"""

class BLEWorker:
    def __init__(self, data_queue, status_cb, stats_cb):
        self.data_queue = data_queue
        self.status_cb = status_cb
        self.stats_cb = stats_cb
        self.client = None
        self.is_running = False
        self.rx_buffer = bytearray()
        self.last_seq = -1
        self.expected = 0
        self.received = 0
        self.start_t = 0

    async def run(self):
        self.status_cb("🔍 正在搜索...", "yellow")
        try:
            device = await BleakScanner.find_device_by_filter(
                lambda d, ad: d.name == DEVICE_NAME, timeout=10.0
            )
            if not device:
                self.status_cb("❌ 未找到设备", "red")
                return

            self.status_cb(f"⏳ 连接中...", "yellow")
            async with BleakClient(device) as client:
                self.client = client
                await client.start_notify(TX_UUID, self.notification_handler)
                
                self.status_cb("✅ 已连接 (待机)", "#00E676")
                self.is_running = True
                
                while self.is_running and client.is_connected:
                    await asyncio.sleep(0.1)

        except Exception as e:
            self.status_cb(f"⚠️ 错误: {e}", "red")
        finally:
            self.is_running = False
            self.client = None
            self.status_cb("⚪ 已断开", "gray")

    async def send_command(self, cmd_char):
        if self.client and self.client.is_connected:
            try:
                await self.client.write_gatt_char(RX_UUID, cmd_char.encode(), response=True)
                return True
            except Exception as e:
                print(f"Send Error: {e}")
        return False

    def notification_handler(self, sender, data):
        self.rx_buffer.extend(data)
        while len(self.rx_buffer) >= 52:
            if self.rx_buffer[0] != 0xA0:
                self.rx_buffer.pop(0)
                continue
            packet = self.rx_buffer[:52]
            del self.rx_buffer[:52]
            self.process_packet(packet)

    def process_packet(self, data):
        seq = data[1]
        if self.last_seq != -1:
            diff = (seq - self.last_seq) & 0xFF
            self.expected += diff
            self.received += 1
        else:
            self.last_seq = seq
        self.last_seq = seq

        if self.received % 50 == 0:
            loss = ((self.expected - self.received) / self.expected) * 100 if self.expected > 0 else 0
            if self.start_t == 0: self.start_t = time.time()
            elapsed = time.time() - self.start_t
            fps = (self.received * 2) / elapsed if elapsed > 0 else 0
            self.stats_cb(loss, fps)

        frames = []
        for offset in [2, 26]:
            frame = []
            for i in range(8):
                idx = offset + i * 3
                val = (data[idx] << 16) | (data[idx+1] << 8) | data[idx+2]
                if val & 0x800000: val -= 0x1000000
                frame.append(val * SCALE_FACTOR)
            frames.append(frame)
        self.data_queue.append(frames[0])
        self.data_queue.append(frames[1])

    def stop(self):
        self.is_running = False

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EEG Control Center (Option 3)")
        self.resize(1100, 750)
        self.setStyleSheet(STYLESHEET)
        
        self.data_queue = deque(maxlen=2500)
        self.plot_buffer = np.zeros((8, 1250))
        self.ble_worker = None
        
        self.setup_ui()
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(30)

    def setup_ui(self):
        w = QWidget()
        self.setCentralWidget(w)
        layout = QHBoxLayout(w)

        sidebar = QFrame()
        sidebar.setFixedWidth(240)
        sidebar.setStyleSheet("background-color: #252525; border-right: 1px solid #333;")
        sl = QVBoxLayout(sidebar)

        sl.addWidget(QLabel("<h2>📡 EEG LAB</h2>"))
        self.lbl_status = QLabel("⚪ 未连接")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet("font-size: 14px; margin-bottom: 10px;")
        sl.addWidget(self.lbl_status)
        
        self.lbl_stats = QLabel("Loss: -- | 0 Hz")
        self.lbl_stats.setStyleSheet("color: cyan; font-family: monospace;")
        sl.addWidget(self.lbl_stats)

        # 连接按钮
        self.btn_connect = QPushButton("连接设备")
        self.btn_connect.clicked.connect(self.toggle_connection)
        self.btn_connect.setStyleSheet("background-color: #00695C;")
        sl.addWidget(self.btn_connect)

        sl.addWidget(QLabel("")) # Spacer

        # 核心控制区
        gb = QGroupBox("模式控制")
        l_gb = QVBoxLayout()
        
        self.btn_start = QPushButton("🚀 开始采集 (Wake & Stream)")
        self.btn_start.clicked.connect(lambda: self.send_cmd('b'))
        
        self.btn_idle = QPushButton("⏸ 暂停待机 (Idle)")
        self.btn_idle.clicked.connect(lambda: self.send_cmd('s'))
        
        self.btn_sleep = QPushButton("🌙 低功耗睡眠 (Sleep)")
        self.btn_sleep.clicked.connect(lambda: self.send_cmd('d'))
        self.btn_sleep.setStyleSheet("background-color: #4A148C; color: #E0E0E0;")
        
        l_gb.addWidget(self.btn_start)
        l_gb.addWidget(self.btn_idle)
        l_gb.addWidget(self.btn_sleep)
        gb.setLayout(l_gb)
        sl.addWidget(gb)
        
        # 提示
        lbl_hint = QLabel("提示: 睡眠模式下保持连接，\n点击'开始'可瞬间唤醒。")
        lbl_hint.setStyleSheet("color: #777; font-size: 11px;")
        sl.addWidget(lbl_hint)

        sl.addStretch()
        layout.addWidget(sidebar)

        win = pg.GraphicsLayoutWidget()
        win.setBackground('#121212')
        self.curves = []
        for i in range(8):
            p = win.addPlot(row=i, col=0)
            p.hideAxis('bottom')
            p.setLabel('left', f'CH{i+1}')
            self.curves.append(p.plot(pen=pg.mkPen(color=pg.intColor(i, 9), width=1.5)))
        layout.addWidget(win)

        self.enable_controls(False)

    def toggle_connection(self):
        if self.ble_worker and self.ble_worker.is_running:
            self.ble_worker.stop()
            self.btn_connect.setText("连接设备")
            self.btn_connect.setStyleSheet("background-color: #00695C;")
            self.enable_controls(False)
        else:
            self.ble_worker = BLEWorker(self.data_queue, self.update_status, self.update_stats)
            asyncio.ensure_future(self.ble_worker.run())
            self.btn_connect.setText("断开连接")
            self.btn_connect.setStyleSheet("background-color: #B00020;")

    def send_cmd(self, char):
        if self.ble_worker:
            asyncio.ensure_future(self.ble_worker.send_command(char))
            if char == 'b':
                self.update_status("🔥 高速采集 (Streaming)", "#00E676")
                self.ble_worker.start_t = time.time()
                self.ble_worker.received = 0
            elif char == 's':
                self.update_status("⏸ 待机中 (Idle)", "orange")
            elif char == 'd':
                self.update_status("🌙 睡眠中 (Low Power)", "#BB86FC")

    def enable_controls(self, enable):
        self.btn_start.setEnabled(enable)
        self.btn_idle.setEnabled(enable)
        self.btn_sleep.setEnabled(enable)

    def update_status(self, text, color):
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 14px;")
        if "已连接" in text or "采集" in text or "睡眠" in text:
            self.enable_controls(True)

    def update_stats(self, loss, fps):
        self.lbl_stats.setText(f"丢包: {loss:.1f}%\n采样: {fps:.0f} Hz")

    def update_plot(self):
        data = []
        try:
            while True: data.append(self.data_queue.popleft())
        except IndexError: pass
        if not data: return
        arr = np.array(data)
        n = len(arr)
        self.plot_buffer = np.roll(self.plot_buffer, -n, axis=1)
        self.plot_buffer[:, -n:] = arr.T
        for i in range(8):
            self.curves[i].setData(self.plot_buffer[i])

if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop) 
    win = MainWindow()
    win.show()
    with loop: loop.run_forever()