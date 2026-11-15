"""cocotb tests for the load/store unit."""
import random

import cocotb
from cocotb.triggers import Timer

M64 = (1 << 64) - 1


def sext(x, bits):
    return (x - (1 << bits) if x >> (bits - 1) else x) & M64


@cocotb.test()
async def test_load_store_all_aligned(dut):
    rng = random.Random(11)
    for size in range(4):
        nbytes = 1 << size
        for addr in range(0, 8, nbytes):  # aligned accesses only
            for unsigned in (0, 1):
                for _ in range(40):
                    mem = rng.getrandbits(64)
                    sdata = rng.getrandbits(64)
                    dut.addr.value = addr
                    dut.size.value = size
                    dut.is_unsigned.value = unsigned
                    dut.store_data.value = sdata
                    dut.mem_rdata.value = mem
                    await Timer(1, units="ns")

                    raw = (mem >> (8 * addr)) & ((1 << (8 * nbytes)) - 1)
                    exp_load = raw if (unsigned or size == 3) else sext(raw, 8 * nbytes)
                    assert int(dut.load_data.value) == exp_load, (
                        f"load size={size} addr={addr} uns={unsigned} mem={mem:#x}")

                    exp_strb = ((1 << nbytes) - 1) << addr
                    exp_wdata = (sdata << (8 * addr)) & M64
                    assert int(dut.wstrb.value) == exp_strb, f"wstrb size={size} addr={addr}"
                    # Only the bytes covered by the strobe matter
                    mask = sum(0xFF << (8 * k) for k in range(8) if (exp_strb >> k) & 1)
                    assert int(dut.wdata.value) & mask == exp_wdata & mask, (
                        f"wdata size={size} addr={addr}")
