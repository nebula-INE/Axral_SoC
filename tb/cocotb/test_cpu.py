"""Program-level tests for the single-cycle RV64I CPU (cpu_tb_top)."""
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer

from asm import (BRANCH_F3, I_OPS, IW_OPS, RAM_BASE, ECALL, RW_OPS, R_OPS, addi, alu_model,
                 auipc, br, halt, i, jal, jalr, li64, load, lui, r, s64, sext32, store)
from riscv_ref import M64, sext

BASE = RAM_BASE


async def run_program(dut, words, cycles):
    """Reset, load the program, release reset and run for 'cycles' clock cycles."""
    clock = cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.rst_n.value = 0
    dut.load_we.value = 0
    dut.dbg_reg_addr.value = 0
    dut.dbg_mem_idx.value = 0
    await RisingEdge(dut.clk)
    for idx, w in enumerate(words):
        dut.load_we.value = 1
        dut.load_addr.value = idx
        dut.load_data.value = w
        await RisingEdge(dut.clk)
    dut.load_we.value = 0
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, cycles)
    await Timer(1, units="ns")  # let non-blocking updates settle
    clock.kill()


async def reg(dut, n):
    dut.dbg_reg_addr.value = n
    await Timer(1, units="ns")
    return int(dut.dbg_reg_data.value)


async def mem(dut, dw_idx):
    dut.dbg_mem_idx.value = dw_idx
    await Timer(1, units="ns")
    return int(dut.dbg_mem_data.value)


@cocotb.test()
async def test_addi(dut):
    """The plan's first goal: addi x1, x0, 42 -> x1 == 42."""
    await run_program(dut, [addi(1, 0, 42), halt()], 4)
    assert await reg(dut, 1) == 42


@cocotb.test()
async def test_loop_sum(dut):
    """Sum 10..1 with a backward branch."""
    prog = [addi(1, 0, 10), addi(2, 0, 0),
            r("add", 2, 2, 1), addi(1, 1, -1), br("bne", 1, 0, -8),
            halt()]
    await run_program(dut, prog, 40)
    assert await reg(dut, 2) == 55
    assert await reg(dut, 1) == 0


@cocotb.test()
async def test_x0_not_writable(dut):
    prog = [addi(0, 0, 5), r("add", 1, 0, 0), addi(2, 0, 7), halt()]
    await run_program(dut, prog, 8)
    assert await reg(dut, 1) == 0
    assert await reg(dut, 2) == 7


@cocotb.test()
async def test_lui_auipc(dut):
    prog = [lui(1, 0x12345), auipc(2, 1), lui(3, 0x80000), halt()]
    await run_program(dut, prog, 6)
    assert await reg(dut, 1) == 0x12345000
    assert await reg(dut, 2) == BASE + 4 + 0x1000
    assert await reg(dut, 3) == 0xFFFFFFFF80000000


@cocotb.test()
async def test_jal_jalr(dut):
    prog = [
        addi(2, 0, 0),        # 0
        addi(7, 0, 0),        # 1
        jal(1, 12),           # 2: -> idx 5, x1 = BASE + 12
        addi(2, 0, 1),        # 3 (skipped)
        addi(2, 0, 2),        # 4 (skipped)
        auipc(5, 0),          # 5: x5 = BASE + 20
        addi(5, 5, 17),       # 6: x5 = BASE + 37 (odd: LSB must be cleared)
        jalr(6, 5, 0),        # 7: x6 = BASE + 32, jump to BASE + 36 (idx 9)
        addi(7, 0, 7),        # 8 (skipped)
        addi(8, 0, 8),        # 9
        halt(),               # 10
    ]
    await run_program(dut, prog, 16)
    assert await reg(dut, 1) == BASE + 12
    assert await reg(dut, 2) == 0
    assert await reg(dut, 5) == BASE + 37
    assert await reg(dut, 6) == BASE + 32
    assert await reg(dut, 7) == 0
    assert await reg(dut, 8) == 8
    # JALR must clear the target's LSB: the final halt loop sits at idx 10 = BASE + 40
    assert int(dut.dbg_pc.value) == BASE + 40


@cocotb.test()
async def test_branches(dut):
    """Every branch type, taken and not taken (x3 = 0 if taken, 1 if not)."""
    for name in BRANCH_F3:
        for a, b in [(1, 2), (2, 1), (-1, 1), (1, -1), (5, 5), (0, 0), (-3, -3)]:
            prog = [addi(1, 0, a), addi(2, 0, b), addi(3, 0, 0),
                    br(name, 1, 2, 8), addi(3, 0, 1), halt()]
            await run_program(dut, prog, 9)
            ua, ub = a & M64, b & M64
            taken = {"beq": ua == ub, "bne": ua != ub, "blt": s64(ua) < s64(ub),
                     "bge": s64(ua) >= s64(ub), "bltu": ua < ub, "bgeu": ua >= ub}[name]
            got = await reg(dut, 3)
            assert got == (0 if taken else 1), f"{name} a={a} b={b}: x3={got}, taken={taken}"


def put(dword, off, nbytes, value):
    """Replace nbytes bytes of a 64-bit word at byte offset off."""
    mask = ((1 << (8 * nbytes)) - 1) << (8 * off)
    return (dword & ~mask & M64) | ((value << (8 * off)) & mask)


