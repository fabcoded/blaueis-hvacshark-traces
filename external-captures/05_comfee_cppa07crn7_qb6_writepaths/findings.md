# Findings — Comfee CPPA-07CRN7-QB6 buzzer / display write-paths

Companion to [`../03_comfee_cppa07crn7_qb6_modewalk/`](../03_comfee_cppa07crn7_qb6_modewalk/) (panel-driven mode walk) and [`../04_comfee_cppa07crn7_qb6_querycoverage/`](../04_comfee_cppa07crn7_qb6_querycoverage/) (query response taxonomy). This dump characterises the buzzer property `0x022C` as a write surface — does it actually mute the device, and is the gate scoped to one frame type or all of them?

## Probe headline

`0x022C BUZZER = 0` is a **global beep gate** on this mainboard:

- Silences the per-frame beep flag in `cmd_0x40` set-state (real state changes — power on, setpoint change — fire silently)
- Silences the implicit beep emitted by the `cmd_0x41/beep` display-toggle frame (the LED still flips visually; only the audio is gated)

The visual display-LED latch (C0 body byte 15 bits[6:4]) is on a separate surface — buzzer property writes do not perturb it, and display-toggle frames do not perturb the buzzer property. The two are independent, contrary to the cap-absent Q11 mainboard where audio and display share one channel.

Writing `0x022C=1` always emits a brief buzzer-arming beep (value-dependent firmware confirmation tone, fires at write-time on any value=1 write — idempotent 1→1 included). Writing `0x022C=0` is always silent.

## Methodology

- **Pre-flight verification.** Every frame in the plan was pre-computed and decode-roundtrip-verified before the live session, then matched byte-for-byte at send time — 21 sends, 21 byte-matches. Frames were emitted to the device on its UART bus.
- **Halt-and-wait single-shot** — every frame had a pre-announced expected outcome. The frame went out, the operator confirmed audible/visual ground-truth at the device, then the next frame was queued.
- **×2 reps for every audible/visual finding.** A single confirmation is anecdote; reps under identical conditions are evidence.
- **Pacing ≥6 s** between mode/field changes, per the AC pacing rule.

## Phase-by-phase results

### Phase 0 — baseline reads (no writes)

| Frame | Reply summary |
|---|---|
| `F1` B1 read `0x022C, 0x0224` | `0x022C BUZZER` = `0` (left from prior session); `0x0224 DISPLAY_CONTROL` returns status=0x00 with **empty payload** (queryable but stub on this mainboard) |
| `F2` C0 status query | `power=OFF, mode=cool, fan=auto, T=22°C`, body[15]=`0x00` (latch enabled, LED on) |

### Phase R — re-validation matrix

The very first `0x022C=1` write produced an unexpected audible beep on a powered-OFF device. Rather than spin a hypothesis, the probe halted and ran a 3-frame discrimination matrix:

| Test | Send | Property transition | Hypothesis A predicts | Hypothesis B predicts | Hypothesis C predicts | Observed |
|---|---|---|---|---|---|---|
| R1 | `0x022C=1` (idempotent) | 1 → 1 | **BEEP** | SILENT | SILENT | **BEEP** |
| R2 | `0x022C=0` | 1 → 0 | **BEEP** | **BEEP** | SILENT | **SILENT** |
| R3 | `0x022C=0` (idempotent) | 0 → 0 | **BEEP** | SILENT | SILENT | **SILENT** |

- Hypothesis A "every write beeps" — falsified by R2.
- Hypothesis B "transitions beep" — falsified by R1.
- Hypothesis C "external/coincidence" — falsified by R1.

→ **Value-dependent**: writing value=1 always emits a beep (firmware buzzer-arming tone); writing value=0 is always silent. This is not propagation lag, not transition-triggered, not write-acknowledgment generally.

### Phase B — does `0x022C=0` silence `cmd_0x40` per-frame beep on real state changes?

Buzzer property=0 (left from R3). Each frame is a real cmd_0x40 set-state with `beep=on` flag.

| # | Frame | State change | Audible | Visual |
|---|---|---|---|---|
| B1 | F6 `set-state cool/22 power=on beep=on` | OFF → ON (real) | **SILENT** | AC starts running |
| B2 | F7 `set-state temp=23 beep=on` | T 22 → 23 (real +1°C) | **SILENT** | – |
| B3 | F6 `set-state temp=22 beep=on` (rep) | T 23 → 22 (real -1°C) | **SILENT** | – |

→ 3/3 SILENT. `0x022C=0` reliably silences the per-frame beep flag in `cmd_0x40` even on genuine state-changing frames.

### Phase C — does `0x022C=1` restore beep on real state changes?

