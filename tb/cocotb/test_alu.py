"""cocotb tests for the ALU, compared against a Python reference model."""
import random

import cocotb
from cocotb.triggers import Timer

M64 = (1 << 64) - 1
M32 = (1 << 32) - 1

# rtl/core/alu.sv の符号化と一致させる
ADD, SUB, SLL, SLT, SLTU, XOR, SRL, SRA, OR, AND = range(10)


def s64(x):
    x &= M64
    return x - (1 << 64) if x >> 63 else x


def s32(x):
    x &= M32
    return x - (1 << 32) if x >> 31 else x


def sext32(x):
    return s32(x) & M64


def model(op, a, b, word):
    """Reference model following the RISC-V spec."""
    a &= M64
    b &= M64
    if op == SLT:
        return int(s64(a) < s64(b))
    if op == SLTU:
        return int(a < b)
    if op == XOR:
        return a ^ b
    if op == OR:
        return a | b
    if op == AND:
        return a & b
    if word:
        a32, b32 = a & M32, b & M32
        sh = b & 0x1F
        if op == ADD:
            return sext32(a32 + b32)
        if op == SUB:
            return sext32(a32 - b32)
        if op == SLL:
            return sext32(a32 << sh)
        if op == SRL:
            return sext32(a32 >> sh)
        if op == SRA:
            return sext32(s32(a32) >> sh)
    sh = b & 0x3F
    if op == ADD:
        return (a + b) & M64
    if op == SUB:
        return (a - b) & M64
    if op == SLL:
        return (a << sh) & M64
    if op == SRL:
        return a >> sh
    if op == SRA:
        return (s64(a) >> sh) & M64
    raise ValueError(op)


async def check(dut, op, a, b, word):
    dut.a.value = a
    dut.b.value = b
    dut.op.value = op
    dut.word.value = word
    await Timer(1, units="ns")
    got = int(dut.y.value)
    exp = model(op, a, b, word)
    assert got == exp, (
        f"op={op} word={word} a={a:#018x} b={b:#018x}: got {got:#018x}, expected {exp:#018x}"
    )


EDGE = [0, 1, 2, 31, 32, 63, 64, M32, 1 << 31, 1 << 32, (1 << 63) - 1, 1 << 63, M64, M64 - 1]


@cocotb.test()
async def test_edge_cases(dut):
    """All combinations of edge-case values (including W-type ops)."""
    for op in range(10):
        for word in (0, 1):
            for a in EDGE:
                for b in EDGE:
                    await check(dut, op, a, b, word)


@cocotb.test()
async def test_random(dut):
    """Random tests with a fixed seed for reproducibility."""
    rng = random.Random(1234)
    for _ in range(3000):
        await check(dut, rng.randrange(10), rng.getrandbits(64), rng.getrandbits(64), rng.randrange(2))
