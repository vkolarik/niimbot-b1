# Third-party labels (printing without the RFID chip)

The Niimbot B1 authenticates its label rolls with an RFID chip glued to the
roll. This page explains what that chip actually does, what happens without it,
and what the firmware patch in this repo changes.

## What the RFID chip does

* The chip is read when the **cover is closed**. After a successful read the
  printer keeps the data in memory, so the chip can then be removed and the
  printer keeps working.
* The chip stores a UUID, a barcode, a serial number, a `total`/`used` counter,
  the label `capacity`, and a `label_type` (e.g. labels-with-gaps).
* The `used` counter increments with every print and is persisted on the tag,
  so it survives opening the cover.

## Stock firmware behaviour without a chip

With no tag read, the stock firmware:

1. **Refuses the print job** with error `0x14` (`WriteRfidFail`) in some
   configurations.
2. **Almost disables the heating element**, so even if a job is accepted, the
   output is faint or blank.
3. **Does not seek the label gap** when the cover is closed. The first print
   after closing the cover lands across two labels; the gap is only found
   again *after* a print, so from the second label onward it is correct.

## The patched firmware

The patch built by `firmware/build_patched.py` changes this:

* **No `0x14` refusal** — the job runs without a chip.
* **Full darkness without a chip** — the heating-time cap that was silently
  applied without a chip is removed (this is the "variant B" part, inherited
  from the [lotabout/niimbot](https://github.com/lotabout/niimbot) community
  patch).
* **Gap seek without a chip** — after the cover is closed the printer seeks
  the label gap by itself, so the first print lands on a single label. No
  blank "alignment" print is needed.
* **Original speed with a chip** — when a tagged (original) roll is present,
  printing keeps the fast, original timing (~2 s per label). Without a chip it
  is intentionally slower (~5 s per label) because the head runs at full power.

The technical details are in
[`firmware-analysis.md`](firmware-analysis.md).

## Do I even need the firmware patch?

| What you want | What you need |
|---|---|
| Print from Python on original rolls | Just the client (`niimbot_b1`); no firmware change |
| Use third-party rolls, keeping the original chip next to the reader when closing the cover | No firmware change (the printer reads the chip at cover close, then you can remove it) |
| Use third-party rolls, **no chip at all**, correct first label, full darkness | The patched firmware |

### Software-only workaround (stock firmware, one wasted label)

Without the chip, the stock firmware does find the gap *after* a print. So you
can print a blank page right after closing the cover to advance to the next
gap, wasting one label, then print normally:

```python
from PIL import Image
from niimbot_b1 import B1Printer

with B1Printer() as p:
    p.align()          # one blank page, wastes a label
    p.print_image(img, density=5)
```

This still produces faint prints (the heating cap), so it is only useful for
testing positioning.

## Label types

The `0x23` label-type value matters:

* **1** — labels with gaps (standard die-cut rolls). The printer seeks the
  optical gap.
* **2** — black-mark labels.
* **3** — continuous thermal paper (no gaps). The firmware uses a **fixed feed**
  from calibration constants instead of seeking a gap, so the patch's
  alignment step only advances a fixed amount and never loops.
* **5** — transparent labels.

For continuous paper, print with `-t 3`:

```sh
python -m niimbot_b1 receipt.png -d 5 -t 3
```
