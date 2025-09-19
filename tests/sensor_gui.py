from kivy.config import Config
Config.set('graphics', 'fullscreen', 'auto')

import threading
import time
import sys
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.clock import Clock

try:
    import max30102
    import hrcalc
    from smbus2 import SMBus
    import numpy as np
except ImportError as e:
    print("Thiếu thư viện:", e)
    sys.exit(1)

class SensorApp(App):
    def build(self):
        self.running = False
        self.test_thread = None

        self.layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        self.label = Label(text="Chọn cảm biến để test", font_size='28sp', size_hint=(1, 0.5))
        self.btn_max = Button(text="Test MAX30102", font_size='28sp', size_hint=(1, 0.2), background_color=(0,1,0,1))
        self.btn_gy = Button(text="Test GY-906", font_size='28sp', size_hint=(1, 0.2), background_color=(0,0,1,1))
        self.btn_stop = Button(text="Dừng lại", font_size='28sp', size_hint=(1, 0.2), background_color=(1,0,0,1))

        self.btn_max.bind(on_press=self.start_max30102)
        self.btn_gy.bind(on_press=self.start_gy906)
        self.btn_stop.bind(on_press=self.stop_test)

        self.layout.add_widget(self.label)
        self.layout.add_widget(self.btn_max)
        self.layout.add_widget(self.btn_gy)
        self.layout.add_widget(self.btn_stop)
        return self.layout

    def start_max30102(self, instance):
        self.stop_test()
        self.running = True
        self.label.text = "Đang test MAX30102..."
        self.test_thread = threading.Thread(target=self.test_max30102)
        self.test_thread.start()

    def start_gy906(self, instance):
        self.stop_test()
        self.running = True
        self.label.text = "Đang test GY-906..."
        self.test_thread = threading.Thread(target=self.test_gy906)
        self.test_thread.start()

    def stop_test(self, *args):
        self.running = False
        self.label.text = "Đã dừng."
        time.sleep(0.1)  # Cho thread cũ dừng hẳn

    def test_max30102(self):
        try:
            m = max30102.MAX30102()
            BUFFER_SIZE = 100
            IR_THRESHOLD = 50000
            while self.running:
                red_buf, ir_buf = m.read_sequential(BUFFER_SIZE)
                ir_mean = np.mean(ir_buf)
                if ir_mean < IR_THRESHOLD:
                    self.update_label("Vui lòng đặt ngón tay lên cảm biến MAX30102.")
                    time.sleep(1)
                    continue
                try:
                    hr, hr_valid, spo2, spo2_valid = hrcalc.calc_hr_and_spo2(np.array(ir_buf), np.array(red_buf))
                    msg = f"Nhịp tim: {hr if hr_valid else '---'} bpm\nSpO2: {spo2:.2f}% " if spo2_valid else "Không xác định được SpO2."
                    self.update_label(msg)
                except Exception as e:
                    self.update_label(f"Lỗi tính toán: {e}")
                time.sleep(1)
            m.shutdown()
        except Exception as e:
            self.update_label(f"Lỗi MAX30102: {e}")

    def test_gy906(self):
        address = 0x5A
        temp_reg = 0x07
        try:
            with SMBus(1) as bus:
                while self.running:
                    try:
                        data = bus.read_word_data(address, temp_reg)
                        temp = (data * 0.02) - 273.15
                        self.update_label(f"Nhiệt độ: {temp:.2f}°C")
                    except Exception as e:
                        self.update_label(f"Lỗi GY-906: {e}")
                    time.sleep(1)
        except Exception as e:
            self.update_label(f"Lỗi SMBus: {e}")

    def update_label(self, text):
        def update(dt=None):
            self.label.text = text
        Clock.schedule_once(update, 0)

if __name__ == '__main__':
    SensorApp().run()
