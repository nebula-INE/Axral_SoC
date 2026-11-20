"""cocotb tests for the M-mode CSR file."""
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from asm import (CSR_MARCHID, CSR_MCAUSE, CSR_MEPC, CSR_MHARTID, CSR_MIE, CSR_MIMPID, CSR_MIP,
                 CSR_MISA, CSR_MSCRATCH, CSR_MSTATUS, CSR_MTVAL, CSR_MTVEC, CSR_MVENDORID)

M64 = (1 << 64) - 1


async def reset(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    for sig in ("csr_addr", "csr_write_attempt", "csr_wen", "csr_wdata", "trap_en", "trap_pc",
                "trap_cause", "trap_tval", "mret_en"):
        getattr(dut, sig).value = 0
    dut.rst_n.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def read(dut, addr):
    dut.csr_addr.value = addr
    dut.csr_write_attempt.value = 0
    await Timer(1, units="ns")
    return int(dut.csr_rdata.value)


async def illegal(dut, addr, write):
    dut.csr_addr.value = addr
    dut.csr_write_attempt.value = int(write)
    await Timer(1, units="ns")
    r = int(dut.csr_illegal.value)
    dut.csr_write_attempt.value = 0
    return r


async def write(dut, addr, value):
    dut.csr_addr.value = addr
    dut.csr_wdata.value = value
    dut.csr_write_attempt.value = 1
    dut.csr_wen.value = 1
    await RisingEdge(dut.clk)
    dut.csr_wen.value = 0
    dut.csr_write_attempt.value = 0
    await Timer(1, units="ns")


@cocotb.test()
async def test_reset_values(dut):
    await reset(dut)
    assert await read(dut, CSR_MSTATUS) == 0x1800        # MPP = M, MIE = MPIE = 0
    assert await read(dut, CSR_MISA) == 0x8000000000000100  # RV64, I
    for addr in (CSR_MIE, CSR_MTVEC, CSR_MSCRATCH, CSR_MEPC, CSR_MCAUSE, CSR_MTVAL, CSR_MIP,
                 CSR_MVENDORID, CSR_MARCHID, CSR_MIMPID, CSR_MHARTID):
        assert await read(dut, addr) == 0, f"CSR {addr:#x} should reset to 0"


@cocotb.test()
async def test_full_width_registers(dut):
    await reset(dut)
    rng = random.Random(5)
    for addr in (CSR_MSCRATCH, CSR_MCAUSE, CSR_MTVAL):
        for _ in range(20):
            v = rng.getrandbits(64)
            await write(dut, addr, v)
            assert await read(dut, addr) == v, f"CSR {addr:#x}"


@cocotb.test()
async def test_warl_behaviour(dut):
    await reset(dut)
    await write(dut, CSR_MEPC, M64)
    assert await read(dut, CSR_MEPC) == M64 & ~3          # low 2 bits are zero
    assert int(dut.mepc_out.value) == M64 & ~3
    await write(dut, CSR_MTVEC, M64)
    assert await read(dut, CSR_MTVEC) == M64 & ~2         # MODE[1] is hardwired to 0
    assert int(dut.mtvec_target.value) == M64 & ~3
    await write(dut, CSR_MSTATUS, M64)
    assert await read(dut, CSR_MSTATUS) == 0x1888         # only MIE/MPIE writable, MPP = 3
    await write(dut, CSR_MSTATUS, 0)
    assert await read(dut, CSR_MSTATUS) == 0x1800
    await write(dut, CSR_MIE, M64)
    assert await read(dut, CSR_MIE) == 0x888
    await write(dut, CSR_MISA, 0)
    assert await read(dut, CSR_MISA) == 0x8000000000000100
    await write(dut, CSR_MIP, M64)
    assert await read(dut, CSR_MIP) == 0


@cocotb.test()
async def test_illegal_access(dut):
    await reset(dut)
    for addr in (0x000, 0x7C0, 0x7FF, 0x100, 0x180, 0xC00, 0x306):
        assert await illegal(dut, addr, False) == 1, f"unknown CSR {addr:#x} must be illegal"
    for addr in (CSR_MHARTID, CSR_MVENDORID, CSR_MARCHID, CSR_MIMPID):
        assert await illegal(dut, addr, False) == 0, f"reading {addr:#x} is legal"
        assert await illegal(dut, addr, True) == 1, f"writing read-only {addr:#x} is illegal"
    for addr in (CSR_MSTATUS, CSR_MISA, CSR_MIE, CSR_MTVEC, CSR_MSCRATCH, CSR_MEPC, CSR_MCAUSE,
                 CSR_MTVAL, CSR_MIP):
        assert await illegal(dut, addr, True) == 0, f"writing {addr:#x} is legal"


@cocotb.test()
async def test_trap_and_mret(dut):
    await reset(dut)
    await write(dut, CSR_MSTATUS, 0x8)                    # MIE = 1
    dut.trap_en.value = 1
    dut.trap_pc.value = 0x80000010
    dut.trap_cause.value = 11
    dut.trap_tval.value = 0x55
    await RisingEdge(dut.clk)
    dut.trap_en.value = 0
    await Timer(1, units="ns")
    assert await read(dut, CSR_MEPC) == 0x80000010
    assert await read(dut, CSR_MCAUSE) == 11
    assert await read(dut, CSR_MTVAL) == 0x55
    assert await read(dut, CSR_MSTATUS) == 0x1880         # MIE=0, MPIE=1
    dut.mret_en.value = 1
    await RisingEdge(dut.clk)
    dut.mret_en.value = 0
    await Timer(1, units="ns")
    assert await read(dut, CSR_MSTATUS) == 0x1888         # MIE=MPIE=1


@cocotb.test()
async def test_trap_overrides_write(dut):
    """A trap and a CSR write in the same cycle: the write must be dropped."""
    await reset(dut)
    await write(dut, CSR_MSCRATCH, 0x1111)
    dut.csr_addr.value = CSR_MSCRATCH
    dut.csr_wdata.value = 0x2222
    dut.csr_wen.value = 1
    dut.trap_en.value = 1
    dut.trap_pc.value = 0x80000000
    await RisingEdge(dut.clk)
    dut.csr_wen.value = 0
    dut.trap_en.value = 0
    await Timer(1, units="ns")
    assert await read(dut, CSR_MSCRATCH) == 0x1111
