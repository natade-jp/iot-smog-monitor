import csv
import json
import subprocess
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean

import RPi.GPIO as GPIO
from smbus import SMBus


@dataclass
class SensorConfig:
    pulse_pin: int
    i2c_address: int
    sample_interval_sec: float
    warmup_sec: float
    divider_ratio: float


@dataclass
class DetectionConfig:
    window_sec: int
    trigger_delta_v: float
    cooldown_sec: int


@dataclass
class AudioConfig:
    player_command: str
    file_path: str


@dataclass
class LoggingConfig:
    summary_interval_sec: int
    output_csv: str


def load_config(path: Path):
    # JSON設定を読み込み、扱いやすい dataclass に詰め替える。
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    sensor = SensorConfig(
        pulse_pin=raw["sensor"]["pulse_pin"],
        i2c_address=int(raw["sensor"]["i2c_address"], 16),
        sample_interval_sec=raw["sensor"]["sample_interval_sec"],
        warmup_sec=raw["sensor"]["warmup_sec"],
        divider_ratio=raw["sensor"]["divider_ratio"],
    )
    detection = DetectionConfig(
        window_sec=raw["detection"]["window_sec"],
        trigger_delta_v=raw["detection"]["trigger_delta_v"],
        cooldown_sec=raw["detection"]["cooldown_sec"],
    )
    audio = AudioConfig(
        player_command=raw["audio"]["player_command"],
        file_path=raw["audio"]["file_path"],
    )
    logging_cfg = LoggingConfig(
        summary_interval_sec=raw["logging"]["summary_interval_sec"],
        output_csv=raw["logging"]["output_csv"],
    )
    return sensor, detection, audio, logging_cfg


def ensure_log_file(path: Path):
    # ログ先ディレクトリとCSVヘッダを初期化する。
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "samples", "mean_v", "max_v", "min_v"])


def read_voltage(bus: SMBus, address: int, divider_ratio: float) -> float:
    # MCP3425 16bit符号付き値を実電圧へ変換する。
    data = bus.read_i2c_block_data(address, 0, 3)
    raw = (data[0] << 8) | data[1]
    if raw >= 0x8000:
        raw -= 0x10000
    measured_voltage = raw * 2.048 / 32768
    return measured_voltage * divider_ratio


def append_summary(path: Path, values: list[float]):
    # 5分窓の集計結果を1行追記する。
    if not values:
        return
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                datetime.now().isoformat(timespec="seconds"),
                len(values),
                f"{mean(values):.6f}",
                f"{max(values):.6f}",
                f"{min(values):.6f}",
            ]
        )


def play_alert(audio_cfg: AudioConfig):
    # 外部プレイヤーを使って警告音を再生する。
    try:
        subprocess.run(
            [audio_cfg.player_command, audio_cfg.file_path],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        print(
            f"[WARN] audio player not found: {audio_cfg.player_command}. "
            "Install alsa-utils or set another player command."
        )


def main():
    config_path = Path(__file__).with_name("config.json")
    sensor, detection, audio, logging_cfg = load_config(config_path)
    log_path = Path(logging_cfg.output_csv)
    ensure_log_file(log_path)

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(sensor.pulse_pin, GPIO.OUT)
    GPIO.output(sensor.pulse_pin, GPIO.LOW)
    bus = SMBus(1)

    # 直近N秒（既定10秒）の移動平均用バッファ。
    window = deque(maxlen=max(1, int(detection.window_sec / sensor.sample_interval_sec)))
    # 5分ごとCSV集計のために、生サンプルを一時保持する。
    summary_values: list[float] = []
    last_alert_at = 0.0
    next_summary_at = time.monotonic() + logging_cfg.summary_interval_sec

    try:
        while True:
            loop_started = time.monotonic()
            # TGS8100はPULSE HIGH中のみ有効値を出すため、毎回パルス駆動する。
            GPIO.output(sensor.pulse_pin, GPIO.HIGH)
            time.sleep(sensor.warmup_sec)

            voltage = read_voltage(bus, sensor.i2c_address, sensor.divider_ratio)
            GPIO.output(sensor.pulse_pin, GPIO.LOW)

            previous_avg = mean(window) if window else voltage
            window.append(voltage)
            current_avg = mean(window)
            summary_values.append(voltage)

            now = time.monotonic()
            delta = voltage - previous_avg
            # 急増判定: 「今回値 - 直前までの平均」がしきい値以上ならアラート。
            # cooldown_sec 内は再通知を抑制して連続再生を避ける。
            if delta >= detection.trigger_delta_v and (now - last_alert_at) >= detection.cooldown_sec:
                print(
                    f"[ALERT] {datetime.now().isoformat(timespec='seconds')} "
                    f"voltage={voltage:.3f}V avg10s={current_avg:.3f}V delta={delta:.3f}V"
                )
                play_alert(audio)
                last_alert_at = now
            else:
                print(
                    f"[INFO ] {datetime.now().isoformat(timespec='seconds')} "
                    f"voltage={voltage:.3f}V avg10s={current_avg:.3f}V"
                )

            if now >= next_summary_at:
                # 5分ごとに集計を確定し、次の窓を開始する。
                append_summary(log_path, summary_values)
                summary_values.clear()
                next_summary_at = now + logging_cfg.summary_interval_sec

            # 計測処理時間を差し引いて、できるだけ1秒周期を維持する。
            elapsed = time.monotonic() - loop_started
            sleep_sec = sensor.sample_interval_sec - elapsed
            if sleep_sec > 0:
                time.sleep(sleep_sec)
    finally:
        # 終了時は安全側に戻す。
        GPIO.output(sensor.pulse_pin, GPIO.LOW)
        GPIO.cleanup()
        bus.close()


if __name__ == "__main__":
    main()
