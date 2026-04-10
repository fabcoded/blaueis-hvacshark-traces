#!/usr/bin/env python3
"""
analyze_eev_position.py — Extract and cross-validate EEV (electronic expansion
valve) position from R/T C1 Group 3 responses, correlated with XYE operating
state from the same capture sessions.

R/T C1 Group 3 fields (serial_protocol.md §4.2.3, mill1000 Finding 11):
  body[10]  Outdoor DC fan speed    raw × 8 = RPM
  body[11]  EEV actual position     raw × 8 = steps
  body[12]  Outdoor return air temp raw AD value
  body[13]  Outdoor DC bus voltage  raw (169–179 observed)
  body[16]  Target compressor freq  raw Hz

XYE fields for correlation:
  C0 byte[8]   Operating mode
  C4 byte[22]  Tp discharge temperature  (raw-40)/2 °C
  C0 byte[14]  T3 outdoor coil           (raw-40)/2 °C

VRF manual (KJR-86S/BK) confirms: check #16 = "EEV opening (actual opening/8)"
— same ×8 encoding as mill1000 Finding 11.

Usage:
    python analyze_eev_position.py [session_dirs...]
"""

import struct, sys, bisect
from pathlib import Path
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

MAX_DT = 3.0  # seconds

BUS_XYE = 0x00
BUS_RT  = 0x03

MODE_NAMES = {
    0x00: 'Off', 0x80: 'Pwr', 0x81: 'Fan', 0x82: 'Dry', 0x84: 'Heat',
    0x88: 'Cool', 0x90: 'Auto', 0x91: 'A+Fan', 0x94: 'A+Heat', 0x98: 'A+Cool',
}

# ── pcap reader ──────────────────────────────────────────────────────────

def read_pcap(path):
    with open(path, 'rb') as f:
        ghdr = f.read(24)
        if len(ghdr) < 24:
            return
        magic = struct.unpack('<I', ghdr[0:4])[0]
        if magic == 0xa1b2c3d4:
            endian = '<'
        elif magic == 0xd4c3b2a1:
            endian = '>'
        else:
            return
        while True:
            phdr = f.read(16)
            if len(phdr) < 16:
                break
            ts_sec, ts_usec, incl_len, orig_len = struct.unpack(endian + 'IIII', phdr)
            data = f.read(incl_len)
            if len(data) < incl_len:
                break
            yield (ts_sec + ts_usec / 1_000_000.0, data)


def parse_hvac_shark(pkt_data):
    if len(pkt_data) < 42 + 13:
        return None
    payload = pkt_data[42:]
    if payload[:10] != b'HVAC_shark':
        return None
    bus_type = payload[11]
    version = payload[12]
    if version == 0x00:
        proto_data = payload[13:]
    elif version == 0x01:
        off = 13
        if off >= len(payload):
            return None
        n = payload[off]; off += 1 + n
        if off >= len(payload):
            return None
        m = payload[off]; off += 1 + m
        if off >= len(payload):
            return None
        c = payload[off]; off += 1 + c
        proto_data = payload[off:]
    else:
        return None
    return (bus_type, bytes(proto_data))


# ── Frame extraction ─────────────────────────────────────────────────────

def extract_frames(pcap_path):
    g3_frames = []     # R/T C1 Group 3: [(ts, body)]
    xye_c0 = []        # XYE C0/C3 32-byte response: [(ts, proto)]
    xye_c4 = []        # XYE C4/C6 32-byte response: [(ts, proto)]

    for ts, pkt_data in read_pcap(pcap_path):
        parsed = parse_hvac_shark(pkt_data)
        if parsed is None:
            continue
        bus_type, proto = parsed

        if bus_type == BUS_XYE and len(proto) == 32 and proto[0] == 0xAA:
            cmd = proto[1]
            if cmd in (0xC0, 0xC3):
                xye_c0.append((ts, proto))
            elif cmd in (0xC4, 0xC6):
                xye_c4.append((ts, proto))

        elif bus_type == BUS_RT and len(proto) >= 15 and proto[0] == 0x55:
            if len(proto) >= 11:
                msg_type = proto[10]
                if msg_type == 0x03:  # Response
                    body = proto[11:]
                    if len(body) >= 17 and body[0] == 0xC1:
                        group = body[3] & 0x0F
                        if group == 3:
                            g3_frames.append((ts, body))

    for lst in (g3_frames, xye_c0, xye_c4):
        lst.sort(key=lambda x: x[0])

    return g3_frames, xye_c0, xye_c4


