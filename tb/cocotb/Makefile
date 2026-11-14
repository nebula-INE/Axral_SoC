# cocotb 用 Makefile。通常は最上位の Makefile から呼ぶ（make test）。
#   make -C tb/cocotb TOPLEVEL=alu MODULE=test_alu
SIM ?= icarus
TOPLEVEL_LANG ?= verilog
TOPLEVEL ?= alu
MODULE ?= test_alu
VERILOG_SOURCES = $(abspath ../../rtl/core/$(TOPLEVEL).sv)
COMPILE_ARGS += -g2012
SIM_BUILD ?= sim_build_$(TOPLEVEL)

include $(shell cocotb-config --makefiles)/Makefile.sim
