#!/usr/bin/env python3
"""UART bus timing analysis for Midea captures.

Reads pre-parsed session.csv files from logic-analyzer sessions, filters to the
wifi* channel (the Wi-Fi dongle UART bus, 9600 8N1), pairs TX/RX frames, and
computes per-session + aggregate timing statistics.

No external dependencies — stdlib only.

Metrics computed (see timing-analysis.md for definitions):
  reply_latency   = tx_end  -> rx_start   (AC response latency)
  post_rx_silence = rx_end  -> next_tx_start (dongle think-time between cycles)
  command_period  = tx_start -> next_tx_start (full poll period)
  post_tx_total   = tx_end  -> next_tx_start (what our frame_spacing_ms approximates)

Outputs (next to this script):
  timing_gaps_all.csv       — every measured gap, one row per observation
  timing_per_session.json   — per-session summary
  timing_summary.json       — aggregate across all sessions
"""
from __future__ import annotations

import csv
import json
import statistics
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterator

# ── Constants ─────────────────────────────────────────────────────────────

BITS_PER_BYTE_9600 = 10.0 / 9600.0  # seconds per byte, 8N1 = 10 bit-times
REPLY_PAIR_WINDOW_S = 0.5           # max TX→RX gap to consider a pair
SESSIONS_ROOT = Path(
    "/workspaces/hvac-shark-dev/blaueis-hvacshark-traces/Midea-XtremeSaveBlue-logicanalyzer"
)
OUT_DIR = Path(__file__).parent

# ── Data model ────────────────────────────────────────────────────────────

@dataclass
class Frame:
    session: str
    channel: str
    direction: str          # "tx" (toACdisplay) or "rx" (fromACdisplay)
    start: float            # seconds
    length: int             # bytes on the wire
    msg_type: int | None    # Midea msg_type byte, or None if not extractable
    hex: str

    @property
    def end(self) -> float:
        return self.start + self.length * BITS_PER_BYTE_9600


# ── Parsing ──────────────────────────────────────────────────────────────

def _parse_hex_bytes(hex_str: str) -> list[int]:
    if not hex_str:
        return []
    return [int(b, 16) for b in hex_str.strip().split()]


def _msg_type_of(frame_bytes: list[int]) -> int | None:
    """Midea UART frame layout: AA <len> AC 00 00 00 00 00 <kind> 03 <msg_type> ...

    byte[0] = 0xAA sync
    byte[1] = total length - 1
    byte[2] = 0xAC (appliance type)
    byte[9] = 0x03 when kind-byte at [8] is 0x00 (query direction) — varies
    We extract byte at offset 10 when frame is long enough; fall back None.
    """
    if len(frame_bytes) < 12 or frame_bytes[0] != 0xAA:
        return None
    return frame_bytes[10]


def _direction_of(csv_direction: str) -> str | None:
    if csv_direction == "toACdisplay":
        return "tx"
    if csv_direction == "fromACdisplay":
        return "rx"
    return None


def load_session(csv_path: Path, session_name: str) -> list[Frame]:
    """Read a pre-parsed session.csv and return wifi* frames as Frame objects."""
    frames: list[Frame] = []
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            channel = row.get("channel", "")
            if not channel.startswith("wifi"):
                continue
            direction = _direction_of(row.get("direction", ""))
            if direction is None:
                continue
            try:
                start = float(row["start_time"])
                length = int(row["packet_len"])
            except (KeyError, ValueError):
                continue
            hex_str = row.get("packet_content", "") or ""
            msg_type = _msg_type_of(_parse_hex_bytes(hex_str))
            frames.append(Frame(
                session=session_name,
                channel=channel,
                direction=direction,
                start=start,
                length=length,
                msg_type=msg_type,
                hex=hex_str,
            ))
    frames.sort(key=lambda f: f.start)
    return frames


# ── Metric extraction ─────────────────────────────────────────────────────

@dataclass
class GapObservation:
    session: str
    kind: str               # reply_latency | post_rx_silence | command_period | post_tx_total
    gap_ms: float
    ref_msg_type: int | None  # msg_type of the reference frame (TX for most kinds)
    ref_start: float


def extract_gaps(frames: list[Frame]) -> Iterator[GapObservation]:
    """Walk frames in time order and emit gap observations.

    Pairing rule for reply_latency: a TX is paired with the next RX iff that RX
    starts within REPLY_PAIR_WINDOW_S after TX end AND no other TX intervenes.
    """
    session = frames[0].session if frames else ""
    n = len(frames)

    # Index TX frames and find their immediate successor for both post_tx_total
    # (any next TX) and command_period (start-to-start).
    tx_indices = [i for i, f in enumerate(frames) if f.direction == "tx"]

    # Reply pairing and post_rx_silence.
    for i, tx_idx in enumerate(tx_indices):
        tx = frames[tx_idx]

        # Look forward for an RX reply before any other TX or timeout.
        reply: Frame | None = None
        for j in range(tx_idx + 1, n):
            if frames[j].start - tx.end > REPLY_PAIR_WINDOW_S:
                break
            if frames[j].direction == "tx":
                break
            if frames[j].direction == "rx":
                reply = frames[j]
                break

        if reply is not None:
            yield GapObservation(
                session=session,
                kind="reply_latency",
                gap_ms=(reply.start - tx.end) * 1000.0,
                ref_msg_type=tx.msg_type,
                ref_start=tx.start,
            )
            # post_rx_silence = reply.end → next TX start
            if i + 1 < len(tx_indices):
                next_tx = frames[tx_indices[i + 1]]
                yield GapObservation(
                    session=session,
                    kind="post_rx_silence",
                    gap_ms=(next_tx.start - reply.end) * 1000.0,
                    ref_msg_type=tx.msg_type,
                    ref_start=reply.end,
                )

        # command_period and post_tx_total, independent of reply existence.
        if i + 1 < len(tx_indices):
            next_tx = frames[tx_indices[i + 1]]
            yield GapObservation(
                session=session,
                kind="command_period",
                gap_ms=(next_tx.start - tx.start) * 1000.0,
                ref_msg_type=tx.msg_type,
                ref_start=tx.start,
            )
            yield GapObservation(
                session=session,
                kind="post_tx_total",
                gap_ms=(next_tx.start - tx.end) * 1000.0,
                ref_msg_type=tx.msg_type,
                ref_start=tx.end,
            )


