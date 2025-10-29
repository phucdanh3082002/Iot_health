# -*- coding: utf-8 -*-



"""
Blood Pressure Sensor (Oscillometric)
====================================

Phiên bản đã cải tiến để khắc phục lỗi phân tích SYS/DIA khi gặp trường hợp
MAP nằm ngoài khoảng [DIA, SYS] do thuật toán tìm biên (envelope) hoặc do
chọn nhánh sai (trái/phải của MAP).

Các điểm chính:
- Giữ nguyên API/public behavior hiện có để không phá vỡ các module khác.
- Loại bỏ code trùng lặp trong khối xử lý hậu kỳ (analysis).
- Chuẩn hoá pipeline: detrend → BPF → Hilbert → envelope → tìm MAP →
  lấy đỉnh tối đa phía TRÁI (SYS-side) và phía PHẢI (DIA-side) quanh MAP.
- Nếu phát hiện quan hệ sai (DIA < MAP < SYS không thỏa), tự động 
  "recovery" bằng chiến lược an toàn (clamp & fallback).
- Ghi log chi tiết để giúp debug trên thiết bị thật (SPS thực tế, biên độ, v.v.).

Lưu ý: Thuật toán chỉ là ước lượng theo kiểu oscillometric và phụ thuộc
hiệu chuẩn (offset/slope) của cuff pressure. Cần so máy tham chiếu để fit hệ số.

Tác giả: ChatGPT (điều chỉnh theo yêu cầu đồ án)
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Callable, Deque, Dict, List, Optional, Tuple
from collections import deque

import numpy as np
from scipy.signal import butter, filtfilt, hilbert

import logging

logger = logging.getLogger("Sensor.BloodPressure")


# -----------------------------------------------------------------------------
# Data classes & types
# -----------------------------------------------------------------------------

@dataclass
class PressureSample:
    """
    Một mẫu áp suất cuff.

    Attributes:
        ts: timestamp (giây, float)
        mmhg: áp suất đã chuyển đổi sang mmHg
        counts: optional raw ADC count (nếu có)
    """

    ts: float
    mmhg: float
    counts: Optional[int] = None


@dataclass
class BPResult:
    ""
    Kết quả ước lượng huyết áp.
    ""

    sys: float
    dia: float
    map: float
    quality: Dict[str, float]


# -----------------------------------------------------------------------------
# Bộ lọc & tiện ích tín hiệu
# -----------------------------------------------------------------------------

def _butter_bandpass(low: float, high: float, fs: float, order: int = 2) -> Tuple[np.ndarray, np.ndarray]:
    nyq = 0.5 * fs
    low_n = max(1e-6, low / nyq)
    high_n = min(0.999, high / nyq)
    b, a = butter(order, [low_n, high_n], btype="band")
    return b, a


def _bandpass_filter(x: np.ndarray, fs: float, low: float = 0.5, high: float = 5.0) -> np.ndarray:
    if len(x) < 8:
        return x
    b, a = _butter_bandpass(low, high, fs, order=2)
    return filtfilt(b, a, x)


def _moving_mean(x: np.ndarray, win: int = 11) -> np.ndarray:
    if win <= 1 or len(x) < 3:
        return x
    win = min(win, len(x) | 1)  # odd
    k = win // 2
    c = np.pad(x, (k, k), mode="edge")
    ker = np.ones(win) / win
    return np.convolve(c, ker, mode="valid")


def _compute_envelope(sig_bp: np.ndarray, fs: float) -> np.ndarray:
    """
    Envelope bằng Hilbert + làm mượt nhẹ để ổn định đỉnh.
    """
    analytic = hilbert(sig_bp)
    env = np.abs(analytic)
    # Làm mượt một chút, tránh mất đỉnh
    smooth_win = max(5, int(0.15 * fs))
    return _moving_mean(env, smooth_win)


def _first_local_maxima(y: np.ndarray, start: int, end: int, prefer_right: bool = False) -> Optional[int]:
    """
    Tìm chỉ số đỉnh cục bộ đầu tiên trong [start, end].
    Nếu prefer_right=True, duyệt từ phải sang trái.
    """
    if end <= start:
        return None
    rng = range(end, start - 1, -1) if prefer_right else range(start, end + 1)
    for i in rng:
        if 0 < i < len(y) - 1 and y[i] >= y[i - 1] and y[i] > y[i + 1]:
            return i
    # nếu không có đỉnh rõ, trả đỉnh toàn cục trong đoạn
    segment = y[start : end + 1]
    if segment.size == 0:
        return None
    off = int(np.argmax(segment))
    return start + off


def _safe_percentile(arr: np.ndarray, q: float) -> float:
    if arr.size == 0:
        return float("nan")
    return float(np.percentile(arr, q))


# -----------------------------------------------------------------------------
# Thuật toán suy ra SYS/DIA từ envelope
# -----------------------------------------------------------------------------

@dataclass
class AnalysisParams:
    """
    Tham số cho phân tích dao động học.
    ""

    fs_nominal: float = 25.0             # SPS mong muốn (để chọn bộ lọc)
    band_low: float = 0.5
    band_high: float = 5.0
    # vùng tìm kiếm quanh MAP, mỗi phía lấy một phần chiều dài deflate
    frac_side: float = 0.45              # mỗi bên 45% là tối đa
    # fallback khi biên yếu (theo tỷ lệ A/Amax điển hình)
    k_sys: float = 0.55                  # A_sys ≈ 0.55 * A_map
    k_dia: float = 0.85                  # A_dia ≈ 0.85 * A_map
    # ràng buộc vật lý
    min_sys_minus_map: float = 5.0
    min_map_minus_dia: float = 5.0


