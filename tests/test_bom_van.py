import RPi.GPIO as GPIO
import time
import sys

# --- Cấu hình chân GPIO (ĐÃ CẬP NHẬT) ---
PUMP_PIN = 26  # GPIO26 điều khiển Bơm
VALVE_PIN = 16  # GPIO16 điều khiển Van (Loại Thường Mở - NO)

# Chân cho HX710B (chưa dùng trong bài test này)
# HX710B_DT_PIN = 6
# HX710B_SCK_PIN = 5

def setup_gpio():
    """Thiết lập các chân GPIO."""
    GPIO.setmode(GPIO.BCM)  # Sử dụng cách đánh số BCM
    GPIO.setwarnings(False)
    
    # Thiết lập chân Bơm và Van là OUTPUT
    GPIO.setup(PUMP_PIN, GPIO.OUT)
    GPIO.setup(VALVE_PIN, GPIO.OUT)
    
    # Trạng thái ban đầu an toàn: Bơm TẮT, Van MỞ (xả khí)
    GPIO.output(PUMP_PIN, GPIO.LOW)  # Tắt bơm
    GPIO.output(VALVE_PIN, GPIO.LOW) # Van NO: LOW -> Mở van, xả khí
    
    print(">>> GPIO đã được thiết lập.")
    print(f">>> Bơm (GPIO{PUMP_PIN}): TẮT")
    print(f">>> Van (GPIO{VALVE_PIN}): MỞ (Đang xả khí)")

def main_test_loop():
    """Vòng lặp chính để người dùng tương tác."""
    print("\n" + "="*40)
    print("    CHƯƠNG TRÌNH KIỂM TRA PHẦN CỨNG BƠM/VAN    ")
    print("="*40)
    print("Lưu ý: Van là loại Thường Mở (NO)")
    print("  - Để BƠM CĂNG: phải ĐÓNG van và BẬT bơm.")
    print("  - Để XẢ KHÍ: phải MỞ van.")
    print("\n--- Menu ---")
    print("  'p' : BẬT/TẮT Bơm (Pump)")
    print("  'v' : ĐÓNG/MỞ Van (Valve)")
    print("  'q' : Thoát chương trình")
    print("------------")

    pump_state = False
    valve_state = False # False = Mở, True = Đóng

    while True:
        try:
            choice = input("\nNhập lựa chọn (p, v, q): ").lower()

            if choice == 'p':
                pump_state = not pump_state
                if pump_state:
                    GPIO.output(PUMP_PIN, GPIO.HIGH)
                    print(">>> [BƠM]: ĐÃ BẬT. (Bạn có nghe thấy tiếng bơm chạy không?)")
                else:
                    GPIO.output(PUMP_PIN, GPIO.LOW)
                    print(">>> [BƠM]: ĐÃ TẮT.")
            
            elif choice == 'v':
                valve_state = not valve_state
                if valve_state:
                    GPIO.output(VALVE_PIN, GPIO.HIGH)
                    print(">>> [VAN]: ĐÃ ĐÓNG. (Bạn có nghe thấy tiếng 'tách' không? Luồng khí bị chặn.)")
                else:
                    GPIO.output(VALVE_PIN, GPIO.LOW)
                    print(">>> [VAN]: ĐÃ MỞ. (Bạn có nghe thấy tiếng 'tách' không? Luồng khí được xả.)")

            elif choice == 'q':
                print(">>> Đang thoát...")
                break
            
            else:
                print("Lựa chọn không hợp lệ. Vui lòng thử lại.")

        except KeyboardInterrupt:
            print("\n>>> Đã nhận tín hiệu ngắt, đang thoát...")
            break

if __name__ == "__main__":
    try:
        setup_gpio()
        main_test_loop()
    finally:
        # Quan trọng: Luôn dọn dẹp GPIO để đưa các chân về trạng thái an toàn
        print(">>> Dọn dẹp GPIO và thoát.")
        GPIO.cleanup()
        sys.exit(0)    