def find_nearest(ts, sorted_list):
    idx = bisect.bisect_left(sorted_list, (ts,))
    best = None
    best_dt = float('inf')
    for i in (idx - 1, idx):
        if 0 <= i < len(sorted_list):
            dt = abs(sorted_list[i][0] - ts)
            if dt < best_dt:
                best_dt = dt
                best = sorted_list[i]
    return best, best_dt


# ── Main ─────────────────────────────────────────────────────────────────

def process_session(pcap_path, label):
    g3_frames, xye_c0, xye_c4 = extract_frames(pcap_path)

    print(f"\n{'=' * 78}")
    print(f"  {label}")
    print(f"  R/T C1-G3: {len(g3_frames)}, XYE C0/C3: {len(xye_c0)}, "
          f"XYE C4/C6: {len(xye_c4)}")
    print(f"{'=' * 78}")

    if not g3_frames:
        print("  No R/T C1 Group 3 frames — skipping")
        return None

    # ── Raw distributions ────────────────────────────────────────────
    eev_dist = Counter()
    fan_dist = Counter()
    freq_dist = Counter()
    for _, body in g3_frames:
        fan_dist[body[10]] += 1
        eev_dist[body[11]] += 1
        freq_dist[body[16]] += 1

    print(f"\n  body[10] outdoor fan (×8 RPM):")
    for val, cnt in sorted(fan_dist.items()):
        print(f"    0x{val:02X} ({val:3d}) → {val*8:5d} RPM : {cnt}×")

    print(f"\n  body[11] EEV position (×8 steps):")
    for val, cnt in sorted(eev_dist.items()):
        print(f"    0x{val:02X} ({val:3d}) → {val*8:5d} steps : {cnt}×")

    print(f"\n  body[16] target compressor freq (Hz):")
    for val, cnt in sorted(freq_dist.items()):
        print(f"    0x{val:02X} ({val:3d}) → {val:5d} Hz    : {cnt}×")

    # ── Cross-correlate with XYE state ───────────────────────────────
    rows = []
    for ts_g3, body in g3_frames:
        row = {
            'ts': ts_g3,
            'fan_raw': body[10],
            'fan_rpm': body[10] * 8,
            'eev_raw': body[11],
            'eev_steps': body[11] * 8,
            'out_air_raw': body[12],
            'dc_bus_raw': body[13],
            'comp_freq': body[16],
        }

        # Nearest XYE C0/C3
        nearest, dt = find_nearest(ts_g3, xye_c0)
        if nearest is not None and dt <= MAX_DT:
            _, p = nearest
            row['mode'] = p[8]
            row['mode_name'] = MODE_NAMES.get(p[8], f'0x{p[8]:02X}')
            row['t1_c'] = (p[11] - 40) / 2.0
            row['t3_c'] = (p[14] - 40) / 2.0
            row['c0_dt'] = dt
            row['c0_proto'] = p  # store full 32 bytes for byte comparison

        # Nearest XYE C4/C6
        nearest, dt = find_nearest(ts_g3, xye_c4)
        if nearest is not None and dt <= MAX_DT:
            _, p = nearest
            row['tp_c'] = (p[22] - 40) / 2.0
            row['t4_c'] = (p[21] - 40) / 2.0
            row['c4_dt'] = dt
            row['c4_proto'] = p  # store full 32 bytes for byte comparison

        rows.append(row)

    # ── Timeline view ────────────────────────────────────────────────
    if rows and 'mode_name' in rows[0]:
        print(f"\n  Timeline (all {len(rows)} G3 frames):")
        print(f"  {'t(s)':>8s}  {'Mode':<8s}  {'Fan RPM':>8s}  {'EEV stp':>8s}  "
              f"{'Freq Hz':>8s}  {'T1°C':>6s}  {'Tp°C':>6s}  {'T3°C':>6s}  {'T4°C':>6s}")
        print(f"  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*6}  {'-'*6}  {'-'*6}  {'-'*6}")

        t0 = rows[0]['ts']
        for row in rows:
            t_rel = row['ts'] - t0
            mode = row.get('mode_name', '—')
            fan = row['fan_rpm']
            eev = row['eev_steps']
            freq = row['comp_freq']
            t1 = f"{row['t1_c']:.1f}" if 't1_c' in row else '—'
            tp = f"{row['tp_c']:.1f}" if 'tp_c' in row else '—'
            t3 = f"{row['t3_c']:.1f}" if 't3_c' in row else '—'
            t4 = f"{row['t4_c']:.1f}" if 't4_c' in row else '—'
            print(f"  {t_rel:8.1f}  {mode:<8s}  {fan:8d}  {eev:8d}  "
                  f"{freq:8d}  {t1:>6s}  {tp:>6s}  {t3:>6s}  {t4:>6s}")

    # ── Physical plausibility check ──────────────────────────────────
    print(f"\n  Plausibility:")
    eev_vals = [body[11] * 8 for _, body in g3_frames]
    fan_vals = [body[10] * 8 for _, body in g3_frames]
    print(f"    EEV range: {min(eev_vals)}–{max(eev_vals)} steps "
          f"(typical split AC: 50–500)")
    print(f"    Fan range: {min(fan_vals)}–{max(fan_vals)} RPM "
          f"(typical outdoor: 0–900)")

    # Check correlation: when compressor runs (freq>0), fan should spin and EEV open
    running = [(r['comp_freq'], r['fan_rpm'], r['eev_steps'])
               for r in rows if r['comp_freq'] > 0]
    idle = [(r['comp_freq'], r['fan_rpm'], r['eev_steps'])
            for r in rows if r['comp_freq'] == 0]

    if running:
        avg_eev_run = sum(e for _, _, e in running) / len(running)
        avg_fan_run = sum(f for _, f, _ in running) / len(running)
        print(f"    Compressor ON ({len(running)} frames): "
              f"avg fan={avg_fan_run:.0f} RPM, avg EEV={avg_eev_run:.0f} steps")
    if idle:
        avg_eev_idle = sum(e for _, _, e in idle) / len(idle)
        avg_fan_idle = sum(f for _, f, _ in idle) / len(idle)
        print(f"    Compressor OFF ({len(idle)} frames): "
              f"avg fan={avg_fan_idle:.0f} RPM, avg EEV={avg_eev_idle:.0f} steps")

    if running and idle:
        avg_run = sum(e for _, _, e in running) / len(running)
        avg_idl = sum(e for _, _, e in idle) / len(idle)
        if avg_run > avg_idl:
            print(f"    ✓ EEV opens wider when compressor runs "
                  f"({avg_run:.0f} vs {avg_idl:.0f} steps)")
        else:
            print(f"    ? EEV does NOT open wider when running — unexpected")

    return rows


