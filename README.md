# Niimbot B1 — print from Python, and use any label roll

A minimal, dependency-light client for the **Niimbot B1** label printer
(USB serial and Bluetooth LE), plus a documented, **reproducible firmware
patch** that lets the printer use third-party label rolls **without the RFID
chip** — full darkness, correct first-label alignment, and original speed when
you do use a tagged roll.

* No vendor app, no cloud, no external library for the protocol itself.
* The firmware patch is **built from source** (two small patch scripts), never
  distributed as a binary. See [`firmware/README.md`](firmware/README.md).

> **⚠️ Flashing firmware can brick your printer and voids the warranty.**
> Everything here is at your own risk. You can use the Python client with
> original (tagged) rolls without touching the firmware at all.

## Quick start — print from Python (no firmware change)

Requirements: Python 3.10+, and either `pyserial` (USB) or `bleak` (Bluetooth).

```sh
pip install -e .[usb]
```

Print an image (384 px wide = 48 mm; the head is 384 px @ 203 dpi):

```sh
python -m niimbot_b1                      # printer status + RFID roll info
python -m niimbot_b1 label.png -d 5       # gap labels (type 1), density 5 (darkest)
python -m niimbot_b1 receipt.png -d 5 -t 3  # continuous thermal paper (type 3)
```

Or use it as a library:

```python
from PIL import Image
from niimbot_b1 import B1Printer

with B1Printer() as p:              # auto-detects the USB port
    print(p.heartbeat())
    print(p.rfid_info())
    p.print_image(Image.open("label.png"), density=5)
```

Bluetooth LE works the same way (`pip install -e .[ble]`, then pass `--ble`):

```sh
python -m niimbot_b1 label.png -d 5 --ble
```

See [`docs/bluetooth.md`](docs/bluetooth.md) for macOS permission notes.

## Quick start — print without the RFID chip (firmware patch)

The firmware patch removes the chip check, restores full darkness without a
chip, seeks the label gap after the cover closes, and keeps fast original
printing when a tagged roll is present.

1. Get the two input firmware files and **build** the patched image:
   [`firmware/README.md`](firmware/README.md).
2. **Flash** it with `@mmote/niimblue-node` (or the [niim.blue](https://niim.blue)
   web flasher).
3. Print as usual — no chip required:

   ```sh
   python -m niimbot_b1 label.png -d 5       # gap labels, no chip, first label is correct
   python -m niimbot_b1 receipt.png -d 5 -t 3  # continuous paper
   ```

## What each piece does

| Piece | Purpose |
|---|---|
| `niimbot_b1/` | Python client (USB + BLE): status, RFID, printing |
| `examples/` | Small runnable examples using the API |
| `firmware/build_patched.py` | Reproducibly builds the patched firmware from two inputs |
| `docs/protocol.md` | The serial/BLE protocol and command reference |
| `docs/bluetooth.md` | Bluetooth LE usage |
| `docs/third-party-labels.md` | What the RFID chip does, and your options without it |
| `docs/firmware-analysis.md` | Full reverse-engineering write-up (addresses, patches) |
| `tools/re/` | Capstone helpers used for the firmware analysis |

## Why a firmware patch?

The B1 authenticates its rolls with an RFID chip. Without a chip, stock
firmware refuses the job (`0x14`), barely heats the head (faint output), and
doesn't align the first label after the cover is closed. The patch removes
those restrictions so ordinary, cheaper label rolls work. Details and the
trade-offs (speed, darkness) are in
[`docs/third-party-labels.md`](docs/third-party-labels.md) and
[`docs/firmware-analysis.md`](docs/firmware-analysis.md).

## FAQ

**My other client prints blank labels — why?**
Some clients send an older print sequence that ends the job too early on this
firmware. This client uses the niimbluelib `B1PrintTask` sequence, which works.
See [`docs/protocol.md`](docs/protocol.md).

**The port isn't found.**
List devices with `npx @mmote/niimblue-node scan`, or pass the port explicitly
with `-p /dev/cu.usbmodemB1_<serial>` (macOS) / `/dev/ttyACM0` (Linux).

**Bluetooth aborts with exit code 134 on macOS.**
Grant the terminal Bluetooth permission: *System Settings → Privacy & Security
→ Bluetooth*.

**Will I lose the original firmware?**
No — the build requires the unmodified firmware as an input, so you always have
a copy to flash back. Rollback instructions are in
[`firmware/README.md`](firmware/README.md).

## Attribution

* Print sequence: [MultiMote/niimbluelib](https://github.com/MultiMote/niimbluelib) (MIT).
* "Variant B" community patch (used as the firmware build base):
  [lotabout/niimbot](https://github.com/lotabout/niimbot).
* Reference client for the (non-working-on-B1) old sequence:
  [AndBondStyle/niimprint](https://github.com/AndBondStyle/niimprint).
* Official, unmodified firmware images: [fw.niim.blue](https://fw.niim.blue).

## License

[MIT](LICENSE) for the code and documentation in this repository. The firmware
input files are obtained separately and are not distributed here.
