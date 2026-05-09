# smog monitor

Raspberry Pi + TGS8100 + MCP3425 を使用した VOC / 臭気監視システムです。

TGS8100 により空気中の VOC（揮発性有機化合物）や臭気変化を検知し、
Raspberry Pi 上で監視します。

## Features

- TGS8100 による VOC / 臭気検知
- MCP3425 による高精度 ADC 読み取り
- Raspberry Pi GPIO による PULSE 制御
- I2C 接続
- 平常時平均との差による変化検知

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

TGS8100 OUT は最大約3Vとなる可能性があるため、
MCP3425 の入力範囲 (±2.048V) に収めるために
10kΩ + 10kΩ の 1/2 分圧を使用しています。

```text
TGS8100 OUT
     │
   [10kΩ]
     │──────→ MCP3425 VIN+
   [10kΩ]
     │
    GND
```

## Enable I2C

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
i2cdetect -y 1
```

MCP3425 が接続されている場合:

```text
68
```

が表示されます。

## License

MIT
