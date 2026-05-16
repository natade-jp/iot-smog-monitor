import csv
import json
import subprocess
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean

import RPi.GPIO as GPIO # pyright: ignore[reportMissingModuleSource]
from smbus import SMBus # pyright: ignore[reportMissingImports]


@dataclass
class SensorConfig:
    """センサーおよびサンプリング設定。

    Attributes:
        pulse_pin: TGS8100 の PULSE に接続する BCM GPIO 番号。
        i2c_address: MCP3425 の I2C アドレス（例: 0x68）。
        sample_interval_sec: サンプリング周期（秒）。
        warmup_sec: PULSE を HIGH にしてから ADC 読み取りまでの待機時間（秒）。
        divider_ratio: 分圧を元に戻す係数（1/2分圧なら 2.0）。
    """

    pulse_pin: int
    i2c_address: int
    sample_interval_sec: float
    warmup_sec: float
    divider_ratio: float


@dataclass
class DetectionConfig:
    """アラート判定設定。

    Attributes:
        window_sec: 移動平均に使う窓サイズ（秒）。
        trigger_delta_v: 急増判定しきい値（今回値 - 直前平均）の電圧差（V）。
        cooldown_sec: アラート再通知までの最小待機時間（秒）。
        startup_ignore_sec: 起動直後にアラート判定を無効化する時間（秒）。
    """

    window_sec: int
    trigger_delta_v: float
    cooldown_sec: int
    startup_ignore_sec: int


@dataclass
class AudioConfig:
    """音声再生設定。

    Attributes:
        player_command: 外部再生コマンド（例: `aplay`）。
        file_path: アラート音声ファイルのパス。
    """

    player_command: str
    file_path: str


@dataclass
class LoggingConfig:
    """定期生ログ設定。

    Attributes:
        write_interval_sec: 生ログを CSV にまとめて追記する間隔（秒）。
        output_dir: ログファイル出力先ディレクトリ。
        output_file_template: 生ログCSVのファイル名テンプレート。
            strftime 形式（例: `smell_raw_%Y-%m-%d.csv`）を含めると日付ごとに分割できる。
    """

    write_interval_sec: int
    output_dir: str
    output_file_template: str


def load_config(path: Path):
    """JSON 設定を読み込み、型付き設定オブジェクトに変換する。

    Args:
        path: `config.json` のパス。

    Returns:
        (SensorConfig, DetectionConfig, AudioConfig, LoggingConfig) のタプル。
    """

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
        startup_ignore_sec=raw["detection"].get("startup_ignore_sec", 0),
    )
    audio = AudioConfig(
        player_command=raw["audio"]["player_command"],
        file_path=raw["audio"]["file_path"],
    )
    logging_cfg = LoggingConfig(
        write_interval_sec=raw["logging"]["write_interval_sec"],
        output_dir=raw["logging"].get("output_dir", "/opt/iot-smog-monitor/data"),
        output_file_template=raw["logging"].get("output_file_template", "smell_raw_%Y-%m-%d.csv"),
    )
    return sensor, detection, audio, logging_cfg


def ensure_log_file(path: Path):
    """ログ用ディレクトリと CSV ヘッダを必要に応じて作成する。

    Args:
        path: CSV ファイルパス。
    """

    # ログ先ディレクトリとCSVヘッダを初期化する。
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "voltage_v", "avg_voltage_v", "level"])


def resolve_log_path(output_dir: str, output_file_template: str, now: datetime | None = None) -> Path:
    """ログ出力先ディレクトリとファイル名テンプレートからパスを解決する。

    Args:
        output_dir: ログ出力先ディレクトリ。
        output_file_template: strftime 形式を含むファイル名テンプレート。
        now: 解決に使う時刻。未指定時は現在時刻。

    Returns:
        解決済みの CSV パス。
    """

    current = now or datetime.now()
    return Path(output_dir) / current.strftime(output_file_template)


def read_voltage(bus: SMBus, address: int, divider_ratio: float) -> float:
    """MCP3425 を1回読み取り、実センサー電圧へ変換する。

    Args:
        bus: 開いている SMBus インスタンス（通常 Raspberry Pi の bus 1）。
        address: MCP3425 の I2C アドレス。
        divider_ratio: 分圧補正の係数。

    Returns:
        センサー電圧（V）。
    """

    # MCP3425 16bit符号付き値を実電圧へ変換する。
    data = bus.read_i2c_block_data(address, 0, 3)
    raw = (data[0] << 8) | data[1]
    if raw >= 0x8000:
        raw -= 0x10000
    measured_voltage = raw * 2.048 / 32768
    return measured_voltage * divider_ratio


