# Findings — Comfee CPPA-07CRN7-QB6 query coverage

Companion to [`../03_comfee_cppa07crn7_qb6_modewalk/`](../03_comfee_cppa07crn7_qb6_modewalk/) (same hardware, panel-driven mode walk). This session sweeps the full set of query bodies a typical Midea AC integration emits and classifies each by reply taxonomy, to establish the device's actual response surface — and to identify queries that are wasted polling on this mainboard.

Three states walked, one set-state write per state followed by 15 queries (14 standard query bodies + querySN at msg_type 0x07).

## Reply taxonomy

Each query body's reply was classified by cross-state body comparison (after stripping the 10-byte header and 2 trailing msg_id+frame_checksum bytes):

| Verdict | Meaning |
|---|---|
| **silent** | No reply within timeout |
| **exception** | Reply with frame_type 0x06 / 0x0A (error) |
| **stub** | Same body across all states, content all-zero except header padding |
| **static** | Same body across all states, content non-zero (config / cap data) |
| **mode-dependent** | Body changes only on mode boundaries, not all state changes |
| **live** | Body content varies meaningfully with state |

## Coverage matrix

Sorted by usefulness for runtime polling:

| Body | Verdict | Notes |
|---|---|---|
| `cmd_0x41` | **live** | C0 status. byte 1 = power flag, byte 2 = mode high-nibble + setpoint low-nibble, byte 3 = fan speed, byte 7 = swing |
| `cmd_0x41_group2` | **live** | Status flags. byte 4 = 0x00 (off) → 0xFF (running). byte 11 = 0x40 only when running. Strong runtime-active signal |
| `cmd_0x41_group1` | **live** | Compressor / heat-exchanger telemetry. bytes 7-9 vary by mode and run state |
| `cmd_0x41_group3` | **live** (weak) | byte 9 = 0x04 in cool only, 0x00 in off and fan-only — cooling-active indicator |
| `cmd_0x41_group5` | **mode-dependent** | byte 12 = 0x07 in cool and off, 0x08 in fan-only — single-byte mode echo |
| `cmd_0x41_ext` | **live** (redundant) | Identical C0 content to `cmd_0x41`. No additional information on this device |
| `cmd_0xb5_simple` | **static** | Cap fingerprint basic — invariant by design |
| `cmd_0xb5_extended` | **static** | Cap fingerprint additional |
| `cmd_0x41_group11` | **static** | Constant non-zero body. Looks like config (gear / fan curve / installer block) |
| `cmd_0x41_group12` | **static** | Constant non-zero body. Config-shaped |
| `cmd_0x41_group0` | **stub** | All-zero — runtime timers not populated on this mainboard |
| `cmd_0x41_group4_power` | **stub** | All-zero — energy stats not populated (consistent with no `0x0216 ENERGY` cap) |
| `cmd_0x41_group6` | **stub** | All-zero |
| `cmd_0x41_group7` | **stub** | All-zero |
| `query_sn` (msg_type=0x07) | **silent** | No reply. msg_type=0x07 not honoured by this transport for this device |

## Observed state-dependent byte-level changes

### `cmd_0x41` → C0 body (24 bytes after header, before msg_id+chk)

```
A_off               c0 00 46 66 7f 7f 00 30 00 00 00 00 00 63 ff 00 00 00 00 00 00 00 00 01
B_cool_auto_22      c0 01 46 66 7f 7f 00 30 00 00 00 00 00 63 ff 00 00 00 00 00 00 00 00 01
C_fanonly_auto      c0 01 a6 66 7f 7f 00 30 00 00 00 00 00 62 ff 00 00 00 00 00 00 00 00 01
                          ^^^^^                                        ^^
                          byte 1: power                                byte 13: ?
                          byte 2: mode high-nibble + temp low-nibble
```

### `cmd_0x41_group2` → C1 group 2 body

```
A_off               c1 21 01 42 00 00 00 00 00 00 00 00 00 ff 00 00 00 00 00 00 00 00 04
B_cool_auto_22      c1 21 01 42 ff 03 00 00 00 00 00 00 40 ff 00 00 00 00 00 00 00 00 04
C_fanonly_auto      c1 21 01 42 ff 04 00 00 00 00 00 00 40 ff 00 00 00 00 00 00 00 00 04
                                ^^^^^                  ^^
                                byte 4: 0x00 off, 0xFF running
                                byte 5: 0x03 cool, 0x04 fan-only (mode echo)
                                byte 12: 0x40 = running flag
```

### `cmd_0x41_group1` → C1 group 1 body

```
A_off               c1 21 01 41 37 00 00 ff ff 04 4f 4f ff ff ff 00 00 00 00 00 00 00 03
B_cool_auto_22      c1 21 01 41 37 00 00 ff ff 01 4f 4f ff ff ff 00 00 00 00 00 00 00 03
C_fanonly_auto      c1 21 01 41 37 00 00 ff ff 04 4e 44 ff ff ff 00 00 00 00 00 00 00 03
                                                  ^^ ^^ ^^
                                                  byte 9: stage / running
                                                  bytes 10-11: temps (ambient / coil)
```

byte 9 takes 0x04 when idle (off or fan-only), 0x01 when actively cooling. bytes 10-11 are temperature-shaped values that drift between states; full decoding would require the Lua plugin for byte-level semantics.

## Implications for AC-protocol integrations

A typical Midea integration polls a fixed superset of query bodies regardless of device. On this mainboard that wastes round-trips: `group0`, `group4_power`, `group6`, `group7` always return all-zero. A cap-fingerprint-aware integration can derive a polling profile from B5 at first contact and skip stub bodies on devices that don't populate them — likely correlating with absent caps (e.g. ENERGY cap absent → group4_power is stub).

A practical poll-cadence proposal for this device:

| Cadence | Bodies |
|---|---|
| Every poll cycle | `cmd_0x41` (or `cmd_0x41_ext`, pick one), `cmd_0x41_group2` |
| Every 5–10 cycles | `cmd_0x41_group1`, `cmd_0x41_group3`, `cmd_0x41_group5` |
| Once at boot | `cmd_0xb5_simple`, `cmd_0xb5_extended`, `cmd_0x41_group11`, `cmd_0x41_group12` |
| Never | `cmd_0x41_group0`, `cmd_0x41_group4_power`, `cmd_0x41_group6`, `cmd_0x41_group7`, `query_sn` |

This roughly halves the per-cycle bandwidth versus the "poll everything" default.

## Caveats and open questions

- The "stub" verdict is conservative on a 3-state walk. A body that's all-zero across A/B/C might respond non-trivially under conditions not tested (long uptime accumulating runtime, energy meter populated, specific schedules). Worth re-running on a device known to have ENERGY cap to confirm `group4_power` becomes non-stub there.
- `cmd_0x41_ext` returning identical content to `cmd_0x41` is specific to this mainboard; on devices with additional state fields (eco/sleep/turbo flags actually toggleable) the extended form may carry extra bytes.
- `query_sn` being silent on msg_type 0x07 is curious. The body was empty, but some devices accept querySN with a specific body shape. Worth probing with `body = bytes([0x07])` or a non-empty SN-query body.
- byte 13 in `cmd_0x41` was 0x63 in A/B and 0x62 in C — single-bit difference. Could be a cap-version field or a counter. Not state-correlated in any obvious way.
