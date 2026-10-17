"""Build the patched Niimbot B1 firmware (``B1_6.19_density_align7.bin``).

This is the reproducible build for the firmware described in
``docs/firmware-analysis.md``. It starts from two inputs you must obtain
yourself (see ``firmware/README.md``):

* ``B1_6.19_stock.bin``         — the unmodified 6.19 firmware from
  https://fw.niim.blue/stable/B1/B1_6.19.bin
* ``B1_6.19_density_coeff.bin`` — the "variant B" community patch from
  https://github.com/lotabout/niimbot (branch ``niimbot-hw6.01``)

It applies two patches on top of ``density_coeff``:

1. **align3** — make the printer seek the label gap after the cover is closed
   *without* an RFID tag, so the first print lands on a single label.
2. **align7** — make heating-time multipliers conditional on the RFID tag, so
   printing is fast with a tagged (original) roll and full/dark without one.

The only dependency is the Python standard library (``capstone`` is optional and
only used for a pretty disassembly of the helpers when ``--verbose`` is passed).

Usage::

    python firmware/build_patched.py [--keep-align3] [--verbose]
"""

import argparse
import hashlib
import struct
import sys
from pathlib import Path

BASE = 0x01010000  # image base address (Cortex-M0, Thumb)

FIRMWARE_DIR = Path(__file__).resolve().parent
SRC_COEFF = FIRMWARE_DIR / "B1_6.19_density_coeff.bin"
SRC_STOCK = FIRMWARE_DIR / "B1_6.19_stock.bin"
OUT_ALIGN3 = FIRMWARE_DIR / "B1_6.19_density_align3.bin"
OUT_ALIGN7 = FIRMWARE_DIR / "B1_6.19_density_align7.bin"

EXPECTED_LEN = 124436
MD5_ALIGN3 = "78dcde4bd7a4a21dfb965b40d7607cc0"
MD5_ALIGN7 = "540ef521d7416cfe1eb561b6effcb0b4"


def enc_bl(addr: int, target: int) -> bytes:
    """Return 4 little-endian bytes of a Thumb ``BL`` (T4) encoding."""
    imm32 = target - (addr + 4)
    assert imm32 % 2 == 0 and -(1 << 24) <= imm32 < (1 << 24), f"bl out of range {addr:#x}->{target:#x}"
    imm25 = imm32 & 0x1FFFFFF
    S = (imm25 >> 24) & 1
    I1 = (imm25 >> 23) & 1
    I2 = (imm25 >> 22) & 1
    imm10 = (imm25 >> 12) & 0x3FF
    imm11 = (imm25 >> 1) & 0x7FF
    J1 = I1 ^ S ^ 1
    J2 = I2 ^ S ^ 1
    hw1 = 0xF000 | (S << 10) | imm10
    hw2 = 0xD000 | (J1 << 13) | (J2 << 11) | imm11
    return struct.pack("<HH", hw1, hw2)


def off(addr: int) -> int:
    return addr - BASE


def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


# --- Patch 1: align3 ---------------------------------------------------------
# After three failed RFID reads (no tag present) the dispatch function normally
# branches to the no-chip fallback (0x102543E), which *clears* the "align" flag
# [0x20637]. We redirect it to a helper that calls the fallback first and then
# sets the flag, mirroring the success path. We also NOP the tag-present check
# in the align block so the gap seek runs without a tag.

ALIGN3_HELPER = 0x1010140
ALIGN3_FALLBACK = 0x102543E
ALIGN3_DISPATCH_BL = 0x1025512
ALIGN3_TAG_CHECK = 0x1025832


def apply_align3(fw: bytearray) -> None:
    # 1. NOP the tag-present check in the align block (bne -> nop;nop).
    at = off(ALIGN3_TAG_CHECK)
    assert fw[at : at + 2] == b"\x1c\xd1", fw[at : at + 2].hex()
    fw[at : at + 2] = b"\x00\xbf"

    # 2. Helper in the empty space after the vector table:
    #      push {lr}         ; bl 0x102543E (fallback)
    #      movs r0, #1       ; ldr r1, [pc, #4]   ; strb r0, [r1]  (set [0x20637])
    #      pop {pc}          ; .word 0x00020637
    helper = b""
    helper += b"\x00\xb5"                                  # push {lr}
    helper += enc_bl(ALIGN3_HELPER + 2, ALIGN3_FALLBACK)   # bl 0x102543E
    helper += b"\x01\x20"                                  # movs r0, #1
    helper += b"\x01\x49"                                  # ldr r1, [pc, #4]
    helper += b"\x08\x70"                                  # strb r0, [r1]
    helper += b"\x00\xbd"                                  # pop {pc}
    helper += b"\x00\x00"                                  # pad
    helper += struct.pack("<I", 0x00020637)                # literal

    assert len(helper) == 20, len(helper)
    at = off(ALIGN3_HELPER)
    assert fw[at : at + len(helper)] == b"\x00" * len(helper), "helper space not zero"
    fw[at : at + len(helper)] = helper

    # 3. Redirect the dispatcher's no-chip branch to the helper.
    at = off(ALIGN3_DISPATCH_BL)
    old_bl = fw[at : at + 4]
    assert old_bl == enc_bl(ALIGN3_DISPATCH_BL, ALIGN3_FALLBACK), old_bl.hex()
    fw[at : at + 4] = enc_bl(ALIGN3_DISPATCH_BL, ALIGN3_HELPER)


