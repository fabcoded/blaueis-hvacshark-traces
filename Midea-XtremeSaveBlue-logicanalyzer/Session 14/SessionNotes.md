# Session 14 — Session Notes

UART group query discovery probe — AC in standby then set to 26 °C heat via
IR remote. Primary goal: determine which C1 group pages respond on the UART
bus and document the body[1] variant requirement.

All queries sent programmatically by `ac_probe.py` through the raspi-midea
WebSocket gateway. No app or wired controller commands. Logic analyser
capturing R/T bus simultaneously for cross-reference.

---

## Hardware under test

- **Unit**: Midea XtremeSaveBlue split A/C (test object)
- **Capture point**: UART (Wi-Fi dongle brown/orange) + R/T extension board (CN1)
- **Logic analyser**: Saleae (3 channels — see channels.yaml)
- **Wi-Fi dongle**: CONNECTED, used as query transport via raspi-midea gateway
- **Wired controller**: KJR-120M (passive, no commands)
- **IR remote**: Used to set temperature to 26 °C before second probe run

---

## Probe setup

Same channel configuration as Sessions 10-13.
See [channels.yaml](channels.yaml).

**HAHB address**: MFB-X rotary switch at position 5 (XYE bus address 0x05).

**Probe tool**: `ac_probe.py` — sends 35 queries sequentially with 1.5 s
response window each. Queries sent over UART via WebSocket gateway at
`192.168.210.30:8765`.

---

## Initial state

- **System power**: OFF (standby)
- **Mode**: Heat (last active mode)
- **Setpoint**: unknown (changed to 26 °C before Session 15)

---

## Probe sequence (35 queries)

### Phase 1 — Known frames

| # | Query | body[0..3] | Response | Result |
|---|-------|-----------|----------|--------|
| 1 | B5 extended | `B5 01 00` | B5 TLV, 8 caps | OK |
| 2 | B5 simple | `B5 01 01 01 21` | B5 TLV, 9 caps | OK |
| 3 | C0 status | `41 81 00 FF` | C0, 29 bytes | OK — power OFF |
| 4 | Group 4 power (v21) | `41 21 01 44` | C1 group4 | **OK — 721.26 kWh total, ~7W standby** |
| 5 | Group 5 (v21) | `41 21 01 45` | C1 group5 | **OK — fan runtime, bus voltages** |
| 6 | Extended state (optCmd) | `41 81 .. 03 .. 02` | Rejected (00 00 00) | Not supported |
| 7-8 | Direct sub-page 0x01/0x02 | `41 01` / `41 02` | Rejected | Not supported |

### Phase 2 — B1 property queries

| # | Properties queried | Responded with data |
|---|-------------------|-------------------|
| 9 | humidity, error, mode, tone, no_wind, wind_straight, self_clean, prevent_wind | tone=0x01, prevent_straight_wind=0x01 |
| 10 | rate_select, ud_angle, lr_angle, pm25, op_time, temp_ranges, icheck, indoor_code | rate_select=0x64, ud=0x32, lr=0x32 |
| 11 | outdoor_code, cool_heat_amount, fresh_air, comfort, ieco, high_temp_monitor | All zero-length (not supported) |

### Phase 3 — Device ID

| # | Query | Response |
|---|-------|---------|
| 12 | msg_type=0x07 | 31 bytes all 0xFF — no SN stored |

### Phase 4 — Group page sweep (v81 variant)

All group pages 0x42–0x4F with body[1]=0x81: **every one rejected** (msg_type=0x00, body=`00 00 00`). Confirms 0x81 is not accepted on UART for group queries.

Exception: group 0x4B (v81) received an unrelated msg_type=0x63 (network status) — timing coincidence.

### Phase 5 — Group page sweep (v21 variant)

| # | Query page | body[1] | Response body[3] | Data? |
|---|-----------|---------|------------------|-------|
| 24 | 0x42 | 0x21 | 0x42 | 1 load-state bit (standby) |
| 25 | **0x46** | 0x21 | 0x46 | **maxCurrent=52, T4 max=177, T4 min=30, flux values** |
| 26 | **0x47** | 0x21 | 0x47 | **Unknown: FE 03 .. 01 — no community decoder** |
| 27 | 0x48 | 0x21 | 0x48 | All zeros |
| 28 | 0x49 | 0x21 | 0x49 | All zeros |

### Phase 6 — optCommand sweep

optCommand 0x00, 0x02, 0x04, 0x05, 0x06 and queryStat 0x01, 0x03: **all rejected**.

---

## Key findings

1. **body[1]=0x21 is required for group queries on UART.** body[1]=0x81 is
   rejected for every group page. The standard C0 status query (body `41 81 00 FF`)
   still works with 0x81.

2. **Group 4 (power) and Group 5 (extended) respond on UART** with body[1]=0x21.
   Group 4 contains total energy (linear uint32/100 kWh) and real-time power
   (uint24/10000 kW). Group 5 contains humidity, fan runtime, EEV target,
   compressor cumulative hours, max/min bus voltage.

3. **Group 0x46 (diagnostics) responds on UART** — field mapping
   cross-validated against community protocol research. Contains lifetime max current, T4 extremes,
   compressor/fan flux, d/q axis currents, peak currents.

4. **Group 0x47 responds but is undocumented** — no decoder in Lua or JS app.
   Values change between standby and running states.

5. **optCommand mechanism (body[1]=0x21, body[4]=optCmd) is not supported** on
   this unit. Neither the 24-byte nor 14-byte form produces a response.

6. **B1 property protocol partially works** — 5 of 22 queried properties returned
   data (tone, prevent_straight_wind, rate_select, ud_angle, lr_angle).

---

## Probe output

- `2026-04-10_17-53-36_probe.json` — full TX/RX transcript (35 queries)
  Located in `HVAC-shark/tools/raspi-midea/examples/ac-monitor/`
