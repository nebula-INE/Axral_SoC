"""Program-level tests for the single-cycle RV64I CPU (cpu_tb_top)."""
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer

from asm import (BRANCH_F3, CSR_MCAUSE, CSR_MEPC, CSR_MHARTID, CSR_MISA, CSR_MSCRATCH,
                 CSR_MSTATUS, CSR_MTVAL, CSR_MTVEC, EBREAK, ECALL, I_OPS, IW_OPS, MRET, RAM_BASE,
                 RW_OPS, R_OPS, addi, alu_model, auipc, br, csr, csrr, csrw, halt, i, jal, jalr,
                 li64, load, lui, r, s64, sext32, store)
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


# ---------------------------------------------------------------------------
# CSR instructions and traps
# ---------------------------------------------------------------------------
def default_handler():
    """x28 = mcause, x29 = mtval, x30 = mepc; return to the instruction after the faulting one."""
    return [csrr(28, CSR_MCAUSE), csrr(29, CSR_MTVAL), csrr(30, CSR_MEPC),
            addi(31, 30, 4), csrw(CSR_MEPC, 31), MRET]


def with_trap_handler(body, handler=None):
    """Layout: [auipc x27 / addi / csrw mtvec] + body + halt + halt + handler.

    x27 and x28..x31 are reserved for the setup and the default handler.
    Returns (words, index of the first body instruction).
    """
    handler = default_handler() if handler is None else handler
    words = [auipc(27, 0), 0, csrw(CSR_MTVEC, 27)] + body + [halt(), halt()]
    words[1] = addi(27, 27, 4 * len(words))
    return words + handler, 3


async def run_trap_program(dut, body, handler=None, cycles=80):
    words, first = with_trap_handler(body, handler)
    await run_program(dut, words, cycles)
    return first, 3 + len(body)  # index of the first body instruction, index of the final halt


@cocotb.test()
async def test_csr_read_write(dut):
    prog = [addi(1, 0, 0x55), csr("csrrw", 0, CSR_MSCRATCH, 1),     # mscratch = 0x55
            csrr(3, CSR_MSCRATCH),                                     # x3 = 0x55 (no write)
            addi(4, 0, 0xF0), csr("csrrs", 5, CSR_MSCRATCH, 4),        # x5 = 0x55, mscratch = 0xF5
            csr("csrrc", 6, CSR_MSCRATCH, 4),                          # x6 = 0xF5, mscratch = 0x05
            csr("csrrwi", 7, CSR_MSCRATCH, 31),                        # x7 = 0x05, mscratch = 31
            csr("csrrsi", 8, CSR_MSCRATCH, 0),                         # x8 = 31 (uimm = 0: no write)
            csr("csrrci", 9, CSR_MSCRATCH, 1),                         # x9 = 31, mscratch = 30
            csrr(10, CSR_MSCRATCH),                                    # x10 = 30
            csrr(11, CSR_MISA), csrr(12, CSR_MHARTID),
            halt()]
    await run_program(dut, prog, len(prog) + 4)
    for n, e in {3: 0x55, 5: 0x55, 6: 0xF5, 7: 0x05, 8: 31, 9: 31, 10: 30,
                 11: 0x8000000000000100, 12: 0}.items():
        got = await reg(dut, n)
        assert got == e, f"x{n}: got {got:#x}, expected {e:#x}"


@cocotb.test()
async def test_csr_rs_zero_does_not_write(dut):
    """csrrs/csrrc with rs1 = x0 never write, even to a read-only CSR (no trap)."""
    prog = [addi(5, 0, 7), csrr(5, CSR_MHARTID),     # legal: read of a read-only CSR
            csrr(6, CSR_MCAUSE), csrr(7, CSR_MEPC),  # still 0: no trap happened
            halt()]
    await run_program(dut, prog, len(prog) + 4)
    assert await reg(dut, 5) == 0
    assert await reg(dut, 6) == 0
    assert await reg(dut, 7) == 0


@cocotb.test()
async def test_ecall(dut):
    first, halt_idx = await run_trap_program(dut, [addi(10, 0, 1), ECALL, addi(10, 10, 100)])
    assert await reg(dut, 28) == 11                    # ecall from M-mode
    assert await reg(dut, 29) == 0
    assert await reg(dut, 30) == BASE + 4 * (first + 1)
    assert await reg(dut, 10) == 101                   # resumed after the ecall
    assert int(dut.dbg_pc.value) == BASE + 4 * halt_idx


@cocotb.test()
async def test_ebreak(dut):
    first, _ = await run_trap_program(dut, [EBREAK])
    assert await reg(dut, 28) == 3
    assert await reg(dut, 29) == BASE + 4 * first      # mtval = pc of the ebreak
    assert await reg(dut, 30) == BASE + 4 * first


@cocotb.test()
async def test_illegal_instruction_trap(dut):
    first, _ = await run_trap_program(dut, [addi(1, 0, 99), 0xFFFFFFFF, addi(2, 0, 5)])
    assert await reg(dut, 28) == 2
    assert await reg(dut, 29) == 0xFFFFFFFF            # mtval = the instruction bits
    assert await reg(dut, 30) == BASE + 4 * (first + 1)
    assert await reg(dut, 2) == 5                      # execution continues after the handler


