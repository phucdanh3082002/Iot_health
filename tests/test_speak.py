"""Tiện ích phát âm thanh WAV trong `asseet/audio` và đọc TTS bằng Piper."""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional


LOGGER = logging.getLogger(__name__)


def project_root() -> Path:
	return Path(__file__).resolve().parent.parent


ASSET_AUDIO_DIR = project_root() / "asseet" / "audio"


def ensure_audio_dir() -> None:
	ASSET_AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def resolve_audio_file(filename: Optional[str]) -> Path:
	ensure_audio_dir()

	if filename:
		candidate = Path(filename)
		if not candidate.is_absolute():
			candidate = ASSET_AUDIO_DIR / candidate
		if candidate.exists():
			return candidate
		raise FileNotFoundError(candidate)

	wav_files = sorted(ASSET_AUDIO_DIR.glob("*.wav"))
	if not wav_files:
		raise FileNotFoundError("Không tìm thấy tệp WAV trong asseet/audio")
	return wav_files[0]


def play_audio(file_path: Path) -> None:
	if not file_path.exists():
		raise FileNotFoundError(file_path)

	LOGGER.info("Phát âm thanh từ %s", file_path)
	subprocess.run(["aplay", "-q", str(file_path)], check=True)


def synthesize_with_piper(
	message: str,
	model_path: Path,
	config_path: Optional[Path] = None,
	speaker: Optional[str] = None,
) -> Path:
	if not model_path.exists():
		raise FileNotFoundError(model_path)

	with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
		output_path = Path(tmp_file.name)

	command: list[str] = [
		"piper",
		"--model",
		str(model_path),
		"--output_file",
		str(output_path),
	]

	if config_path:
		if not config_path.exists():
			raise FileNotFoundError(config_path)
		command.extend(["--config", str(config_path)])

	if speaker:
		command.extend(["--speaker", speaker])

	command.append(message)

	LOGGER.info("Sinh giọng nói bằng Piper: model=%s speaker=%s", model_path, speaker)
	subprocess.run(command, check=True)

	return output_path


def speak_text(
	message: str,
	model_path: Path,
	config_path: Optional[Path] = None,
	speaker: Optional[str] = None,
) -> None:
	wav_path = synthesize_with_piper(message, model_path, config_path, speaker)
	try:
		play_audio(wav_path)
	finally:
		try:
			wav_path.unlink(missing_ok=True)
		except AttributeError:
			# Python < 3.8 không có missing_ok, nhưng dự án yêu cầu Python 3.11+
			# nên nhánh này hầu như không chạy.
			if wav_path.exists():
				wav_path.unlink()


def main(argv: Optional[list[str]] = None) -> int:
	logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
	parser = argparse.ArgumentParser(
		description="Phát âm thanh WAV trong asseet/audio và/hoặc đọc TTS",
		formatter_class=argparse.ArgumentDefaultsHelpFormatter,
	)
	parser.add_argument(
		"--file",
		type=str,
		help="Tên tệp WAV (hoặc đường dẫn tuyệt đối) để phát; mặc định chọn file đầu tiên",
	)
	parser.add_argument(
		"--no-audio",
		action="store_true",
		help="Bỏ qua phát WAV",
	)
	parser.add_argument(
		"--text",
		type=str,
		default="Xin chào, đây là kiểm tra âm thanh.",
		help="Thông điệp TTS (bỏ qua khi dùng --no-tts)",
	)
	parser.add_argument(
		"--piper-model",
		type=str,
		required=True,
		help="Đường dẫn tới file model Piper (.onnx)",
	)
	parser.add_argument(
		"--piper-config",
		type=str,
		help="Đường dẫn tới file config Piper (.json) nếu cần",
	)
	parser.add_argument(
		"--piper-speaker",
		type=str,
		help="Tên speaker trong model Piper (ví dụ: vi_vocalist)",
	)
	parser.add_argument(
		"--no-tts",
		action="store_true",
		help="Không đọc TTS",
	)

	args = parser.parse_args(argv)

	model_path = Path(args.piper_model) if args.piper_model else None
	config_path = Path(args.piper_config) if args.piper_config else None

	try:
		if not args.no_audio:
			audio_file = resolve_audio_file(args.file)
			play_audio(audio_file)

		if not args.no_tts:
			if model_path is None:
				raise ValueError("Thiếu đường dẫn model Piper (--piper-model)")
			speak_text(args.text, model_path, config_path, args.piper_speaker)
	except FileNotFoundError as exc:
		LOGGER.error("Không tìm thấy tệp: %s", exc)
		return 1
	except subprocess.CalledProcessError as exc:
		LOGGER.error("Lệnh hệ thống thất bại (mã %s)", exc.returncode)
		return exc.returncode or 1
	except Exception as exc:  # pylint: disable=broad-except
		LOGGER.exception("Lỗi không mong đợi")
		return 1

	return 0


if __name__ == "__main__":
	sys.exit(main())