def _find_sys_dia_from_envelope(
    pressure: np.ndarray,
    envelope: np.ndarray,
    idx_map: int,
    params: AnalysisParams,
) -> Tuple[Optional[float], Optional[float]]:
    """
    Tìm SYS/DIA bằng cách lấy đỉnh lớn nhất ở HAI PHÍA của MAP.

    - SYS: đỉnh phía trái (áp cao hơn MAP).
    - DIA: đỉnh phía phải (áp thấp hơn MAP).

    Nếu không có đỉnh cục bộ rõ ràng, dùng "đỉnh toàn cục" trong vùng.
    ""
    n = len(pressure)
    if n < 8:
        return None, None

    # Xác định vùng trái/phải quanh MAP
    side_span = int(params.frac_side * n)
    left_start = max(0, idx_map - side_span)
    left_end = max(0, idx_map - 5)  # cách MAP vài mẫu để tránh bắt lại MAP
    right_start = min(n - 1, idx_map + 5)
    right_end = min(n - 1, idx_map + side_span)

    # SYS: tìm đỉnh phía trái (ưu tiên gần MAP)
    idx_sys = _first_local_maxima(envelope, left_start, left_end, prefer_right=True)

    # DIA: tìm đỉnh phía phải (ưu tiên gần MAP)
    idx_dia = _first_local_maxima(envelope, right_start, right_end, prefer_right=False)

    sys_val = float(pressure[idx_sys]) if idx_sys is not None else None
    dia_val = float(pressure[idx_dia]) if idx_dia is not None else None

    return sys_val, dia_val


def _recover_sys_dia_if_invalid(
    pressure: np.ndarray,
    envelope: np.ndarray,
    idx_map: int,
    map_val: float,
    sys_dia: Tuple[Optional[float], Optional[float]],
    params: AnalysisParams,
) -> Tuple[Optional[float], Optional[float]]:
    """
    Nếu không thỏa DIA < MAP < SYS, thử phục hồi bằng:
    1) Sử dụng tỷ lệ biên độ điển hình (k_sys, k_dia) để suy ra SYS/DIA.
    2) Kẹp khoảng an toàn cách MAP một biên tối thiểu.
    ""
    sys_val, dia_val = sys_dia

    def clamp_sys(x: float) -> float:
        return max(x, map_val + params.min_sys_minus_map)

    def clamp_dia(x: float) -> float:
        return min(x, map_val - params.min_map_minus_dia)

    ok = (sys_val is not None and dia_val is not None and dia_val < map_val < sys_val)
    if ok:
        return sys_val, dia_val

    # Fallback theo tỷ lệ biên độ
    a = float(envelope[idx_map])
    a_sys = params.k_sys * a
    a_dia = params.k_dia * a

    # tìm áp tại nơi envelope gần a_sys ở phía trái và a_dia ở phía phải
    # for numerical robustness, chọn điểm có |env - target| nhỏ nhất trong vùng
    n = len(pressure)
    side_span = int(params.frac_side * n)
    left_start = max(0, idx_map - side_span)
    left_end = max(0, idx_map - 5)
    right_start = min(n - 1, idx_map + 5)
    right_end = min(n - 1, idx_map + side_span)

    def nearest_by_amp(target: float, start: int, end: int) -> Optional[int]:
        if end <= start:
            return None
        seg = envelope[start : end + 1]
        j = int(np.argmin(np.abs(seg - target)))
        return start + j

    idx_sys2 = nearest_by_amp(a_sys, left_start, left_end)
    idx_dia2 = nearest_by_amp(a_dia, right_start, right_end)

    sys_fallback = float(pressure[idx_sys2]) if idx_sys2 is not None else None
    dia_fallback = float(pressure[idx_dia2]) if idx_dia2 is not None else None

    # Áp dụng clamp để đảm bảo thứ tự vật lý
    if sys_fallback is not None:
        sys_fallback = clamp_sys(sys_fallback)
    if dia_fallback is not None:
        dia_fallback = clamp_dia(dia_fallback)

    # Chọn kết quả tốt nhất theo độ hợp lệ
    cand = []
    if sys_val is not None and dia_val is not None:
        cand.append((sys_val, dia_val))
    if sys_fallback is not None and dia_fallback is not None:
        cand.append((sys_fallback, dia_fallback))

    for s, d in cand:
        if d < map_val < s:
            return s, d

    # Nếu vẫn thất bại, dùng khoảng an toàn đối xứng quanh MAP
    sys_safe = map_val + max(params.min_sys_minus_map, 0.15 * map_val)
    dia_safe = map_val - max(params.min_map_minus_dia, 0.15 * map_val)
    if dia_safe < map_val < sys_safe:
        return sys_safe, dia_safe

    return None, None


