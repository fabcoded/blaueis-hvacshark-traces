# blaueis-hvacshark-traces

Part of the [Blaueis](https://github.com/fabcoded) project umbrella.
Protocol library: [blaueis-libmidea](https://github.com/fabcoded/blaueis-libmidea).
Dissector + research: [blaueis-hvacshark](https://github.com/fabcoded/blaueis-hvacshark).

> Blaueis is a small glacier in the Bavarian Alps, retreating year by year.
> Use energy responsibly — climate change is real.

# Capture traces

This repository contains packet capture dumps from HVAC (Heating, Ventilation, and
Air Conditioning) systems, analysed using the Blaueis protocol toolkit.

## Companion repository: blaueis-hvacshark

The tools to capture, convert, and dissect the data in this repository live in the
main project:

**[blaueis-hvacshark](https://github.com/fabcoded/blaueis-hvacshark)**

Contents of blaueis-hvacshark relevant to this repository:
- **Wireshark Lua dissector** (`tools/dissector/`) — load this to decode `.pcap` files from this repo
- **ESP32 / Python live-capture dongle** (`tools/dongle/mid-xye/`) — for live capture over UDP
- **Protocol documentation** (`protocols/`) — spec, devices, analysis per manufacturer
- **`AGENTS.md`** — instructions for AI agents working across both repositories

The offline pcap converter that processes the raw Saleae exports in this repository:

```
logicanalyzer-tools/saleae_midea_recording_to_pcap.py
```

## Disclaimer

Please note that the data provided in this repository may contain errors, malformed
entries, or lack proper annotations. Users should not rely solely on this data for
critical applications. Always validate and verify the information before using it
in your projects.

**Brand names and trademarks**: Any manufacturer, product, or model names mentioned
in this repository (including but not limited to "Midea" and associated product
lines) are used solely to identify the hardware under test. Their use is purely
descriptive — to specify which physical device was captured — and does not imply
affiliation, endorsement, or any commercial relationship with the respective
trademark holders. All trademarks remain the property of their respective owners.

## Repository structure

Captures are organised by device, then by session:

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

## External captures

The `external-captures/` directory contains protocol frames sourced from
third-party community posts, forums, and public repositories. **These
subfolders may be licensed differently from the rest of this repository.**
Each subfolder's `capture.yaml` header states the original source, author,
and applicable license. Please review those headers before redistributing
any external-captures content.

## Devices

| Folder                          | Hardware                        |
|---------------------------------|---------------------------------|
| `Midea-XtremeSaveBlue-logicanalyzer` | Midea XtremeSaveBlue split A/C — display board (CN1, CN3, IR), logic analyzer |
| `Midea-XtremeSaveBlue-dongle`   | Midea XtremeSaveBlue split A/C — MFB-C XYE bus, blaueis-hvacshark ESP dongle |

## Usage

1. Install Wireshark
2. Install the blaueis-hvacshark dissector from the [blaueis-hvacshark repository](https://github.com/fabcoded/blaueis-hvacshark/tree/master/tools/dissector)
3. Open any `.pcap` file from this repository in Wireshark
4. Packets are automatically decoded by the dissector

## Compatibility

These dumps are meant to be used with the latest version of the blaueis-hvacshark Wireshark
dissector. Please ensure you have the latest version installed for proper decoding.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) — covers the session layout, the external-captures provenance format, the citation rule, and what good capture submissions look like.

## Related projects in this ecosystem

- [blaueis-hvacshark](https://github.com/fabcoded/blaueis-hvacshark) — dissector, live-capture dongle, and protocol specifications (companion tooling).
- [blaueis-libmidea](https://github.com/fabcoded/blaueis-libmidea) — Python library that consumes the protocol knowledge captured here.
- [blaueis-ha-midea](https://github.com/fabcoded/blaueis-ha-midea) — Home Assistant integration.
- [blaueis-esphome](https://github.com/fabcoded/blaueis-esphome) — ESP32 port of the gateway (placeholder).

## Acknowledgments

Captures here trace real Midea HVAC hardware on our workbench. Understanding what's on the wire, however, stands on many shoulders. A deep thank you to the open-source and home-automation community — especially the contributors around **Home Assistant** and the broader maker community — for their protocol research and for publishing it openly.

Community projects whose work informed what these captures are compared against:

- [dudanov/MideaUART](https://github.com/dudanov/MideaUART) — ESP/Arduino library for Midea UART.
- [chemelli74/midea-local](https://github.com/chemelli74/midea-local) — Python client for the Midea LAN protocol.
- [reneklootwijk/node-mideahvac](https://github.com/reneklootwijk/node-mideahvac) — Node.js driver for Midea AC.
- [NeoAcheron/midea-ac-py](https://github.com/NeoAcheron/midea-ac-py) — early Python Midea AC implementation.
- [wuwentao/midea_ac_lan](https://github.com/wuwentao/midea_ac_lan) — HA integration covering a broad Midea device set.
- [codeberg.org/xye/xye](https://codeberg.org/xye/xye) — XYE bus reference documentation.
- Countless forum threads, GitHub issues, and pull requests in the HA and ESPHome communities.

`external-captures/` subfolders carry their own provenance YAML and may be independently licensed — see each subfolder's `capture.yaml`.

If you believe your work is referenced here without proper attribution, or you have licensing concerns, please open an issue — we will respond promptly.

## For AI agents

AI agents working in this repository should follow the instructions in
[AGENTS.md](https://github.com/fabcoded/blaueis-hvacshark/blob/master/AGENTS.md)
in the companion blaueis-hvacshark repository. Unless otherwise advised by the repository
owner, `AGENTS.md` is the authoritative guide for working conventions, protocol
documentation standards, and confidence labelling.
