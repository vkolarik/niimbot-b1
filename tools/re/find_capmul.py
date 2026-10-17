"""usage: find_capmul.py <bin> — for each `ldr r1, =K` (heating-time constant) find
the following `bl 0x1026156` (fmul) call site."""
import struct, sys
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

BASE = 0x01010000
FMUL = 0x1026156
fw = open(sys.argv[1], "rb").read()
SITES = [0x1011d24, 0x1011d42, 0x1011d50, 0x1011d5e, 0x1011dcc, 0x1011dda, 0x1011df0, 0x1011e10,
         0x1016204, 0x1016228, 0x1016236, 0x1016242, 0x1016272, 0x1016280, 0x101628e, 0x1016292,
         0x1016950, 0x1016966, 0x1016988, 0x10169d2, 0x10169e0, 0x10169f0, 0x1016a1c]
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)


def walk(a, depth=0):
    for ins in md.disasm(fw[a - BASE:a - BASE + 40], a):
        if ins.address == a and ins.mnemonic.startswith("ldr"):
            continue
        if ins.mnemonic == "bl":
            return ins.address, int(ins.op_str.lstrip("#"), 16)
        if ins.mnemonic == "b" and depth == 0:
            return walk(int(ins.op_str.lstrip("#"), 16), 1)
        if "r1" in ins.op_str.split(",")[0] or ins.mnemonic.startswith(("b", "pop", "bx")):
            return ins.address, f"STOP {ins.mnemonic} {ins.op_str}"
    return None, "none"


bls = {}
for s in SITES:
    addr, tgt = walk(s)
    print(f"{s:#x} -> bl @ {addr:#x} target {tgt if isinstance(tgt, str) else hex(tgt)}")
    bls.setdefault(addr, []).append(s)

print({hex(k): [hex(x) for x in v] for k, v in bls.items()})
