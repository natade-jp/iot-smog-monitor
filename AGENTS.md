# AGENTS

## Purpose

This repository is a Raspberry Pi application for odor/VOC monitoring with TGS8100 + MCP3425.
The app samples every second, detects sudden increases, plays an alert sound, and writes 5-minute summaries.

## Primary Edit Targets

- `app/main.py`
- `app/config.json`
- `deploy/install.sh`
- `deploy/smog-monitor.service`
- `readme.md`

## Guardrails

- Keep hardware pin/I2C assumptions consistent with README unless explicitly asked to change.
- Do not change default GPIO/I2C settings in `app/config.json` without clear reason.
- Keep `systemd` unit paths aligned with `/opt/iot-smog-monitor`.
- Prefer additive and backward-compatible changes.
- Avoid introducing heavy dependencies unless required.

## Runtime Notes

- Target hardware is Raspberry Pi B+ (legacy model). Prefer compatibility-first and lightweight choices.
- This project depends on Raspberry Pi hardware (`RPi.GPIO`, `smbus`) and cannot be fully validated on non-Pi environments.
- Audio playback uses external command from config (`audio.player_command`, default `aplay`).

## Validation Checklist

When making changes, verify at least:

1. Python syntax is valid for edited files.
2. README instructions still match actual file paths and commands.
3. `deploy/install.sh` and `deploy/smog-monitor.service` remain consistent with each other.
4. Logging and alert behavior remain configurable via `app/config.json`.

## Style

- Keep code simple and readable.
- Add concise comments only where intent is non-obvious.
- Prefer explicit names over compact clever logic.