# ── Aggregation ───────────────────────────────────────────────────────────

def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return float("nan")
    k = (len(sorted_values) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(sorted_values) - 1)
    if lo == hi:
        return sorted_values[lo]
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo)


def summarize(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    s = sorted(values)
    return {
        "n": len(s),
        "min": round(s[0], 2),
        "p5": round(_percentile(s, 0.05), 2),
        "p50": round(_percentile(s, 0.50), 2),
        "p95": round(_percentile(s, 0.95), 2),
        "max": round(s[-1], 2),
        "mean": round(statistics.mean(s), 2),
        "stdev": round(statistics.pstdev(s), 2) if len(s) > 1 else 0.0,
    }


def summarize_by_kind(gaps: list[GapObservation]) -> dict:
    out: dict[str, dict] = {}
    for kind in ("reply_latency", "post_rx_silence", "command_period", "post_tx_total"):
        vals = [g.gap_ms for g in gaps if g.kind == kind]
        out[kind] = summarize(vals)
    return out


def summarize_by_msg_type(gaps: list[GapObservation], kind: str) -> dict:
    out: dict[str, dict] = {}
    buckets: dict[int, list[float]] = {}
    for g in gaps:
        if g.kind != kind or g.ref_msg_type is None:
            continue
        buckets.setdefault(g.ref_msg_type, []).append(g.gap_ms)
    for mt, vals in sorted(buckets.items()):
        out[f"0x{mt:02x}"] = summarize(vals)
    return out


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> int:
    all_gaps: list[GapObservation] = []
    per_session: dict[str, dict] = {}

    session_dirs = sorted(
        (d for d in SESSIONS_ROOT.iterdir() if d.is_dir() and d.name.startswith("Session ")),
        key=lambda d: int(d.name.split()[1]),
    )

    for sdir in session_dirs:
        name = sdir.name
        csv_path = sdir / "session.csv"
        if not csv_path.exists():
            per_session[name] = {"skipped": "no session.csv"}
            continue
        frames = load_session(csv_path, name)
        if not frames:
            per_session[name] = {"skipped": "no wifi* frames"}
            continue
        gaps = list(extract_gaps(frames))
        all_gaps.extend(gaps)

        tx_count = sum(1 for f in frames if f.direction == "tx")
        rx_count = sum(1 for f in frames if f.direction == "rx")
        duration = frames[-1].start - frames[0].start

        per_session[name] = {
            "wifi_frames": len(frames),
            "tx_count": tx_count,
            "rx_count": rx_count,
            "duration_s": round(duration, 2),
            "by_kind": summarize_by_kind(gaps),
        }

    # Write outputs.
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Gaps CSV.
    with (OUT_DIR / "timing_gaps_all.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["session", "kind", "gap_ms", "ref_msg_type_hex", "ref_start_s"])
        for g in all_gaps:
            w.writerow([
                g.session, g.kind, f"{g.gap_ms:.3f}",
                f"0x{g.ref_msg_type:02x}" if g.ref_msg_type is not None else "",
                f"{g.ref_start:.6f}",
            ])

    # Per-session JSON.
    (OUT_DIR / "timing_per_session.json").write_text(
        json.dumps(per_session, indent=2)
    )

    # Aggregate summary.
    aggregate = {
        "sessions_with_data": sum(
            1 for v in per_session.values() if "wifi_frames" in v
        ),
        "total_wifi_frames": sum(
            v.get("wifi_frames", 0) for v in per_session.values()
        ),
        "total_observations": len(all_gaps),
        "by_kind": summarize_by_kind(all_gaps),
        "reply_latency_by_msg_type": summarize_by_msg_type(all_gaps, "reply_latency"),
        "post_tx_total_by_msg_type": summarize_by_msg_type(all_gaps, "post_tx_total"),
    }
    (OUT_DIR / "timing_summary.json").write_text(json.dumps(aggregate, indent=2))

    # Console summary.
    print(f"Sessions processed: {aggregate['sessions_with_data']}")
    print(f"Total wifi frames: {aggregate['total_wifi_frames']}")
    print(f"Total gap observations: {aggregate['total_observations']}")
    print()
    print("Aggregate (ms):")
    for kind, stats in aggregate["by_kind"].items():
        if stats.get("n", 0) == 0:
            continue
        print(
            f"  {kind:18s}  n={stats['n']:5d}  "
            f"min={stats['min']:7.2f}  p50={stats['p50']:7.2f}  "
            f"p95={stats['p95']:7.2f}  max={stats['max']:7.2f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
