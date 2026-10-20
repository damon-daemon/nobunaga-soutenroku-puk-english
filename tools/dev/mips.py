"""ELF disassembly helpers for reverse engineering (capstone MIPS, R5900).

  refs(lo, hi)   -> [(vaddr, target)] of lui+addiu/ori/load/store pairs and 32-bit
                    data words pointing into [lo, hi)
  dis(vaddr, n)  -> print n instructions
usage: .venv/bin/python tools/dev/mips.py refs 0x5290d0 0x529270 | dis 0x123456 40
"""
import os, struct, sys
import capstone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ELF = open(os.path.join(ROOT, 'extract', 'SLPM_654.55'), 'rb').read()
BASE, FOFF = 0x100000, 0x800
TEXT_END = 0x3A0000                      # code ends where the data starts (survey)
md = capstone.Cs(capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS64 | capstone.CS_MODE_LITTLE_ENDIAN)
REG = ['zero', 'at', 'v0', 'v1', 'a0', 'a1', 'a2', 'a3', 't0', 't1', 't2', 't3', 't4', 't5', 't6', 't7',
       's0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 't8', 't9', 'k0', 'k1', 'gp', 'sp', 'fp', 'ra']

def r5900(w):
    """Decode the R5900 instructions capstone lacks (lq/sq, 3-operand mult, MMI)."""
    op, rs, rt, rd, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31, w & 0xFFFF
    if op in (0x1E, 0x1F):
        return ('lq' if op == 0x1E else 'sq'), '$%s, %d($%s)' % (REG[rt], s16(imm), REG[rs])
    if op == 0 and (w & 0x3F) in (0x18, 0x19) and rd:
        return ('mult' if w & 1 == 0 else 'multu'), '$%s, $%s, $%s' % (REG[rd], REG[rs], REG[rt])
    if op == 0x1C:
        f = w & 0x3F
        name = {0x10: 'mfhi1', 0x12: 'mflo1', 0x18: 'mult1', 0x19: 'multu1', 0x1A: 'div1', 0x1B: 'divu1'}.get(f, 'mmi.%02x.%02x' % (f, (w >> 6) & 31))
        return name, '$%s, $%s, $%s' % (REG[rd], REG[rs], REG[rt])
    return None

def word(va):
    return struct.unpack_from('<I', ELF, va - BASE + FOFF)[0]

def s16(x):
    return x - 0x10000 if x & 0x8000 else x

def refs(lo, hi, code_end=TEXT_END):
    out, lui = [], {}
    for va in range(BASE, code_end, 4):
        w = word(va)
        op, rs, rt, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
        if op == 0x0F:
            lui[rt] = (imm << 16, va)
            continue
        if op in (0x09, 0x0D) or 0x20 <= op <= 0x3F:      # addiu, ori, loads/stores
            if rs in lui and va - lui[rs][1] < 64:
                t = lui[rs][0] + (imm if op == 0x0D else s16(imm))
                if lo <= t < hi:
                    out.append((va, t))
        if op == 0x02 or op == 0x03 or (op == 0 and (w & 0x3F) in (8, 9)):
            lui.clear()
    for va in range(code_end, BASE + len(ELF) - FOFF - 3, 4):
        if lo <= word(va) < hi:
            out.append((va, word(va)))
    return out

def dis(va, n):
    for a in range(va, va + 4 * n, 4):
        w = word(a)
        x = r5900(w)
        if not x:
            ins = next(md.disasm(struct.pack('<I', w), a), None)
            x = (ins.mnemonic, ins.op_str) if ins else ('.word', '0x%08x' % w)
        print('%08x  %-8s %s' % ((a,) + x))

if __name__ == '__main__':
    cmd, a = sys.argv[1], [int(x, 0) for x in sys.argv[2:]]
    if cmd == 'refs':
        for va, t in refs(a[0], a[1]):
            print('%08x -> %08x' % (va, t))
    else:
        dis(a[0], a[1] if len(a) > 1 else 40)
