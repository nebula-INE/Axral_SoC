"""RISC-V reference helpers for tests: instruction encoders and constants.

The encoders follow the RISC-V spec and do not share logic with the RTL.
"""

M64 = (1 << 64) - 1
M32 = (1 << 32) - 1

# ALU op codes (must match rtl/core/alu.sv and decoder.sv)
ADD, SUB, SLL, SLT, SLTU, XOR, SRL, SRA, OR, AND = range(10)

# a_sel / wb_sel (must match decoder.sv)
A_RS1, A_PC, A_ZERO = 0, 1, 2
WB_ALU, WB_MEM, WB_PC4 = 0, 1, 2

# opcodes
OP_LUI, OP_AUIPC, OP_JAL, OP_JALR = 0x37, 0x17, 0x6F, 0x67
OP_BRANCH, OP_LOAD, OP_STORE = 0x63, 0x03, 0x23
OP_IMM, OP_REG, OP_IMM32, OP_REG32 = 0x13, 0x33, 0x1B, 0x3B
OP_FENCE, OP_SYSTEM = 0x0F, 0x73


def sext(x, bits):
    x &= (1 << bits) - 1
    return x - (1 << bits) if x >> (bits - 1) else x


def r_type(op, rd, f3, rs1, rs2, f7):
    return (f7 << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op


def i_type(op, rd, f3, rs1, imm):
    return ((imm & 0xFFF) << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op


def s_type(op, f3, rs1, rs2, imm):
    return (((imm >> 5) & 0x7F) << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | ((imm & 0x1F) << 7) | op


def b_type(op, f3, rs1, rs2, imm):
    return (
        (((imm >> 12) & 1) << 31)
        | (((imm >> 5) & 0x3F) << 25)
        | (rs2 << 20)
        | (rs1 << 15)
        | (f3 << 12)
        | (((imm >> 1) & 0xF) << 8)
        | (((imm >> 11) & 1) << 7)
        | op
    )


def u_type(op, rd, imm20):
    return ((imm20 & 0xFFFFF) << 12) | (rd << 7) | op


def j_type(op, rd, imm):
    return (
        (((imm >> 20) & 1) << 31)
        | (((imm >> 1) & 0x3FF) << 21)
        | (((imm >> 11) & 1) << 20)
        | (((imm >> 12) & 0xFF) << 12)
        | (rd << 7)
        | op
    )


# Encoder self-checks against well-known machine code
assert i_type(OP_IMM, 1, 0, 0, 42) == 0x02A00093      # addi x1, x0, 42
assert r_type(OP_REG, 3, 0, 1, 2, 0) == 0x002081B3    # add  x3, x1, x2
assert r_type(OP_REG, 3, 0, 1, 2, 0x20) == 0x402081B3  # sub  x3, x1, x2
assert s_type(OP_STORE, 3, 1, 5, 8) == 0x0050B423     # sd   x5, 8(x1)
assert u_type(OP_LUI, 1, 0x12345) == 0x123450B7       # lui  x1, 0x12345