@cocotb.test()
async def test_load_store(dut):
    v1 = 0x8899AABBCCDDEEFF
    v2 = 0x1122334455667788
    prog = (li64(1, v1) + li64(2, v2)
            + [addi(5, 0, 1), i("slli", 5, 5, 31), addi(5, 5, 0x7F0)]   # x5 = BASE + 0x7F0
            + [store("sd", 1, 5, 8 * k) for k in range(5)]
            + [store("sb", 2, 5, 8 + 3),     # dword1: byte 3
               store("sh", 2, 5, 16 + 4),    # dword2: bytes 4..5
               store("sw", 2, 5, 24 + 4),    # dword3: bytes 4..7
               store("sw", 2, 5, 32)]        # dword4: bytes 0..3
            + [load("lb", 10, 5, 0), load("lbu", 11, 5, 0), load("lh", 12, 5, 2),
               load("lhu", 13, 5, 2), load("lw", 14, 5, 4), load("lwu", 15, 5, 4),
               load("ld", 16, 5, 0), load("lb", 17, 5, 7)]
            + [halt()])
    await run_program(dut, prog, len(prog) + 6)

    base_idx = 0x7F0 // 8
    exp = [v1, put(v1, 3, 1, v2), put(v1, 4, 2, v2), put(v1, 4, 4, v2), put(v1, 0, 4, v2)]
    for k, e in enumerate(exp):
        got = await mem(dut, base_idx + k)
        assert got == e, f"dword {k}: got {got:#018x}, expected {e:#018x}"

    b = v1.to_bytes(8, "little")
    def sx(x, bits):
        return sext(x, bits) & M64  # sign-extend, then view as an unsigned 64-bit value

    expected_regs = {
        10: sx(b[0], 8), 11: b[0],
        12: sx(int.from_bytes(b[2:4], "little"), 16), 13: int.from_bytes(b[2:4], "little"),
        14: sx(int.from_bytes(b[4:8], "little"), 32), 15: int.from_bytes(b[4:8], "little"),
        16: v1, 17: sx(b[7], 8),
    }
    for n, e in expected_regs.items():
        got = await reg(dut, n)
        assert got == e, f"x{n}: got {got:#018x}, expected {e:#018x}"


@cocotb.test()
async def test_w_ops(dut):
    prog = [addi(1, 0, -1), i("srli", 1, 1, 33),          # x1 = 0x7FFFFFFF
            i("addiw", 2, 1, 1),                           # 0xFFFFFFFF80000000
            i("sraiw", 3, 2, 4), i("srliw", 4, 2, 4),
            r("subw", 5, 0, 1), addi(7, 0, 1), r("sllw", 6, 1, 7), r("addw", 8, 1, 1),
            halt()]
    await run_program(dut, prog, 16)
    assert await reg(dut, 1) == 0x7FFFFFFF
    assert await reg(dut, 2) == 0xFFFFFFFF80000000
    assert await reg(dut, 3) == 0xFFFFFFFFF8000000
    assert await reg(dut, 4) == 0x08000000
    assert await reg(dut, 5) == 0xFFFFFFFF80000001
    assert await reg(dut, 6) == 0xFFFFFFFFFFFFFFFE
    assert await reg(dut, 8) == 0xFFFFFFFFFFFFFFFE


@cocotb.test()
async def test_illegal_halts(dut):
    """An illegal instruction raises illegal_inst and stops the PC."""
    await run_program(dut, [addi(1, 0, 5), ECALL, addi(1, 0, 9), halt()], 12)
    assert int(dut.illegal_inst.value) == 1
    assert int(dut.dbg_pc.value) == BASE + 4
    assert await reg(dut, 1) == 5


def gen_fuzz(rng, n):
    """Random ALU program + expected final registers from a Python model."""
    regs = [0] * 32
    words = []
    for rd in range(1, 32):
        val = rng.getrandbits(64)
        words += li64(rd, val)
        regs[rd] = val
    all_r = {**R_OPS, **RW_OPS}
    all_i = {**I_OPS, **IW_OPS}
    for _ in range(n):
        pc = BASE + 4 * len(words)
        kind = rng.choice(["r", "r", "i", "i", "lui", "auipc"])
        rd = rng.randrange(32)
        if kind == "r":
            name = rng.choice(list(all_r))
            rs1, rs2 = rng.randrange(32), rng.randrange(32)
            words.append(r(name, rd, rs1, rs2))
            val = alu_model(all_r[name][2], regs[rs1], regs[rs2], name in RW_OPS)
        elif kind == "i":
            name = rng.choice(list(all_i))
            _, alu_op, is_shift = all_i[name]
            word = name in IW_OPS
            rs1 = rng.randrange(32)
            imm = rng.randrange(32 if word else 64) if is_shift else rng.randrange(-2048, 2048)
            words.append(i(name, rd, rs1, imm))
            val = alu_model(alu_op, regs[rs1], imm & M64, word)
        elif kind == "lui":
            imm20 = rng.getrandbits(20)
            words.append(lui(rd, imm20))
            val = sext32(imm20 << 12)
        else:
            imm20 = rng.getrandbits(20)
            words.append(auipc(rd, imm20))
            val = (pc + sext32(imm20 << 12)) & M64
        if rd != 0:
            regs[rd] = val
    words.append(halt())
    return words, regs


@cocotb.test()
async def test_random_alu_programs(dut):
    """Random programs: compare all registers with the Python model."""
    for seed in (1, 2, 3):
        words, expected = gen_fuzz(random.Random(seed), 300)
        await run_program(dut, words, len(words) + 4)
        for n in range(1, 32):
            got = await reg(dut, n)
            assert got == expected[n], f"seed {seed}: x{n} got {got:#018x}, expected {expected[n]:#018x}"
