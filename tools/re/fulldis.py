"""usage: fulldis.py <bin> — linear Thumb disassembly of the whole image with
literal-pool values and BL targets annotated."""
import struct, sys
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

BASE = 0x01010000
fw = open(sys.argv[1], "rb").read()
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB); md.skipdata = True

for ins in md.disasm(fw, BASE):
    extra = ""
    if ins.mnemonic.startswith("ldr") and "[pc" in ins.op_str:
        imm = int(ins.op_str.split("#")[-1].rstrip("]"), 0) if "#" in ins.op_str else 0
        lit = ((ins.address + 4) & ~3) + imm - BASE
        if 0 <= lit <= len(fw) - 4:
            extra = f"   ; ={struct.unpack('<I', fw[lit:lit+4])[0]:#010x}"
    print(f"{ins.address:08x}  {ins.bytes.hex():10s} {ins.mnemonic:8s} {ins.op_str}{extra}")
