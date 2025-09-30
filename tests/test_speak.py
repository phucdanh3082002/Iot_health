"""Kiểm thử phát âm thanh qua bộ khuếch đại MAX98357A.

Chương trình ưu tiên phát một tệp WAV có sẵn trong thư mục `asseet/audio/` để
kiểm tra đường I²S. Khi không tìm thấy tệp, ứng dụng sẽ sinh một tone 440 Hz và
phát thông qua `aplay`. Tuỳ chọn, bạn có thể dùng `espeak-ng` đọc câu thông báo
tiếng Việt.

Sơ đồ nối dây (I²S0 mặc định):

		MAX98357A → Raspberry Pi
		* VIN  → Pin 2/4 (5 V)
		* GND  → Pin 6 (GND)
		* BCLK → GPIO18 (Pin 12)
		* LRCLK → GPIO19 (Pin 35)
		* DIN  → GPIO21 (Pin 40)
		* GAIN, SD → để trống (tuỳ chọn cấu hình gain)

Yêu cầu phần mềm:
* Raspberry Pi đã bật I²S (`dtparam=audio=off`, `dtoverlay=i2s-mmap` hoặc tương
	tự).
* Gói `alsa-utils` (cung cấp lệnh `aplay`).
* Tuỳ chọn: `espeak-ng` để kiểm tra TTS.
"""

from __future__ import annotations

import argparse
import logging
import math
import struct
import subprocess
import sys
from pathlib import Path
from typing import Optional


LOGGER = logging.getLogger(__name__)


def _project_root() -> Path:
	return Path(__file__).resolve().parent.parent


ASSET_DIR = _project_root() / "asseet"
AUDIO_DIR = ASSET_DIR / "audio"
DEFAULT_WAV = AUDIO_DIR / "test_tone.wav"


def ensure_asset_folders() -> None:
	"""Tạo sẵn các thư mục assets nếu chưa tồn tại."""

	AUDIO_DIR.mkdir(parents=True, exist_ok=True)
	(ASSET_DIR / "images").mkdir(parents=True, exist_ok=True)


def find_audio_asset(filename: Optional[str] = None) -> Path:
	"""Tìm tệp WAV trong thư mục `asseet/audio`.

	Nếu `filename` được truyền, cho phép cả đường dẫn tương đối (tính từ
	`asseet/audio`) hoặc đường dẫn tuyệt đối. Khi không truyền, chọn tệp `.wav`
	đầu tiên trong thư mục.
	"""

	ensure_asset_folders()

	if filename:
		candidate = Path(filename)
		if not candidate.is_absolute():
			candidate = AUDIO_DIR / candidate
		if candidate.exists():
			return candidate
		raise FileNotFoundError(candidate)

	wav_files = sorted(AUDIO_DIR.glob("*.wav"))
	if wav_files:
		return wav_files[0]

	raise FileNotFoundError("Không tìm thấy tệp WAV trong asseet/audio")


def generate_test_tone(
	target: Path = DEFAULT_WAV,
	duration_sec: float = 3.0,
	freq_hz: float = 440.0,
	sample_rate: int = 44_100,
	volume: float = 0.6,
) -> Path:
	"""Sinh tone dạng sóng sine và lưu thành file WAV."""

	ensure_asset_folders()

	total_samples = int(duration_sec * sample_rate)
	amplitude = int(volume * 32767)

	LOGGER.info(
		"Tạo tone %.1f Hz, %.1f s, sample_rate=%d vào %s",
		freq_hz,
		duration_sec,
		sample_rate,
		target,
	)

	with target.open("wb") as wav_file:
		with WaveWriter(wav_file, sample_rate) as wave_writer:
			for n in range(total_samples):
				sample = amplitude * math.sin(2 * math.pi * freq_hz * n / sample_rate)
				wave_writer.write_sample(int(sample))

	return target


class WaveWriter:
	"""Trợ giúp ghi WAV 16-bit mono."""

	def __init__(self, file_obj, sample_rate: int):
		import wave

		self.wave = wave.open(file_obj, "wb")
		self.wave.setnchannels(1)
		self.wave.setsampwidth(2)
		self.wave.setframerate(sample_rate)

	def write_sample(self, sample: int) -> None:
		self.wave.writeframes(struct.pack("<h", sample))

	def close(self) -> None:
		self.wave.close()

	def __enter__(self) -> "WaveWriter":
		return self

	def __exit__(self, exc_type, exc, tb) -> None:
		self.close()


def play_wav(file_path: Path) -> None:
	"""Phát file WAV thông qua `aplay`."""

	if not file_path.exists():
		raise FileNotFoundError(file_path)

	LOGGER.info("Phát thử âm thanh tại %s", file_path)

	subprocess.run(
		["aplay", "-q", str(file_path)],
		check=True,
	)


def speak_message(message: str, voice: Optional[str] = None) -> None:
	"""Đọc thông báo bằng espeak-ng (tuỳ chọn)."""

	command = ["espeak-ng", message]
	if voice:
		command.extend(["-v", voice])

	LOGGER.info("Đọc thông báo bằng espeak-ng: %s", message)
	subprocess.run(command, check=True)



def run_test(
	play_tone: bool = True,
	run_tts: bool = True,
	audio_filename: Optional[str] = None,
) -> None:
	"""Chạy quy trình kiểm thử."""

	ensure_asset_folders()

	if play_tone:
		try:
			wav_path = find_audio_asset(audio_filename)
		except FileNotFoundError:
			LOGGER.warning(
				"Không tìm thấy file WAV trong asseet/audio, sẽ tạo tone mặc định để kiểm tra."
			)
			wav_path = generate_test_tone()
		play_wav(wav_path)

	if run_tts:
		speak_message("Xin chào, đây là kiểm thử loa MAX chín 8 ba năm 7 A", voice="vi")


def _parse_args(argv: list[str]) -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Kiểm thử phát âm thanh qua MAX98357A bằng tệp WAV trong asseet/audio",
		formatter_class=argparse.ArgumentDefaultsHelpFormatter,
	)
	parser.add_argument(
		"--no-tone",
		action="store_true",
		help="Bỏ qua bước phát tệp WAV",
	)
	parser.add_argument(
		"--no-tts",
		action="store_true",
		help="Bỏ qua kiểm thử espeak-ng",
	)
	parser.add_argument(
		"--file",
		type=str,
		help="Tên tệp WAV trong asseet/audio (hoặc đường dẫn tuyệt đối) để phát thử",
	)
	return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
	logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
	argv = list(argv or sys.argv[1:])
	args = _parse_args(argv)

	try:
		run_test(
			play_tone=not args.no_tone,
			run_tts=not args.no_tts,
			audio_filename=args.file,
		)
	except FileNotFoundError as exc:
		LOGGER.error("Không tìm thấy tệp âm thanh: %s", exc)
		return 1
	except subprocess.CalledProcessError as exc:
		LOGGER.error("Lệnh phát âm thanh thất bại (mã %s)", exc.returncode)
		return exc.returncode or 1
	except Exception as exc:  # pylint: disable=broad-except
		LOGGER.exception("Lỗi không mong đợi")
		return 1

	LOGGER.info("Hoàn tất kiểm thử âm thanh")
	return 0


if __name__ == "__main__":
	sys.exit(main())
