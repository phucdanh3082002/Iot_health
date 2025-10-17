#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bp_demo_test_full.py
Test bơm/xả qua 4N35+MOSFET và đọc HX710B (giả lập đo oscillometric).
- Zero offset trước khi bơm
- Bơm đến TARGET, soft-limit bảo vệ
- Đóng/mở van đúng với loại NO/NC
- Xả theo nhịp để ~2–4 mmHg/s
- Detrend + envelope đơn giản để ước lượng MAP/SYS/DIA (chỉ để test quy trình)

PHẦN CỨNG (BCM):
  Pump via 4N35 LED : PUMP_GPIO
  Valve via 4N35 LED: VALVE_GPIO
  HX710B: OUT=HX_OUT, SCK=HX_SCK  (miền 3.3 V, chung GND với Pi)

AN TOÀN:
  - Luôn có van relief cơ khí 250–300 mmHg
  - Không đeo cuff quá chặt khi test lần đầu
  - Ctrl+C -> xả khẩn rồi cleanup
"""
import time
import statistics
import RPi.GPIO as GPIO

# ===================== CẤU HÌNH CHÂN (BCM) =====================
PUMP_GPIO  = 26   # <-- theo log bạn đang dùng 26; nếu chuyển dây sang 27 thì đổi số này
VALVE_GPIO = 16
HX_OUT     = 6
HX_SCK     = 5

# ===================== LOẠI VAN =====================
# True  = van NO (thường mở) -> muốn ĐÓNG xả thì phải bật (ON)
# False = van NC (thường đóng) -> muốn MỞ xả thì phải bật (ON)
VALVE_IS_NO = True

# ===================== THAM SỐ ĐO/AN TOÀN =====================
TARGET_MMHG        = 170.0   # mmHg
SOFT_LIMIT_MMHG    = 200.0   # mmHg
INFLATE_TIMEOUT_S  = 30.0
MEASURE_TIMEOUT_S  = 120.0
SAMPLE_INTERVAL_S  = 1/160.0
MIN_INFLATE_TIME_S = 3.0     # ép bơm tối thiểu 3 s để tránh dừng sớm vì 1 mẫu nhiễu

# ===================== CHUYỂN ĐỔI COUNTS -> mmHg =====================
# Lưu ý: chỉ để hiển thị/tương đối. Sau này hiệu chuẩn đúng bằng offset/slope theo máy tham chiếu.
COUNTS_SLOPE  = 0.0003   # mmHg / count (nếu số lên quá chậm -> tăng; nếu nhảy quá lớn -> giảm)
COUNTS_OFFSET = None     # sẽ đo bằng zero_offset() trước khi bơm

# Bỏ mẫu "điên"
MMHG_MIN_VALID = -10.0
MMHG_MAX_VALID = 260.0

# ===================== LỌC VÀ ƯỚC LƯỢNG THỬ =====================
EMA_ALPHA_BASE = 0.02
ENV_ALPHA      = 0.10
SYS_RATIO      = 0.55
DIA_RATIO      = 0.85

# ===================== ĐỌC HX710B (hai chế độ) =====================
# Một số board cần chốt bit ở cạnh khác, hoặc phải đảo bit. Cho tuỳ chọn để thử nhanh.
HX_READ_MODE = 0   # 0: lấy bit khi SCK lên; 1: lấy bit khi SCK xuống
INVERT_BITS  = False

# ===================== GPIO HELPERS =====================
def gpio_setup():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(PUMP_GPIO,  GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(VALVE_GPIO, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(HX_OUT, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # DRDY thường LOW khi sẵn
    GPIO.setup(HX_SCK, GPIO.OUT, initial=GPIO.LOW)

def pump(on: bool):
    GPIO.output(PUMP_GPIO, GPIO.HIGH if on else GPIO.LOW)

def valve(on: bool):
    GPIO.output(VALVE_GPIO, GPIO.HIGH if on else GPIO.LOW)

# ===================== HX710B =====================
def hx_read_raw(timeout_s=0.25):
    """Đọc 24-bit từ HX710B. Trả None nếu timeout đợi DRDY."""
    t0 = time.time()
    while GPIO.input(HX_OUT) == 1:
        if time.time() - t0 > timeout_s:
            return None

    value = 0
    if HX_READ_MODE == 0:
        # chốt bit khi SCK lên
        for _ in range(24):
            GPIO.output(HX_SCK, True)
            bit = GPIO.input(HX_OUT)
            GPIO.output(HX_SCK, False)
            value = (value << 1) | bit
    else:
        # chốt bit khi SCK xuống
        for _ in range(24):
            GPIO.output(HX_SCK, True)
            GPIO.output(HX_SCK, False)
            bit = GPIO.input(HX_OUT)
            value = (value << 1) | bit

    # 25th pulse để chốt gain/channel (mặc định)
    GPIO.output(HX_SCK, True)
    GPIO.output(HX_SCK, False)

    if INVERT_BITS:
        value ^= 0xFFFFFF

    # Two's complement 24-bit
    if value & 0x800000:
        value -= 1 << 24
    return value

def counts_to_mmhg(counts: float) -> float:
    return (counts - COUNTS_OFFSET) * COUNTS_SLOPE

def zero_offset(n=40, timeout_s_per=0.25):
    """Mở van, lấy N mẫu để ZERO COUNTS_OFFSET."""
    global COUNTS_OFFSET
    print("[ZERO] Mở van để xả hoàn toàn & đo offset ...")
    # MỞ xả theo loại van
    if VALVE_IS_NO:
        # van NO: OFF là mở
        valve(False)
    else:
        # van NC: ON là mở
        valve(True)

    time.sleep(0.6)  # xả sạch
    samples = []
    t0 = time.time()
    while len(samples) < n and (time.time() - t0) < n*timeout_s_per*2:
        r = hx_read_raw(timeout_s=timeout_s_per)
        if r is not None:
            samples.append(r)
            time.sleep(0.01)

    # ĐÓNG xả lại
    if VALVE_IS_NO:
        # NO: ON là đóng
        valve(True)
    else:
        # NC: OFF là đóng
        valve(False)

    if not samples:
        print("[ZERO] KHÔNG đọc được mẫu nào. Kiểm tra OUT/SCK/VCC/GND.")
        return False
    # Median cho robust
    COUNTS_OFFSET = statistics.median(samples)
    print(f"[ZERO] COUNTS_OFFSET = {COUNTS_OFFSET}")
    return True

# ===================== AN TOÀN =====================
def safe_cleanup():
    try:
        pump(False)
        # MỞ xả khẩn:
        if VALVE_IS_NO:
            valve(False)  # NO: OFF là mở
        else:
            valve(True)   # NC: ON là mở
        time.sleep(1.0)
        # Đóng lại
        if VALVE_IS_NO:
            valve(True)   # NO: ON là đóng
        else:
            valve(False)  # NC: OFF là đóng
    finally:
        GPIO.cleanup()

# ===================== PHA BƠM =====================
def inflate_to_target():
    print(f"[INFLATE] Bơm tới {TARGET_MMHG:.0f} mmHg (soft-limit {SOFT_LIMIT_MMHG:.0f})")

    # ĐÓNG xả theo loại van
    if VALVE_IS_NO:
        valve(True)    # NO: ON = đóng xả
    else:
        valve(False)   # NC: OFF = đóng xả

    t_start = time.time()
    last_log = 0
    pump(True)

    while True:
        raw = hx_read_raw()
        now = time.time()

        mmhg = None
        if raw is not None and COUNTS_OFFSET is not None:
            p = counts_to_mmhg(raw)
            if MMHG_MIN_VALID <= p <= MMHG_MAX_VALID:
                mmhg = p

        if now - last_log > 0.25:
            if mmhg is None:
                print("[INFLATE] Đang bơm... (đợi dữ liệu hợp lệ)")
            else:
                print(f"[INFLATE] P ≈ {mmhg:6.1f} mmHg")
            last_log = now

        # ép bơm tối thiểu vài giây
        if now - t_start < MIN_INFLATE_TIME_S:
            time.sleep(SAMPLE_INTERVAL_S)
            continue

        # chỉ xét điều kiện dừng khi có mmHg hợp lệ
        if mmhg is not None and (mmhg >= TARGET_MMHG or mmhg >= SOFT_LIMIT_MMHG):
            break
        if now - t_start > INFLATE_TIMEOUT_S:
            print("[INFLATE] TIMEOUT. Dừng bơm.")
            break

        time.sleep(SAMPLE_INTERVAL_S)

    pump(False)
    print("[INFLATE] Dừng bơm.")

# ===================== PHA XẢ & THU DAO ĐỘNG =====================
def deflate_with_measure():
    print("[DEFLATE] Xả ~2–4 mmHg/s, thu dao động ...")

    # Van phải MỞ trong xả:
    if VALVE_IS_NO:
        valve(False)  # NO: OFF = mở xả
    else:
        valve(True)   # NC: ON  = mở xả

    # Nhịp xả dạng pulse (tinh chỉnh để đạt ~2–4 mmHg/s)
    VALVE_PULSE_ON_S  = 0.060
    VALVE_PULSE_OFF_S = 0.260

    ema = None
    env = 0.0
    amax = 0.0
    p_at_amax = None
    p_sys = None
    p_dia = None
    crossed_sys = False
    crossed_dia = False

    t0 = time.time()
    last_log = 0

    while True:
        raw = hx_read_raw()
        if raw is None or COUNTS_OFFSET is None:
            # mất dữ liệu -> vẫn giữ xả an toàn
            time.sleep(VALVE_PULSE_ON_S + VALVE_PULSE_OFF_S)
            continue

        p = counts_to_mmhg(raw)
        # sanity clamp
        if not (MMHG_MIN_VALID <= p <= MMHG_MAX_VALID):
            # tiếp tục xả nhẹ
            time.sleep(VALVE_PULSE_ON_S + VALVE_PULSE_OFF_S)
            continue

        # detrend & envelope
        if ema is None:
            ema = p
        ema = ema + EMA_ALPHA_BASE * (p - ema)
        hi = p - ema
        env = (1 - ENV_ALPHA) * env + ENV_ALPHA * abs(hi)

        # xả theo nhịp (nếu muốn điều tiết tốc độ xả tinh hơn)
        time.sleep(VALVE_PULSE_ON_S)
        # (van đã mở liên tục theo kiểu NO/NC bên trên; nếu bạn muốn "đóng–mở nhịp"
        #  thì hãy điều khiển valve(True/False) tại đây tuỳ loại van của bạn)

        time.sleep(VALVE_PULSE_OFF_S)

        # theo dõi Amax / MAP / SYS / DIA đơn giản (chỉ test luồng)
        if env > amax:
            amax = env
            p_at_amax = p
        if amax > 1.0:
            th_sys = SYS_RATIO * amax
            th_dia = DIA_RATIO * amax
            if not crossed_sys and env <= th_sys:
                p_sys = p; crossed_sys = True
            if not crossed_dia and env <= th_dia:
                p_dia = p; crossed_dia = True

        now = time.time()
        if now - last_log > 0.35:
            msg = f"[DEFLATE] P≈{p:6.1f} | env≈{env:5.2f} | Amax≈{amax:5.2f}"
            if p_at_amax is not None: msg += f" | MAP≈{p_at_amax:6.1f}"
            if p_sys is not None:     msg += f" | SYS~{p_sys:6.1f}"
            if p_dia is not None:     msg += f" | DIA~{p_dia:6.1f}"
            print(msg)
            last_log = now

        # điều kiện kết thúc cơ bản
        if p <= 40.0:
            break
        if p_at_amax is not None and crossed_sys and crossed_dia:
            break
        if now - t0 > MEASURE_TIMEOUT_S:
            print("[DEFLATE] TIMEOUT đo.")
            break

    # Mở xả thêm 1s để về 0
    if VALVE_IS_NO:
        valve(False)  # NO: OFF = mở
    else:
        valve(True)   # NC: ON  = mở
    time.sleep(1.0)
    # Đóng lại
    if VALVE_IS_NO:
        valve(True)   # NO: ON = đóng
    else:
        valve(False)  # NC: OFF = đóng

    return p_sys, p_dia, p_at_amax

# ===================== MAIN =====================
def main():
    print("== BP DEMO TEST (Full) ==")
    print(f"BCM: Pump={PUMP_GPIO}  Valve={VALVE_GPIO}  HX_OUT={HX_OUT}  HX_SCK={HX_SCK}  | Valve_is_NO={VALVE_IS_NO}")
    gpio_setup()
    try:
        if not zero_offset():
            print("[WARN] Không zero được. Vẫn tiếp tục nhưng giá trị có thể lệch.")
        inflate_to_target()
        sys_est, dia_est, map_est = deflate_with_measure()

        print("\n===== KẾT THÚC PHIÊN (ƯỚC LƯỢNG THỬ) =====")
        if sys_est is not None and dia_est is not None and map_est is not None:
            print(f"SYS≈{sys_est:5.1f} | DIA≈{dia_est:5.1f} | MAP≈{map_est:5.1f}  (giả lập)")
        else:
            print("Chưa đủ tín hiệu để ước lượng. Kiểm tra zero, nhịp xả, dây HX710B, COUNTS_SLOPE.")
    except KeyboardInterrupt:
        print("\n[!] Ctrl+C: XẢ KHẨN & THOÁT")
    finally:
        safe_cleanup()
        print("GPIO cleaned. Bye.")

if __name__ == "__main__":
    main()