def append_samples(path: Path, values: list[tuple[str, float, float, str]]):
    """現在の集計窓に溜めた生サンプルを CSV にまとめて追記する。

    Args:
        path: 出力先 CSV パス。
        values: (ISO日時文字列, 電圧値, 移動平均電圧値, 判定レベル) の列。
    """

    if not values:
        return
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for timestamp, voltage, avg_voltage, level in values:
            writer.writerow([timestamp, f"{voltage:.6f}", f"{avg_voltage:.6f}", level])


def play_alert(audio_cfg: AudioConfig):
    """外部コマンドでアラート音を再生する。

    Args:
        audio_cfg: 音声再生設定。
    """

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
    """監視のメインループ。

    センサー値を継続サンプリングし、急増検知時に音を再生し、
    定期的に集計ログを出力する。
    """

    config_path = Path(__file__).with_name("config.json")
    sensor, detection, audio, logging_cfg = load_config(config_path)
    log_path = resolve_log_path(logging_cfg.output_dir, logging_cfg.output_file_template)
    ensure_log_file(log_path)

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(sensor.pulse_pin, GPIO.OUT)
    GPIO.output(sensor.pulse_pin, GPIO.LOW)
    bus = SMBus(1)

    # 直近N秒（既定10秒）の移動平均用バッファ。
    window = deque(maxlen=max(1, int(detection.window_sec / sensor.sample_interval_sec)))
    # 5分ごとCSV書き込みのために、生サンプルを一時保持する。
    raw_samples: list[tuple[str, float, float, str]] = []
    last_alert_at = 0.0
    next_summary_at = time.monotonic() + logging_cfg.write_interval_sec
    alert_enabled_at = time.monotonic() + detection.startup_ignore_sec

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
            now = time.monotonic()
            delta = voltage - previous_avg
            # Excel で自動認識されやすい日時形式で保存する。
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            level = "INFO"
            # 急増判定: 「今回値 - 直前までの平均」がしきい値以上ならアラート。
            # cooldown_sec 内は再通知を抑制して連続再生を避ける。
            is_startup_ignored = now < alert_enabled_at
            if (
                (not is_startup_ignored)
                and delta >= detection.trigger_delta_v
                and (now - last_alert_at) >= detection.cooldown_sec
            ):
                level = "ALERT"
                print(
                    f"[ALERT] {timestamp} "
                    f"voltage={voltage:.3f}V avg10s={current_avg:.3f}V delta={delta:.3f}V"
                )
                play_alert(audio)
                last_alert_at = now
            else:
                if is_startup_ignored:
                    remaining_sec = max(0, int(alert_enabled_at - now))
                    print(
                        f"[INFO ] {timestamp} "
                        f"voltage={voltage:.3f}V avg10s={current_avg:.3f}V "
                        f"(startup_ignore: {remaining_sec}s)"
                    )
                else:
                    print(
                        f"[INFO ] {timestamp} "
                        f"voltage={voltage:.3f}V avg10s={current_avg:.3f}V"
                    )
            raw_samples.append((timestamp, voltage, current_avg, level))

            if now >= next_summary_at:
                # 5分ごとに生サンプルを書き出し、次の窓を開始する。
                # 日付入りファイル名を使っている場合は、ここで自動的に当日ファイルへ切り替わる。
                log_path = resolve_log_path(logging_cfg.output_dir, logging_cfg.output_file_template)
                ensure_log_file(log_path)
                append_samples(log_path, raw_samples)
                raw_samples.clear()
                next_summary_at = now + logging_cfg.write_interval_sec

            # 計測処理時間を差し引いて、できるだけ1秒周期を維持する。
            elapsed = time.monotonic() - loop_started
            sleep_sec = sensor.sample_interval_sec - elapsed
            if sleep_sec > 0:
                time.sleep(sleep_sec)
    finally:
        # 終了時に未書き出しバッファがあれば保存する。
        log_path = resolve_log_path(logging_cfg.output_dir, logging_cfg.output_file_template)
        ensure_log_file(log_path)
        append_samples(log_path, raw_samples)
        # 終了時は安全側に戻す。
        GPIO.output(sensor.pulse_pin, GPIO.LOW)
        GPIO.cleanup()
        bus.close()


if __name__ == "__main__":
    main()
