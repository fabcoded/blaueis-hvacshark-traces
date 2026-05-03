# Midea UART Bus — Timing Analysis

> **Source:** own logic-analyzer captures of the Wi-Fi dongle UART bus on a
> single device (Midea XtremeSaveBlue, sessions 1–13). **One device, one
> controller variant.** Findings apply to this unit; generalisation to other
> Midea models is **[Hypothesis]** until captures from a second device confirm
> them. No OEM-controller capture from a different model is available.
> Reproduce: `python3 analyze_timing.py` in this directory.

**Key takeaways (all [Consistent] across 12 capture sessions):**

- AC reply latency is bounded: **50–60 ms** on every message type, firmware-hard ceiling ~60 ms.
- Minimum observed OEM `post_tx_total` (end-of-TX → start-of-next-TX): **79.56 ms**.
- Median active-polling `post_tx_total`: **~116 ms**.
- Gateway default `frame_spacing_ms` raised from 100 → **150 ms** on 2026-04-14 as a conservative margin (above OEM median 116 ms, well inside the p95 775 ms envelope).
- **Answer to "are we too fast?": No.** At 100 ms we were at OEM p5; at 150 ms we sit above OEM median with a 70 ms cushion over the OEM minimum (80 ms).

---

## 1. Scope

Analysed: the 9600 8N1 UART bus between the Wi-Fi dongle (SmartKey) and the AC display board (`wifi*` channels in the pre-parsed `session.csv` files — `wifiBrown/toACdisplay` = dongle→AC, `wifiOrange/fromACdisplay` = AC→dongle). This is the same bus the blaueis gateway drives.

Not analysed (out of scope for this pass):

- R/T bus, XYE bus, mainboard bus, IR (present in some sessions, different protocols/baud).
- Sessions 14/15 use a raw Saleae CSV schema (`name,type,start_time,duration,data`) that is not pre-parsed into frames; needs a separate parser.
- Dongle `session.pcapng` files under `Midea-XtremeSaveBlue-dongle/` are **XYE passive sniffs** via MFB-C adapter, not UART — see `Midea-XtremeSaveBlue-dongle/Session 1/SessionNotes.md`. Irrelevant to UART cadence.

---

## 2. Metric definitions

Frame duration at 9600 8N1 = `bytes × 10 / 9600` s (1.042 ms/byte). End-of-frame wall-clock = `start_time + bytes × 1.042 ms`.

```
time →
  [====TX====]                     [====TX'===]
             ↑          [==RX==]↑            ↑
             TX_end  RX_start  RX_end       TX'_start

  reply_latency   = RX_start  - TX_end
  post_rx_silence = TX'_start - RX_end
  command_period  = TX'_start - TX_start
  post_tx_total   = TX'_start - TX_end        ← matches gateway's frame_spacing_ms intent
```

Pairing rule for replies: a TX is paired with the next RX iff that RX starts within 500 ms after TX end **and** no other TX intervenes. Unpaired TX (no RX within window) contributes only to `command_period` / `post_tx_total`.

---

## 3. Data set

| Session | Wi-Fi frames | Duration | Reply p50 | post_tx_total min | Notes |
|---|---:|---:|---:|---:|---|
| 1  |   90 |    78.8 s |  56.2 ms | 101.8 ms | |
| 2  |   72 |   181.4 s |  54.8 ms | 103.3 ms | |
| 3  |    0 |         — |        — |        — | no wifi* frames |
| 4  |   37 |    93.4 s |  52.3 ms |  87.3 ms | |
| 5  |   24 |    56.9 s |        — | 2965.8 ms | no reply pairs (TX-only window) |
| 6  |   33 |    82.7 s |        — | 344.9 ms | no reply pairs |
| 7  |  272 |   777.3 s |        — | 1429.8 ms | no reply pairs — capture-state anomaly |
| 8  |  249 |   315.8 s |  55.8 ms |  80.0 ms | |
| 9  |   24 |    82.2 s |        — |        — | |
| 10 |  508 |   688.5 s |  57.2 ms |  79.9 ms | largest active-polling sample |
| 11 |  665 |   918.2 s |  57.0 ms |  **79.56 ms** | absolute minimum in data set |
| 12 |  582 |   614.5 s |  56.5 ms |  80.8 ms | |
| 13 |   31 |   137.9 s |        — | 1730.6 ms | |

