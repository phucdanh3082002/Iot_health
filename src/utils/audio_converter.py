"""Công cụ chuyển đổi MP3 sang WAV chuẩn PCM 16-bit cho MAX98357A.

Sử dụng `ffmpeg` để chuyển định dạng với các tham số mặc định:
- Tần số lấy mẫu: 44.1 kHz
- Số kênh: 2 (có tuỳ chọn mono)
- Định dạng mẫu: PCM signed 16-bit little-endian (pcm_s16le)

Ví dụ:
    python -m src.utils.audio_converter input.mp3
    python -m src.utils.audio_converter input.mp3 -o asseet/audio/my_track.wav
    python -m src.utils.audio_converter input.mp3 --mono --sample-rate 48000
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

LOGGER = logging.getLogger(__name__)

# Định nghĩa thư mục audio mặc định trong asseet
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSEET_AUDIO_DIR = PROJECT_ROOT / "asseet" / "audio"

DEFAULT_SAMPLE_RATE = 44_100
DEFAULT_CHANNELS = 2
DEFAULT_SAMPLE_FORMAT = "pcm_s16le"


def ensure_audio_dir() -> None:
    """Bảo đảm thư mục đích tồn tại."""

    ASSEET_AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def check_ffmpeg_available() -> None:
    """Kiểm tra ffmpeg đã được cài đặt trong PATH."""

    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "Không tìm thấy ffmpeg. Hãy cài đặt bằng: sudo apt install ffmpeg"
        )


def convert_mp3_to_wav(
    input_path: Path,
    output_path: Optional[Path] = None,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    channels: int = DEFAULT_CHANNELS,
    sample_format: str = DEFAULT_SAMPLE_FORMAT,
) -> Path:
    """Chuyển đổi một tệp MP3 sang WAV PCM chuẩn."""

    check_ffmpeg_available()

    if not input_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file nguồn: {input_path}")

    ensure_audio_dir()

    if output_path is None:
        output_path = ASSEET_AUDIO_DIR / (input_path.stem + ".wav")
    else:
        output_path = output_path.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

    LOGGER.info(
        "Chuyển %s → %s (sr=%d, channels=%d, format=%s)",
        input_path,
        output_path,
        sample_rate,
        channels,
        sample_format,
    )

    command = [
        "ffmpeg",
        "-y",  # overwrite không hỏi lại
        "-i",
        str(input_path),
        "-ar",
        str(sample_rate),
        "-ac",
        str(channels),
        "-acodec",
        sample_format,
        str(output_path),
    ]

    subprocess.run(command, check=True)

    LOGGER.info("Đã tạo file WAV tại %s", output_path)
    return output_path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Chuyển MP3 sang WAV PCM 16-bit cho kiểm thử MAX98357A",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("input", type=str, help="Đường dẫn tệp MP3 nguồn")
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Đường dẫn WAV đích (mặc định lưu vào asseet/audio/)"
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=DEFAULT_SAMPLE_RATE,
        help="Tần số lấy mẫu đầu ra"
    )
    parser.add_argument(
        "--mono",
        action="store_true",
        help="Cưỡng bức xuất âm thanh mono (1 kênh)"
    )
    parser.add_argument(
        "--channels",
        type=int,
        default=DEFAULT_CHANNELS,
        help="Số kênh xuất âm thanh (bỏ qua nếu dùng --mono)"
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve() if args.output else None

    channels = 1 if args.mono else max(1, args.channels)

    try:
        convert_mp3_to_wav(
            input_path=input_path,
            output_path=output_path,
            sample_rate=args.sample_rate,
            channels=channels,
        )
    except subprocess.CalledProcessError as exc:
        LOGGER.error("ffmpeg trả về lỗi (mã %s)", exc.returncode)
        return exc.returncode or 1
    except Exception as exc:  # pylint: disable=broad-except
        LOGGER.exception("Chuyển đổi thất bại")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