# --- Patch 2: align7 ---------------------------------------------------------
# "Variant B" raised the heating-time *multipliers* to 400.0f (needed to print
# dark without a tag), but with a tag the firmware takes a fast motor path, so a
# line takes longer to print than the motor takes to advance -> the print is
# stretched ~2x. align7 restores the original multipliers and ramp, then routes
# every ``bl fmul`` through a helper that only substitutes 400.0f when no tag is
# present. Result: fast with a tag, full/dark without one.

ALIGN7_HELPER = 0x1010160
FMUL = 0x1026156
# (address, length) of literal pools that variant B changed to 400.0f.
ALIGN7_POOLS = [(0x1011E60, 16), (0x1016600, 4), (0x1016614, 20), (0x1016D4C, 20)]
ALIGN7_RAMP = (0x102D21C, 200)  # motor ramp table that variant B replaced
ALIGN7_BL_SITES = [
    0x1011D26, 0x1011D10, 0x1011DDC, 0x1011DF2, 0x1016208, 0x101622C,
    0x101623A, 0x1016248, 0x1016276, 0x1016284, 0x1016296, 0x1016954,
    0x1016A32, 0x1016990, 0x10169D6, 0x10169E4, 0x10169F6, 0x1016A20,
]


def apply_align7(fw: bytearray, stock: bytes) -> None:
    # 1. Restore the original literal pools and motor ramp from stock.
    for addr, n in ALIGN7_POOLS + [ALIGN7_RAMP]:
        fw[off(addr) : off(addr) + n] = stock[off(addr) : off(addr) + n]
    # A non-multiplier literal inside one of those pools must stay untouched.
    assert fw[off(0x1016610) : off(0x1016614)] == struct.pack("<I", 0x2E48C)

    # 2. Helper in the empty space after the vector table:
    #      push {r2, lr}              ; ldr r2, [pc, #16]   ; =0x0002e458
    #      ldrb r2, [r2, #8]          ; tag-present
    #      cmp r2, #1                 ; beq +0 (skip next if tagged)
    #      ldr r1, [pc, #12]          ; =400.0f
    #      bl fmul                    ; pop {r2, pc}
    #      .word 0x0002e458, 0x43c80000
    h = b""
    h += b"\x04\xb5"                              # push {r2, lr}
    h += b"\x04\x4a"                              # ldr r2, [pc, #16]
    h += b"\x12\x7a"                              # ldrb r2, [r2, #8]
    h += b"\x01\x2a"                              # cmp r2, #1
    h += b"\x00\xd0"                              # beq +0
    h += b"\x03\x49"                              # ldr r1, [pc, #12]
    h += enc_bl(ALIGN7_HELPER + 0xC, FMUL)        # bl fmul
    h += b"\x04\xbd"                              # pop {r2, pc}
    h += b"\x00\x00"                              # pad
    h += struct.pack("<II", 0x0002E458, 0x43C80000)  # literals

    assert len(h) == 28
    at = off(ALIGN7_HELPER)
    assert fw[at : at + len(h)] == b"\x00" * len(h), "helper space not zero"
    fw[at : at + len(h)] = h

    # 3. Redirect every heating multiplier ``bl fmul`` to the helper.
    for addr in ALIGN7_BL_SITES:
        at = off(addr)
        assert fw[at : at + 4] == enc_bl(addr, FMUL), hex(addr)
        fw[at : at + 4] = enc_bl(addr, ALIGN7_HELPER)


def disasm_helpers(fw: bytes) -> None:
    try:
        from capstone import CS_ARCH_ARM, CS_MODE_THUMB, Cs
    except ImportError:
        print("(install 'capstone' for a pretty disassembly of the helpers)")
        return
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    for label, addr, n in (("align3", ALIGN3_HELPER, 20), ("align7", ALIGN7_HELPER, 28)):
        print(f"\n--- {label} helper @ {addr:#010x} ---")
        for ins in md.disasm(bytes(fw[off(addr) : off(addr) + n]), addr):
            print(f"{ins.address:#010x}  {ins.bytes.hex():10s} {ins.mnemonic:8s} {ins.op_str}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keep-align3", action="store_true", help="also write the intermediate align3 image")
    ap.add_argument("--verbose", action="store_true", help="print helper disassembly")
    args = ap.parse_args(argv)

    if not SRC_COEFF.exists():
        sys.exit(f"missing input {SRC_COEFF.name} (see firmware/README.md)")
    if not SRC_STOCK.exists():
        sys.exit(f"missing input {SRC_STOCK.name} (see firmware/README.md)")

    coeff = SRC_COEFF.read_bytes()
    stock = SRC_STOCK.read_bytes()
    assert len(coeff) == EXPECTED_LEN, len(coeff)
    assert len(stock) == EXPECTED_LEN, len(stock)

    fw = bytearray(coeff)
    apply_align3(fw)
    align3 = bytes(fw)
    print(f"align3  md5 {md5(align3)}  {'OK' if md5(align3) == MD5_ALIGN3 else 'MISMATCH (expected ' + MD5_ALIGN3 + ')'}")
    if md5(align3) != MD5_ALIGN3:
        sys.exit("align3 did not build as expected — input files may be wrong")

    apply_align7(fw, stock)
    align7 = bytes(fw)
    print(f"align7  md5 {md5(align7)}  {'OK' if md5(align7) == MD5_ALIGN7 else 'MISMATCH (expected ' + MD5_ALIGN7 + ')'}")
    if md5(align7) != MD5_ALIGN7:
        sys.exit("align7 did not build as expected — input files may be wrong")

    if args.keep_align3:
        OUT_ALIGN3.write_bytes(align3)
        print(f"wrote {OUT_ALIGN3.name}")
    OUT_ALIGN7.write_bytes(align7)
    print(f"wrote {OUT_ALIGN7.name}")

    if args.verbose:
        disasm_helpers(align7)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
