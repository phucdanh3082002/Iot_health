"""Utility script to pre-generate Piper TTS audio assets into asset/tts."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Iterable, Tuple

import yaml

project_root = Path(__file__).resolve().parents[2]
config_path = project_root / "config" / "app_config.yaml"
output_default = project_root / "asset" / "tts"

# Adjust import path for project modules
import sys

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.utils.tts_manager import (  # noqa: E402
    SCENARIO_LIBRARY,
    ScenarioID,
    TTSManager,
)

LOGGER = logging.getLogger("export_tts_assets")


def _load_audio_config() -> dict:
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found at {config_path}")

    with config_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}

    audio_cfg = config.get("audio", {}) or {}
    audio_cfg.setdefault("piper", {})
    return audio_cfg


def _iter_static_scenarios() -> Tuple[ScenarioID, ...]:
    static_ids: Iterable[ScenarioID] = (
        scenario
        for scenario, template in SCENARIO_LIBRARY.items()
        if not template.required_fields
    )
    return tuple(static_ids)


def export_assets(output_dir: Path, locale: str | None = None, volume: int | None = None) -> None:
    audio_cfg = _load_audio_config()
    piper_cfg = audio_cfg.get("piper", {}) or {}

    model_path = Path(piper_cfg.get("model_path", "")).expanduser() if piper_cfg.get("model_path") else None
    config_file = Path(piper_cfg.get("config_path", "")).expanduser() if piper_cfg.get("config_path") else None
    speaker = piper_cfg.get("speaker") or None

    if model_path is None or not model_path.exists():
        raise FileNotFoundError("Piper model_path is missing or invalid in configuration")

    default_locale = locale or audio_cfg.get("locale", "vi")
    default_volume = volume or int(audio_cfg.get("volume", 100))

    output_dir = output_dir.expanduser()
    if not output_dir.is_absolute():
        output_dir = (project_root / output_dir).resolve()

    output_dir.mkdir(parents=True, exist_ok=True)

    LOGGER.info("Exporting TTS assets to %s", output_dir)

    tts_manager = TTSManager.create_default(
        model_path=model_path,
        config_path=config_file,
        speaker=speaker,
        default_locale=default_locale,
        default_volume=default_volume,
        cache_dir=output_dir,
        strict_assets=False,
    )

    try:
        static_scenarios = _iter_static_scenarios()
        LOGGER.info("Preloading %d static scenarios", len(static_scenarios))
        tts_manager.preload_scenarios(static_scenarios, locale=default_locale, volume=default_volume)

        # Wait for worker queue to finish processing
        tts_manager._queue.join()  # type: ignore[attr-defined]

        LOGGER.info("Generated %d audio files", len(list(output_dir.glob("*.wav"))))
    finally:
        tts_manager.shutdown()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    assets_default = output_default
    try:
        audio_cfg = _load_audio_config()
        piper_cfg = audio_cfg.get("piper", {}) or {}
        assets_dir_cfg = piper_cfg.get("assets_dir")
        if assets_dir_cfg:
            candidate = Path(assets_dir_cfg).expanduser()
            if not candidate.is_absolute():
                candidate = (project_root / assets_dir_cfg).resolve()
            assets_default = candidate
    except FileNotFoundError:
        LOGGER.warning("Configuration file missing; using default assets directory")

    parser = argparse.ArgumentParser(description="Generate Piper TTS audio prompts")
    parser.add_argument(
        "--output",
        type=Path,
        default=assets_default,
        help=f"Directory to store generated audio assets (default: {assets_default})",
    )
    parser.add_argument("--locale", type=str, default=None, help="Override locale (vi/en)")
    parser.add_argument("--volume", type=int, default=None, help="Override playback volume (0-200)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    args = parse_args(argv)
    export_assets(args.output, locale=args.locale, volume=args.volume)


if __name__ == "__main__":
    main()
