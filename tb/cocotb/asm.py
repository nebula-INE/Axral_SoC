"""Tiny RV64I assembler and ALU reference model for CPU tests."""
from riscv_ref import (ADD, AND, M32, M64, OP_SYSTEM, OP_AUIPC, OP_BRANCH, OP_IMM, OP_IMM32, OP_JAL,
                       OP_JALR, OP_LOAD, OP_LUI, OP_REG, OP_REG32, OP_STORE, OR, SLL, SLT, SLTU,
                       SRA, SRL, SUB, XOR, b_type, i_type, j_type, r_type, s_type, u_type)

RAM_BASE = 0x8000_0000

# name -> (funct3, funct7, alu_op)
R_OPS = {"add": (0, 0x00, ADD), "sub": (0, 0x20, SUB), "sll": (1, 0, SLL), "slt": (2, 0, SLT),
         "sltu": (3, 0, SLTU), "xor": (4, 0, XOR), "srl": (5, 0, SRL), "sra": (5, 0x20, SRA),
         "or": (6, 0, OR), "and": (7, 0, AND)}
RW_OPS = {"addw": (0, 0x00, ADD), "subw": (0, 0x20, SUB), "sllw": (1, 0, SLL),
          "srlw": (5, 0, SRL), "sraw": (5, 0x20, SRA)}
# name -> (funct3, alu_op, is_shift)
I_OPS = {"addi": (0, ADD, False), "slti": (2, SLT, False), "sltiu": (3, SLTU, False),
         "xori": (4, XOR, False), "ori": (6, OR, False), "andi": (7, AND, False),
         "slli": (1, SLL, True), "srli": (5, SRL, True), "srai": (5, SRA, True)}
IW_OPS = {"addiw": (0, ADD, False), "slliw": (1, SLL, True), "srliw": (5, SRL, True),
          "sraiw": (5, SRA, True)}


def r(name, rd, rs1, rs2):
    f3, f7, _ = {**R_OPS, **RW_OPS}[name]
    return r_type(OP_REG32 if name in RW_OPS else OP_REG, rd, f3, rs1, rs2, f7)


def i(name, rd, rs1, imm):
    """OP-IMM / OP-IMM-32. For shifts, imm is the shift amount."""
    table = IW_OPS if name in IW_OPS else I_OPS
    f3, _, is_shift = table[name]
    if is_shift and name in ("srai", "sraiw"):
        imm |= 0x400
    return i_type(OP_IMM32 if name in IW_OPS else OP_IMM, rd, f3, rs1, imm)


def addi(rd, rs1, imm): return i("addi", rd, rs1, imm)
def lui(rd, imm20): return u_type(OP_LUI, rd, imm20)
def auipc(rd, imm20): return u_type(OP_AUIPC, rd, imm20)
def jal(rd, off): return j_type(OP_JAL, rd, off)
def jalr(rd, rs1, imm): return i_type(OP_JALR, rd, 0, rs1, imm)
def nop(): return addi(0, 0, 0)
def halt(): return jal(0, 0)  # self-loop
ECALL = 0x00000073
EBREAK = 0x00100073
MRET = 0x30200073

# CSR addresses
CSR_MSTATUS, CSR_MISA, CSR_MIE, CSR_MTVEC = 0x300, 0x301, 0x304, 0x305
CSR_MSCRATCH, CSR_MEPC, CSR_MCAUSE, CSR_MTVAL, CSR_MIP = 0x340, 0x341, 0x342, 0x343, 0x344
CSR_MVENDORID, CSR_MARCHID, CSR_MIMPID, CSR_MHARTID = 0xF11, 0xF12, 0xF13, 0xF14

CSR_F3 = {"csrrw": 1, "csrrs": 2, "csrrc": 3, "csrrwi": 5, "csrrsi": 6, "csrrci": 7}


def csr(name, rd, csr_addr, src):
    """CSR instruction. src is rs1 (register number) or a 5-bit immediate for the *i forms."""
    return i_type(OP_SYSTEM, rd, CSR_F3[name], src, csr_addr)


def csrr(rd, csr_addr): return csr("csrrs", rd, csr_addr, 0)   # read only (no write)
def csrw(csr_addr, rs1): return csr("csrrw", 0, csr_addr, rs1)  # write only

BRANCH_F3 = {"beq": 0, "bne": 1, "blt": 4, "bge": 5, "bltu": 6, "bgeu": 7}
LOAD_F3 = {"lb": 0, "lh": 1, "lw": 2, "ld": 3, "lbu": 4, "lhu": 5, "lwu": 6}
STORE_F3 = {"sb": 0, "sh": 1, "sw": 2, "sd": 3}


def br(name, rs1, rs2, off): return b_type(OP_BRANCH, BRANCH_F3[name], rs1, rs2, off)
def load(name, rd, rs1, imm): return i_type(OP_LOAD, rd, LOAD_F3[name], rs1, imm)
def store(name, rs2, rs1, imm): return s_type(OP_STORE, STORE_F3[name], rs1, rs2, imm)


def li64(rd, value):
    """Load a 64-bit constant using only addi/slli/ori (13 instructions)."""
    words = [addi(rd, 0, 0)]
    for k in range(6):
        chunk = (value >> (11 * (5 - k))) & 0x7FF
        words += [i("slli", rd, rd, 11), i("ori", rd, rd, chunk)]
    return words


# ---- ALU reference model (RISC-V spec) ----
def s64(x):
    x &= M64
    return x - (1 << 64) if x >> 63 else x


def s32(x):
    x &= M32
    return x - (1 << 32) if x >> 31 else x


def sext32(x):
    return s32(x) & M64


def alu_model(op, a, b, word):
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
        a32, b32, sh = a & M32, b & M32, b & 0x1F
        return {ADD: lambda: sext32(a32 + b32), SUB: lambda: sext32(a32 - b32),
                SLL: lambda: sext32(a32 << sh), SRL: lambda: sext32(a32 >> sh),
                SRA: lambda: sext32(s32(a32) >> sh)}[op]()
    sh = b & 0x3F
    return {ADD: lambda: (a + b) & M64, SUB: lambda: (a - b) & M64, SLL: lambda: (a << sh) & M64,
            SRL: lambda: a >> sh, SRA: lambda: (s64(a) >> sh) & M64}[op]()

# Encoder self-checks against known machine code
assert csr("csrrw", 1, CSR_MSCRATCH, 2) == 0x340110F3   # csrrw x1, mscratch, x2
assert csrr(5, CSR_MCAUSE) == 0x342022F3                 # csrr  x5, mcause
assert csrw(CSR_MTVEC, 1) == 0x30509073                  # csrw  mtvec, x1
