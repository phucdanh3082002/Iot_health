"""Utility helpers for handling Piper TTS playback and speech scenarios."""

from __future__ import annotations

import atexit
import audioop
from array import array
import hashlib
import logging
import shutil
import subprocess
import tempfile
import time
import wave
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from itertools import count
from queue import Empty, PriorityQueue
from threading import Event, Thread
from typing import Callable, Dict, Iterable, Optional, Tuple, Union


LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Piper engine wrappers
# ---------------------------------------------------------------------------


DEFAULT_PIPER_MODEL = Path("/home/pi/piper_models/vi_VN-vais1000-medium.onnx")
DEFAULT_PIPER_CONFIG = Path("/home/pi/piper_models/vi_VN-vais1000-medium.onnx.json")


class PiperTTS:
    """Simple wrapper for invoking Piper TTS and playing audio."""

    def __init__(
        self,
        model_path: Path,
        config_path: Optional[Path] = None,
        speaker: Optional[str] = None,
    ) -> None:
        self.model_path = Path(model_path)
        self.config_path = Path(config_path) if config_path else None
        self.speaker = speaker or None
        self._validate_paths()

    def _validate_paths(self) -> None:
        if shutil.which("piper") is None:
            raise FileNotFoundError("Piper binary not found in PATH")

        if not self.model_path.exists():
            raise FileNotFoundError(f"Piper model not found: {self.model_path}")

        if self.config_path and not self.config_path.exists():
            raise FileNotFoundError(f"Piper config not found: {self.config_path}")

    def speak(
        self,
        message: str,
        volume: Optional[int] = None,
        cache_path: Optional[Path] = None,
        playback: bool = True,
    ) -> None:
        if not message:
            return

        use_cache = cache_path is not None
        tmp_path: Optional[Path] = None

        try:
            if use_cache:
                self.ensure_cached(message, volume, cache_path)
                target_path = cache_path
            else:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                    tmp_path = Path(tmp_file.name)

                self._synthesize(message, tmp_path)

                if volume is not None:
                    self._apply_volume(tmp_path, volume)

                self._apply_fade_edges(tmp_path)
                target_path = tmp_path

            if playback:
                subprocess.run(["aplay", "-q", str(target_path)], check=True)

        except subprocess.CalledProcessError as exc:
            LOGGER.error("Piper command failed: return code %s", exc.returncode)
            raise
        except FileNotFoundError as exc:
            LOGGER.error("TTS resource missing: %s", exc)
            raise
        finally:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink()

    def _synthesize(self, message: str, output_path: Path) -> None:
        command = [
            "piper",
            "--model",
            str(self.model_path),
            "--output_file",
            str(output_path),
        ]

        if self.config_path:
            command.extend(["--config", str(self.config_path)])

        if self.speaker:
            command.extend(["--speaker", str(self.speaker)])

        command.append(message)

        LOGGER.debug("Running Piper command: %s", command)
        subprocess.run(command, check=True)

    def ensure_cached(
        self,
        message: str,
        volume: Optional[int],
        cache_path: Path,
    ) -> None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        if cache_path.exists():
            return

        tmp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                tmp_path = Path(tmp_file.name)

            self._synthesize(message, tmp_path)

            if volume is not None:
                self._apply_volume(tmp_path, volume)

            self._apply_fade_edges(tmp_path)
            shutil.move(str(tmp_path), str(cache_path))
        except Exception:
            if cache_path.exists():
                cache_path.unlink()
            raise
        finally:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink()

    @staticmethod
    def _apply_volume(wav_path: Path, volume: int) -> None:
        """Scale audio amplitude using the requested volume (0-200)."""
        volume = max(0, min(volume, 200))
        factor = volume / 100.0

        if abs(factor - 1.0) < 0.01:
            return

        with wave.open(str(wav_path), "rb") as wav_file:
            params = wav_file.getparams()
            frames = wav_file.readframes(params.nframes)

        scaled_frames = audioop.mul(frames, params.sampwidth, factor)
        with wave.open(str(wav_path), "wb") as wav_file:
            wav_file.setparams(params)
            wav_file.writeframes(scaled_frames)

    @staticmethod
    def _apply_fade_edges(wav_path: Path, fade_ms: float = 6.0) -> None:
        """Apply a short fade-in/fade-out to reduce pop noise on playback."""
        if fade_ms <= 0:
            return

        with wave.open(str(wav_path), "rb") as wav_file:
            params = wav_file.getparams()
            frames = wav_file.readframes(params.nframes)

        sampwidth = params.sampwidth
        nchannels = params.nchannels
        framerate = params.framerate

        if sampwidth != 2 or params.nframes == 0:
            # Only handle 16-bit PCM; skip otherwise.
            return

        fade_samples = max(1, int(framerate * fade_ms / 1000.0))
        total_samples = params.nframes

        if fade_samples * 2 >= total_samples:
            fade_samples = max(1, total_samples // 4)

        samples = array("h")
        samples.frombytes(frames)

        def _apply(section_start: int, section_length: int, reverse: bool = False) -> None:
            for i in range(section_length):
                factor = (i + 1) / section_length if not reverse else (section_length - i) / section_length
                for ch in range(nchannels):
                    idx = (section_start + i) * nchannels + ch
                    value = samples[idx]
                    samples[idx] = int(max(-32768, min(32767, value * factor)))

        _apply(0, fade_samples, reverse=False)
        _apply(total_samples - fade_samples, fade_samples, reverse=True)

        with wave.open(str(wav_path), "wb") as wav_file:
            wav_file.setparams(params)
            wav_file.writeframes(samples.tobytes())


class NullTTS:
    """Fallback TTS that logs messages when Piper is not available."""

    def speak(
        self,
        message: str,
        volume: Optional[int] = None,
        cache_path: Optional[Path] = None,
        playback: bool = True,
    ) -> None:  # pragma: no cover
        LOGGER.warning("TTS unavailable. Message skipped: %s", message)


# ---------------------------------------------------------------------------
# Scenario definitions (Vietnamese first)
# ---------------------------------------------------------------------------


def _format_int(value: Union[int, float, str], fallback: str = "0") -> str:
    try:
        return str(int(round(float(value))))
    except (TypeError, ValueError):
        return fallback


def _format_decimal(value: Union[int, float, str], decimals: int = 1, fallback: str = "0") -> str:
    try:
        number = float(value)
        return f"{number:.{decimals}f}"
    except (TypeError, ValueError):
        return fallback


class ScenarioID(str, Enum):
    """Identifiers for speech scenarios."""

    # System
    SYSTEM_START = "system_start"
    SYSTEM_SHUTDOWN = "system_shutdown"
    NAVIGATE_DASHBOARD = "navigate_dashboard"
    SETTINGS_UPDATED = "settings_updated"
    
    # Network & Sync
    NETWORK_CONNECTED = "network_connected"
    NETWORK_DISCONNECTED = "network_disconnected"
    MQTT_PUBLISH_OK = "mqtt_publish_ok"
    MQTT_PUBLISH_FAIL = "mqtt_publish_fail"
    STORE_FORWARD_ACTIVE = "store_forward_active"
    
    # Heart Rate & SpO2
    HR_PROMPT_FINGER = "hr_prompt_finger"
    HR_NO_FINGER = "hr_no_finger"
    HR_MEASURING = "hr_measuring"
    HR_RESULT = "hr_result"
    HR_SIGNAL_WEAK = "hr_signal_weak"
    
    # Continuous Monitoring
    CONTINUOUS_MONITOR_START = "continuous_monitor_start"
    
    # Temperature
    TEMP_PREP = "temp_prep"
    TEMP_MEASURING = "temp_measuring"
    TEMP_NORMAL = "temp_normal"
    TEMP_HIGH_ALERT = "temp_high_alert"
    TEMP_RESULT_CRITICAL_LOW = "temp_result_critical_low"
    TEMP_RESULT_LOW = "temp_result_low"
    TEMP_RESULT_NORMAL = "temp_result_normal"
    TEMP_RESULT_FEVER = "temp_result_fever"
    TEMP_RESULT_HIGH_FEVER = "temp_result_high_fever"
    TEMP_RESULT_CRITICAL_HIGH = "temp_result_critical_high"
    
    # Blood Pressure
    BP_INFLATE = "bp_inflate"
    BP_OVERPRESSURE = "bp_overpressure"
    BP_DEFLATE = "bp_deflate"
    BP_RESULT = "bp_result"
    SAFETY_EMERGENCY_RELEASE = "safety_emergency_release"
    
    # Errors & Maintenance
    SENSOR_FAILURE = "sensor_failure"
    PUMP_VALVE_FAILURE = "pump_valve_failure"
    
    # Navigation & Interaction
    NAVIGATION_TAP_HEART = "navigation_tap_heart"
    HISTORY_OPEN = "history_open"
    ANOMALY_DETECTED = "anomaly_detected"
    CHATBOT_PROMPT = "chatbot_prompt"
    REMINDER_DAILY = "reminder_daily"
    
    # ============================================================
    # NEW SCENARIOS - Emergency & Safety (5 scenarios)
    # ============================================================
    EMERGENCY_BUTTON_PRESSED = "emergency_button_pressed"
    EMERGENCY_CALL_INITIATED = "emergency_call_initiated"
    EMERGENCY_CONTACT_NOTIFIED = "emergency_contact_notified"
    CRITICAL_VITALS_ALERT = "critical_vitals_alert"
    EMERGENCY_CANCELLED = "emergency_cancelled"
    
    # ============================================================
    # NEW SCENARIOS - Vital Signs Alerts (8 scenarios)
    # ============================================================
    HR_TOO_LOW = "hr_too_low"
    HR_TOO_HIGH = "hr_too_high"
    SPO2_LOW = "spo2_low"
    SPO2_CRITICAL = "spo2_critical"
    BP_HYPERTENSION = "bp_hypertension"
    BP_HYPOTENSION = "bp_hypotension"
    BP_HYPERTENSIVE_CRISIS = "bp_hypertensive_crisis"
    IRREGULAR_HEARTBEAT = "irregular_heartbeat"
    
    # ============================================================
    # NEW SCENARIOS - User Guidance (6 scenarios)
    # ============================================================
    FIRST_TIME_SETUP = "first_time_setup"
    SENSOR_PLACEMENT_GUIDE = "sensor_placement_guide"
    MEASUREMENT_TIPS = "measurement_tips"
    DEVICE_READY = "device_ready"
    CALIBRATION_NEEDED = "calibration_needed"
    MAINTENANCE_REMINDER = "maintenance_reminder"
    
    # ============================================================
    # NEW SCENARIOS - Results & Reports (3 scenarios)
    # ============================================================
    MEASUREMENT_COMPLETE = "measurement_complete"
    DAILY_SUMMARY = "daily_summary"
    TREND_IMPROVING = "trend_improving"
    
    # ============================================================
    # NEW SCENARIOS - Device Connection (1 scenario)
    # ============================================================
    QR_PAIRING_SUCCESS = "qr_pairing_success"


@dataclass(frozen=True)
class ScenarioTemplate:
    """Speech template that supports Vietnamese (and optional English)."""

    template_vi: str
    template_en: Optional[str] = None
    required_fields: Tuple[str, ...] = ()
    formatters: Dict[str, Callable[[Union[str, int, float]], str]] = field(default_factory=dict)
    cooldown_seconds: float = 0.0

    def render(self, locale: str, **kwargs: Union[str, int, float]) -> Optional[str]:
        """Render message for the requested locale."""
        template = None
        if locale == "vi":
            template = self.template_vi
        elif locale == "en":
            template = self.template_en

        if not template:
            return None

        for field in self.required_fields:
            if field not in kwargs or kwargs[field] is None:
                LOGGER.warning("Scenario missing required field '%s'", field)
                return None

        formatted_kwargs = {}
        for key, value in kwargs.items():
            formatter = self.formatters.get(key)
            if formatter:
                formatted_kwargs[key] = formatter(value)
            else:
                formatted_kwargs[key] = str(value)

        try:
            return template.format(**formatted_kwargs)
        except KeyError as exc:
            LOGGER.error("Scenario formatting missing key: %s", exc)
        except ValueError as exc:
            LOGGER.error("Scenario formatting error: %s", exc)
        return None


SCENARIO_LIBRARY: Dict[ScenarioID, ScenarioTemplate] = {
    ScenarioID.SYSTEM_START: ScenarioTemplate(
        template_vi="Hệ thống IoT Health đã khởi động. Vui lòng đợi cảm biến ổn định.",
        template_en="IoT Health system started. Please allow the sensors to stabilize.",
        cooldown_seconds=5.0,
    ),
    ScenarioID.NAVIGATE_DASHBOARD: ScenarioTemplate(
        template_vi="Đang chuyển sang màn hình chính.",
        template_en="Switching to the main dashboard.",
        cooldown_seconds=2.0,
    ),
    ScenarioID.NETWORK_CONNECTED: ScenarioTemplate(
        template_vi="Đã kết nối mạng thành công.",
        template_en="Network connection established.",
        cooldown_seconds=10.0,
    ),
    ScenarioID.NETWORK_DISCONNECTED: ScenarioTemplate(
        template_vi="Mất kết nối mạng, hệ thống sẽ thử lại trong giây lát.",
        template_en="Network connection lost, the system will retry shortly.",
        cooldown_seconds=10.0,
    ),
    ScenarioID.HR_PROMPT_FINGER: ScenarioTemplate(
        template_vi="Vui lòng đặt ngón tay lên cảm biến nhịp tim.",
        template_en="Please place your finger on the heart-rate sensor.",
        cooldown_seconds=5.0,
    ),
    ScenarioID.HR_NO_FINGER: ScenarioTemplate(
        template_vi="Không phát hiện ngón tay, xin thử lại.",
        template_en="No finger detected, please try again.",
        cooldown_seconds=5.0,
    ),
    ScenarioID.HR_MEASURING: ScenarioTemplate(
        template_vi="Đang đo nhịp tim và SpO₂, giữ nguyên tay trong mười lăm giây.",
        template_en="Measuring heart rate and SpO₂, keep still for fifteen seconds.",
        cooldown_seconds=6.0,
    ),
    ScenarioID.HR_RESULT: ScenarioTemplate(
        template_vi="Nhịp tim {bpm} nhịp mỗi phút, SpO₂ {spo2} phần trăm.",
        template_en="Heart rate {bpm} beats per minute, SpO₂ {spo2} percent.",
        required_fields=("bpm", "spo2"),
        formatters={
            "bpm": lambda value: _format_int(value, "0"),
            "spo2": lambda value: _format_int(value, "0"),
        },
        cooldown_seconds=3.0,
    ),
    ScenarioID.HR_SIGNAL_WEAK: ScenarioTemplate(
        template_vi="Tín hiệu yếu, vui lòng giữ ngón tay áp sát cảm biến.",
        template_en="Weak signal detected, please press your finger firmly on the sensor.",
        cooldown_seconds=8.0,
    ),
    ScenarioID.CONTINUOUS_MONITOR_START: ScenarioTemplate(
        template_vi="Ngồi hoặc nằm yên để tiến hành theo dõi.",
        template_en="Sit or lie still to start continuous monitoring.",
        cooldown_seconds=10.0,
    ),
    ScenarioID.TEMP_PREP: ScenarioTemplate(
        template_vi="Đưa cảm biến hồng ngoại lại gần trán, cách khoảng ba đến năm centimet.",
        template_en="Hold the infrared sensor near the forehead, about three to five centimeters away.",
        cooldown_seconds=6.0,
    ),
    ScenarioID.TEMP_MEASURING: ScenarioTemplate(
        template_vi="Đang đo nhiệt độ cơ thể, vui lòng đứng yên.",
        template_en="Measuring body temperature, please remain still.",
        cooldown_seconds=6.0,
    ),
    ScenarioID.TEMP_NORMAL: ScenarioTemplate(
        template_vi="Nhiệt độ {temp} độ C, trong giới hạn bình thường.",
        template_en="Temperature {temp} degrees Celsius, within normal range.",
        required_fields=("temp",),
        formatters={"temp": lambda value: _format_decimal(value, decimals=1, fallback="0")},
        cooldown_seconds=4.0,
    ),
    ScenarioID.TEMP_HIGH_ALERT: ScenarioTemplate(
        template_vi="Nhiệt độ cao bất thường, hãy kiểm tra lại hoặc liên hệ nhân viên y tế.",
        template_en="Abnormally high temperature detected, please double-check or contact medical staff.",
        cooldown_seconds=15.0,
    ),
    ScenarioID.TEMP_RESULT_CRITICAL_LOW: ScenarioTemplate(
        template_vi="Nhiệt độ rất thấp, khoảng {temp} độ C. Cần làm ấm cơ thể ngay.",
        template_en="Temperature is critically low at about {temp} degrees Celsius. Warm the body immediately.",
        required_fields=("temp",),
        formatters={"temp": lambda value: _format_decimal(value, decimals=1, fallback="0")},
        cooldown_seconds=4.0,
    ),
    ScenarioID.TEMP_RESULT_LOW: ScenarioTemplate(
        template_vi="Nhiệt độ hơi thấp, khoảng {temp} độ C.",
        template_en="Body temperature slightly low at {temp} degrees Celsius.",
        required_fields=("temp",),
        formatters={"temp": lambda value: _format_decimal(value, decimals=1, fallback="0")},
        cooldown_seconds=4.0,
    ),
    ScenarioID.TEMP_RESULT_NORMAL: ScenarioTemplate(
        template_vi="Nhiệt độ {temp} độ C, trong giới hạn bình thường.",
        template_en="Temperature {temp} degrees Celsius, within normal range.",
        required_fields=("temp",),
        formatters={"temp": lambda value: _format_decimal(value, decimals=1, fallback="0")},
        cooldown_seconds=4.0,
    ),
    ScenarioID.TEMP_RESULT_FEVER: ScenarioTemplate(
        template_vi="Nhiệt độ hơi cao, khoảng {temp} độ C. Theo dõi thêm các triệu chứng.",
        template_en="Mild fever detected at about {temp} degrees Celsius. Keep monitoring symptoms.",
        required_fields=("temp",),
        formatters={"temp": lambda value: _format_decimal(value, decimals=1, fallback="0")},
        cooldown_seconds=6.0,
    ),
    ScenarioID.TEMP_RESULT_HIGH_FEVER: ScenarioTemplate(
        template_vi="Nhiệt độ cao {temp} độ C. Cần hạ sốt và liên hệ nhân viên y tế nếu kéo dài.",
        template_en="High fever at {temp} degrees Celsius. Take antipyretic measures and contact medical staff if it persists.",
        required_fields=("temp",),
        formatters={"temp": lambda value: _format_decimal(value, decimals=1, fallback="0")},
        cooldown_seconds=6.0,
    ),
    ScenarioID.TEMP_RESULT_CRITICAL_HIGH: ScenarioTemplate(
        template_vi="Nhiệt độ rất cao, khoảng {temp} độ C. Đây là tình trạng nguy hiểm, cần hỗ trợ y tế khẩn." ,
        template_en="Temperature is dangerously high at about {temp} degrees Celsius. Seek immediate medical assistance.",
        required_fields=("temp",),
        formatters={"temp": lambda value: _format_decimal(value, decimals=1, fallback="0")},
        cooldown_seconds=6.0,
    ),
    ScenarioID.BP_INFLATE: ScenarioTemplate(
        template_vi="Bắt đầu bơm cuff, bạn sẽ cảm thấy hơi căng.",
        template_en="Inflating the cuff, you may feel slight pressure.",
        cooldown_seconds=10.0,
    ),
    ScenarioID.BP_OVERPRESSURE: ScenarioTemplate(
        template_vi="Cảnh báo áp suất nguy hiểm, cuff sẽ xả ngay lập tức.",
        template_en="Dangerous cuff pressure detected, releasing immediately.",
        cooldown_seconds=5.0,
    ),
    ScenarioID.BP_DEFLATE: ScenarioTemplate(
        template_vi="Đang xả cuff, vui lòng giữ tay không cử động.",
        template_en="Deflating the cuff, please keep your arm still.",
        cooldown_seconds=8.0,
    ),
    ScenarioID.BP_RESULT: ScenarioTemplate(
        template_vi="Huyết áp {sys} trên {dia} mi li mét thủy ngân, MAP {map}.",
        template_en="Blood pressure {sys} over {dia} millimeters of mercury, MAP {map}.",
        required_fields=("sys", "dia", "map"),
        formatters={
            "sys": lambda value: _format_int(value, "0"),
            "dia": lambda value: _format_int(value, "0"),
            "map": lambda value: _format_int(value, "0"),
        },
        cooldown_seconds=5.0,
    ),
    ScenarioID.SAFETY_EMERGENCY_RELEASE: ScenarioTemplate(
        template_vi="Áp suất vượt giới hạn, hệ thống đang xả để đảm bảo an toàn.",
        template_en="Pressure exceeded the limit; releasing air for safety.",
        cooldown_seconds=5.0,
    ),
    ScenarioID.SENSOR_FAILURE: ScenarioTemplate(
        template_vi="Không thể đọc dữ liệu từ cảm biến {sensor}, vui lòng kiểm tra kết nối.",
        template_en="Unable to read data from the {sensor} sensor, please check the connection.",
        required_fields=("sensor",),
        cooldown_seconds=15.0,
    ),
    ScenarioID.PUMP_VALVE_FAILURE: ScenarioTemplate(
        template_vi="Lỗi điều khiển bơm hoặc van, yêu cầu bảo trì.",
        template_en="Pump or valve control failure detected, maintenance required.",
        cooldown_seconds=20.0,
    ),
    ScenarioID.MQTT_PUBLISH_OK: ScenarioTemplate(
        template_vi="Đã gửi dữ liệu lên máy chủ.",
        template_en="Data published to the server.",
        cooldown_seconds=15.0,
    ),
    ScenarioID.MQTT_PUBLISH_FAIL: ScenarioTemplate(
        template_vi="Không gửi được dữ liệu, hệ thống sẽ thử lại.",
        template_en="Failed to publish data, the system will retry.",
        cooldown_seconds=15.0,
    ),
    ScenarioID.STORE_FORWARD_ACTIVE: ScenarioTemplate(
        template_vi="Chế độ offline đang hoạt động, dữ liệu sẽ được gửi khi có mạng.",
        template_en="Offline mode active; data will sync once connectivity returns.",
        cooldown_seconds=30.0,
    ),
    ScenarioID.NAVIGATION_TAP_HEART: ScenarioTemplate(
        template_vi="Chạm vào khối nhịp tim để xem chi tiết.",
        template_en="Tap the heart-rate tile for detailed view.",
        cooldown_seconds=10.0,
    ),
    ScenarioID.SETTINGS_UPDATED: ScenarioTemplate(
        template_vi="Cập nhật cấu hình thành công.",
        template_en="Configuration updated successfully.",
        cooldown_seconds=10.0,
    ),
    ScenarioID.HISTORY_OPEN: ScenarioTemplate(
        template_vi="Mở lịch sử đo, chạm vào bản ghi để xem chi tiết.",
        template_en="Opening measurement history; tap a record to view details.",
        cooldown_seconds=10.0,
    ),
    ScenarioID.ANOMALY_DETECTED: ScenarioTemplate(
        template_vi="Phát hiện dấu hiệu bất thường trong chuỗi số đo, hãy xem lại trang cảnh báo.",
        template_en="An anomaly was detected in the vitals trend, please review the alerts page.",
        cooldown_seconds=15.0,
    ),
    ScenarioID.CHATBOT_PROMPT: ScenarioTemplate(
        template_vi="Bạn muốn biết thông tin nào? Nói 'Xin tư vấn' để kết nối chatbot.",
        template_en="What information would you like? Say 'Assistant help' to connect with the chatbot.",
        cooldown_seconds=20.0,
    ),
    ScenarioID.REMINDER_DAILY: ScenarioTemplate(
        template_vi="Đến giờ đo sức khỏe định kỳ, hãy chuẩn bị các cảm biến.",
        template_en="It's time for your scheduled health check; please prepare the sensors.",
        cooldown_seconds=60.0,
    ),
    ScenarioID.SYSTEM_SHUTDOWN: ScenarioTemplate(
        template_vi="Đang tắt hệ thống IoT Health, hẹn gặp lại.",
        template_en="Shutting down the IoT Health system, see you next time.",
        cooldown_seconds=5.0,
    ),
    
    # ============================================================
    # NEW SCENARIOS - Emergency & Safety
    # ============================================================
    ScenarioID.EMERGENCY_BUTTON_PRESSED: ScenarioTemplate(
        template_vi="Đã kích hoạt cảnh báo khẩn cấp. Đang gửi thông báo đến người thân và trung tâm y tế.",
        template_en="Emergency alert activated. Notifying family members and medical center.",
        cooldown_seconds=3.0,
    ),
    ScenarioID.EMERGENCY_CALL_INITIATED: ScenarioTemplate(
        template_vi="Đang kết nối với số khẩn cấp. Vui lòng giữ máy.",
        template_en="Connecting to emergency services. Please stay on the line.",
        cooldown_seconds=5.0,
    ),
    ScenarioID.EMERGENCY_CONTACT_NOTIFIED: ScenarioTemplate(
        template_vi="Đã gửi tin nhắn khẩn cấp đến {contact_name}.",
        template_en="Emergency message sent to {contact_name}.",
        required_fields=("contact_name",),
        cooldown_seconds=10.0,
    ),
    ScenarioID.CRITICAL_VITALS_ALERT: ScenarioTemplate(
        template_vi="Cảnh báo: Chỉ số sức khỏe ở mức nguy hiểm. Vui lòng liên hệ y tế ngay.",
        template_en="Warning: Critical health vitals detected. Contact medical assistance immediately.",
        cooldown_seconds=5.0,
    ),
    ScenarioID.EMERGENCY_CANCELLED: ScenarioTemplate(
        template_vi="Đã hủy cảnh báo khẩn cấp.",
        template_en="Emergency alert cancelled.",
        cooldown_seconds=5.0,
    ),
    
    # ============================================================
    # NEW SCENARIOS - Vital Signs Alerts
    # ============================================================
    ScenarioID.HR_TOO_LOW: ScenarioTemplate(
        template_vi="Cảnh báo: Nhịp tim quá thấp, {bpm} nhịp mỗi phút. Hãy nghỉ ngơi và theo dõi.",
        template_en="Warning: Heart rate too low at {bpm} beats per minute. Rest and monitor closely.",
        required_fields=("bpm",),
        formatters={"bpm": lambda value: _format_int(value, "0")},
        cooldown_seconds=10.0,
    ),
    ScenarioID.HR_TOO_HIGH: ScenarioTemplate(
        template_vi="Cảnh báo: Nhịp tim quá cao, {bpm} nhịp mỗi phút. Hãy ngồi xuống và thở sâu.",
        template_en="Warning: Heart rate too high at {bpm} beats per minute. Sit down and breathe deeply.",
        required_fields=("bpm",),
        formatters={"bpm": lambda value: _format_int(value, "0")},
        cooldown_seconds=10.0,
    ),
    ScenarioID.SPO2_LOW: ScenarioTemplate(
        template_vi="Cảnh báo: Nồng độ oxy trong máu thấp, {spo2} phần trăm. Hãy thở sâu và kiểm tra lại.",
        template_en="Warning: Blood oxygen level low at {spo2} percent. Breathe deeply and recheck.",
        required_fields=("spo2",),
        formatters={"spo2": lambda value: _format_int(value, "0")},
        cooldown_seconds=10.0,
    ),
    ScenarioID.SPO2_CRITICAL: ScenarioTemplate(
        template_vi="Nguy hiểm: Oxy máu rất thấp, {spo2} phần trăm. Cần hỗ trợ y tế khẩn cấp.",
        template_en="Critical: Blood oxygen critically low at {spo2} percent. Emergency medical assistance required.",
        required_fields=("spo2",),
        formatters={"spo2": lambda value: _format_int(value, "0")},
        cooldown_seconds=5.0,
    ),
    ScenarioID.BP_HYPERTENSION: ScenarioTemplate(
        template_vi="Cảnh báo: Huyết áp cao, {sys} trên {dia}. Hãy nghỉ ngơi và uống thuốc nếu có chỉ định.",
        template_en="Warning: High blood pressure at {sys} over {dia}. Rest and take medication if prescribed.",
        required_fields=("sys", "dia"),
        formatters={
            "sys": lambda value: _format_int(value, "0"),
            "dia": lambda value: _format_int(value, "0"),
        },
        cooldown_seconds=10.0,
    ),
    ScenarioID.BP_HYPOTENSION: ScenarioTemplate(
        template_vi="Cảnh báo: Huyết áp thấp, {sys} trên {dia}. Hãy nằm xuống và nâng chân lên.",
        template_en="Warning: Low blood pressure at {sys} over {dia}. Lie down and elevate your legs.",
        required_fields=("sys", "dia"),
        formatters={
            "sys": lambda value: _format_int(value, "0"),
            "dia": lambda value: _format_int(value, "0"),
        },
        cooldown_seconds=10.0,
    ),
    ScenarioID.BP_HYPERTENSIVE_CRISIS: ScenarioTemplate(
        template_vi="Nguy hiểm: Huyết áp rất cao, {sys} trên {dia}. Cần đến bệnh viện ngay.",
        template_en="Critical: Blood pressure dangerously high at {sys} over {dia}. Go to hospital immediately.",
        required_fields=("sys", "dia"),
        formatters={
            "sys": lambda value: _format_int(value, "0"),
            "dia": lambda value: _format_int(value, "0"),
        },
        cooldown_seconds=5.0,
    ),
    ScenarioID.IRREGULAR_HEARTBEAT: ScenarioTemplate(
        template_vi="Phát hiện nhịp tim không đều. Hãy đo lại và liên hệ bác sĩ nếu tình trạng kéo dài.",
        template_en="Irregular heartbeat detected. Retest and contact your doctor if it persists.",
        cooldown_seconds=15.0,
    ),
    
    # ============================================================
    # NEW SCENARIOS - User Guidance
    # ============================================================
    ScenarioID.FIRST_TIME_SETUP: ScenarioTemplate(
        template_vi="Chào mừng đến với IoT Health. Hãy làm theo hướng dẫn trên màn hình để thiết lập.",
        template_en="Welcome to IoT Health. Please follow the on-screen instructions to set up.",
        cooldown_seconds=0.0,
    ),
    ScenarioID.SENSOR_PLACEMENT_GUIDE: ScenarioTemplate(
        template_vi="Để đo chính xác, hãy đặt cảm biến {sensor} đúng vị trí như hình minh họa.",
        template_en="For accurate readings, place the {sensor} sensor in the correct position as illustrated.",
        required_fields=("sensor",),
        cooldown_seconds=10.0,
    ),
    ScenarioID.MEASUREMENT_TIPS: ScenarioTemplate(
        template_vi="Để kết quả chính xác, hãy ngồi yên, thư giãn và không nói chuyện trong khi đo.",
        template_en="For accurate results, sit still, relax, and avoid talking during measurement.",
        cooldown_seconds=20.0,
    ),
    ScenarioID.DEVICE_READY: ScenarioTemplate(
        template_vi="Thiết bị đã sẵn sàng. Chạm vào nút đo để bắt đầu.",
        template_en="Device ready. Tap the measure button to begin.",
        cooldown_seconds=5.0,
    ),
    ScenarioID.CALIBRATION_NEEDED: ScenarioTemplate(
        template_vi="Cảm biến cần hiệu chuẩn. Vui lòng liên hệ nhân viên kỹ thuật.",
        template_en="Sensor calibration required. Please contact technical support.",
        cooldown_seconds=30.0,
    ),
    ScenarioID.MAINTENANCE_REMINDER: ScenarioTemplate(
        template_vi="Đã đến lịch bảo trì định kỳ. Vui lòng vệ sinh cảm biến và kiểm tra kết nối.",
        template_en="Scheduled maintenance due. Please clean sensors and check connections.",
        cooldown_seconds=60.0,
    ),
    
    # ============================================================
    # NEW SCENARIOS - Results & Reports
    # ============================================================
    ScenarioID.MEASUREMENT_COMPLETE: ScenarioTemplate(
        template_vi="Đo xong. Kết quả đã được lưu vào lịch sử.",
        template_en="Measurement complete. Results saved to history.",
        cooldown_seconds=3.0,
    ),
    ScenarioID.DAILY_SUMMARY: ScenarioTemplate(
        template_vi="Hôm nay bạn đã đo {count} lần. Các chỉ số trung bình trong giới hạn bình thường.",
        template_en="You measured {count} times today. Average vitals are within normal range.",
        required_fields=("count",),
        formatters={"count": lambda value: _format_int(value, "0")},
        cooldown_seconds=0.0,
    ),
    ScenarioID.TREND_IMPROVING: ScenarioTemplate(
        template_vi="Chúc mừng! Các chỉ số sức khỏe của bạn đang cải thiện trong tuần qua.",
        template_en="Congratulations! Your health vitals are improving over the past week.",
        cooldown_seconds=0.0,
    ),
    
    # ============================================================
    # NEW SCENARIOS - Device Connection
    # ============================================================
    ScenarioID.QR_PAIRING_SUCCESS: ScenarioTemplate(
        template_vi="Đã ghép nối với ứng dụng di động thành công.",
        template_en="Successfully paired with mobile application.",
        cooldown_seconds=5.0,
    ),
}


# ---------------------------------------------------------------------------
# TTS Manager façade
# ---------------------------------------------------------------------------


@dataclass
class _SpeechJob:
    scenario_id: ScenarioID
    message: str
    volume: int
    playback: bool = True


class TTSManager:
    """High-level manager to produce speech for defined scenarios."""

    def __init__(
        self,
        engine: Union[PiperTTS, NullTTS],
        default_locale: str = "vi",
        default_volume: int = 100,
        cache_dir: Optional[Path] = None,
        strict_assets: bool = False,
    ) -> None:
        self.engine = engine
        self.default_locale = default_locale
        self.default_volume = default_volume
        self._last_spoken: Dict[ScenarioID, float] = {}
        self._queue: PriorityQueue[Tuple[int, int, Optional[_SpeechJob]]] = PriorityQueue()
        self._counter = count()
        self._stop_event = Event()
        self._shutdown_called = False
        self._cache_dir: Optional[Path] = None
        self._cache_index: Dict[str, Path] = {}
        self._owns_cache_dir = False
        self._strict_assets = strict_assets

        if isinstance(self.engine, PiperTTS):
            if cache_dir:
                self._cache_dir = Path(cache_dir).expanduser()
                self._cache_dir.mkdir(parents=True, exist_ok=True)
                self._owns_cache_dir = False
            else:
                self._cache_dir = Path(tempfile.mkdtemp(prefix="tts_cache_"))
                self._owns_cache_dir = True

        self._worker = Thread(target=self._worker_loop, name="tts-worker", daemon=True)
        self._worker.start()
        atexit.register(self.shutdown)

    @classmethod
    def create_default(
        cls,
        model_path: Path = DEFAULT_PIPER_MODEL,
        config_path: Path = DEFAULT_PIPER_CONFIG,
        speaker: Optional[str] = None,
        default_locale: str = "vi",
        default_volume: int = 100,
        cache_dir: Optional[Path] = None,
        strict_assets: bool = False,
    ) -> "TTSManager":
        try:
            engine = PiperTTS(model_path=model_path, config_path=config_path, speaker=speaker)
        except FileNotFoundError:
            LOGGER.warning("Falling back to NullTTS (missing Piper model or binary).")
            engine = NullTTS()
        return cls(
            engine=engine,
            default_locale=default_locale,
            default_volume=default_volume,
            cache_dir=cache_dir,
            strict_assets=strict_assets,
        )

    def speak_scenario(
        self,
        scenario: Union[ScenarioID, str],
        *,
        locale: Optional[str] = None,
        volume: Optional[int] = None,
        force: bool = False,
        override_message: Optional[str] = None,
        **kwargs: Union[str, int, float],
    ) -> bool:
        """Render and speak the requested scenario."""

        scenario_id = self._normalize_scenario(scenario)
        if scenario_id is None:
            return False

        template = SCENARIO_LIBRARY.get(scenario_id)
        if not template:
            LOGGER.error("Scenario '%s' not defined", scenario_id)
            return False

        if not force and self._is_in_cooldown(scenario_id, template.cooldown_seconds):
            LOGGER.debug("Scenario '%s' suppressed by cooldown", scenario_id.value)
            return False

        message = override_message
        if not message:
            chosen_locale = locale or self.default_locale
            message = template.render(chosen_locale, **kwargs)
            if not message:
                LOGGER.debug(
                    "Scenario '%s' has no renderable message for locale '%s'",
                    scenario_id.value,
                    chosen_locale,
                )
                return False

        job_volume = volume or self.default_volume
        try:
            self._enqueue_job(_SpeechJob(scenario_id, message, job_volume))
            return True
        except Exception as exc:  # pragma: no cover
            LOGGER.error("Failed to enqueue scenario '%s': %s", scenario_id.value, exc)
            return False

    @staticmethod
    def _normalize_scenario(scenario: Union[ScenarioID, str]) -> Optional[ScenarioID]:
        if isinstance(scenario, ScenarioID):
            return scenario
        if isinstance(scenario, str):
            try:
                return ScenarioID(scenario)
            except ValueError:
                LOGGER.error("Unknown scenario key: %s", scenario)
        return None

    def _enqueue_job(self, job: Optional[_SpeechJob], priority: int = 0) -> None:
        self._queue.put((priority, next(self._counter), job))

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                priority, _, job = self._queue.get(timeout=0.5)
            except Empty:
                continue

            if job is None:
                self._queue.task_done()
                break

            try:
                self._process_job(job)
                if job.playback:
                    self._last_spoken[job.scenario_id] = time.monotonic()
            except Exception as exc:  # pragma: no cover
                LOGGER.error("Failed to play scenario '%s': %s", job.scenario_id.value, exc)
            finally:
                self._queue.task_done()

    def _process_job(self, job: _SpeechJob) -> None:
        cache_path: Optional[Path] = None
        template = SCENARIO_LIBRARY.get(job.scenario_id)
        can_use_cache = self._cache_dir is not None and isinstance(self.engine, PiperTTS)

        if can_use_cache:
            cache_candidate = self._get_cache_path(job.message, job.volume)
            if cache_candidate.exists():
                cache_path = cache_candidate
            else:
                if self._strict_assets and self._is_static_scenario(job.scenario_id):
                    LOGGER.warning(
                        "Missing pre-generated audio for scenario '%s' at %s",
                        job.scenario_id.value,
                        cache_candidate,
                    )
                    return
                cache_path = cache_candidate

        if job.playback:
            self.engine.speak(
                job.message,
                volume=job.volume,
                cache_path=cache_path,
                playback=True,
            )
        else:
            if isinstance(self.engine, PiperTTS) and cache_path is not None:
                if cache_path.exists():
                    LOGGER.debug("Asset already present for %s", job.scenario_id.value)
                    return
                self.engine.ensure_cached(job.message, job.volume, cache_path)
            else:
                LOGGER.debug("Skipping preload for scenario '%s'", job.scenario_id.value)

    def _get_cache_path(self, message: str, volume: int) -> Path:
        assert self._cache_dir is not None
        key = f"{volume}:{message}"
        cached_path = self._cache_index.get(key)

        if cached_path and cached_path.exists():
            return cached_path

        path = self._cache_dir / f"{hashlib.sha1(key.encode('utf-8')).hexdigest()}.wav"
        self._cache_index[key] = path
        return path

    def _is_static_scenario(self, scenario: ScenarioID) -> bool:
        template = SCENARIO_LIBRARY.get(scenario)
        if not template:
            return False
        return not template.required_fields

    def _is_in_cooldown(self, scenario: ScenarioID, cooldown_seconds: float) -> bool:
        if cooldown_seconds <= 0:
            return False
        last_time = self._last_spoken.get(scenario)
        if last_time is None:
            return False
        return (time.monotonic() - last_time) < cooldown_seconds

    def preload_scenarios(
        self,
        scenarios: Union[Tuple[ScenarioID, ...], Iterable[ScenarioID]],
        *,
        locale: Optional[str] = None,
        volume: Optional[int] = None,
    ) -> None:
        if not isinstance(self.engine, PiperTTS):
            return

        chosen_locale = locale or self.default_locale
        job_volume = volume or self.default_volume

        for scenario in scenarios:
            template = SCENARIO_LIBRARY.get(scenario)
            if not template or template.required_fields:
                continue

            message = template.render(chosen_locale)
            if not message:
                continue

            try:
                self._enqueue_job(_SpeechJob(scenario, message, job_volume, playback=False), priority=10)
            except Exception as exc:  # pragma: no cover
                LOGGER.debug("Unable to queue preload for %s: %s", scenario.value, exc)

    def shutdown(self) -> None:
        if self._shutdown_called:
            return

        self._shutdown_called = True
        try:
            atexit.unregister(self.shutdown)
        except Exception:
            pass
        self._stop_event.set()

        self._enqueue_job(None, priority=-100)

        if self._worker.is_alive():
            self._worker.join(timeout=2.0)

        if self._cache_dir and self._owns_cache_dir and self._cache_dir.exists():
            shutil.rmtree(self._cache_dir, ignore_errors=True)


__all__ = [
    "PiperTTS",
    "NullTTS",
    "TTSManager",
    "ScenarioID",
    "SCENARIO_LIBRARY",
    "ScenarioTemplate",
]