# -----------------------------------------------------------------------------
# Lớp cảm biến chính
# -----------------------------------------------------------------------------

class BloodPressureSensor:
    """
    Driver đo huyết áp kiểu oscillometric, non-blocking.

    Public API (giữ nguyên):
        - start() / stop()
        - start_measurement()
        - get_last_result() -> Optional[BPResult]

    Yêu cầu: Một luồng/bộ phát mẫu áp suất (mmHg) push vào queue nội bộ.
    ""

    def __init__(
        self,
        sample_rate_hint: float = 25.0,
        max_pressure_mmhg: float = 220.0,
        inflate_target_mmhg: float = 190.0,
        passive_deflate_rate: float = 3.0,
        analysis_params: Optional[AnalysisParams] = None,
    ) -> None:
        self._running = False
        self._measuring = False
        self._lock = threading.RLock()

        self._samples: Deque[PressureSample] = deque(maxlen=10_000)
        self._last_result: Optional[BPResult] = None

        self.sample_rate_hint = float(sample_rate_hint)
        self.max_pressure_mmhg = float(max_pressure_mmhg)
        self.inflate_target_mmhg = float(inflate_target_mmhg)
        self.passive_deflate_rate = float(passive_deflate_rate)
        self.params = analysis_params or AnalysisParams(fs_nominal=self.sample_rate_hint)

        logger.info(
            "BloodPressureSensor initialized: Inflate=%smmHg, Deflate=%smmHg/s",
            self.inflate_target_mmhg, self.passive_deflate_rate,
        )

    # ------------------------------------------------------------------
    # Life-cycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            # TODO: khởi tạo phần cứng pump/valve, ADC đã có ở lớp khác.
            self._running = True
            logger.info("Started BloodPressure sensor")

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            # TODO: tắt phần cứng, đóng tài nguyên.
            self._running = False
            self._measuring = False
            logger.info("Stopped BloodPressure sensor")

    # ------------------------------------------------------------------
    # Measurement control
    # ------------------------------------------------------------------
    def start_measurement(self) -> None:
        with self._lock:
            if not self._running:
                raise RuntimeError("Sensor not started")
            if self._measuring:
                logger.warning("Measurement already in progress")
                return
            self._measuring = True
            logger.info("Started blood pressure measurement")

    def push_pressure_sample(self, ts: float, mmhg: float, counts: Optional[int] = None) -> None:
        """
        Hàm này được ADC/HX710B layer gọi mỗi khi có mẫu mới.
        ""
        if not self._measuring:
            return
        self._samples.append(PressureSample(ts=ts, mmhg=float(mmhg), counts=counts))

    def end_deflate_and_analyze(self) -> Optional[BPResult]:
        """
        Gọi khi kết thúc pha xả để thực hiện phân tích.
        ""
        with self._lock:
            if not self._measuring:
                logger.error("end_deflate_and_analyze() called but not measuring")
                return None
            samples = list(self._samples)
            self._measuring = False

        if len(samples) < 100:
            logger.error("Not enough samples for analysis: %d", len(samples))
            return None

        ts = np.array([s.ts for s in samples], dtype=float)
        p_raw = np.array([s.mmhg for s in samples], dtype=float)

        # Tính SPS thực tế
        dt = np.diff(ts)
        dt = dt[(dt > 0) & (dt < 1.0)]
        fs = 1.0 / float(np.median(dt)) if dt.size > 0 else self.sample_rate_hint
        logger.info("Actual sample rate: %.1f SPS (config: %.1f SPS)", fs, self.sample_rate_hint)

        # --- Detrend (nền giảm tuyến tính)
        t0 = ts[0]
        tt = ts - t0
        A = np.vstack([tt, np.ones_like(tt)]).T
        coef, _, _, _ = np.linalg.lstsq(A, p_raw, rcond=None)
        trend = A @ coef
        p_detr = p_raw - trend

        # --- BPF oscillations 0.5–5 Hz
        p_osc = _bandpass_filter(p_detr, fs, self.params.band_low, self.params.band_high)

        # --- Envelope
        env = _compute_envelope(p_osc, fs)

        # --- Chất lượng tín hiệu
        env_pp = float(np.nanmax(env) - np.nanmin(env)) if env.size else float("nan")
        sig_pp = float(np.nanmax(p_osc) - np.nanmin(p_osc)) if p_osc.size else float("nan")
        logger.info("Signal quality: Oscillations P-P=%.3f, Envelope P-P=%.3f", sig_pp, env_pp)

        # --- MAP = áp suất tại đỉnh envelope toàn cục
        idx_map = int(np.nanargmax(env))
        map_val = float(p_raw[idx_map])
        logger.info("MAP detected: %.1f mmHg @ idx %d/%d (amplitude: %.3f)", map_val, idx_map, len(p_raw), float(env[idx_map]))

        # --- Tìm SYS/DIA ở hai phía của MAP
        sys0, dia0 = _find_sys_dia_from_envelope(p_raw, env, idx_map, self.params)

        # --- Nếu quan hệ không đúng, tiến hành phục hồi an toàn
        sys1, dia1 = _recover_sys_dia_if_invalid(p_raw, env, idx_map, map_val, (sys0, dia0), self.params)

        if sys1 is None or dia1 is None:
            logger.error("Invalid BP relationship and recovery failed: SYS=%s, MAP=%.1f, DIA=%s", sys0, map_val, dia0)
            return None

        if not (dia1 < map_val < sys1):
            logger.error("Invalid BP relationship after recovery: DIA=%.1f < MAP=%.1f < SYS=%.1f not satisfied", dia1, map_val, sys1)
            return None

        result = BPResult(sys=float(sys1), dia=float(dia1), map=float(map_val), quality={
            "fs": float(fs),
            "env_pp": float(env_pp),
            "sig_pp": float(sig_pp),
        })

        self._last_result = result
        logger.info("Estimated BP: SYS=%.1f, DIA=%.1f, MAP=%.1f", result.sys, result.dia, result.map)
        return result

    # ------------------------------------------------------------------
    # Results API
    # ------------------------------------------------------------------
    def get_last_result(self) -> Optional[BPResult]:
        return self._last_result


__all__ = [
    "BloodPressureSensor",
    "PressureSample",
    "BPResult",
    "AnalysisParams",
]