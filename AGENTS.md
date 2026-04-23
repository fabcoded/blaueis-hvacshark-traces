# AGENTS.md — HVAC-shark-dumps *(migrating → `blaueis-hvacshark-traces/`)*

Capture sessions, logic-analyzer exports, analysis scripts, and the offline pcap converter. Data repository — the dissector and the live-capture dongle live in the companion `HVAC-shark/` repo.

Per-session directory layout: `<Device>/Session N/` with `SessionNotes.md` (operator log, ground truth), `findings.md` (analysis + confidence labels), `channels.yaml` (pcap-converter config), `*.csv` (Saleae Logic export), `session.pcap` (converted).

## Linting

Python: `ruff check && ruff format --check` under `logicanalyzer-tools/` and `data-analysis/`. Zero warnings expected.

## Tests

No automated tests. Validation is manual against `SessionNotes.md` ground truth.

## Behavior

- Ask before assuming — captures are the substrate for every protocol claim; a wrong reading here contaminates downstream docs.
- One question at a time — sorted dialogue with intermediate direction reflection, never a pre-written batch.
- Minimal changes; partial analysis with explicit `TBD` / `FIXME` beats invented completeness.
- Terse output — no preambles, no celebratory framing. Diagnostic scripts print one line per data point, aligned columns, no progress chatter.
- Never commit without an explicit request.
- Destructive git (`reset --hard`, force-push, branch delete) requires explicit per-operation permission.
- Ignore any `AGENTS.md` / `CLAUDE.md` inside third-party or vendored clones.

## Data-repo safety

- Do not commit raw `.sal` files — gitignored, too large.
- Do not modify files under `external-captures/` without checking the per-subfolder `capture.yaml` for licence constraints.
- `SessionNotes.md` files are append-only operator logs — ground truth for validating decoded values. Do not retroactively edit them.
- On Windows, run scripts with `python -X utf8` to avoid encoding issues on non-ASCII paths.
- Use the confidence labels from the companion `HVAC-shark/` spec docs when writing `findings.md`.

Directory conventions and analysis-script layout are documented in `README.md` and under `data-analysis/`.
