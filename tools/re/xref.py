"""usage: xref.py <bin> <target_hex>... — find BL/B calls and literal refs to targets."""
import struct, sys
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

BASE = 0x01010000
fw = open(sys.argv[1], "rb").read()
targets = {int(t, 16) for t in sys.argv[2:]}
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)

for off in range(0, len(fw) - 4, 2):
    for ins in md.disasm(fw[off:off + 4], BASE + off, count=1):
        if ins.mnemonic in ("bl", "b", "blx") or ins.mnemonic.startswith("b."):
            try:
                t = int(ins.op_str.lstrip("#"), 16)
            except ValueError:
                continue
            if t in targets:
                print(f"{ins.address:#010x} {ins.mnemonic} {t:#x}")

for off in range(0, len(fw) - 4, 4):
    v = struct.unpack("<I", fw[off:off + 4])[0]
    if v in targets or (v & ~1) in targets:
        print(f"literal @ {BASE + off:#010x} = {v:#x}")
