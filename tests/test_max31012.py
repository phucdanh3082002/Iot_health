import time
import sys

# Import MAX30102 và hrcalc nếu đã copy vào lib hoặc cùng thư mục
try:
	import max30102
	import hrcalc
except ImportError:
	print("Không tìm thấy max30102 hoặc hrcalc! Hãy chắc chắn đã copy vào lib hoặc PYTHONPATH.")
	sys.exit(1)

# Import smbus2 cho GY-906 (MLX90614)
try:
	from smbus2 import SMBus
except ImportError:
	print("Chưa cài đặt thư viện smbus2! Hãy chạy: pip install smbus2")
	sys.exit(1)

def test_max30102():
	print("\n--- Test cảm biến MAX30102 ---")
	try:
		m = max30102.MAX30102()
	except Exception as e:
		print(f"Lỗi khi khởi tạo MAX30102: {e}")
		print("\u2716 Không thể giao tiếp với cảm biến MAX30102. Kiểm tra lại kết nối, nguồn, và địa chỉ I2C (mặc định 0x57).")
		return
	print("Bắt đầu test liên tục nhịp tim và SpO2. Nhấn Ctrl+C để dừng.")
	try:
		import numpy as np
		BUFFER_SIZE = 100  # Theo hrcalc.py
		IR_THRESHOLD = 50000  # Có thể điều chỉnh theo thực tế
		while True:
			red_buf, ir_buf = m.read_sequential(BUFFER_SIZE)
			ir_mean = np.mean(ir_buf)
			if ir_mean < IR_THRESHOLD:
				print("\u26A0\uFE0F Không phát hiện tay đặt lên cảm biến. Vui lòng đặt ngón tay lên cảm biến MAX30102.")
				time.sleep(1)
				continue
			print(f"Đang đo... (IR trung bình: {int(ir_mean)})")
			try:
				hr, hr_valid, spo2, spo2_valid = hrcalc.calc_hr_and_spo2(np.array(ir_buf), np.array(red_buf))
				if hr_valid:
					print(f"Nhịp tim: {hr} bpm")
				else:
					print("Không xác định được nhịp tim.")
				if spo2_valid:
					print(f"SpO2: {spo2:.2f}%")
				else:
					print("Không xác định được SpO2.")
			except Exception as e:
				print(f"Không tính được HR/SpO2: {e}")
			time.sleep(1)
	except KeyboardInterrupt:
		print("\nDừng test MAX30102.")
	except Exception as e:
		print(f"Lỗi khi đọc dữ liệu MAX30102: {e}")
	finally:
		try:
			m.shutdown()
		except Exception:
			pass
	print("Hoàn thành test MAX30102.")

def test_gy906():
	print("\n--- Test cảm biến GY-906 (MLX90614) ---")
	address = 0x5A
	temp_reg = 0x07
	print("Bắt đầu test liên tục GY-906. Nhấn Ctrl+C để dừng.")
	try:
		with SMBus(1) as bus:
			while True:
				try:
					data = bus.read_word_data(address, temp_reg)
					temp = (data * 0.02) - 273.15
					print(f"Nhiệt độ = {temp:.2f}°C")
				except Exception as e:
					print(f"Lỗi khi đọc GY-906: {e}")
				time.sleep(1)
	except KeyboardInterrupt:
		print("\nDừng test GY-906.")
	except Exception as e:
		print(f"Lỗi khi giao tiếp với GY-906: {e}")
	print("Hoàn thành test GY-906.")

if __name__ == "__main__":
	def main_menu():
		while True:
			print("\n===== MENU TEST CẢM BIẾN =====")
			print("1. Test cảm biến MAX30102")
			print("2. Test cảm biến GY-906 (MLX90614)")
			print("3. Test cả hai cảm biến")
			print("0. Thoát")
			choice = input("Chọn chức năng (0-3): ").strip()
			if choice == '1':
				test_max30102()
			elif choice == '2':
				test_gy906()
			elif choice == '3':
				test_max30102()
				test_gy906()
			elif choice == '0':
				print("Thoát chương trình.")
				break
			else:
				print("Lựa chọn không hợp lệ. Vui lòng chọn lại.")

	if __name__ == "__main__":
		main_menu()