def main():
    if len(sys.argv) > 1:
        session_dirs = sys.argv[1:]
    else:
        base = Path(r"c:\Users\fabia\OneDrive\Elektronik und Basteln\HVAC and Heat"
                     r"\HVAC Shark DEV\HVAC-shark-dumps"
                     r"\Midea-XtremeSaveBlue-logicanalyzer")
        session_dirs = []
        for i in range(3, 14):
            d = base / f"Session {i}"
            if d.exists():
                session_dirs.append(str(d))

    all_rows = []
    for sd in session_dirs:
        p = Path(sd)
        pcap = p / "session.pcap"
        if not pcap.exists():
            continue
        result = process_session(str(pcap), p.name)
        if result:
            all_rows.extend(result)

    # ── Global summary ────────────────────────────────────────────────
    if not all_rows:
        print("\nNo R/T C1 Group 3 data found in any session.")
        return

    print(f"\n{'=' * 78}")
    print(f"  GLOBAL SUMMARY — {len(all_rows)} C1 Group 3 frames across all sessions")
    print(f"{'=' * 78}")

    eev_all = Counter(r['eev_steps'] for r in all_rows)
    fan_all = Counter(r['fan_rpm'] for r in all_rows)
    freq_all = Counter(r['comp_freq'] for r in all_rows)

    print(f"\n  EEV position distribution (×8 steps):")
    for val, cnt in sorted(eev_all.items()):
        print(f"    {val:5d} steps : {cnt:5d}×")

    print(f"\n  Outdoor fan distribution (×8 RPM):")
    for val, cnt in sorted(fan_all.items()):
        print(f"    {val:5d} RPM   : {cnt:5d}×")

    print(f"\n  Compressor target freq (Hz):")
    for val, cnt in sorted(freq_all.items()):
        print(f"    {val:5d} Hz    : {cnt:5d}×")

    # ── Mode vs EEV summary ──────────────────────────────────────────
    mode_eev = {}
    for r in all_rows:
        if 'mode_name' not in r:
            continue
        m = r['mode_name']
        if m not in mode_eev:
            mode_eev[m] = []
        mode_eev[m].append(r['eev_steps'])

    if mode_eev:
        print(f"\n  EEV position by operating mode:")
        print(f"  {'Mode':<10s}  {'N':>5s}  {'Min':>6s}  {'Avg':>6s}  {'Max':>6s}")
        print(f"  {'-'*10}  {'-'*5}  {'-'*6}  {'-'*6}  {'-'*6}")
        for mode in sorted(mode_eev.keys()):
            vals = mode_eev[mode]
            avg = sum(vals) / len(vals)
            print(f"  {mode:<10s}  {len(vals):5d}  {min(vals):6d}  {avg:6.0f}  {max(vals):6d}")

    # ── Byte-by-byte EEV correlation against XYE frames ──────────────
    # For each G3 frame with a matched XYE C0 or C4 response, compare
    # EEV raw and EEV÷8 against every byte in the XYE frame.
    print(f"\n{'=' * 78}")
    print(f"  EEV BYTE-BY-BYTE CORRELATION — R/T G3 body[11] vs XYE bytes")
    print(f"{'=' * 78}")

    # Only use pairs where EEV varies (skip constant-EEV sessions)
    eev_varying = [r for r in all_rows if r['eev_raw'] > 0]
    if len(set(r['eev_raw'] for r in eev_varying)) < 3:
        print(f"  Insufficient EEV variation ({len(set(r['eev_raw'] for r in eev_varying))} "
              f"distinct values) — skipping correlation")
    else:
        for frame_type, proto_key in [('C0/C3', 'c0_proto'), ('C4/C6', 'c4_proto')]:
            pairs = [(r['eev_raw'], r[proto_key]) for r in all_rows if proto_key in r]
            if not pairs:
                print(f"\n  No {frame_type} pairs")
                continue

            n_pairs = len(pairs)
            n_distinct_eev = len(set(eev for eev, _ in pairs))

            print(f"\n  vs XYE {frame_type} response ({n_pairs} pairs, "
                  f"{n_distinct_eev} distinct EEV values):")
            print(f"  {'Byte':>6s}  {'match: raw':>12s}  {'match: raw/8':>12s}  "
                  f"{'mean|Δ| raw':>12s}  {'mean|Δ| /8':>12s}  {'XYE range':>16s}")
            print(f"  {'-'*6}  {'-'*12}  {'-'*12}  {'-'*12}  {'-'*12}  {'-'*16}")

            for byte_idx in range(6, 30):  # payload bytes only
                diffs_raw = []
                diffs_div8 = []
                xye_vals = set()
                for eev_raw, proto in pairs:
                    xye_byte = proto[byte_idx]
                    xye_vals.add(xye_byte)
                    diffs_raw.append(abs(eev_raw - xye_byte))
                    diffs_div8.append(abs(eev_raw - xye_byte / 8.0) if xye_byte > 0 else abs(eev_raw))

                mean_raw = sum(diffs_raw) / len(diffs_raw)
                mean_div8 = sum(diffs_div8) / len(diffs_div8)
                exact_raw = sum(1 for d in diffs_raw if d == 0)
                exact_div8 = sum(1 for d in diffs_div8 if d < 0.5)

                marker = ''
                if mean_raw < 1.0 or mean_div8 < 1.0:
                    marker = ' <<<'
                elif mean_raw < 3.0 or mean_div8 < 3.0:
                    marker = ' << '
                elif mean_raw < 10.0 or mean_div8 < 10.0:
                    marker = ' <  '

                xye_range = f"0x{min(xye_vals):02X}–0x{max(xye_vals):02X}" if xye_vals else "—"
                n_xye_distinct = len(xye_vals)

                print(f"  [{byte_idx:2d}]   {exact_raw:5d}/{n_pairs:5d}  "
                      f"{exact_div8:5d}/{n_pairs:5d}  "
                      f"{mean_raw:12.2f}  {mean_div8:12.2f}  "
                      f"{xye_range:>12s} ({n_xye_distinct:2d}){marker}")

            # Also test: does any XYE byte × 8 match EEV steps?
            print(f"\n  Reverse test: XYE byte × 8 vs EEV steps (raw×8):")
            print(f"  {'Byte':>6s}  {'exact':>12s}  {'mean|Δ|':>12s}  {'XYE range':>16s}")
            print(f"  {'-'*6}  {'-'*12}  {'-'*12}  {'-'*16}")

            for byte_idx in range(6, 30):
                diffs = []
                xye_vals = set()
                for eev_raw, proto in pairs:
                    eev_steps = eev_raw * 8
                    xye_steps = proto[byte_idx] * 8
                    xye_vals.add(proto[byte_idx])
                    diffs.append(abs(eev_steps - xye_steps))

                mean_d = sum(diffs) / len(diffs)
                exact = sum(1 for d in diffs if d == 0)

                xye_range = f"0x{min(xye_vals):02X}–0x{max(xye_vals):02X}"
                n_xye_distinct = len(xye_vals)
                marker = ' <<<' if mean_d < 8.0 else (' << ' if mean_d < 24.0 else (' <  ' if mean_d < 80.0 else ''))
                print(f"  [{byte_idx:2d}]   {exact:5d}/{n_pairs:5d}  "
                      f"{mean_d:12.1f}  {xye_range:>12s} ({n_xye_distinct:2d}){marker}")


if __name__ == '__main__':
    main()
