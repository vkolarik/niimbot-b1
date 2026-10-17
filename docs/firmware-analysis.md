# Firmware reverse-engineering notes

A write-up of how the patched firmware in `firmware/` was derived, for anyone
who wants to understand, verify, or extend it.

* Target: **Niimbot B1**, hardware **6.01**, firmware **6.19**
  (`B1_6.19_stock.bin`, 124,436 bytes).
* CPU: Cortex-M0 (Thumb), image base address `0x01010000`.
* The community patch "[variant B](https://github.com/lotabout/niimbot)"
  (branch `niimbot-hw6.01`) is used as a starting point; the two patches below
  are applied on top of it.

All offsets are absolute addresses; subtract `0x01010000` to get a file offset.

## Tooling

The `tools/re/` directory contains small Capstone-based helpers used for the
analysis:

* `dis.py <bin> <start> <n>` — disassemble `n` instructions, resolving
  PC-relative literal-pool loads.
* `fulldis.py <bin>` — linear disassembly of the whole image with literal
  values and branch targets annotated.
* `xref.py <bin> <target...>` — find `bl`/`b` calls and literal references to
  the given addresses.
* `fieldref.py <bin> <base> <offset>` — find `ldrb`/`strb [rX,#offset]` near a
  `ldr rX, =base`.
* `track.py <bin> <base...>` — like `fieldref`, but follows simple
  `adds rX,#imm` base adjustments (this is how the align flag was found).
* `litref.py <bin> <lo>-<hi>...` — find `ldr` instructions whose literal falls
  in a range.

Run them with Capstone available, e.g.:

```sh
uv run --no-project --with capstone python tools/re/dis.py firmware/B1_6.19_stock.bin 0x1025832 4
```

## Key data structures

* `cfg` — configuration struct, base `0x2073c` (includes `cfg[6]` = label type
  at `0x20742`, and density at `0x20740`).
* `[0x20637]` — the "align" flag: `1` means "seek the gap once, then clear".
* `[0x2e458]` — RFID tag data block:
  * `+0x08` = tag-present flag,
  * `+0x60` = label dimensions from the tag.
* `[0x204ca]` — heating mode (0 = full, 3 = attenuated).

## What a successful chip read does

`0x1024f88` (on a successful read):

* sets tag-present `[0x2e458+8] = 1`,
* sets `cfg[6] = tag.label_type`,
* calls `0x1017dd2(label_type)` to select the sensor threshold (also used by
  calibration, not chip-exclusive).

The tag-present flag is read in **14 places**: the renderers that attenuate
heating (`0x1014158`, `0x1015af2`, `0x1016116`), the paper-feed code
(`0x101752c`, `0x10177e6`), the `0x8E` calibration handler (`0x101db34`,
`0x101dca2`, `0x101ddf2`), the RFID-curve flag (patched in variant A/B:
`0x10205d4`, `0x1021ab2`, `0x1022314`, `0x1022a2c`, `0x1022b30`), and the align
block (`0x102582e`).

## Gap seeking / paper feed (`0x10174f2`)

The gap-search limit depends on the tag:

* **With tag, type != 3:** `min(1600*k, 16*k*(t[7]*t[0xe] + t[0xa]) + 48*k)`,
  where `t = 0x2e458+0x60` (tag data) and `k = [0x2007b] & 0x7f`.
* **Without tag:** `1600*k` (a fixed, looser limit).

The paper-type dispatch (from `cfg[6]`) then runs identically:

* `type 3` (continuous) → `0x10175cc`: **fixed feed** from calibration
  constants (`120.0f`, `~101.6f`), does **not** seek a gap.
* `type 2` (black mark) → `0x10175fa`.
* `type 1/5` (gaps / transparent) → real gap seeking.

So without a chip the gap *is* still searched for, just with a looser limit —
which by itself does not explain the "first label off by one" symptom.

## Why the first label was off without a chip

The align task (`0x10257d4`) has a block (`0x1025822`) that performs the
pre-print gap seek. That block is gated by two conditions:

1. the tag-present flag (`[0x2e458+8]`), checked at `0x1025832`, and
2. the align flag (`[0x20637] == 1`), checked at `0x102582a`.

The align flag is set to `1` in **exactly one place**: the *successful* chip
read path (`0x102541a`, inside `0x102536e`). The no-chip fallback
(`0x102543e`) instead *clears* it. So without a chip the flag is never set and
the align block never runs — hence the first print lands across two labels.

Two earlier attempts failed for these reasons:

* **Attempt 1** NOP'd only the tag-present check (`0x1025832`). The block was
  still gated by `[0x20637] == 1`, which nothing set.
