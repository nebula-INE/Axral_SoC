"""cocotb tests for the decoder."""
import random

import cocotb
from cocotb.triggers import Timer

from riscv_ref import (A_PC, A_RS1, A_ZERO, ADD, AND, OP_AUIPC, OP_BRANCH, OP_FENCE, OP_IMM,
                       OP_IMM32, OP_JAL, OP_JALR, OP_LOAD, OP_LUI, OP_REG, OP_REG32,
                       OP_STORE, OP_SYSTEM, OR, SLL, SLT, SLTU, SRA, SRL, SUB, WB_ALU, WB_MEM,
                       WB_PC4, XOR, b_type, i_type, j_type, r_type, s_type, u_type)

FIELDS = ["reg_we", "a_sel", "b_sel_imm", "alu_op", "alu_word", "mem_re", "mem_we",
          "mem_size", "mem_unsigned", "wb_sel", "is_branch", "is_jal", "is_jalr", "illegal"]


def E(**kw):
    """Expected outputs with default (all-zero, ALU=ADD) values."""
    d = dict(reg_we=0, a_sel=A_RS1, b_sel_imm=0, alu_op=ADD, alu_word=0, mem_re=0, mem_we=0,
             mem_size=0, mem_unsigned=0, wb_sel=WB_ALU, is_branch=0, is_jal=0, is_jalr=0, illegal=0)
    d.update(kw)
    return d


ILLEGAL = E(illegal=1)


def build_table():
    t = []
    # OP (R-type)
    for name, f3, f7, op in [("add", 0, 0, ADD), ("sub", 0, 0x20, SUB), ("sll", 1, 0, SLL),
                             ("slt", 2, 0, SLT), ("sltu", 3, 0, SLTU), ("xor", 4, 0, XOR),
                             ("srl", 5, 0, SRL), ("sra", 5, 0x20, SRA), ("or", 6, 0, OR),
                             ("and", 7, 0, AND)]:
        t.append((name, r_type(OP_REG, 3, f3, 1, 2, f7), E(reg_we=1, alu_op=op)))
    # OP-32
    for name, f3, f7, op in [("addw", 0, 0, ADD), ("subw", 0, 0x20, SUB), ("sllw", 1, 0, SLL),
                             ("srlw", 5, 0, SRL), ("sraw", 5, 0x20, SRA)]:
        t.append((name, r_type(OP_REG32, 3, f3, 1, 2, f7), E(reg_we=1, alu_op=op, alu_word=1)))
    # OP-IMM
    for name, f3, op in [("addi", 0, ADD), ("slti", 2, SLT), ("sltiu", 3, SLTU), ("xori", 4, XOR),
                         ("ori", 6, OR), ("andi", 7, AND)]:
        t.append((name, i_type(OP_IMM, 3, f3, 1, -5), E(reg_we=1, b_sel_imm=1, alu_op=op)))
    t.append(("slli", i_type(OP_IMM, 3, 1, 1, 63), E(reg_we=1, b_sel_imm=1, alu_op=SLL)))
    t.append(("srli", i_type(OP_IMM, 3, 5, 1, 63), E(reg_we=1, b_sel_imm=1, alu_op=SRL)))
    t.append(("srai", i_type(OP_IMM, 3, 5, 1, 0x400 | 63), E(reg_we=1, b_sel_imm=1, alu_op=SRA)))
    # OP-IMM-32
    t.append(("addiw", i_type(OP_IMM32, 3, 0, 1, -5), E(reg_we=1, b_sel_imm=1, alu_word=1)))
    t.append(("slliw", i_type(OP_IMM32, 3, 1, 1, 31), E(reg_we=1, b_sel_imm=1, alu_word=1, alu_op=SLL)))
    t.append(("srliw", i_type(OP_IMM32, 3, 5, 1, 31), E(reg_we=1, b_sel_imm=1, alu_word=1, alu_op=SRL)))
    t.append(("sraiw", i_type(OP_IMM32, 3, 5, 1, 0x400 | 31), E(reg_we=1, b_sel_imm=1, alu_word=1, alu_op=SRA)))
    # LOAD / STORE
    for name, f3 in [("lb", 0), ("lh", 1), ("lw", 2), ("ld", 3), ("lbu", 4), ("lhu", 5), ("lwu", 6)]:
        t.append((name, i_type(OP_LOAD, 3, f3, 1, 8),
                  E(reg_we=1, b_sel_imm=1, mem_re=1, mem_size=f3 & 3, mem_unsigned=f3 >> 2, wb_sel=WB_MEM)))
    for name, f3 in [("sb", 0), ("sh", 1), ("sw", 2), ("sd", 3)]:
        t.append((name, s_type(OP_STORE, f3, 1, 2, 8), E(b_sel_imm=1, mem_we=1, mem_size=f3)))
    # BRANCH
    for name, f3 in [("beq", 0), ("bne", 1), ("blt", 4), ("bge", 5), ("bltu", 6), ("bgeu", 7)]:
        t.append((name, b_type(OP_BRANCH, f3, 1, 2, 8), E(a_sel=A_PC, b_sel_imm=1, is_branch=1)))
    # U / J
    t.append(("lui", u_type(OP_LUI, 1, 0x12345), E(reg_we=1, a_sel=A_ZERO, b_sel_imm=1)))
    t.append(("auipc", u_type(OP_AUIPC, 1, 0x12345), E(reg_we=1, a_sel=A_PC, b_sel_imm=1)))
    t.append(("jal", j_type(OP_JAL, 1, 2048), E(reg_we=1, a_sel=A_PC, b_sel_imm=1, wb_sel=WB_PC4, is_jal=1)))
    t.append(("jalr", i_type(OP_JALR, 1, 0, 2, 4), E(reg_we=1, b_sel_imm=1, wb_sel=WB_PC4, is_jalr=1)))
    # FENCE / FENCE.I are NOPs
    t.append(("fence", i_type(OP_FENCE, 0, 0, 0, 0x0FF), E()))
    t.append(("fence.i", i_type(OP_FENCE, 0, 1, 0, 0), E()))
    return t


