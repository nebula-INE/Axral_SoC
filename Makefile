# Axral_SoC Makefile
VERILATOR ?= verilator
HELLO_SRCS := $(shell find rtl/hello -name '*.sv')

# CPU コア一式（cpu_tb_top は sim 専用のため lint 対象外）
CPU_CORE_SRCS := $(addprefix $(CURDIR)/rtl/core/, cpu_core.sv alu.sv regfile.sv imm_gen.sv decoder.sv lsu.sv branch_cmp.sv csr_file.sv)
CPU_TB_SRCS   := $(CURDIR)/rtl/sim/cpu_tb_top.sv $(CPU_CORE_SRCS)

.PHONY: all lint hello test clean
all: lint hello test

lint:
	$(VERILATOR) --lint-only -Wall --top-module hello_counter $(HELLO_SRCS)
	@set -e; for m in alu regfile imm_gen decoder lsu branch_cmp csr_file; do \
	  echo "lint $$m"; $(VERILATOR) --lint-only -Wall --top-module $$m rtl/core/$$m.sv; \
	done
	$(VERILATOR) --lint-only -Wall --top-module cpu_core $(CPU_CORE_SRCS)

hello:
	mkdir -p build
	$(VERILATOR) --cc --exe --build --trace-fst -Wall \
	  --top-module hello_counter -Mdir build/obj_hello \
	  $(HELLO_SRCS) $(CURDIR)/tb/verilator/sim_main.cpp -o hello_sim
	./build/obj_hello/hello_sim
	@ls -lh build/hello.fst

# cocotb（Icarus Verilog）。要: pip install cocotb==1.9.2
UNIT_TESTS := alu regfile imm_gen decoder lsu branch_cmp csr_file
test:
	@set -e; for m in $(UNIT_TESTS); do \
	  $(MAKE) -C tb/cocotb TOPLEVEL=$$m MODULE=test_$$m; \
	done
	$(MAKE) -C tb/cocotb TOPLEVEL=cpu_tb_top MODULE=test_cpu VERILOG_SOURCES="$(CPU_TB_SRCS)"

clean:
	rm -rf build tb/cocotb/sim_build_* tb/cocotb/results.xml tb/cocotb/__pycache__
