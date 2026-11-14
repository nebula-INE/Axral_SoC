"""cocotb tests for the immediate generator."""
import random

import cocotb
from cocotb.triggers import Timer

from riscv_ref import (M64, OP_AUIPC, OP_BRANCH, OP_IMM, OP_IMM32, OP_JAL, OP_JALR,
                       OP_LOAD, OP_LUI, OP_REG, OP_STORE, b_type, i_type, j_type,
                       r_type, s_type, sext, u_type)


async def check(dut, inst, expected):
    dut.inst.value = inst
    await Timer(1, units="ns")
    got = int(dut.imm.value)
    assert got == expected & M64, f"inst={inst:#010x}: got {got:#018x}, expected {expected & M64:#018x}"


def edge_and_random(bits, step, rng, n=200):
    """Edge values and random values of a signed 'bits'-bit field (multiples of step)."""
    lo, hi = -(1 << (bits - 1)), (1 << (bits - 1)) - step
    vals = {lo, hi, 0, step, -step}
    vals |= {rng.randrange(lo, hi + 1) // step * step for _ in range(n)}
    return sorted(vals)


@cocotb.test()
async def test_i_type(dut):
    rng = random.Random(1)
    for op in (OP_IMM, OP_IMM32, OP_LOAD, OP_JALR):
        for imm in edge_and_random(12, 1, rng):
            await check(dut, i_type(op, rng.randrange(32), rng.randrange(8), rng.randrange(32), imm), sext(imm, 12))


@cocotb.test()
async def test_s_type(dut):
    rng = random.Random(2)
    for imm in edge_and_random(12, 1, rng):
        await check(dut, s_type(OP_STORE, rng.randrange(4), rng.randrange(32), rng.randrange(32), imm), sext(imm, 12))


@cocotb.test()
async def test_b_type(dut):
    rng = random.Random(3)
    for imm in edge_and_random(13, 2, rng):
        await check(dut, b_type(OP_BRANCH, rng.choice([0, 1, 4, 5, 6, 7]), rng.randrange(32), rng.randrange(32), imm), sext(imm, 13))


@cocotb.test()
async def test_u_type(dut):
    rng = random.Random(4)
    for op in (OP_LUI, OP_AUIPC):
        for imm20 in [0, 1, 0x7FFFF, 0x80000, 0xFFFFF] + [rng.getrandbits(20) for _ in range(100)]:
            await check(dut, u_type(op, rng.randrange(32), imm20), sext(imm20 << 12, 32))


@cocotb.test()
async def test_j_type(dut):
    rng = random.Random(5)
    for imm in edge_and_random(21, 2, rng):
        await check(dut, j_type(OP_JAL, rng.randrange(32), imm), sext(imm, 21))


@cocotb.test()
async def test_r_type_is_zero(dut):
    """R-type and unknown opcodes produce an immediate of 0."""
    rng = random.Random(6)
    for _ in range(50):
        await check(dut, r_type(OP_REG, rng.randrange(32), 0, rng.randrange(32), rng.randrange(32), 0), 0)
    await check(dut, 0xFFFFFFFF, 0)
