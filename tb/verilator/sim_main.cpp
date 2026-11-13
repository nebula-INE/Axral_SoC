// M1 用 Verilator テストベンチ（C++）。FST 波形を build/hello.fst に出力する。
#include <cstdio>
#include <cstdlib>
#include "Vhello_counter.h"
#include "verilated.h"
#include "verilated_fst_c.h"

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    Verilated::traceEverOn(true);

    auto* dut = new Vhello_counter;
    auto* tfp = new VerilatedFstC;
    dut->trace(tfp, 99);
    tfp->open("build/hello.fst");

    uint64_t t = 0;
    dut->clk = 0; dut->rst_n = 0;
    for (int cycle = 0; cycle < 40; ++cycle) {
        if (cycle == 4) dut->rst_n = 1;
        dut->clk = 0; dut->eval(); tfp->dump(t++);
        dut->clk = 1; dut->eval(); tfp->dump(t++);
    }
    tfp->close();

    std::printf("Hello, RISC-V SoC! final count = %u\n", (unsigned)dut->count);
    // 期待値: リセット解除後のクロック数 = 40 - 4 = 36
    int rc = (dut->count == 36) ? 0 : 1;
    delete tfp; delete dut;
    return rc;
}
