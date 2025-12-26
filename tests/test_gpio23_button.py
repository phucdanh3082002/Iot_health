#!/usr/bin/env python3
"""
GPIO button press/release test (BCM numbering).

Default behavior matches: released=0V, pressed=3.3V (active-high).
"""
from __future__ import annotations

import argparse
import sys
import time

try:
    import RPi.GPIO as GPIO
except (ImportError, RuntimeError) as exc:
    print(f"RPi.GPIO not available: {exc}")
    sys.exit(1)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test GPIO button press/release.")
    parser.add_argument("--gpio", type=int, default=23, help="BCM GPIO pin number.")
    parser.add_argument(
        "--pull",
        choices=("up", "down", "off"),
        default="down",
        help="Internal pull resistor (default: down).",
    )
    parser.add_argument(
        "--active",
        choices=("high", "low"),
        default="high",
        help="Active level when button is pressed (default: high).",
    )
    parser.add_argument(
        "--bouncetime",
        type=int,
        default=200,
        help="Debounce time in ms for edge detect.",
    )
    parser.add_argument(
        "--poll",
        type=float,
        default=0.0,
        help="If >0, also print state every N seconds.",
    )
    return parser.parse_args()


def _pull_mode(name: str) -> int:
    if name == "up":
        return GPIO.PUD_UP
    if name == "down":
        return GPIO.PUD_DOWN
    return GPIO.PUD_OFF


def main() -> int:
    args = _parse_args()
    active_high = args.active == "high"

    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(args.gpio, GPIO.IN, pull_up_down=_pull_mode(args.pull))

    def label_for_level(level: int) -> str:
        pressed = level == GPIO.HIGH if active_high else level == GPIO.LOW
        return "PRESSED" if pressed else "RELEASED"

    def handle_edge(channel: int) -> None:
        level = GPIO.input(channel)
        ts = time.strftime("%H:%M:%S")
        print(f"{ts} GPIO{channel} level={level} {label_for_level(level)}")

    edge_enabled = False

    def _try_add_event_detect() -> bool:
        nonlocal edge_enabled
        try:
            GPIO.add_event_detect(
                args.gpio,
                GPIO.BOTH,
                callback=handle_edge,
                bouncetime=args.bouncetime,
            )
            edge_enabled = True
            return True
        except RuntimeError as exc:
            print(f"Edge detect failed: {exc}")
            return False

    if not _try_add_event_detect():
        try:
            GPIO.remove_event_detect(args.gpio)
        except Exception:
            pass
        GPIO.cleanup(args.gpio)
        time.sleep(0.2)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(args.gpio, GPIO.IN, pull_up_down=_pull_mode(args.pull))
        if not _try_add_event_detect():
            edge_enabled = False
            print(
                "Falling back to polling mode. "
                "If this persists, try running with sudo or stop other GPIO users."
            )

    initial_level = GPIO.input(args.gpio)
    print(
        f"Listening on BCM GPIO{args.gpio} "
        f"(pull={args.pull}, active={args.active})"
    )
    print(f"Initial: level={initial_level} {label_for_level(initial_level)}")

    poll_interval = args.poll
    if not edge_enabled and poll_interval <= 0:
        poll_interval = 0.2

    try:
        if poll_interval > 0:
            while True:
                time.sleep(poll_interval)
                level = GPIO.input(args.gpio)
                ts = time.strftime("%H:%M:%S")
                print(f"{ts} GPIO{args.gpio} level={level} {label_for_level(level)}")
        else:
            while True:
                time.sleep(1.0)
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        GPIO.cleanup(args.gpio)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
