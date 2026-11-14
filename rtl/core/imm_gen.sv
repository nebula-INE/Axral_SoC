// 即値生成器: 命令語から 64bit に符号拡張した即値を作る（I/S/B/U/J 形式）。
// R 形式や未対応の opcode では 0 を返す。
module imm_gen (
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [31:0] inst,
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [63:0] imm
);
    always_comb begin
        case (inst[6:0])
            // I 形式: OP-IMM, OP-IMM-32, LOAD, JALR
            7'b0010011, 7'b0011011, 7'b0000011, 7'b1100111:
                imm = {{52{inst[31]}}, inst[31:20]};
            // S 形式: STORE
            7'b0100011:
                imm = {{52{inst[31]}}, inst[31:25], inst[11:7]};
            // B 形式: BRANCH（最下位ビットは常に 0）
            7'b1100011:
                imm = {{51{inst[31]}}, inst[31], inst[7], inst[30:25], inst[11:8], 1'b0};
            // U 形式: LUI, AUIPC
            7'b0110111, 7'b0010111:
                imm = {{32{inst[31]}}, inst[31:12], 12'd0};
            // J 形式: JAL（最下位ビットは常に 0）
            7'b1101111:
                imm = {{43{inst[31]}}, inst[31], inst[19:12], inst[20], inst[30:21], 1'b0};
            default:
                imm = 64'd0;
        endcase
    end
endmodule
