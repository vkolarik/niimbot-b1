"""usage: dis.py <bin> <start_hex> <count> — Thumb disasm with literal-pool resolution."""
import struct, sys
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

BASE = 0x01010000
fw = open(sys.argv[1], "rb").read()
start, count = int(sys.argv[2], 16), int(sys.argv[3])
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB); md.skipdata = True

def u32(a):
    return struct.unpack("<I", fw[a - BASE:a - BASE + 4])[0]

for i, ins in enumerate(md.disasm(fw[start - BASE:start - BASE + count * 4], start)):
    if i >= count:
        break
    extra = ""
    if ins.mnemonic.startswith("ldr") and "pc" in ins.op_str and "[" in ins.op_str:
        imm = int(ins.op_str.split("#")[-1].rstrip("]"), 0) if "#" in ins.op_str else 0
        lit = ((ins.address + 4) & ~3) + imm
        try:
            extra = f"   ; ={u32(lit):#010x}"
        except Exception:
            pass
    print(f"{ins.address:#010x}  {ins.bytes.hex():10s} {ins.mnemonic:8s} {ins.op_str}{extra}")
