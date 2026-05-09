## Run

```bash
python3 sample.py
```

## Example Output

```text
2026/05/09 12:00:01  0.083 V
2026/05/09 12:00:02  0.084 V
2026/05/09 12:00:03  0.149 V ←検知
```

## How It Works

TGS8100 は PULSE が HIGH の間のみ有効なアナログ電圧を出力します。

```text
PULSE HIGH
↓
OUT 電圧生成
↓
MCP3425 ADC変換
↓
Raspberry Pi で取得
```

臭気・VOC が増加するとセンサ抵抗 Rs が低下し、
OUT 電圧が上昇します。
