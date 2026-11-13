# Axral_SoC

自作 64bit RISC-V SoC（RV64I + Zicsr + Zifencei、5段パイプライン、Wishbone、UART 16550互換、CLINT）。
iPad から自宅 Linux PC へリモート接続して開発する。詳細な計画は [plan.md](plan.md)。

## 確定している設計方針
- **RTL 記述言語**: SystemVerilog（Verilator / Icarus / Yosys が扱える合成可能サブセット）
- **検証 IF**: RVFI（Spike 突き合わせ、riscv-formal）
- **メモリマップ**: Spike / QEMU virt 互換（CLINT `0x0200_0000` / UART `0x1000_0000` / RAM `0x8000_0000`）
- **UART**: 16550 互換
- **バス**: Wishbone

## ディレクトリ構成
| パス | 内容 |
|------|------|
| `rtl/` | RTL（SystemVerilog）。`hello/` は M1 用サンプル |
| `tb/` | テストベンチ（Verilator C++ / cocotb） |
| `sw/` | RISC-V 側のソフトウェア（Hello World など） |
| `scripts/` | セットアップ・補助スクリプト |
| `docs/` | 設計メモ |

## M1: Verilator Hello World
```bash
./scripts/setup_ubuntu.sh   # 初回のみ
make                        # lint + Hello World シミュレーション
```
`build/hello.fst` が生成される。iPad の Safari で Surfer（https://app.surfer-project.org/）を開き、この FST を読み込めば M1 完了。

## 開発環境メモ
- 作業ファイルは必ず Linux 側のファイルシステムに置く
- 長時間ジョブは `tmux` で実行する
- 波形は VCD ではなく FST で出力する
