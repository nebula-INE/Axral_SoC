# Axral_SoC Makefile (M1)
VERILATOR ?= verilator
RTL_SRCS  := $(shell find rtl -name '*.sv')

.PHONY: all lint hello clean
all: lint hello

lint:
	$(VERILATOR) --lint-only -Wall --top-module hello_counter $(RTL_SRCS)

hello:
	mkdir -p build
	$(VERILATOR) --cc --exe --build --trace-fst -Wall \
	  --top-module hello_counter -Mdir build/obj_hello \
	  $(RTL_SRCS) $(CURDIR)/tb/verilator/sim_main.cpp -o hello_sim
	./build/obj_hello/hello_sim
	@ls -lh build/hello.fst

clean:
	rm -rf build
