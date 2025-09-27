# -*- coding: utf-8 -*-
"""
UI 3.5" Waveshare cho hệ thống theo dõi sức khỏe
- Màn hình: Dashboard / Đo huyết áp (stub bơm/xả) / Lịch sử / Cài đặt
- Cảm biến: MAX30102 (HR/SpO2), MLX90614 (nhiệt độ)
- Cảnh báo & hướng dẫn: đọc qua loa bằng TTS (espeak, không dùng buzzer)
- Lưu trữ: SQLite (data/vitals.db)
- MQTT (tùy chọn): publish vitals/alerts (paho-mqtt)
- Fullscreen, ẩn taskbar (borderless), có phím tắt thoát an toàn
"""

from kivy.config import Config
# Fullscreen, không viền (che taskbar)
Config.set("graphics", "borderless", "1")
Config.set("graphics", "fullscreen", "auto")
Config.set("graphics", "width", "480")    # Waveshare 3.5": 480x320
Config.set("graphics", "height", "320")
Config.set("kivy", "log_level", "info")
Config.write()

import os, time, json, queue, threading, sqlite3, subprocess, datetime
from dataclasses import dataclass
from typing import Optional, Dict

import numpy as np
from smbus2 import SMBus

# MQTT tùy chọn
try:
    import paho.mqtt.client as mqtt
except Exception:
    mqtt = None

# --- Kivy ---
from kivy.app import App
from kivy.uix.screenmanager import Screen, ScreenManager, NoTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.properties import StringProperty, NumericProperty, ListProperty
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

# ------------------------
# CẤU HÌNH / NGƯỠNG
# ------------------------
DEFAULT_THRESHOLDS = {
    "hr_min": 50, "hr_max": 110,
    "spo2_min": 94,
    "temp_min": 35.5, "temp_max": 38.0,
}

MQTT_CFG = {
    "enabled": False,                # bật True nếu đã có broker
    "host": "127.0.0.1",
    "port": 1883,
    "base_topic": "health/demo1",
    "username": None,
    "password": None,
    "tls": False,
}

# DB lưu tại ../data/vitals.db (nếu bạn đặt file ở tests/, đường dẫn vẫn hợp lý)
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "vitals.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# ------------------------
# TIỆN ÍCH
# ------------------------
def speak(text: str):
    """Đọc lời nhắc/cảnh báo/kết quả qua loa bằng espeak (offline)."""
    try:
        subprocess.Popen(["espeak", "-v", "vi+m1", text])
    except Exception:
        pass

def now_ts() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")

