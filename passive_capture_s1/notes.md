# passive_capture_s1 — cool/16 °C cycle

**Captured:** 2026-05-01 (~16:05 local, 395 s capture window)
**Method:** passive listen-only on the deployed blaueis-gw WebSocket
(`192.168.210.30:8765`); no probe traffic injected. The gateway's
normal poll cycle hits every C1 group once per ~16 s, so a 7-minute
window yields ~26 frames per group.

## Why this session

We needed wire-level evidence of what `compressor_idle` (C1 Group 1
`body[6]`) does on the dev unit when the compressor is actually
running. Existing fixtures from the probed XtremeSaveBlue all read 0
(firmware quirk on that variant), so they couldn't disambiguate
"binary idle/running flag" from an alternative interpretation seen
in community protocol research that treats `body[6]` as a
compressor-current reading (unit ~0.25 A).

## Test cycle

Pre-test snapshot: heat / 18 °C / Medium / preset none / swing off.
Room 22.2 °C, outdoor 22.3 °C.

| T+ | Event |
|---|---|
| 0 s | `climate.set_hvac_mode(cool)` |
| 6 s | `climate.set_temperature(16)` |
| ~16 s | compressor visible at 8 Hz, ramps to 39 → 56 Hz over the next minute |
| +180 s | hold at 56 Hz steady-state, room 22.3 → 22.1 °C |
| ~+240 s | `climate.set_hvac_mode(heat)` |
| ~+246 s | `climate.set_temperature(18)` (restore) |
| ~+395 s | capture window closes |

Restore verified: post-test climate state matches pre-test snapshot
exactly.

## Capture stats

- Duration: 395.6 s
- 241 frames total
- Distribution: 26 each of C1 Group 1–6 (gateway poll cycle), 35
  C0/A0 status, 26 B1 property responses, 2 B5 capability responses,
  scattered A1–A6 heartbeats and short `0x00` queries

## Key finding: `compressor_idle` is binary, not analog

Across the 26 C1 Group 1 response frames, `body[6]` took only two
values:

| body[6] | count | state |
|---|---|---|
| `0x01` | 4 | compressor idle (frames before spool-up + frames after restore) |
| `0x00` | 22 | compressor running (8–56 Hz) |

If `body[6]` were the analog compressor-current measurement posited
by some community decoders (unit ~0.25 A), running at 56 Hz would
have produced raw values in the 5–30 range (1.25–7.5 A typical for
residential split-AC compressor under load). It stayed at 0.

**Conclusion:** the firmware on this unit treats `body[6]` as a 1-bit
idle/running flag. The community-research "compressor current"
interpretation is not supported by observed values on either
blaueis-monitored unit and likely applies to a different firmware
family. The blaueis glossary's existing classification
(`compressor_idle`, `field_class: binary_sensor`, `1=idle,
0=running`) is correct.

## Cross-unit context

- Probed XtremeSaveBlue (cap `0x16=0`) reads `body[6]=0` always —
  firmware quirk, the bit never updates regardless of compressor
  state. Documented in the glossary note for `compressor_idle`.
- Atelier Midea (this capture) reads `body[6]=1` when idle, `0` when
  running — bit functions correctly.

## Files

- `capture.jsonl` — full gateway WebSocket dump, schema-preserving
  archive. Authoritative source for re-extracting fixtures if the
  PCAP encapsulation evolves.
- `capture.pcap` — Ethernet/IP/UDP-wrapped HVAC_shark frames,
  decodable in Wireshark with the `tools/dissector/HVAC-shark_mid-xye.lua`
  dissector. Verified clean: 241/241 frames decoded, 0 invalid CRCs.

## Derivative artifacts

- `blaueis-libmidea/packages/blaueis-core/tests/test-cases/passive_capture_s1/c1g1_frames.yaml`
  — 26 C1 Group 1 frames in the codec-test fixture format. Drives
  regression tests for the `compressor_idle` decode path.
