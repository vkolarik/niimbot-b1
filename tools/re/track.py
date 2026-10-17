"""usage: track.py <bin> <base_hex>... — find all memory accesses reaching the given
bases via ldr =literal, tracking simple adds/subs register moves within a small window."""
import re, struct, sys
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

BASE = 0x01010000
fw = open(sys.argv[1], "rb").read()
want = {int(t, 16) for t in sys.argv[2:]}
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
md.skipdata = True
ins = list(md.disasm(fw, BASE))


def litval(a):
    m = re.search(r"\[pc, #(-?0x[0-9a-f]+|-?\d+)\]", a.op_str)
    if not m:
        return None
    s = m.group(1)
    neg = s.startswith("-")
    s = s.lstrip("+-")
    imm = int(s, 0) if s.lower().startswith("0x") else int(s)
    if neg:
        imm = -imm
    lit = ((a.address + 4) & ~3) + imm - BASE
    if lit + 4 > len(fw) or lit < 0:
        return None
    return struct.unpack("<I", fw[lit:lit + 4])[0]


for i, a in enumerate(ins):
    v = litval(a)
    if v not in want:
        continue
    reg = a.op_str.split(",")[0]
    for b in ins[i + 1:i + 60]:
        d = b.op_str.split(",")[0]
        # stop if reg is written as destination (clobbered)
        if d == reg and b.mnemonic not in ("cmp", "str", "strb", "strh", "tst", "cbz", "cbnz"):
            break
        m2 = re.search(rf"\[{reg}(?:, #(-?\d+|-?0x[0-9a-f]+))?\]", b.op_str)
        if m2:
            off = 0
            if m2.group(1):
                s = m2.group(1)
                neg = s.startswith("-")
                s = s.lstrip("+-")
                off = int(s, 0) if s.lower().startswith("0x") else int(s)
                if neg:
                    off = -off
            print(f"{b.address:#010x}  {b.mnemonic:6s} {b.op_str:22s} ; base {v:#x} off {off:#x} -> {v+off:#x}  (ldr @ {a.address:#x})")
