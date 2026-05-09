from smbus import SMBus # pyright: ignore[reportMissingImports]
import RPi.GPIO as GPIO # pyright: ignore[reportMissingModuleSource]
import time
from datetime import datetime

# TGS8100 の PULSE ピンを接続している Raspberry Pi の GPIO 番号
# Raspberry Pi 物理ピン11
PULSE_PIN = 17

# MCP3425 の I2C アドレス
# A0ピン未接続時のデフォルトは 0x68
ADDRESS = 0x68

# GPIO番号を BCM 番号で扱う
GPIO.setmode(GPIO.BCM)

# PULSE ピンを出力モードに設定
GPIO.setup(PULSE_PIN, GPIO.OUT)

# 初期状態は LOW
GPIO.output(PULSE_PIN, GPIO.LOW)

# I2C バス1を使用
# Raspberry Pi:
#   GPIO2  (物理ピン3) = SDA
#   GPIO3  (物理ピン5) = SCL
bus = SMBus(1)


def read_voltage():
    """
    MCP3425 から現在の電圧を取得する
    戻り値は TGS8100 OUT の実際の電圧(V)
    """

    # MCP3425 から3バイト読み込み
    # [上位バイト, 下位バイト, 設定バイト]
    data = bus.read_i2c_block_data(ADDRESS, 0, 3)

    # ADC の 16bit 生値へ変換
    raw = (data[0] << 8) | data[1]

    # MCP3425 は符号付き値を返すため、
    # 負値の場合は Python の負数へ変換
    if raw >= 0x8000:
        raw -= 0x10000

    # MCP3425 入力電圧へ変換
    #
    # MCP3425:
    #   ±2.048V
    #   16bit (-32768 ～ +32767)
    #
    # 1カウント = 2.048 / 32768 V
    measured_voltage = raw * 2.048 / 32768

    # TGS8100 OUT は 10kΩ + 10kΩ の
    # 1/2 分圧をしているため、
    # 実際の電圧へ戻す
    actual_voltage = measured_voltage * 2

    return actual_voltage


try:
    while True:

        # TGS8100 の測定開始
        #
        # TGS8100 は PULSE が HIGH の間だけ
        # OUT に有効なアナログ電圧を出力する
        GPIO.output(PULSE_PIN, GPIO.HIGH)

        # OUT 電圧安定待ち
        time.sleep(0.001)

        # TGS8100 OUT 電圧を取得
        voltage = read_voltage()

        # 測定終了
        GPIO.output(PULSE_PIN, GPIO.LOW)

        # 現在日時
        now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

        # 電圧表示
        #
        # 電圧が高いほど、
        # TGS8100 が検知したガス量が多い
        print(f"{now}  {voltage:.3f} V")

        # TGS8100 推奨周期:
        # 1000ms 周期中 2ms だけ測定
        time.sleep(0.999)

finally:

    # 終了時は LOW に戻す
    GPIO.output(PULSE_PIN, GPIO.LOW)

    # GPIO解放
    GPIO.cleanup()
