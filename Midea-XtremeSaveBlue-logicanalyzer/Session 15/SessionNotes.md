# Session 15 — Session Notes

Full group-page probe with AC actively heating at 26 °C. Follow-up to
Session 14 (standby probe). Confirms all group pages respond on UART with
body[1]=0x21 and provides running-state baseline data. Two probe runs
~10 min apart capture compressor ramp-down as room approaches setpoint.

All queries sent programmatically by `ac_probe.py` (updated to include
groups 0x40–0x4F with v21 variant). Logic analyser capturing R/T bus
simultaneously for cross-reference.

---

## Hardware under test

- **Unit**: Midea XtremeSaveBlue split A/C (test object)
- **Capture point**: UART (Wi-Fi dongle brown/orange) + R/T extension board (CN1)
- **Logic analyser**: Saleae (3 channels — see channels.yaml)
- **Wi-Fi dongle**: CONNECTED, used as query transport via raspi-midea gateway
- **Wired controller**: KJR-120M (passive, no commands)
- **IR remote**: Used to set 26 °C heat before session start

---

## Probe setup

Same channel configuration as Session 14.
See [channels.yaml](channels.yaml).

**HAHB address**: MFB-X rotary switch at position 5 (XYE bus address 0x05).

**Probe tool**: `ac_probe.py` (v2 — added groups 0x40, 0x4B with v21;
replaced v81 sweep with full v21 sweep; added groups 0x41/0x43 v21 R/T test).
27 queries per run, 1.5 s response window each.

---

## Initial state

- **System power**: ON (set via IR remote before session)
- **Mode**: Heat
- **Setpoint**: 26 °C
- **Fan**: Auto
- **Temperature unit**: Celsius

---

## Probe runs

### Run 1 — 18:11:29 UTC (compressor active, higher load)

| Group | body[0..3] | Key decoded values |
|-------|-----------|-------------------|
| C0 status | `41 81 00 FF` | power=ON, mode=heat, setT=26, indoor=17°C, outdoor=9°C |
| **Group 1 (0x41) v21** | `41 21 01 41` | **FR=47Hz, FT=48Hz, current=12, voltage=231, T1=24.0, T2=36.5, T3=6.5, T4=9.5, Tp=36 °C** |
| Group 2 (0x42) v21 | `41 21 01 42` | indoor fan set=824RPM, actual=824RPM, load bits |
| **Group 3 (0x43) v21** | `41 21 01 43` | **outdoor fan=776RPM, EEV=496 steps, DC bus=175V, IPM=179, target freq=48Hz** |
| Group 4 (0x44) v21 | `41 21 01 44` | total=721.27 kWh, realtime=**660W** |
| Group 5 (0x45) v21 | `41 21 01 45` | Tsc=85, fan runtime=7145min, EEV target=496 steps, compressor=1915h, Vmax=243V, Vmin=196V |
| Group 6 (0x46) v21 | `41 21 01 46` | maxCurrent=52, T4max=177, T4min=30, compFlux=136, fanFlux=184, dAxis=0xFF, qAxis=0x03 |
| Group 7 (0x47) v21 | `41 21 01 47` | `00 FD 07 01 06 00 8F 02` — undocumented |
| Group 11 (0x4B) v21 | `41 21 01 4B` | **UD cool limit=100, heat limit=100, UD angle=48, LR limit=100, LR angle=240** |
| Group 12 (0x4C) v21 | `41 21 01 4C` | `02 00 0F` — undocumented |
| Group 0 (0x40) v21 | `41 21 01 40` | All zeros |
| Group 8 (0x48) v21 | `41 21 01 48` | **Returned group 1 data (body[3]=0x41)** — page alias |

### Run 2 — 18:21:56 UTC (compressor slowing, ~10 min later)

| Group | Key changes vs Run 1 |
|-------|---------------------|
| C0 status | indoor temp 17→20 °C (room warming) |
| Group 1 | FR=47→**35Hz**, FT=48→**35Hz**, T1=24→**27.5°C**, Tp=36→**38°C** |
| Group 3 | outdoor fan 776→**696RPM**, EEV 496→**288 steps**, target 48→**35Hz** |
| Group 4 | total 721.27→**721.40 kWh** (+0.13 in 10min), realtime 660→**376W** |
| Group 5 | compressor run time 11→**704 sec (×64)**, EEV target 496→288 |
| Group 6 | d/q axis and peak current values shifted (lower load) |
| Group 7 | `FD→FE`, `07→04`, `8F→58` — correlates with compressor load |
| Group 8 | **All zeros** (no longer aliasing group 1 — timing dependent?) |
| Group 11 | Unchanged (vane angles static) |

---

## Key findings

### 1. Groups 1 and 3 work on UART with body[1]=0x21 **[Confirmed]**

Previously marked R/T-only because body[1]=0x81 is rejected on UART.
With body[1]=0x21, the AC returns full compressor/outdoor telemetry on
UART — all 20 fields that were thought to require a second dongle:

- Compressor frequency (running + target)
- Temperatures T1, T2, T3, T4, Tp
- Outdoor fan speed, EEV position, DC bus voltage
- IPM module temperature, outdoor target frequency
- Currents and voltages

### 2. body[1] is a bus-origin variant marker **[Confirmed]**

```
0x81 = 1000 0001  — R/T wall controller style (rejected on UART for groups)
0x21 = 0010 0001  — UART WiFi dongle style (works on both buses)
```

The C0 status query (`41 81 00 FF`) is the only 0x81 command accepted on
UART. All group pages require 0x21 on UART.

### 3. New group pages discovered

| Page | Decoded by app? | Data on this unit? |
|------|:-:|:-:|
| 0x40 (Group 0 — timers) | Yes (JS) | All zeros |
| 0x42 (Group 2 — indoor diag) | Yes (JS) | Fan speeds, fault/load bits |
| 0x46 (Group 6 — diagnostics) | Yes (JS) | Peak currents, flux, T4 extremes |
| 0x47 (Group 7) | **No** | Non-zero, changes with load — undocumented |
| 0x4B (Group 11 — vanes) | Yes (JS) | Vane limits and current angles |
| 0x4C (Group 12) | **No** | Sparse data — undocumented |

### 4. Group 0x48 aliases to Group 1 (intermittent)

Query page 0x48 returned body[3]=0x41 (group 1 data) in Run 1, but all
zeros in Run 2. May be a firmware alias that depends on timing or internal
state.

### 5. Compressor ramp-down captured across two runs

10-minute delta with room approaching setpoint:
- Frequency: 47→35 Hz
- Power: 660→376 W
- EEV: 496→288 steps (closing)
- Total energy: +0.13 kWh in 10 min

---

## Glossary/tooling patches applied during this session

Based on probe results, the following were updated:

- `serial_glossary.yaml`: Groups 1/3 body[1] changed from 0x81 to 0x21,
  bus changed from `[rt]` to `[uart, rt]`. Groups 4/5 bus widened to
  `[uart, rt]`. New frame entries for groups 0, 2, 6, 7, 11, 12.
- `midea_frame.py`: `_GROUP_PAGE_TO_FRAME_ID` expanded with new pages.
- `midea_codec.py`: `PROTOCOL_KEY_MAP` expanded with new group keys.
- `ac_monitor.py`: `identify_body()` now handles B1 responses.

---

## Probe output

- `2026-04-10_18-11-29_probe.json` — Run 1 (27 queries, compressor at ~47Hz)
- `2026-04-10_18-21-56_probe.json` — Run 2 (27 queries, compressor at ~35Hz)
  Located in `HVAC-shark/tools/raspi-midea/examples/ac-monitor/`