* **Attempt 2** inserted a helper to set the flag, but the helper ended in
  `pop` instead of `bx lr` (crash), and it patched the wrong branch.

## Patch: align3 (no-chip gap seek)

`firmware/build_patched.py` applies two changes to `density_coeff`:

1. `0x1025832`: `1c d1` (`bne`) → `00 bf` (`nop;nop`) — drop the tag-present
   check in the align block.
2. The no-chip dispatch branch `0x1025512` (`bl 0x102543e`) is redirected to a
   helper placed in the empty space after the vector table (`0x1010140`). The
   helper calls the original fallback `0x102543e` **first**, then sets
   `[0x20637] = 1`, mirroring the success path:

   ```
   push {lr}
   bl   0x102543e      ; no-chip fallback (clears the flag)
   movs r0, #1
   ldr  r1, [pc, #4]   ; = 0x00020637
   strb r0, [r1]       ; set the align flag
   pop  {pc}
   .word 0x00020637
   ```

Because the fallback runs *before* the flag is set, it cannot clobber it. The
flag semantics (`==1` → align once, then clear at `0x1025846`) are unchanged,
so the tagged path is untouched.

**Result:** after closing the cover without a chip the printer seeks the gap
and the first print lands on a single label. The no-chip seek uses the looser
`1600*k` limit, so it is a little slower than with a chip — expected, not a bug.

## Why prints stretched ~2× with a chip

`density_coeff` ("variant B") replaces many heating-time constants with
`400.0f` and swaps the heating curve. Without a chip this is what makes prints
dark. But with a chip the firmware takes a **fast motor path**, and the line
now takes longer to print than the motor takes to advance — so more paper moves
per line and the image stretches ~2× vertically (the bottom overflows the
label).

Investigation (bisection) isolated the cause:

* Restoring only the original heating caps (`bisect_caps`) fixed the stretch
  with a chip, but made prints **without** a chip almost invisible and slower —
  so the raised caps are genuinely needed for no-chip printing.
* Restoring only the motor ramp (`align6`) did **not** fix the speed, so the
  ramp was not the bottleneck.
* `align5` (hide the tag-present flag after a read) fixed both cases but forced
  the slow path **always** — even for original tagged rolls — and made the
  heartbeat report `rfid_ok: False`.

The multipliers are applied through `bl 0x1026156` (`fmul`). Re-examining them
revealed they are **multipliers of the heating time**, not caps: 23 constants,
18 `fmul` call sites.

## Patch: align7 (fast with chip, full without)

`firmware/build_patched.py` then applies, on top of `align3`:

1. Restore the original literal pools and motor ramp from `stock.bin`
   (undoing the part of "variant B" that caused the stretch).
2. Place a helper at `0x1010160` (empty space after the vector table):

   ```
   push {r2, lr}
   ldr  r2, [pc, #16]   ; = 0x0002e458
   ldrb r2, [r2, #8]    ; tag-present
   cmp  r2, #1
   beq  +0              ; skip the override when tagged
   ldr  r1, [pc, #12]   ; = 400.0f
   bl   0x1026156       ; fmul
   pop  {r2, pc}
   .word 0x0002e458
   .word 0x43c80000     ; 400.0f
   ```

3. Redirect all 18 `bl fmul` sites to this helper.

The helper substitutes `400.0f` only when no tag is present, and keeps the
original constant when a tag is present. The tag stays visible, so `rfid_ok`
and RFID reading keep working.

## Final result

| Firmware | With chip | Without chip |
|---|---|---|
| stock | ✅ fast (~2 s), full | ❌ `0x14` refusal / faint |
| align3 (variant B + gap seek) | ❌ stretched ~2× | ✅ full, slow |
| align5 (hide tag-present) | ✅ full, but slow (~5 s) | ✅ full, slow |
| **align7** (multiplier per tag) | ✅ **fast (~2 s), full** | ✅ **full, slow (~5 s)** |

The intermediate/exploratory images (`align4`, `align5`, `align6`,
`bisect_caps`) were dead ends and are not part of the build.

## References

* [lotabout/niimbot](https://github.com/lotabout/niimbot) — the "variant B"
  community patch this build starts from.
* [MultiMote/niimbluelib](https://github.com/MultiMote/niimbluelib) — the
  working `B1PrintTask` print sequence (MIT).
* [AndBondStyle/niimprint](https://github.com/AndBondStyle/niimprint) — the
  older client that prints blank labels on this firmware.
* [fw.niim.blue](https://fw.niim.blue) — official, unmodified firmware images.
