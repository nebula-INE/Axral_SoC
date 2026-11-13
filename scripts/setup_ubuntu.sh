#!/usr/bin/env bash
# Ubuntu / Linux Mint 用セットアップ（M1 の最低限）。
# Tailscale・Spike・RISC-V ツールチェーンなどは README の手順に従って別途導入する。
set -euo pipefail

sudo apt-get update
sudo apt-get install -y \
  build-essential git tmux ccache \
  verilator iverilog \
  python3 python3-venv python3-pip \
  openssh-server

# cocotb（venv 内）
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install cocotb pytest

echo "OK: verilator=$(verilator --version)"
