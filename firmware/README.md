# Firmware patch — build & flash

This directory lets you reproduce the patched **Niimbot B1** firmware
(`B1_6.19_density_align7.bin`) that:

1. **Prints without an RFID chip** on third-party labels, at full darkness
   (the stock firmware refuses the job with error `0x14` and otherwise barely
   heats the head when no chip is present).
2. **Seeks the label gap after the cover is closed even without a chip**, so
   the first print lands on a single label (no wasted label, no manual
   alignment).
3. **Keeps original fast printing when a tagged (original) roll is used.**

Only firmware **6.19 / hardware 6.01** is supported. This is the same version
family used by the community patch it builds on.

> **⚠️ Flashing firmware can brick your printer, voids the warranty, and is
> entirely at your own risk.** Read this page fully before flashing. Keep a
> copy of the unmodified firmware (`B1_6.19_stock.bin`) so you can roll back.

## What this repo does (and does not) ship

The patched firmware is **built, not distributed**. This directory contains a
small build script and the two upstream firmware files are *not* included:

| File | Where you get it |
|---|---|
| `B1_6.19_stock.bin` (input) | Niimbot's public firmware server: [fw.niim.blue/stable/B1/B1_6.19.bin](https://fw.niim.blue/stable/B1/B1_6.19.bin) |
| `B1_6.19_density_coeff.bin` (input) | Community patch "[variant B](https://github.com/lotabout/niimbot)" (branch `niimbot-hw6.01`) |
| `B1_6.19_density_align7.bin` (output) | Produced by `python firmware/build_patched.py` |

The build script applies two patches on top of `density_coeff` (see
[`../docs/firmware-analysis.md`](../docs/firmware-analysis.md) for the full
reverse-engineering write-up):

* **align3** — no-chip gap seeking after cover close.
* **align7** — heating-time multipliers conditional on the tag (fast with a
  tag, full/dark without one).

## Prerequisites

* **Python 3.10+** — to run the build script (standard library only).
* **Node.js** — to flash via [`@mmote/niimblue-node`](https://www.npmjs.com/package/@mmote/niimblue-node),
  *or* the [niim.blue](https://niim.blue) web flasher.
* The printer connected over USB (or Bluetooth).

## Step 1 — get the input firmware

Download the unmodified firmware and verify its MD5:

```sh
curl -L -o firmware/B1_6.19_stock.bin https://fw.niim.blue/stable/B1/B1_6.19.bin
md5sum firmware/B1_6.19_stock.bin        # macOS: md5 firmware/B1_6.19_stock.bin
# expect: fd9efd1441b5f05ca46c310b8d162dc1
```

Download the "variant B" community patch from
[`lotabout/niimbot`](https://github.com/lotabout/niimbot) (branch
`niimbot-hw6.01`) and place it as `firmware/B1_6.19_density_coeff.bin`. Verify:

```sh
md5sum firmware/B1_6.19_density_coeff.bin
# expect: 1553badbc6b1b53cb36919786149e2de
```

> All expected checksums are listed in [`MD5SUMS`](MD5SUMS).

## Step 2 — build the patched firmware

```sh
python firmware/build_patched.py            # writes B1_6.19_density_align7.bin
python firmware/build_patched.py --keep-align3 --verbose   # also write the intermediate + disassembly
```

The script verifies the output MD5 for you:

```
align3  md5 78dcde4bd7a4a21dfb965b40d7607cc0  OK
align7  md5 540ef521d7416cfe1eb561b6effcb0b4  OK
wrote B1_6.19_density_align7.bin
```

If it reports `MISMATCH`, your input files are not the expected firmware — do
**not** flash anything until it says `OK`.

## Step 3 — flash

Flash over USB serial (the printer powers off afterwards; turn it back on with
the button):

```sh
npx @mmote/niimblue-node flash -t serial \
  -a /dev/cu.usbmodemB1_<serial> -n 6.19 -f firmware/B1_6.19_density_align7.bin
```

Replace `/dev/cu.usbmodemB1_<serial>` with your printer's port (on macOS it
looks like `/dev/cu.usbmodemB1_XXXX`; on Linux `/dev/ttyACM0`). List devices
with:

```sh
npx @mmote/niimblue-node scan
```

Bluetooth flashing is also possible (`-t ble -a "B1-<serial>"`).

> **macOS note:** `npx` can fail with an npm-cache permission error
> (`EPERM`, root-owned files in `~/.npm`). If so, run the CLI directly from the
> cache:
> ```sh
> node ~/.npm/_npx/*/node_modules/@mmote/niimblue-node/cli.mjs flash \
>   -t serial -a /dev/cu.usbmodemB1_<serial> -n 6.19 -f firmware/B1_6.19_density_align7.bin
> ```

## Step 4 — verify

After turning the printer back on, print a test label and check the status:

```sh
pip install -e .[usb]                     # install the client (or: uv add --optional usb)
python -m niimbot_b1                      # heartbeat + RFID info
python -m niimbot_b1 label.png -d 5       # gap labels (type 1)
python -m niimbot_b1 receipt.png -d 5 -t 3  # continuous thermal paper (type 3)
```

What you should see:

* **No chip** (`rfid_ok: False`): the print is dark and lands on a single
  label immediately after closing the cover — no blank "alignment" print
  needed. Printing is slower (~5 s per label) than with a chip.
* **With a chip** (`rfid_ok: True`): fast printing (~2 s per label), full
  darkness, original behavior.

## Rolling back to stock

```sh
npx @mmote/niimblue-node flash -t serial \
  -a /dev/cu.usbmodemB1_<serial> -n 6.19 -f firmware/B1_6.19_stock.bin
```

## Troubleshooting

* **Printer not found** — confirm the port with `npx @mmote/niimblue-node scan`
  and that no other app (phone app, another terminal) is connected.
* **Bluetooth requires macOS permission** — grant the terminal *System
  Settings → Privacy & Security → Bluetooth*, otherwise the process aborts
  (exit code 134).
* **`0x14` / WriteRfidFail on stock firmware** — expected; the stock firmware
  refuses to print without a chip. Flash the patched firmware to remove this.