def build_illegal():
    return [
        ("all zeros", 0x00000000),
        ("all ones", 0xFFFFFFFF),
        ("compressed (low bits != 11)", 0x00000001),
        ("ecall (SYSTEM, not yet supported)", 0x00000073),
        ("ebreak (SYSTEM, not yet supported)", 0x00100073),
        ("mret (SYSTEM, not yet supported)", 0x30200073),
        ("csrrw (SYSTEM, not yet supported)", i_type(OP_SYSTEM, 1, 1, 2, 0x300)),
        ("mul (M extension, not yet supported)", r_type(OP_REG, 3, 0, 1, 2, 1)),
        ("add with bad funct7", r_type(OP_REG, 3, 0, 1, 2, 0x10)),
        ("sub-like with funct3=1", r_type(OP_REG, 3, 1, 1, 2, 0x20)),
        ("slli with funct6 != 0", i_type(OP_IMM, 3, 1, 1, 0x400 | 1)),
        ("srli/srai with bad funct6", i_type(OP_IMM, 3, 5, 1, 0x200)),
        ("slliw with shamt[5]=1", i_type(OP_IMM32, 3, 1, 1, 32)),
        ("srliw with bad funct7", i_type(OP_IMM32, 3, 5, 1, 0x200)),
        ("OP-IMM-32 funct3=2", i_type(OP_IMM32, 3, 2, 1, 0)),
        ("sllw with bad funct7", r_type(OP_REG32, 3, 1, 1, 2, 0x20)),
        ("OP-32 slt (no such W op)", r_type(OP_REG32, 3, 2, 1, 2, 0)),
        ("load funct3=7", i_type(OP_LOAD, 3, 7, 1, 0)),
        ("store funct3=4", s_type(OP_STORE, 4, 1, 2, 0)),
        ("branch funct3=2", b_type(OP_BRANCH, 2, 1, 2, 8)),
        ("branch funct3=3", b_type(OP_BRANCH, 3, 1, 2, 8)),
        ("jalr funct3=1", i_type(OP_JALR, 1, 1, 2, 4)),
        ("misc-mem funct3=2", i_type(OP_FENCE, 0, 2, 0, 0)),
    ]


async def decode(dut, inst):
    dut.inst.value = inst
    await Timer(1, units="ns")
    return {f: int(getattr(dut, f).value) for f in FIELDS}


@cocotb.test()
async def test_legal_instructions(dut):
    for name, inst, exp in build_table():
        got = await decode(dut, inst)
        assert got == exp, f"{name} ({inst:#010x}):\n  got      {got}\n  expected {exp}"


@cocotb.test()
async def test_illegal_instructions(dut):
    for name, inst in build_illegal():
        got = await decode(dut, inst)
        assert got == ILLEGAL, f"{name} ({inst:#010x}) should be illegal with no side effects: {got}"


@cocotb.test()
async def test_random_properties(dut):
    """Random words: illegal implies no side effects; no loads and stores at once; no X."""
    rng = random.Random(42)
    opcodes = [OP_LUI, OP_AUIPC, OP_JAL, OP_JALR, OP_BRANCH, OP_LOAD, OP_STORE, OP_IMM,
               OP_REG, OP_IMM32, OP_REG32, OP_FENCE, OP_SYSTEM]
    for _ in range(5000):
        inst = (rng.getrandbits(25) << 7) | (rng.choice(opcodes) if rng.random() < 0.9 else rng.getrandbits(7))
        got = await decode(dut, inst)
        if got["illegal"]:
            assert got == ILLEGAL, f"{inst:#010x}: illegal but has side effects: {got}"
        assert not (got["mem_re"] and got["mem_we"]), f"{inst:#010x}: load and store together"
        assert not (got["mem_we"] and got["reg_we"]), f"{inst:#010x}: store with register write"
        assert got["is_branch"] + got["is_jal"] + got["is_jalr"] <= 1, f"{inst:#010x}: multiple jumps"
