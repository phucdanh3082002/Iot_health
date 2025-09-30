"""Utility helpers for handling Piper TTS playback."""

from __future__ import annotations

import audioop
import logging
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Optional


LOGGER = logging.getLogger(__name__)


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

    def speak(self, message: str, volume: Optional[int] = None) -> None:
        if not message:
            return

        tmp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                tmp_path = Path(tmp_file.name)

            command = [
                "piper",
                "--model",
                str(self.model_path),
                "--output_file",
                str(tmp_path),
            ]

            if self.config_path:
                command.extend(["--config", str(self.config_path)])

            if self.speaker:
                command.extend(["--speaker", str(self.speaker)])

            command.append(message)

            LOGGER.debug("Running Piper command: %s", command)
            subprocess.run(command, check=True)

            if volume is not None:
                self._apply_volume(tmp_path, volume)

            subprocess.run(["aplay", "-q", str(tmp_path)], check=True)

        except subprocess.CalledProcessError as exc:
            LOGGER.error("Piper command failed: return code %s", exc.returncode)
            raise
        except FileNotFoundError as exc:
            LOGGER.error("TTS resource missing: %s", exc)
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


class NullTTS:
    """Fallback TTS that logs messages when Piper is not available."""

    def speak(self, message: str, volume: Optional[int] = None) -> None:  # pragma: no cover
        LOGGER.warning("TTS unavailable. Message skipped: %s", message)
