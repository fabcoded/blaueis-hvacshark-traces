# Findings — Comfee CPPA-07CRN7-QB6 mode walk

Operator-driven panel-state walk on a Comfee CPPA-07CRN7-QB6 (7000 BTU portable split, cooling-only). For each of 11 panel states the operator set the unit, then 3× B1 + 5× C0 + 3× A1 query frames were captured on the device's UART bus with ≥2 s spacing per pacing rules.

121 frames total. See `capture.yaml` for per-state context, `frames.jsonl` for the full record, `session_NN.pcap` for per-state captures, `session_full.pcap` for the combined timeline.

## Cap fingerprint

The B5 capability response (basic + additional pages) declares this mainboard's feature surface:

```
B5_basic    (8 caps): 14 02 01 00  15 02 01 02  1e 02 01 00  17 02 01 02
                     1a 02 01 02  10 02 01 04  25 02 07 20 3c 20 3c 20 3c 00
                     24 02 01 01
B5_additional (3): 1f 02 01 00  2c 02 01 01  8c 00 01 00
```

Decoded against the Midea cap-id reference:

- `0x0214 MODES = 0x00` → cool, dry, auto. **No heat mode.**
- `0x0215 SWING_MODES = 0x02` → no horizontal swing, no vertical swing.
- `0x0210 FAN_SPEED_CONTROL = 0x04` → low / high / auto only. No medium, no silent, no custom.
- `0x021A PRESET_TURBO = 0x02` → no turbo (neither cool-turbo nor heat-turbo).
- `0x021E ANION = 0x00` → no anion / ionizer.
- `0x0217 FILTER_REMIND = 0x02` → filter-replace notice yes, self-clean cycle no.
- `0x0224 DISPLAY_CONTROL = 0x01` → display LED toggle present.
- `0x0225 TEMPERATURES` → cool / auto / heat all 16 – 30 °C, no half-degree resolution.
- `0x021F HUMIDITY = 0x00` → no humidity readout/control.
- `0x022C BUZZER = 0x01` → buzzer present, controllable.
- `0x008C = 0x00` → undocumented cap byte, present but zero.

The cap fingerprint matches the "budget cooling-only single-axis" archetype: heat, swing, eco, turbo, anion, self-clean, freeze-protect, fahrenheit, energy-stats and rate-select are all absent.

## Mode encoding (confirmed)

C0 byte [2] high three bits encode operating mode. This device exposes:

| Mode      | byte[2] high nibble | byte[2] example |
|-----------|---------------------|-----------------|
| auto      | 0x2_                | 0x2e (auto, 30 °C) |
| cool      | 0x4_                | 0x46 (cool, 22 °C) |
| dry       | 0x6_                | 0x6e (dry, 30 °C) |
| fan-only  | 0xA_                | 0xae (fan-only, 30 °C) |

`0x8_` (heat) was never observed — consistent with the cap fingerprint.

C0 byte [2] low nibble encodes setpoint as `(low_nibble + 16) °C`, confirmed by the 16/22/30 °C transitions.

## Independent display and sound — protocol surfaces

The panel exposes display LED and sound (`Ton`) as **separate buttons**. The captures isolate both:

- **Display off (session_05)** — operator pressed display-LED button only. Visible C0 change in the body region; B1 untouched.
- **Sound off (session_11)** — operator pressed sound button only. **B1's first-response tail flipped from `00 00 00 00` (all 10 prior states) to `01 2c 02`.** C0 unchanged.

So on this mainboard, sound state lives on the **B1 property channel**, not in the C0 state byte. This is the most striking protocol observation in the session: display and sound use entirely different surfaces. A "buzzer enable" entity in any host integration must read/write B1, not C0.

## B1 channel: delta-only, with auto-mode tail byte

B1 responses across all states had the same shell: `b1 01 00 01 00 00 …` — count = 1 with a zero-size TLV. The interesting variability was in the **trailing 4 bytes after the formal TLV list**:

| State | B1 tail (first response) |
|-------|--------------------------|
| off, cool/*, dry, fan-only-sound-on | `00 00 00 00` |
| auto                                 | `00 00 00 30 00` *(0x30 byte appears only in auto mode)* |
| fan-only with sound off              | `00 00 01 2c 02` *(0x012c02 — the sound-off pattern)* |

The tail bytes appear to be an extension area outside the formal property-count protocol — only populated when specific firmware-internal state is non-default.

## A1 channel: stub on this mainboard

The A1 query reply (`c1 21 01 44 00 …`) was byte-identical across all 11 states. The mainboard returns a fixed stub. Consistent with the cap fingerprint having no `0x0216 ENERGY` cap. A1 polling on this device is non-informative.

## Compressor cycling

State 07 (cool, setpoint 30 °C, room well below) — operator reported audible compressor stop on the 16 → 30 °C setpoint change. The C0 prefix bytes (mode + setpoint) updated cleanly; the running/idle bit lives further into the body and is preserved in the per-state pcap for downstream analysis.