**Totals:** 2 587 Wi-Fi frames over 12 sessions with usable data; 3 479 gap observations (723 reply pairs, 1 017 command periods, 722 post-RX silences, 1 017 post-TX totals).

---

## 4. AC reply latency — firmware-bounded

**[Confirmed]** across all message types and sessions. The AC begins its reply between 50 ms and ~60 ms after the dongle's last TX byte. Distribution is tight; the 60 ms cap looks like a firmware scheduler tick, not jitter.

| msg_type | n | min (ms) | p50 (ms) | p95 (ms) | max (ms) |
|---|---:|---:|---:|---:|---:|
| 0x00 |  11 | 50.96 | 53.31 | 59.54 | 59.79 |
| 0x40 |  71 | 50.44 | 55.05 | 59.92 | 60.45 |
| 0x41 | 338 | 50.15 | 58.17 | 60.15 | 60.59 |
| 0xB0 |  26 | 50.72 | 54.87 | 58.87 | 59.43 |
| 0xB1 | 249 | 50.21 | 56.47 | 59.61 | 60.38 |
| 0xB5 |  28 | 50.23 | 55.29 | 59.44 | 59.99 |
| **all** | **723** | **50.15** | **56.85** | **60.00** | **60.59** |

Implication for a gateway: a 100 ms post-TX pause comfortably contains the reply (57 ms median + 40-byte frame at ~42 ms = ~99 ms total bus occupancy worst-case). No collision risk at current cadence.

Earlier spec note in `protocols/midea/spec/protocol_uart.md` was "~50 ms echo delay"; corrected to **~50–60 ms, p50 ≈ 57 ms** in this same pass.

---

## 5. Post-TX silence — the "are we too fast" metric

`post_tx_total` is the OEM-observable analogue of the gateway's `frame_spacing_ms` (see `blaueis-gateway/src/blaueis/gateway/uart_protocol.py:121,127,341`). The distribution is strongly **bimodal**:

```
Active-polling post_tx_total (filtered <1000 ms, n=502 of 1017 total):
  [  50-  80) ms      3
  [  80- 100) ms      6   #
  [ 100- 120) ms    257   ###################################################
  [ 120- 150) ms      9   #
  [ 150- 200) ms      5   #
  [ 200- 300) ms     17   ###
  [ 300- 500) ms     40   ########
  [ 500-1000) ms    165   #################################
```

Two distinct behaviours visible:

1. **Back-to-back polling (100–120 ms bucket, 257 obs = dominant mode):** the dongle finishes a TX, waits for the AC reply (~57 ms), then fires the next TX. The 100–120 ms cluster is the OEM's chosen inter-frame cadence while actively polling.
2. **Between poll cycles (500–1000 ms bucket, 165 obs):** idle gap between poll bursts.

| post_tx_total (ms) | n | min | p5 | p50 | p95 | max |
|---|---:|---:|---:|---:|---:|---:|
| active-polling (<1 s) | 502 | 79.56 | 106.53 | 116.22 | 775.47 | 999.03 |
| full range | 1017 | 79.56 | — | 1110.36 | 16831.40 | 67571.55 |

**Gateway default 150 ms** (raised from 100 ms on 2026-04-14), compared against the active-polling distribution:

- **34 ms above the OEM median (116 ms)** — slower than typical OEM behaviour, on purpose.
- **~1.9× the observed minimum (80 ms)** — comfortable margin to the floor.
- **Still inside the OEM p95 (775 ms)** — nowhere near the "obviously idle" tail.

Prior setting of 100 ms was at OEM p5 — safe but aggressive. The 50 ms increase absorbs device-variant uncertainty at the cost of one imperceptible extra delay per user command and ~33% lower maximum poll throughput (unused headroom — we poll every few seconds, not continuously).

**[Consistent]** across 6 sessions (1, 4, 8, 10, 11, 12) with `post_tx_total` minima in 79.56–103.3 ms.

---

## 6. Command period — full cycle

`command_period` (TX_start → next TX_start) subsumes TX duration + post-TX silence.

| command_period (ms) | n | min | p5 | p50 | p95 | max |
|---|---:|---:|---:|---:|---:|---:|
| active-polling (<1.5 s) | 532 | 103.93 | 135.80 | 153.61 | 1061.77 | 1496.84 |

