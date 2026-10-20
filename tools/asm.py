"""Minimal MIPS (R5900) encoder for the ELF patches: only the instructions used.

lines are ('op', args...) tuples or 'label:' strings; registers by name without
'$'; memory operands as ('lw', rt, offset, base). Branch/jump targets are labels or
absolute addresses.
"""
import struct

R = {n: i for i, n in enumerate(
    'zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 s7 '
    't8 t9 k0 k1 gp sp fp ra'.split())}

def _i(op, rs, rt, imm):
    return op << 26 | R[rs] << 21 | R[rt] << 16 | imm & 0xFFFF

def _r(rs, rt, rd, sa, fn):
    return R[rs] << 21 | R[rt] << 16 | R[rd] << 11 | sa << 6 | fn

def labels(origin, lines):
    """{label: address} of an assemble() listing."""
    out, pc = {}, origin
    for ln in lines:
        if isinstance(ln, str):
            out[ln.rstrip(':')] = pc
        else:
            pc += 4
    return out

def assemble(origin, lines):
    """lines: ('op', args...) tuples or 'label:' strings. Branch/jump targets are
    labels or absolute addresses. Returns bytes."""
    labels, pc = {}, origin
    for ln in lines:
        if isinstance(ln, str):
            labels[ln.rstrip(':')] = pc
        else:
            pc += 4
    out, pc = [], origin
    for ln in lines:
        if isinstance(ln, str):
            continue
        op, *a = ln
        tgt = lambda x: labels[x] if isinstance(x, str) else x
        off = lambda x: (tgt(x) - pc - 4) >> 2
        w = {
            'nop': lambda: 0,
            'addiu': lambda: _i(0x09, a[1], a[0], a[2]),
            'sltiu': lambda: _i(0x0B, a[1], a[0], a[2]),
            'andi': lambda: _i(0x0C, a[1], a[0], a[2]),
            'ori': lambda: _i(0x0D, a[1], a[0], a[2]),
            'lui': lambda: _i(0x0F, 'zero', a[0], a[1]),
            'lbu': lambda: _i(0x24, a[2], a[0], a[1]),
            'lhu': lambda: _i(0x25, a[2], a[0], a[1]),
            'beq': lambda: _i(0x04, a[0], a[1], off(a[2])),
            'bne': lambda: _i(0x05, a[0], a[1], off(a[2])),
            'beqz': lambda: _i(0x04, a[0], 'zero', off(a[1])),
            'bnez': lambda: _i(0x05, a[0], 'zero', off(a[1])),
            'b': lambda: _i(0x04, 'zero', 'zero', off(a[0])),
            'j': lambda: 0x02 << 26 | (tgt(a[0]) >> 2) & 0x3FFFFFF,
            'jr': lambda: _r(a[0], 'zero', 'zero', 0, 0x08),
            'addu': lambda: _r(a[1], a[2], a[0], 0, 0x21),
            'sll': lambda: _r('zero', a[1], a[0], a[2], 0x00),
            'movz': lambda: _r(a[1], a[2], a[0], 0, 0x0A),
            'movn': lambda: _r(a[1], a[2], a[0], 0, 0x0B),
            'subu': lambda: _r(a[1], a[2], a[0], 0, 0x23),
            'or': lambda: _r(a[1], a[2], a[0], 0, 0x25),
            'xor': lambda: _r(a[1], a[2], a[0], 0, 0x26),
            'sltu': lambda: _r(a[1], a[2], a[0], 0, 0x2B),
            'srl': lambda: _r('zero', a[1], a[0], a[2], 0x02),
            'slt': lambda: _r(a[1], a[2], a[0], 0, 0x2A),
            'mult': lambda: _r(a[1], a[2], a[0], 0, 0x18),     # R5900: rd = LO = rs * rt
            'div': lambda: _r(a[0], a[1], 'zero', 0, 0x1A),
            'mflo': lambda: _r('zero', 'zero', a[0], 0, 0x12),
            'jal': lambda: 0x03 << 26 | (tgt(a[0]) >> 2) & 0x3FFFFFF,
            'lw': lambda: _i(0x23, a[2], a[0], a[1]),
            'sw': lambda: _i(0x2B, a[2], a[0], a[1]),
            'ld': lambda: _i(0x37, a[2], a[0], a[1]),
            'sd': lambda: _i(0x3F, a[2], a[0], a[1]),
            'sb': lambda: _i(0x28, a[2], a[0], a[1]),
            'sh': lambda: _i(0x29, a[2], a[0], a[1]),
        }[op]()
        out.append(struct.pack('<I', w))
        pc += 4
    return b''.join(out)

def lo(addr):
    return addr - ((addr + 0x8000) & 0xFFFF0000)

def hi(addr):
    return ((addr + 0x8000) >> 16) & 0xFFFF
