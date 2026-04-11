# Session 16 — Session Notes

First probe round against the live Q11 since the bulk B0/B1 expansion
and the per-frame source storage refactor landed. Two probe runs over
the same gateway, ~8 minutes apart:

| File | AC state | Outcome |
|---|---|---|
| `2026-04-11_19-09-26_probe.json` | powered OFF (idle) | 31/31 probes responded; B1 mostly `dl=0`; group pages mostly empty |
| `2026-04-11_19-17-15_probe.json` | powered ON via `ac_monitor --set power=true` | 31/31 probes responded; **98 fields decoded** end-to-end through the live decoder; group 1/2/3/6/7 all populated |

Both runs used the extended `B1_PROPERTY_IDS` list (51 entries — adds
the 22 Tier 1-4 props from the bulk B0/B1 commit plus the 7 Tier 5
deferred props). All C1 group page sweeps used `body[1]=0x21` (UART
variant).

## Findings

### 1. `body[1]=0x21` is the right variant for UART group queries

Confirmed end to end. Every group page (0x40..0x4F) we queried with v21
got an echo. **Group 1 (page 0x41) — previously documented as R/T-only —
is reachable on UART with v21**, and its payload decodes cleanly through
the existing `rsp_0xc1_group1` glossary entries when the AC is running:

- `compressor_frequency = 66 Hz` (target 90)
- `t1_indoor_coil = 21.0 °C`, `t2_indoor_temp = 23.5 °C`,
  `t3_outdoor_coil_temp = 0.5 °C`, `t4_outdoor_ambient_temp = 14.0 °C`
- `outdoor_supply_voltage = 229 V`
- `discharge_pipe_temp = 20.0 °C`
- `vane_ud_*`, `vane_lr_*` populated

The `t4` value (14 °C) and the C0 `outdoor_temperature` field (also
14 °C) agree, validating the byte mapping.

### 2. Q11 unconditionally strips the prop_id `hi` byte in B1 queries

Confirmed by the audit: every prop_id we sent with `hi != 0x00` came
back with `hi == 0x00` and the data the device has at `(lo, 0x00)`.
11/11 mismatches; not even one passed through unchanged.

| Sent | Received | Notes |
|---|---|---|
| `0x0B,0x02 pm25_value` | `0x0B,0x00` `dl=0` | substituted to nothing |
| `0x28,0x02 operating_time` | `0x28,0x00` `dl=0` | substituted to nothing |
| `0x1B,0x02 little_angel` | `0x1B,0x00` `dl=1 data=[0]` | accidentally surfaces a real undocumented prop at `0x1B,0x00` |
| `0x09,0x04 filter_level` | `0x09,0x00` `dl=1 data=[0]` | substituted to `wind_swing_ud_angle` |
| `0x25,0x02 temperature_ranges` | `0x25,0x00` `dl=0` | |
| `0x30,0x02 main_horizontal_guide_strip` | `0x30,0x00` `dl=0` | |
| ... | ... | (all 11 follow the same pattern) |

**Implication**: the entire Tier 3 (composites with `hi=0x02`), Tier 4
(multi-byte `hi=0x02`), and Tier 5 deferred properties (most are
`hi=0x02` / `hi=0x04`) **cannot be tested on Q11**. The wiring stays
correct based on mill1000/midea-msmart Finding 9; we just have no live
data to verify against on this hardware. Verification needs an FA-class
device or a model with the floor-sensor / pre-cool-heat / body-check
features.

This is a Q11 firmware quirk, not a glossary bug. Worth recording so
the next probe round on a different device knows to expect it.

### 3. Q11 B1 protocol is essentially inert for live state

Of the 51 prop_ids probed, only 8 returned `dl > 0`, and none of those
8 changed between the OFF and ON probes. The B1 protocol on this
firmware exposes config/capability flags only — not live-state
telemetry. All the moving values live in C0 + C1 group pages.

Populated B1 props (identical OFF and ON):

| prop_id | field | value |
|---|---|---|
| `0x42,0x00` | `breezeless` | 1 |
| `0x48,0x00` | `rate_select` | 100 |
| `0x09,0x00` | `wind_swing_ud_angle` | 0 |
| `0x0A,0x00` | `wind_swing_lr_angle` | 0 |
| `0x1A,0x00` | `buzzer` | 0 |
| `0x39,0x00` | `self_clean` | 0 |
| `0x1B,0x00` | (unmapped — see below) | 0 |