| # | Frame | Audible |
|---|---|---|
| C0 | F3 `0x022C=1` (transition 0→1) | **BEEP** (arming confirmation) |
| C2 | F7 `set-state temp=23 beep=on` (real +1°C) | **BEEP** |
| C3 | F6 `set-state temp=22 beep=on` (rep -1°C) | **BEEP** |

→ 3/3 BEEP. Buzzer property=1 restores the per-frame beep behaviour symmetrically.

### Phase D — display-toggle × buzzer matrix (the global-gate question)

The `cmd_0x41/beep` display-toggle frame (body[1]=0x61) is documented as a state-changer that flips the C0 display-LED latch. The open question: does `0x022C=0` also silence its implicit beep, or is the display-toggle on a separate audio path?

| # | Frame | Buzzer prop | Audible | Visual (LED) |
|---|---|---|---|---|
| D1 | F5 toggle | 1 | **BEEP** | off (latch flipped to disabled) |
| D2 | F5 toggle | 1 | **BEEP** | on (latch flipped back) |
| D3 | F4 `0x022C=0` | 1 → 0 | SILENT (consistent with R2) | – |
| D4 | F5 toggle | 0 | **SILENT** | off |
| D5 | F5 toggle | 0 | **SILENT** | on |

→ 5/5 confirmed. The display-toggle's implicit beep is **also gated** by `0x022C`. The visual LED response fires regardless of buzzer property — display latch and buzzer property are on independent surfaces.

### Phase 3 — separation read

After Phase D, an explicit C0 query and B1 read confirmed:

- C0 body[15] = `0x00` (latch enabled — matches user-reported LED on)
- B1 `0x022C` = `0` (matches D3 last write)
- B1 `0x0224` returns empty payload (consistent with baseline)

Throughout Phase B/C/D, body[15] flipped only on F5 toggle frames — never on a B0 `0x022C` write. The latch is not a side-effect of the buzzer property.

### Phase E — restore

| # | Frame | Audible | Result |
|---|---|---|---|
| E1 | F3 `0x022C=1` (re-arm) | BEEP (arming) | buzzer property restored |
| E2 | F8 `set-state power=off beep=on` | (not listened) | device powered off, cleanup complete |

## C0 latch byte offset note

In this probe the display latch flipped at C0 body[15] (bit pattern `0x00 ↔ 0x70` — bits[6:4] enum `0b000` enabled / `0b111` disabled). The 03 modewalk findings recorded the latch at body[14]. Same enum semantics, 1-byte offset between the two captures. Likely explanations: different request-frame proto/sub bytes producing slightly different reply layouts, or a wall-clock counter byte at body[12] that occupies a variable position. The bit semantics hold at either offset; the exact alignment is worth re-validating on a follow-up scan.

## Implications for AC-protocol integrations

**Cap fingerprint is the load-bearing identifier**, not the product family or stick firmware code (SN8). Two different mainboards in the same 0xAC protocol family expose different audio-control surfaces:

- **Cap-having mainboard (this Comfee, has `0x022C BUZZER` in B5)**: a single B0 property toggle is the canonical audio mute. Write `0x022C=0` and every audio path stays silent — set-state per-frame beep, display-toggle implicit beep, anything else gated by the same firmware path. Integration design = one `audio_mute` entity, B0 write path, B1 read path. Side-effect-free with respect to display state.
- **Cap-absent mainboard (Q11-class, has no `0x022C`)**: no global-mute property. Silencing requires the display-LED latch toggle workaround (write display-off latch → send the silenced frame → write display-on latch). Integration design = no separate audio entity; the silent operation is a side-effect of the display entity, surfaced in its tradeoff documentation.

A "poll everything, write everything" approach that ignores the cap fingerprint produces wrong UX on at least one of these mainboards. The B5 fingerprint must drive the entity surface.

## Caveats and open follow-ups

- **B0 `0x0224 DISPLAY_CONTROL` write is rejected** with status=0x10 on this mainboard (verified in the prior session, consistent with this session's reads). Display state is therefore writable only via the `cmd_0x41/beep` toggle frame on Comfee-class hardware. `0x0224` exists as a B1-readable property but returns empty payload (queryable stub).
- **Atelier (Q11-stick) hasn't been re-tested for B0 `0x022C` behaviour** — the device was offline during this probe. Worth confirming that the cap-absent mainboard rejects B0 `0x022C` writes (status=0x10) or accepts-but-silently-no-effect, and whether B0 `0x0224` behaves analogously.
- **The buzzer-arming beep on `0x022C=1`** is idempotent — even writing the same value when the property is already 1 emits the beep. Acceptable UX (rare event, confirms armed state) but worth documenting in the entity description for HA integrations.
- **Wall-clock counter byte at C0 body[12]** wasn't decoded — value drifted across the session (0x61 → 0x62 → 0x63). Could be a minute counter, a periodic state-update sequence, or a tick. Not state-correlated in any obvious way.