# ------------------------
# DB
# ------------------------
def db_init():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS vitals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            hr REAL, spo2 REAL, temp REAL,
            alert TEXT DEFAULT NULL
        )
    """)
    con.commit()
    con.close()

def db_insert(ts: str, hr: Optional[float], spo2: Optional[float], temp: Optional[float], alert: Optional[str]):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("INSERT INTO vitals(ts, hr, spo2, temp, alert) VALUES (?,?,?,?,?)",
                (ts, hr, spo2, temp, alert))
    con.commit()
    con.close()

def db_recent(limit=100):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT ts, hr, spo2, temp, COALESCE(alert,'') FROM vitals ORDER BY id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    con.close()
    return rows

# ------------------------
# CẢM BIẾN
# ------------------------
class GY906:
    """MLX90614 – đo nhiệt độ đối tượng (°C). I2C addr mặc định 0x5A."""
    def __init__(self, bus_id=1, addr=0x5A):
        self.bus_id = bus_id
        self.addr = addr
        self.reg = 0x07

    def read(self) -> float:
        with SMBus(self.bus_id) as bus:
            raw = bus.read_word_data(self.addr, self.reg)
            # MLX90614 little-endian -> swap bytes
            raw = ((raw << 8) & 0xFF00) | (raw >> 8)
            temp = (raw * 0.02) - 273.15
            return float(temp)

class MAX30102Reader(threading.Thread):
    """Luồng đọc MAX30102 -> tính HR/SpO2 (đơn giản hóa để chạy demo)."""
    def __init__(self, out_queue: queue.Queue, stop_event: threading.Event, sample_period=1.0):
        super().__init__(daemon=True)
        self.out_q = out_queue
        self.stop_event = stop_event
        self.sample_period = sample_period
        # Sử dụng tích hợp MAX30102 libraries
        try:
            from src.sensors.max30102_sensor import MAX30102Hardware, HRCalculator
            self.has_real = True
            self.m = MAX30102Hardware()
            self.hrcalc = HRCalculator
        except Exception:
            self.has_real = False

    def run(self):
        while not self.stop_event.is_set():
            ts = now_ts()
            try:
                if self.has_real:
                    BUFFER = 100
                    red, ir = self.m.read_sequential(BUFFER)
                    arr_ir = np.array(ir)
                    arr_red = np.array(red)
                    # Sử dụng tích hợp HRCalculator
                    hr, hr_valid, spo2, spo2_valid = self.hrcalc.calc_hr_and_spo2(arr_ir, arr_red)
                    hr_val = float(hr) if hr_valid else None
                    spo2_val = float(spo2) if spo2_valid else None
                else:
                    # FAKE: dao động quanh 78 bpm & 97% SpO2
                    hr_val = 75 + np.random.randint(-5, 6)
                    spo2_val = 97 + np.random.randint(-1, 2)
                self.out_q.put(("max30102", ts, hr_val, spo2_val))
            except Exception as e:
                self.out_q.put(("max30102_err", ts, str(e)))
            time.sleep(self.sample_period)

# ------------------------
# MQTT
# ------------------------
class MQTTClient:
    def __init__(self, cfg: Dict):
        self.cfg = cfg
        self.client = None
        self.connected = False
        if cfg.get("enabled") and mqtt is not None:
            self.client = mqtt.Client(client_id=f"rpi-edge-{int(time.time())}", clean_session=True)
            if cfg.get("username"):
                self.client.username_pw_set(cfg["username"], cfg.get("password"))
            if cfg.get("tls"):
                self.client.tls_set()
            self.client.on_connect = self.on_connect
            self.client.on_disconnect = self.on_disconnect

    def on_connect(self, client, userdata, flags, rc, properties=None):
        self.connected = (rc == 0)

    def on_disconnect(self, client, userdata, rc, properties=None):
        self.connected = False

    def start(self):
        if self.client:
            try:
                self.client.connect(self.cfg["host"], self.cfg["port"], keepalive=30)
                self.client.loop_start()
            except Exception:
                pass

    def stop(self):
        if self.client:
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except Exception:
                pass

    def pub(self, topic_suffix: str, payload: dict, retain=False):
        if self.client and self.connected:
            topic = f'{self.cfg["base_topic"]}/{topic_suffix}'
            try:
                self.client.publish(topic, json.dumps(payload), qos=0, retain=retain)
            except Exception:
                pass

# ------------------------
# MÀN HÌNH
# ------------------------
class TopBar(BoxLayout):
    title = StringProperty("Smart Health Edge")
    status = StringProperty("")
    def __init__(self, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, height=40, padding=5, spacing=5, **kwargs)
        self.add_widget(Label(text=self.title, font_size="18sp", bold=True, size_hint_x=0.6))
        self.lbl_status = Label(text="", font_size="14sp", halign="right", valign="middle")
        self.add_widget(self.lbl_status)
        btn_exit = Button(text="⏻", size_hint_x=0.15, on_release=self._on_exit, font_size="18sp")
        self.add_widget(btn_exit)
        # nhấn giữ 1.5s để thoát an toàn
        btn_exit.bind(on_touch_down=self._touch_down, on_touch_up=self._touch_up)
        self._press_time = None

    def _on_exit(self, *_):
        pass  # dùng nhấn giữ

    def _touch_down(self, instance, touch):
        if touch.grab_current is None and instance.collide_point(*touch.pos):
            self._press_time = time.time()

    def _touch_up(self, instance, touch):
        if self._press_time and (time.time() - self._press_time) >= 1.5:
            App.get_running_app().safe_exit()
        self._press_time = None

    def set_status(self, text):
        self.lbl_status.text = text

class DashboardScreen(Screen):
    hr = StringProperty("--")
    spo2 = StringProperty("--")
    temp = StringProperty("--")
    alert_text = StringProperty("")
    color_hr = ListProperty([1,1,1,1])
    color_spo2 = ListProperty([1,1,1,1])
    color_temp = ListProperty([1,1,1,1])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=6, spacing=6)
        self.title_bar = TopBar()
        root.add_widget(self.title_bar)

        grid = GridLayout(cols=3, spacing=6, size_hint_y=0.72)
        self.lbl_hr = Label(text="HR\n-- bpm", font_size="26sp")
        self.lbl_spo2 = Label(text="SpO₂\n-- %", font_size="26sp")
        self.lbl_temp = Label(text="Temp\n-- °C", font_size="26sp")

        grid.add_widget(self._card(self.lbl_hr))
        grid.add_widget(self._card(self.lbl_spo2))
        grid.add_widget(self._card(self.lbl_temp))
        root.add_widget(grid)

        # điều hướng
        nav = GridLayout(cols=4, size_hint_y=None, height=60, spacing=6)
        nav.add_widget(Button(text="Dashboard", bold=True, disabled=True))
        nav.add_widget(Button(text="Đo Huyết áp", on_release=lambda *_: setattr(self.manager, "current", "bp")))
        nav.add_widget(Button(text="Lịch sử", on_release=lambda *_: setattr(self.manager, "current", "history")))
        nav.add_widget(Button(text="Cài đặt", on_release=lambda *_: setattr(self.manager, "current", "settings")))
        root.add_widget(nav)

        self.add_widget(root)

    def _card(self, widget):
        box = AnchorLayout()
        box.add_widget(widget)
        return box

    def update_vitals(self, hr: Optional[float], spo2: Optional[float], temp: Optional[float], thr: dict):
        if hr is not None:
            self.hr = f"{int(hr)}"
            self.lbl_hr.text = f"HR\n{self.hr} bpm"
            self.color_hr = [1,0.3,0.3,1] if (hr < thr["hr_min"] or hr > thr["hr_max"]) else [0.5,1,0.5,1]
            self.lbl_hr.color = self.color_hr
        if spo2 is not None:
            self.spo2 = f"{int(spo2)}"
            self.lbl_spo2.text = f"SpO₂\n{self.spo2} %"
            self.color_spo2 = [1,0.3,0.3,1] if (spo2 < thr["spo2_min"]) else [0.5,1,0.5,1]
            self.lbl_spo2.color = self.color_spo2
        if temp is not None:
            self.temp = f"{temp:.1f}"
            self.lbl_temp.text = f"Temp\n{self.temp} °C"
            self.color_temp = [1,0.3,0.3,1] if (temp < thr["temp_min"] or temp > thr["temp_max"]) else [0.5,1,0.5,1]
            self.lbl_temp.color = self.color_temp

    def show_alert(self, text: str):
        self.alert_text = text
        Popup(title="⚠️ Cảnh báo", content=Label(text=text, font_size="20sp"),
              size_hint=(0.9, 0.6)).open()

class BPMeasurementScreen(Screen):
    """Khung đo Huyết áp kiểu dao động học – mô phỏng tiến trình UI."""
    status = StringProperty("Sẵn sàng đo")
    pressure = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=6, spacing=6)
        self.title_bar = TopBar()
        root.add_widget(self.title_bar)

        info = Label(text="Đo Huyết áp (mô phỏng)—\nNhấn Bắt đầu để bơm → xả", font_size="18sp")
        root.add_widget(info)

        btns = GridLayout(cols=3, size_hint_y=None, height=60, spacing=6)
        btns.add_widget(Button(text="Bắt đầu", on_release=self.start_bp))
        btns.add_widget(Button(text="Dừng", on_release=self.stop_bp))
        btns.add_widget(Button(text="Về Dashboard", on_release=lambda *_: setattr(self.manager, "current", "dash")))
        root.add_widget(btns)

        self.lbl = Label(text="Áp suất: 0 mmHg\nTrạng thái: " + self.status, font_size="20sp")
        root.add_widget(self.lbl)

        self.add_widget(root)
        self._bp_running = False
        self._bp_ev = None

    def start_bp(self, *_):
        if self._bp_running: return
        self._bp_running = True
        self.status = "Bơm…"
        self.pressure = 0
        speak("Bắt đầu đo huyết áp. Vui lòng giữ yên tay.")
        self._bp_ev = Clock.schedule_interval(self._bp_step, 0.05)

    def stop_bp(self, *_):
        self._bp_running = False
        if self._bp_ev:
            self._bp_ev.cancel()
        self.status = "Dừng"
        self._refresh()

    def _refresh(self):
        self.lbl.text = f"Áp suất: {int(self.pressure)} mmHg\nTrạng thái: {self.status}"

    def _bp_step(self, dt):
        if not self._bp_running:
            return
        if self.status == "Bơm…":
            self.pressure += 4
            if self.pressure >= 170:
                self.status = "Xả…"
                speak("Đang xả. Vui lòng giữ yên.")
        elif self.status == "Xả…":
            self.pressure -= 2
            if self.pressure <= 40:
                self.status = "Hoàn tất"
                self._bp_running = False
                if self._bp_ev: self._bp_ev.cancel()
                # Kết quả ước lượng (placeholder)
                Popup(title="Kết quả BP (demo)",
                      content=Label(text="SYS ≈ 122\nDIA ≈ 79\nMAP ≈ 93", font_size="20sp"),
                      size_hint=(0.7,0.6)).open()
                speak("Kết quả. Huyết áp một trăm hai mươi hai trên bảy mươi chín mi li mét thủy ngân.")
        self._refresh()

class HistoryScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=6, spacing=6)
        self.title_bar = TopBar()
        root.add_widget(self.title_bar)

        self.scroll = ScrollView()
        self.lbl = Label(text="", font_size="16sp", size_hint_y=None)
        self.lbl.bind(texture_size=lambda *_: setattr(self.lbl, "height", self.lbl.texture_size[1]))
        self.scroll.add_widget(self.lbl)
        root.add_widget(self.scroll)

        nav = GridLayout(cols=2, size_hint_y=None, height=60, spacing=6)
        nav.add_widget(Button(text="Làm mới", on_release=lambda *_: self.refresh()))
        nav.add_widget(Button(text="Về Dashboard", on_release=lambda *_: setattr(self.manager, "current", "dash")))
        root.add_widget(nav)

        self.add_widget(root)

    def on_pre_enter(self, *args):
        self.refresh()

    def refresh(self):
        rows = db_recent(200)
        lines = ["Thời gian                 HR   SpO₂   Temp    Alert"]
        for ts, hr, sp, tp, al in rows:
            lines.append(f"{ts:19}   {str(hr or '--'):>3}   {str(sp or '--'):>3}   {str(round(tp,1) if tp else '--'):>5}   {al}")
        self.lbl.text = "\n".join(lines)

class SettingsScreen(Screen):
    def __init__(self, app_ref, **kwargs):
        super().__init__(**kwargs)
        self._app = app_ref
        root = BoxLayout(orientation="vertical", padding=6, spacing=6)
        self.title_bar = TopBar()
        root.add_widget(self.title_bar)

        info = Label(text="[Cài đặt nhanh]\n- Ngưỡng HR/SpO₂/Temp dùng mặc định trong code.\n- MQTT: sửa cờ enabled/host/port trong code hoặc thêm file YAML.\n- Âm thanh: đang dùng espeak-ng offline.",
                     font_size="16sp", halign="center")
        root.add_widget(info)

        nav = GridLayout(cols=2, size_hint_y=None, height=60, spacing=6)
        nav.add_widget(Button(text="Thử cảnh báo (TTS)", on_release=lambda *_: self._app.raise_alert("Cảnh báo thử nghiệm!")))
        nav.add_widget(Button(text="Về Dashboard", on_release=lambda *_: setattr(self.manager, "current", "dash")))
        root.add_widget(nav)

        self.add_widget(root)

# ------------------------
# APP CHÍNH
# ------------------------
@dataclass
class VitalState:
    hr: Optional[float] = None
    spo2: Optional[float] = None
    temp: Optional[float] = None

class SmartHealthApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.title = "Smart Health Edge"
        self.thr = DEFAULT_THRESHOLDS.copy()
        self.vital = VitalState()
        self.msg_q = queue.Queue()
        self.stop_ev = threading.Event()
        self.reader = MAX30102Reader(self.msg_q, self.stop_ev, sample_period=1.0)
        self.temp_sensor = GY906()
        self.temp_ev = None
        self.mqttc = MQTTClient(MQTT_CFG)
        self._last_alert_ts = 0

    def build(self):
        db_init()
        self.sm = ScreenManager(transition=NoTransition())
        self.scr_dash = DashboardScreen(name="dash")
        self.scr_bp = BPMeasurementScreen(name="bp")
        self.scr_hist = HistoryScreen(name="history")
        self.scr_settings = SettingsScreen(self, name="settings")
        self.sm.add_widget(self.scr_dash)
        self.sm.add_widget(self.scr_bp)
        self.sm.add_widget(self.scr_hist)
        self.sm.add_widget(self.scr_settings)

        # luồng cảm biến
        self.reader.start()
        Clock.schedule_interval(self._poll_queue, 0.1)
        self.temp_ev = Clock.schedule_interval(self._read_temp, 2.0)

        # mqtt
        self.mqttc.start()

        # phím cứng ESC/F12 -> thoát nhanh
        Window.bind(on_keyboard=self._on_key)
        # status
        Clock.schedule_interval(lambda dt: self.scr_dash.title_bar.set_status(f"MQTT: {'OK' if self.mqttc.connected else 'Off'}"), 1.0)
        return self.sm

    def _on_key(self, win, key, scancode, codepoint, modifier):
        # ESC hoặc F12 -> thoát
        if key in (27, 318):
            self.safe_exit()
            return True
        return False

    def safe_exit(self):
        try:
            self.stop_ev.set()
            if self.temp_ev:
                self.temp_ev.cancel()
            self.mqttc.stop()
        finally:
            App.get_running_app().stop()

    # --- cảm biến ---
    def _poll_queue(self, dt):
        try:
            while True:
                msg = self.msg_q.get_nowait()
                if msg[0] == "max30102":
                    _, ts, hr, spo2 = msg
                    self.vital.hr = hr
                    self.vital.spo2 = spo2
                    self._update_ui_store(ts)
                elif msg[0] == "max30102_err":
                    _, ts, err = msg
                    self.scr_dash.title_bar.set_status(f"MAX30102 lỗi: {err}")
        except queue.Empty:
            pass

    def _read_temp(self, dt):
        ts = now_ts()
        try:
            temp = self.temp_sensor.read()
            self.vital.temp = temp
            self._update_ui_store(ts)
        except Exception as e:
            self.scr_dash.title_bar.set_status(f"GY-906 lỗi: {e}")

    def _update_ui_store(self, ts: str):
        # cập nhật giao diện
        self.scr_dash.update_vitals(self.vital.hr, self.vital.spo2, self.vital.temp, self.thr)

        # kiểm tra cảnh báo
        alert_msg = self._check_rules(self.vital)
        if alert_msg and time.time() - self._last_alert_ts > 15:
            self.raise_alert(alert_msg)
            self._last_alert_ts = time.time()

        # ghi DB
        db_insert(ts, self.vital.hr, self.vital.spo2, self.vital.temp, alert_msg or None)

        # publish MQTT
        if MQTT_CFG["enabled"]:
            self.mqttc.pub("vitals", {
                "ts": ts,
                "hr": self.vital.hr, "spo2": self.vital.spo2, "temp": self.vital.temp
            })
            if alert_msg:
                self.mqttc.pub("alerts", {"ts": ts, "msg": alert_msg})

    def _check_rules(self, v: VitalState) -> Optional[str]:
        alerts = []
        if v.hr is not None and (v.hr < self.thr["hr_min"] or v.hr > self.thr["hr_max"]):
            alerts.append(f"Nhịp tim bất thường: {int(v.hr)} bpm")
        if v.spo2 is not None and v.spo2 < self.thr["spo2_min"]:
            alerts.append(f"SpO₂ thấp: {int(v.spo2)}%")
        if v.temp is not None and (v.temp < self.thr["temp_min"] or v.temp > self.thr["temp_max"]):
            alerts.append(f"Nhiệt độ bất thường: {v.temp:.1f}°C")
        return "; ".join(alerts) if alerts else None

    def raise_alert(self, text: str):
        speak(text)                 # chỉ đọc qua loa (không beep buzzer)
        self.scr_dash.show_alert(text)

if __name__ == "__main__":
    # Gợi ý môi trường nếu chạy trên Desktop/X11:
    # export DISPLAY=:0
    SmartHealthApp().run()
