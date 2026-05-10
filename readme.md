# smog monitor

Raspberry Pi + TGS8100 + MCP3425 で、におい/VOCの急増を検知して音声アラートを出す監視アプリです。

## このリポジトリでできること

- 1秒ごとににおいセンサー電圧を取得
- 直近10秒の移動平均を維持
- 突然の増加（しきい値超過）で音声再生
- 1秒サンプルを5分ごとに一括で CSV 保存（SD 書き込み負荷を抑制）
- systemd で Raspberry Pi 起動時に自動起動

## ディレクトリ構成

```text
app/
  main.py          # 本番アプリ本体
  config.json      # 閾値・GPIO・ログ先などの設定
assets/
  alert.wav        # アラート音声（ユーザー配置）
deploy/
  install.sh       # 配置・依存導入・systemd登録
  smog-monitor.service
sample/
  sample.py        # 単体読み取りサンプル
```

## Raspberry Pi

### 下準備

#### Git

```bash
sudo apt update
sudo apt install -y git
git --version
```

#### I2C 有効化

```bash
sudo raspi-config
```

```text
Interface Options
→ I2C
→ Enable
```

確認:

```bash
sudo apt install -y i2c-tools
i2cdetect -y 1
```

`68` が見えれば MCP3425 を検出できています。

#### Python

`deploy/install.sh` でも導入されます。手動で入れる場合は以下です。

```bash
sudo apt install python3-rpi.gpio -y
sudo apt install python3-smbus -y
```

#### 音声再生

`app/config.json` の既定では `aplay` を使用するため、以下を導入してください。

```bash
sudo apt install -y alsa-utils
```

#### その他

ラズパイでの作業履歴が消えないように以下を `~/.bashrc` に書き込むことをおすすめします。

```bash
# コマンド実行ごとに履歴を追記し、他セッションの履歴も読み込む
export PROMPT_COMMAND='history -a; history -n'
```

### 配置と自動起動

1. Git から取得

```bash
git clone https://github.com/natade-jp/iot-smog-monitor
cd iot-smog-monitor
```

2. アラート音声を配置

```bash
cp /path/to/alert.wav assets/alert.wav
```

3. 必要に応じて設定を変更

```bash
nano app/config.json
```

4. インストール（`/opt/iot-smog-monitor` に配置し systemd 登録）

```bash
sudo bash deploy/install.sh
```

5. 状態確認

```bash
systemctl status smog-monitor.service
journalctl -u smog-monitor.service -f
```

### アンインストール

```bash
# サービス停止
sudo systemctl stop smog-monitor.service

# 自動起動無効化
sudo systemctl disable smog-monitor.service

# systemd 定義削除
sudo rm /etc/systemd/system/smog-monitor.service
sudo systemctl daemon-reload

# 配置先アプリ削除
sudo rm -rf /opt/iot-smog-monitor
```

確認:

```bash
systemctl status smog-monitor.service
```

### アップデート

既存インストール済み環境を更新する場合は、以下を実行します。

1. リポジトリへ移動

```bash
cd ~/iot-smog-monitor
```

2. 最新コード取得

```bash
git pull origin main
```

3. （必要なら）設定差分を確認・反映

```bash
git diff app/config.json
nano app/config.json
```

4. 再インストール（`/opt/iot-smog-monitor` 配下を更新し systemd を再登録）

```bash
sudo bash deploy/install.sh
```

5. 再起動と状態確認

```bash
sudo systemctl restart smog-monitor.service
systemctl status smog-monitor.service
journalctl -u smog-monitor.service -n 100
```

## ログ仕様

- 出力先ディレクトリ: `app/config.json` の `logging.output_dir`
- ファイル名テンプレート: `app/config.json` の `logging.output_file_template`
- ファイル名テンプレートは `strftime` 形式が使えます（例: `smell_raw_%Y-%m-%d.csv`）
- `%Y-%m-%d` は `yyyy-mm-dd` 形式です（例: `2026-05-09`）
- 1秒サンプルを5分ごとにまとめて追記
- CSV には以下を追記
    - timestamp
    - voltage_v

## 主要設定 (`app/config.json`)

- `detection.window_sec`: 平均の窓サイズ（秒）
- `detection.trigger_delta_v`: 急増判定しきい値（V）
- `detection.cooldown_sec`: アラート連発を防ぐ待ち時間（秒）
- `audio.file_path`: 再生する音声ファイル
- `logging.write_interval_sec`: 生ログをまとめて書き出す周期（秒）
- `logging.output_dir`: 生ログの出力先ディレクトリ
- `logging.output_file_template`: 生ログのファイル名（`%Y-%m-%d` などの日付展開に対応）

## Hardware

### Raspberry Pi

- Raspberry Pi B+

### Sensor

- AE-TGS8100
- MCP3425

## Wiring

### MCP3425

[MCP3425(16Bit ADC I2C 基準電圧内蔵)搭載モジュール](https://akizukidenshi.com/catalog/g/g108018/)

```text
        ┌───────┐
 VIN+ 1 │ ●     │ 6 VIN-
 VSS  2 │3425   │ 5 VDD
 SCL  3 │       │ 4 SDA
        └───────┘
```

### TGS8100

[TGS8100使用においセンサーモジュールキット](https://akizukidenshi.com/catalog/g/g115562/)

```text
┌─────────┐
│ 1 VDD   │  電源 +3.3V
│ 2 GND   │  GND
│ 3 PULSE │  測定パルス入力
│ 4 OUT   │  アナログ出力
└─────────┘
```

### Raspberry Pi ⇔ MCP3425

| MCP3425 | Raspberry Pi       |
| ------- | ------------------ |
| VDD     | 3.3V (Pin1)        |
| VSS     | GND (Pin6)         |
| SDA     | GPIO2 / SDA (Pin3) |
| SCL     | GPIO3 / SCL (Pin5) |
| VIN-    | GND                |

### Raspberry Pi ⇔ TGS8100

| TGS8100 | Raspberry Pi   |
| ------- | -------------- |
| VDD     | 3.3V           |
| GND     | GND            |
| PULSE   | GPIO17 (Pin11) |
| OUT     | MCP3425 VIN+   |

## Voltage Divider

TGS8100 OUT は最大約3Vとなる可能性があるため、MCP3425 の入力範囲 (±2.048V) に収めるために 10kΩ + 10kΩ の 1/2 分圧を使用します。

```text
TGS8100 OUT
     │
   [10kΩ]
     │──────→ MCP3425 VIN+
   [10kΩ]
     │
    GND
```

## License

MIT
