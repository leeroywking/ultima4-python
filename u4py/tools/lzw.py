"""LZW decompression for Ultima IV's compressed picture files (.EGA/.PIC).

A faithful port of `u4/forVS/lzw.c` (Marc Winterrowd, GPL) — itself a port of the original
`u4/SRC-TITLE/INFLATE.ASM`. U4's LZW is unusual: fixed 12-bit codewords and a hash-table
dictionary (with a quirky secondary probe that simulates the 8086 MUL/RCL), re-initialised
when it exceeds 0xCCC entries. This is an IMPORT-time tool only — the game never reads .EGA;
`convert_graphics.py` uses this to produce the canonical PNGs.
"""
from __future__ import annotations

_DICT = 0x1000
_MAX_DICT = 0xCCC


def _next_codeword(bits: int, data: bytes) -> int:
    cw = (data[bits // 8] << 8) + data[bits // 8 + 1]
    cw >>= (4 - (bits % 8))
    return cw & 0xFFF


def _get_string(codeword: int, root: list, code: list, stack: list) -> None:
    cw = codeword
    while cw > 0xFF:
        stack.append(root[cw])
        cw = code[cw]
    stack.append(cw & 0xFF)


def _probe1(root: int, codeword: int) -> int:
    return ((root << 4) ^ codeword) & 0xFFF


def _probe2(root: int, codeword: int) -> int:
    # Simulates the original's 8086 MUL/RCL secondary hash (forVS/lzw.c probe2).
    ax = ((root << 1) + codeword) | 0x800
    temp = (ax & 0xFF) * (ax & 0xFF)
    temp += 2 * (ax & 0xFF) * (ax >> 8) * 0x100
    dx = (temp >> 16) + (ax >> 8) * (ax >> 8)
    ax = temp & 0xFFFF
    carry = 0 if dx == 0 else 1
    regs = [ax, dx]
    for _ in range(2):
        for j in range(2):
            old_carry = carry
            carry = (regs[j] >> 15) & 1
            regs[j] = ((regs[j] << 1) | old_carry) & 0xFFFF
    return ((regs[0] >> 8) | (regs[1] << 8)) & 0xFFF


def _probe3(h: int) -> int:
    return (h + 0x1FD) & 0xFFF


def _found(h: int, root: int, codeword: int, r: list, c: list, occ: bytearray) -> bool:
    if h <= 0xFF:
        return False
    if not occ[h]:
        return True
    return r[h] == root and c[h] == codeword


def _new_hash(root: int, codeword: int, r: list, c: list, occ: bytearray) -> int:
    h = _probe1(root, codeword)
    if _found(h, root, codeword, r, c, occ):
        return h
    h = _probe2(root, codeword)
    if _found(h, root, codeword, r, c, occ):
        return h
    while not _found(h, root, codeword, r, c, occ):
        h = _probe3(h)
    return h


def decompress(compressed: bytes) -> bytes:
    """Decompress an LZW block. C: forVS/lzw.c lzwDecompress / generalizedDecompress."""
    data = bytes(compressed) + b"\x00\x00"     # pad so the 2-byte codeword read never overflows
    total_bits = len(compressed) * 8
    root = [0] * _DICT
    code = [0] * _DICT
    occ = bytearray(_DICT)
    for i in range(0x100):
        occ[i] = 1
    out = bytearray()
    bits = 0
    in_dict = 0

    if bits + 12 > total_bits:
        return bytes(out)
    old = _next_codeword(bits, data); bits += 12
    ch = old & 0xFF
    out.append(ch)

    while bits + 12 <= total_bits:
        new = _next_codeword(bits, data); bits += 12
        stack: list = []
        if occ[new]:
            unknown = False
            _get_string(new, root, code, stack)
        else:
            unknown = True
            stack.append(ch)
            _get_string(old, root, code, stack)
        ch = stack[-1]
        while stack:
            out.append(stack.pop())
        pos = _new_hash(ch, old, root, code, occ)
        root[pos] = ch
        code[pos] = old
        occ[pos] = 1
        in_dict += 1
        if unknown and pos != new:
            raise ValueError("corrupt LZW stream")
        if in_dict > _MAX_DICT:                 # dictionary full -> reset (C: maxDictEntries)
            in_dict = 0
            root = [0] * _DICT
            code = [0] * _DICT
            occ = bytearray(_DICT)
            for i in range(0x100):
                occ[i] = 1
            if bits + 12 > total_bits:
                return bytes(out)
            new = _next_codeword(bits, data); bits += 12
            ch = new & 0xFF
            out.append(ch)
        old = new
    return bytes(out)
