# Axral_SoC Makefile
VERILATOR ?= verilator
HELLO_SRCS := $(shell find rtl/hello -name '*.sv')

.PHONY: all lint hello test clean
all: lint hello test

lint:
	$(VERILATOR) --lint-only -Wall --top-module hello_counter $(HELLO_SRCS)
	$(VERILATOR) --lint-only -Wall --top-module alu rtl/core/alu.sv
	$(VERILATOR) --lint-only -Wall --top-module regfile rtl/core/regfile.sv

hello:
	mkdir -p build
	$(VERILATOR) --cc --exe --build --trace-fst -Wall \
	  --top-module hello_counter -Mdir build/obj_hello \
	  $(HELLO_SRCS) $(CURDIR)/tb/verilator/sim_main.cpp -o hello_sim
	./build/obj_hello/hello_sim
	@ls -lh build/hello.fst

# cocotb（Icarus Verilog）。要: pip install cocotb==1.9.2
test:
	$(MAKE) -C tb/cocotb TOPLEVEL=alu MODULE=test_alu
	$(MAKE) -C tb/cocotb TOPLEVEL=regfile MODULE=test_regfile

clean:
	rm -rf build tb/cocotb/sim_build_* tb/cocotb/results.xml tb/cocotb/__pycache__