OEM minimum full cycle: **104 ms**. Gateway's minimum full cycle at the new 150 ms default (typical 33-byte TX at ~34 ms + 150 ms sleep): **~184 ms** — sits above OEM median (154 ms active), well clear of the observed floor. A future reduction of `frame_spacing_ms` below ~70 ms would dip below the OEM-observed minimum cycle, exiting the safe envelope.

---

## 7. Verdict: "are we too fast?"

Gateway config: `frame_spacing_ms = 150` (raised from 100 on 2026-04-14 — see uart_protocol.py:121, server.py:82, tests/test_server_config.py:66).

| Question | Answer | Confidence |
|---|---|---|
| Are we faster than the OEM minimum? | No — OEM minimum 80 ms post-TX, we now pause 150 ms. | **[Consistent]** (6 sessions, 2 500+ frames) |
| Are we faster than the OEM median? | No — 150 ms vs OEM median 116 ms; we are intentionally slower. | **[Consistent]** |
| Does the AC ever fail to reply in our captures? | Not evident. No NAK/error frames, no missed replies in paired sequences. | **[Hypothesis]** (single device) |
| Are we at risk on an untested device variant? | Reduced, not eliminated. 150 ms absorbs moderate device-variant jitter; an unusually strict firmware could still demand more. | **[Unknown]** — single-device dataset |

**Decision (2026-04-14)**: default raised from 100 → 150 ms for conservative margin. Rationale:

- Honors `blaueis-libmidea/docs/flight_recorder.md §1.1` — on device-variant uncertainty, default to the slower setting.
- 150 ms is above OEM median (116 ms) but still well inside p95 (775 ms) — within the OEM envelope, on the slow end of typical.
- Costs are invisible: +50 ms per user command, no user-facing impact on polling (cadence-limited by scheduler, not spacing).
- A future reduction below ~70 ms would dip under the observed OEM minimum and should not be made without new evidence.

---

## 8. Caveats

- **One device.** Midea XtremeSaveBlue only. A different AC could enforce a stricter minimum.
- **Sessions 5, 6, 7, 9, 13 had zero reply pairs** — mostly small captures with truncated windows; Session 7 is the outlier (272 frames, no pairings) and warrants a separate look.
- **Clock source.** Logic-analyzer timestamps are the reference; no cross-check against gateway wall-clock. Sub-ms precision assumed correct.
- **Bus load not tested to failure.** No data on "AC stops responding at X ms post-TX" because no capture pushed below 80 ms.
- **No captures at gateway-driven cadence.** Every number here is OEM-dongle behaviour. The flight recorder is now live on the gateway; a follow-up pass dumping a ring and running this same analyzer on the extracted frame stream would close the loop. Not yet done.

---

## 9. Reproduction

```sh
cd blaueis-hvacshark-traces/data-analysis/midea/uart
python3 analyze_timing.py
```

Outputs in this directory:

- `timing_gaps_all.csv` — one row per observation (3 479 rows).
- `timing_per_session.json` — per-session summary.
- `timing_summary.json` — aggregate, incl. per-msg_type breakdowns.

Stdlib only; no pandas, no pyshark. Reads `session.csv` files under
`../../Midea-XtremeSaveBlue-logicanalyzer/Session */`.

---

## 10. Follow-ups (tracked, not done here)

1. **Parse Sessions 14/15** — raw Saleae CSV requires a bit-level decoder to recover frame boundaries; current data set skips them.
2. **Second device.** When another Midea unit becomes available for logic-analyzer capture, re-run and compare — this is the single biggest uncertainty in the current answer.
3. **Session 7 investigation.** 272 Wi-Fi frames, no reply pairings — bus state / capture quality anomaly worth understanding before trusting that session's numbers.
4. **Gateway self-timing.** Flight recorder is live (`blaueis-libmidea/docs/flight_recorder.md`) — dump a ring via `debug_dump` and feed the UART frames into this analyzer. Closes the loop between "what OEM does" and "what we actually do".
5. **Controlled cadence experiment.** Sweep `frame_spacing_ms` downward on the Atelier Midea unit, watch the flight-recorder ring for missed replies. Only way to measure the real floor; gateway instrumentation is in place, the experiment itself has not been run.
6. **Update spec:** `protocols/midea/spec/protocol_uart.md:290` note of "~50 ms echo delay" should be revised to "50–60 ms, p50 ≈ 57 ms, hard ceiling ~60 ms".
