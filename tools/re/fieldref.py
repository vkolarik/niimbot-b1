"""usage: fieldref.py <bin> <base_hex> <offset> — find ldrb/strb [rX,#offset] where
rX is loaded with =base nearby."""
import re, struct, sys
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

BASE = 0x01010000
fw = open(sys.argv[1], "rb").read()
want, foff = int(sys.argv[2], 16), int(sys.argv[3], 0)
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB); md.skipdata = True
ins = list(md.disasm(fw, BASE))

for i, a in enumerate(ins):
    if a.mnemonic == "ldr" and "[pc" in a.op_str:
        imm = int(a.op_str.split("#")[-1].rstrip("]"), 0) if "#" in a.op_str else 0
        lit = ((a.address + 4) & ~3) + imm - BASE
        if lit + 4 > len(fw) or struct.unpack("<I", fw[lit:lit + 4])[0] != want:
            continue
        reg = a.op_str.split(",")[0]
        for b in ins[i + 1:i + 25]:
            if re.search(rf"\[{reg}, #(?:{foff}|{foff:#x})\]", b.op_str) and b.mnemonic[:3] in ("ldr", "str"):
                print(f"{b.address:#010x} {b.mnemonic} {b.op_str}   (base loaded @ {a.address:#x})")
            if b.op_str.startswith(reg + ",") and b.mnemonic not in ("cmp", "str", "strb", "strh", "tst"):
                break
