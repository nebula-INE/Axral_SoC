"""cocotb tests for the branch comparator."""
import random

import cocotb
from cocotb.triggers import Timer

from asm import s64

M64 = (1 << 64) - 1
F3 = {"beq": 0, "bne": 1, "blt": 4, "bge": 5, "bltu": 6, "bgeu": 7}
EDGE = [0, 1, 2, M64, M64 - 1, 1 << 63, (1 << 63) - 1, 0x1234, 0xFFFFFFFF]


def model(name, a, b):
    return {"beq": a == b, "bne": a != b, "blt": s64(a) < s64(b), "bge": s64(a) >= s64(b),
            "bltu": a < b, "bgeu": a >= b}[name]


async def check(dut, name, a, b):
    dut.a.value = a
    dut.b.value = b
    dut.funct3.value = F3[name]
    await Timer(1, units="ns")
    assert int(dut.taken.value) == int(model(name, a, b)), f"{name} a={a:#x} b={b:#x}"


@cocotb.test()
async def test_edges(dut):
    for name in F3:
        for a in EDGE:
            for b in EDGE:
                await check(dut, name, a, b)


@cocotb.test()
async def test_random(dut):
    rng = random.Random(7)
    for _ in range(2000):
        a = rng.getrandbits(64)
        b = a if rng.random() < 0.2 else rng.getrandbits(64)
        await check(dut, rng.choice(list(F3)), a, b)


@cocotb.test()
async def test_invalid_funct3_not_taken(dut):
    for f3 in (2, 3):
        dut.a.value = 5
        dut.b.value = 5
        dut.funct3.value = f3
        await Timer(1, units="ns")
        assert int(dut.taken.value) == 0
