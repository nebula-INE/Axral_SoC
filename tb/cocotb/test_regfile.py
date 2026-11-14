"""cocotb tests for the register file."""
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

M64 = (1 << 64) - 1


async def setup(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.we.value = 0
    dut.waddr.value = 0
    dut.wdata.value = 0
    dut.raddr1.value = 0
    dut.raddr2.value = 0
    await RisingEdge(dut.clk)


async def write(dut, addr, data):
    dut.we.value = 1
    dut.waddr.value = addr
    dut.wdata.value = data
    await RisingEdge(dut.clk)
    dut.we.value = 0


async def read(dut, r1, r2):
    dut.raddr1.value = r1
    dut.raddr2.value = r2
    await Timer(1, units="ns")
    return int(dut.rdata1.value), int(dut.rdata2.value)


@cocotb.test()
async def test_x0_is_zero(dut):
    """Writes to x0 are ignored and x0 always reads as 0."""
    await setup(dut)
    await write(dut, 0, 0xDEADBEEF)
    assert await read(dut, 0, 0) == (0, 0)


@cocotb.test()
async def test_write_read_all(dut):
    """Write x1..x31 and read them all back."""
    await setup(dut)
    rng = random.Random(1)
    ref = {0: 0}
    for i in range(1, 32):
        ref[i] = rng.getrandbits(64)
        await write(dut, i, ref[i])
    for i in range(32):
        got, _ = await read(dut, i, 0)
        assert got == ref[i], f"x{i}: got {got:#x}, expected {ref[i]:#x}"


@cocotb.test()
async def test_forwarding(dut):
    """A same-cycle write is forwarded to the read port (except x0)."""
    await setup(dut)
    await write(dut, 6, 0)  # 未初期化(X)を避ける
    dut.we.value = 1
    dut.waddr.value = 5
    dut.wdata.value = 0x1234
    got1, got2 = await read(dut, 5, 6)
    assert got1 == 0x1234
    assert got2 == 0  # 別レジスタには転送されない
    dut.waddr.value = 0
    dut.wdata.value = 0xFFFF
    assert await read(dut, 0, 0) == (0, 0)
    dut.we.value = 0