### 4. New finding: `0x1B,0x00` is an undocumented B1 property

Surfaced accidentally via the hi-byte substitution above.
mill1000/midea-msmart Finding 9 lists only `0x1B,0x02 little_angel`;
no `0x1B,0x00`. The device returns `dl=1 data=[0]` for it. We have one
data point; no meaning yet. Confidence: **Hypothesis**.

Not adding to the glossary in this round — a single byte at value 0
without context isn't enough to name. Re-probe in a few different
device states (cool / heat / fan-only / sleep) and see if the value
moves; if it does, we have something to characterise.

### 5. C1 group pages with newly populated bytes

OFF→ON diff. **Pages with bytes that aren't covered by an existing
decoder are NOT being chased in this round** — per the rule that we
don't probe further when there's no decoder spec to anchor against.
Listed for completeness so the next round can pick them up if a spec
appears:

| Page | Group | Status | New populated bytes |
|---|---|---|---|
| `0x41` | 1 (compressor) | **fully decoded** | n/a — works |
| `0x42` | 2 (indoor faults) | partially decoded | byte 4=2, byte 9=1 (already wired as `indoor_fault_flags_3` / `indoor_load_flags_2`) |
| `0x43` → `0x03` (substituted) | 3 (outdoor) | partially decoded | byte 5-12 populated; outdoor compressor freq, EEV, DC bus all wired |
| `0x46` | 6 | bytes 0-2 wired (lifetime stats) | bytes 4-9 = `[0x10, 0, 0xff, 2, 1, 2]` — **not in mill1000 docs** → skip |
| `0x47` | 7 | placeholder fields only | bytes 5-11 = `[252, 9, 1, 6, 0, 45, 1]` — **not in mill1000 docs** → skip |
| `0x4B` | (page 11 if `& 0x0F`) | unmapped | `[1]=100, [3]=100, [6]=100, [8]=0xf0` — looks like vane position pairs but no decoder spec → skip |
| `0x4C` | (page 12 if `& 0x0F`) | unmapped | `[0]=2, [2]=15` — unknown → skip |

### 6. C1 sub-page direct queries (`0x41 01`/`0x41 02`) — not supported on Q11

Both `direct_subpage_0x01` and `direct_subpage_0x02` returned a 3-byte
`00 00 00` error response. Q11 firmware does not implement the
sub-page direct query path that mill1000 documents in §3.1.4.4.

### 7. `device_id_0x07` (msg_type=0x07) — not supported

Returned 31 × `0xff`. Q11 firmware does not implement the device-ID
query.

### 8. `cmd_0x41_ext` (extended state, optCmd=0x03) — not supported

Returned a 3-byte `00 00 00`. Q11 firmware does not implement the
extended-state query path. We tried this in Session 14 too; result is
unchanged on Q11.

## Decoded snapshot — AC powered on, mode 4, target 23 °C

98 fields populated end-to-end through `process_raw_frame` +
`field_query.read_field`. Highlights:

| Field | Value |
|---|---|
| `power` | true |
| `operating_mode` | 4 |
| `target_temperature` | 23 |
| `indoor_temperature` | 21.3 °C |
| `outdoor_temperature` | 14.0 °C |
| `compressor_frequency` | 66 Hz (target 90) |
| `outdoor_fan_speed` | 66 |
| `eev_position` | 62 steps |
| `outdoor_dc_bus_voltage` | 176 V |
| `outdoor_supply_voltage` | 229 V |
| `t1`/`t2`/`t3`/`t4` | 21.0 / 23.5 / 0.5 / 14.0 °C |

Plus all the standard C0 booleans (eco, turbo, swing, etc.) at their
correct OFF state for an idle-cooling unit.

## What this session does NOT do

- Does NOT wire any new fields. Most of the populated B1 props were
  already in the glossary; the rest of the unknowns lack a decoder
  spec, so we leave them.
- Does NOT touch any of the bulk B0/B1 or Tier 5 fields. They are
  unverifiable on Q11 firmware (hi-byte stripping, see §2). Their
  confidence stays at Hypothesis.
- Does NOT chase the four exploratory pages (0x46/0x47/0x4B/0x4C
  unknown bytes). Without a mill1000 decoder spec for those bytes,
  any naming would be guessing.

## Sources

- Probe data: this directory
- Glossary fields validated against probe: `protocols/midea/spec/serial_glossary.yaml`
- Reference: mill1000/midea-msmart (see midea-msmart-mill1000.md, Findings 9 and 11)
