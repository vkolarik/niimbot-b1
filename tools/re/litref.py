"""usage: litref.py <bin> <lo_hex>-<hi_hex> [...] — find PC-relative ldr instructions
whose literal lies within the given address ranges."""
import struct, sys
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

BASE = 0x01010000
fw = open(sys.argv[1], "rb").read()
ranges = [tuple(int(x, 16) for x in r.split("-")) for r in sys.argv[2:]]

for a in range(BASE, BASE + len(fw) - 1, 2):
    hw = struct.unpack("<H", fw[a - BASE:a - BASE + 2])[0]
    if hw & 0xF800 == 0x4800:  # ldr rt, [pc, #imm8*4]
        lit = ((a + 4) & ~3) + (hw & 0xFF) * 4
        if any(lo <= lit < hi for lo, hi in ranges):
            val = struct.unpack("<I", fw[lit - BASE:lit - BASE + 4])[0]
            print(f"{a:#010x}  ldr r{(hw >> 8) & 7}, ={val:#010x}  (lit {lit:#x})")