@cocotb.test()
async def test_illegal_csr_access(dut):
    """Unknown CSR and writes to read-only CSRs trap, and rd is not written."""
    for word in (csr("csrrw", 1, 0x7C0, 0), csr("csrrw", 1, CSR_MHARTID, 0),
                 csr("csrrsi", 1, CSR_MHARTID, 1)):
        first, _ = await run_trap_program(dut, [addi(1, 0, 99), word])
        assert await reg(dut, 28) == 2, f"{word:#010x}"
        assert await reg(dut, 29) == word, f"{word:#010x}"
        assert await reg(dut, 1) == 99, f"{word:#010x}: rd must not be written on a trap"


@cocotb.test()
async def test_misaligned_load_has_no_side_effects(dut):
    prog = [addi(5, 0, 1), i("slli", 5, 5, 31), addi(5, 5, 0x7F0), addi(6, 0, 77),
            load("lw", 6, 5, 1), addi(7, 0, 1)]
    await run_trap_program(dut, prog)
    assert await reg(dut, 28) == 4
    assert await reg(dut, 29) == BASE + 0x7F0 + 1      # mtval = the effective address
    assert await reg(dut, 6) == 77                     # not written
    assert await reg(dut, 7) == 1                      # execution continued


@cocotb.test()
async def test_misaligned_store_has_no_side_effects(dut):
    v = 0x0123456789ABCDEF
    prog = (li64(1, v) + [addi(5, 0, 1), i("slli", 5, 5, 31), addi(5, 5, 0x7F0),
                          store("sd", 1, 5, 0), store("sh", 1, 5, 1), store("sw", 1, 5, 6)])
    await run_trap_program(dut, prog, cycles=120)
    assert await reg(dut, 28) == 6                     # the last (sw at +6) trapped; sh at +1 too
    assert await reg(dut, 29) == BASE + 0x7F0 + 6
    assert await mem(dut, 0x7F0 // 8) == v             # memory unchanged by the faulting stores


@cocotb.test()
async def test_misaligned_jumps(dut):
    # JALR: x5 is aligned, target = x5 + 2 has bit 1 set
    first, _ = await run_trap_program(dut, [addi(1, 0, 99), auipc(5, 0), addi(5, 5, 0x40), jalr(1, 5, 2)])
    assert await reg(dut, 28) == 0
    assert await reg(dut, 29) == BASE + 4 * (first + 1) + 0x40 + 2
    assert await reg(dut, 1) == 99                     # link register not written
    assert await reg(dut, 30) == BASE + 4 * (first + 3)
    # JAL with an offset of 2
    first, _ = await run_trap_program(dut, [addi(1, 0, 99), jal(1, 2)])
    assert await reg(dut, 28) == 0
    assert await reg(dut, 29) == BASE + 4 * (first + 1) + 2
    assert await reg(dut, 1) == 99
    # taken branch with an odd-word offset traps, a not-taken one does not
    first, _ = await run_trap_program(dut, [br("beq", 0, 0, 2)])
    assert await reg(dut, 28) == 0
    assert await reg(dut, 29) == BASE + 4 * first + 2
    prog = [addi(1, 0, 1), br("bne", 1, 1, 2), csrr(6, CSR_MCAUSE), csrr(7, CSR_MEPC)]
    await run_trap_program(dut, prog)
    assert await reg(dut, 6) == 0 and await reg(dut, 7) == 0


@cocotb.test()
async def test_mstatus_across_trap(dut):
    handler = [csrr(26, CSR_MSTATUS)] + default_handler()
    body = [csr("csrrsi", 0, CSR_MSTATUS, 8),          # MIE = 1
            ECALL,
            csrr(25, CSR_MSTATUS)]
    await run_trap_program(dut, body, handler=handler)
    assert await reg(dut, 26) == 0x1880                # in the handler: MIE=0, MPIE=1, MPP=3
    assert await reg(dut, 25) == 0x1888                # after mret: MIE=1, MPIE=1


@cocotb.test()
async def test_mret_jumps_to_mepc(dut):
    """The handler can change mepc: skip the instruction after the ecall."""
    handler = [csrr(30, CSR_MEPC), addi(31, 30, 8), csrw(CSR_MEPC, 31), MRET]
    body = [addi(10, 0, 0), ECALL, addi(10, 0, 1), addi(11, 0, 2)]
    await run_trap_program(dut, body, handler=handler)
    assert await reg(dut, 10) == 0                     # skipped
    assert await reg(dut, 11) == 2


@cocotb.test()
async def test_trap_vector_is_mtvec(dut):
    """A trap goes to mtvec (BASE); the low 2 bits of mtvec are ignored for the target."""
    first, halt_idx = await run_trap_program(dut, [ECALL])
    assert await reg(dut, 28) == 11
    # With mtvec = handler address + 1 (vectored mode flag), the target is still the handler
    words, f = with_trap_handler([ECALL])
    words[1] = words[1] + (1 << 20)                    # addi imm + 1
    await run_program(dut, words, 80)
    assert await reg(dut, 28) == 11
