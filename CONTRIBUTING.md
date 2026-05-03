# Contributing to blaueis-hvacshark-traces

Captures are welcome. This project is CC0 — by submitting a capture you agree that your contribution is dedicated to the public domain under the same terms. (Exception: the `external-captures/` subtree, where each folder carries its own provenance and possibly a different license.)

## Before you capture

- For a new device or bus you want to submit, **open an issue first**. We may be able to suggest capture parameters or point you at an existing session that covers the same ground.
- Read [`AGENTS.md`](https://github.com/fabcoded/blaueis-hvacshark/blob/master/AGENTS.md) in the companion [blaueis-hvacshark](https://github.com/fabcoded/blaueis-hvacshark) repo — it describes capture conventions, confidence labels, and session-layout expectations.

## Session layout

```
<Device>/
  README.md              Device overview, bus list, session index
  Session N/
    SessionNotes.md      Operator log — initial state, sequence of actions
    findings.md          Analysis output — field encodings, confidence levels, open questions
    channels.yaml        Channel config for the pcap converter
    Session N.csv        Pre-decoded Saleae Logic export (converter input)
    session.pcap         Converted pcap, open directly in Wireshark
```

`SessionNotes.md` is the operator log — what state the device was in, what you did, in order, with timestamps where useful. `findings.md` is the analysis output — what you decoded, with confidence labels.

## Citation rule — the one that matters

Analysis in `findings.md` is documented as **our own observation**. When editing, **never**:

- Reference file paths, function names, or line numbers from external implementations.
- Copy content from external source code — comments, variable names, logic blocks.

A single README-level acknowledgment line names community projects (see [README.md#acknowledgments](README.md#acknowledgments)). Cross-reference to specs in [blaueis-hvacshark](https://github.com/fabcoded/blaueis-hvacshark) by section anchor (e.g. "§3.2 of serial_protocol.md"), not by file path of a third-party project.

## External captures

Contributions from other people's public captures go under `external-captures/<group>/`. Each subfolder MUST have a `capture.yaml` with at least:

```yaml
source:  <URL or citation>
author:  <original author name or handle>
license: <SPDX identifier or explicit terms>
notes:   <optional — caveats, what the capture covers>
```

The `capture.yaml` header is the single source of truth for that subfolder's provenance. Do not merge its content into the repo's top-level README — keep provenance next to the data.

## Confidence labels

```
confirmed > consistent > hypothesis > disputed > unknown
```

In `findings.md`, every decoded field carries a label. Hardware verification = `confirmed`. Multiple consistent captures with no round-trip = `consistent`. One capture with a plausible interpretation = `hypothesis`.

## License and attribution

By contributing, you dedicate your contribution to the public domain under [CC0 1.0 Universal](LICENSE), except where `external-captures/*/capture.yaml` declares otherwise. If you have attribution or licensing concerns, please open an issue — we will respond promptly.
