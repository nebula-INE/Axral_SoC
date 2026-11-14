// RV64I デコーダ（組み合わせ回路）。命令語から制御信号を生成する。
//
// ALU の使い方（単一サイクル CPU 向け）:
//   通常の演算 : a = rs1,  b = rs2 または 即値
//   LUI        : a = 0,    b = 即値            -> 結果 = 即値
//   AUIPC      : a = PC,   b = 即値
//   JAL/分岐   : a = PC,   b = 即値            -> 結果 = ジャンプ先アドレス
//   JALR       : a = rs1,  b = 即値            -> 結果 = ジャンプ先（下位1bitのクリアはトップ側）
//   LOAD/STORE : a = rs1,  b = 即値            -> 結果 = メモリアドレス
//
// 現時点では SYSTEM（ecall/ebreak/mret/CSR）と M 拡張は illegal 扱い（2.3 節で対応）。
// illegal のとき、書き込み系の制御信号はすべて 0 になる。
module decoder (
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [31:0] inst,
    /* verilator lint_on UNUSEDSIGNAL */
    output logic        reg_we,        // レジスタ書き込み
    output logic [1:0]  a_sel,         // 0: rs1, 1: PC, 2: ゼロ
    output logic        b_sel_imm,     // 1: 即値, 0: rs2
    output logic [3:0]  alu_op,        // alu.sv の op と同じ符号化
    output logic        alu_word,      // W 系命令
    output logic        mem_re,
    output logic        mem_we,
    output logic [1:0]  mem_size,      // 0: B, 1: H, 2: W, 3: D
    output logic        mem_unsigned,  // ロードのゼロ拡張
    output logic [1:0]  wb_sel,        // 0: ALU, 1: メモリ, 2: PC+4
    output logic        is_branch,
    output logic        is_jal,
    output logic        is_jalr,
    output logic        illegal
);
    // alu.sv と同じ符号化
    localparam logic [3:0] ALU_ADD  = 4'd0;
    localparam logic [3:0] ALU_SUB  = 4'd1;
    localparam logic [3:0] ALU_SLL  = 4'd2;
    localparam logic [3:0] ALU_SLT  = 4'd3;
    localparam logic [3:0] ALU_SLTU = 4'd4;
    localparam logic [3:0] ALU_XOR  = 4'd5;
    localparam logic [3:0] ALU_SRL  = 4'd6;
    localparam logic [3:0] ALU_SRA  = 4'd7;
    localparam logic [3:0] ALU_OR   = 4'd8;
    localparam logic [3:0] ALU_AND  = 4'd9;

    localparam logic [1:0] A_RS1 = 2'd0, A_PC = 2'd1, A_ZERO = 2'd2;
    localparam logic [1:0] WB_ALU = 2'd0, WB_MEM = 2'd1, WB_PC4 = 2'd2;

    logic [6:0] opcode;
    logic [2:0] funct3;
    logic [6:0] funct7;
    assign opcode = inst[6:0];
    assign funct3 = inst[14:12];
    assign funct7 = inst[31:25];

    always_comb begin
        reg_we       = 1'b0;
        a_sel        = A_RS1;
        b_sel_imm    = 1'b0;
        alu_op       = ALU_ADD;
        alu_word     = 1'b0;
        mem_re       = 1'b0;
        mem_we       = 1'b0;
        mem_size     = 2'd0;
        mem_unsigned = 1'b0;
        wb_sel       = WB_ALU;
        is_branch    = 1'b0;
        is_jal       = 1'b0;
        is_jalr      = 1'b0;
        illegal      = 1'b0;

        case (opcode)
            7'b0110111: begin // LUI
                reg_we = 1'b1; a_sel = A_ZERO; b_sel_imm = 1'b1;
            end
            7'b0010111: begin // AUIPC
                reg_we = 1'b1; a_sel = A_PC; b_sel_imm = 1'b1;
            end
            7'b1101111: begin // JAL
                reg_we = 1'b1; a_sel = A_PC; b_sel_imm = 1'b1;
                wb_sel = WB_PC4; is_jal = 1'b1;
            end
            7'b1100111: begin // JALR
                if (funct3 == 3'b000) begin
                    reg_we = 1'b1; b_sel_imm = 1'b1;
                    wb_sel = WB_PC4; is_jalr = 1'b1;
                end else illegal = 1'b1;
            end
            7'b1100011: begin // BRANCH
                case (funct3)
                    3'b000, 3'b001, 3'b100, 3'b101, 3'b110, 3'b111: begin
                        a_sel = A_PC; b_sel_imm = 1'b1; is_branch = 1'b1;
                    end
                    default: illegal = 1'b1;
                endcase
            end
            7'b0000011: begin // LOAD
                if (funct3 != 3'b111) begin
                    reg_we = 1'b1; b_sel_imm = 1'b1; mem_re = 1'b1;
                    mem_size = funct3[1:0]; mem_unsigned = funct3[2];
                    wb_sel = WB_MEM;
                end else illegal = 1'b1;
            end
            7'b0100011: begin // STORE
                if (!funct3[2]) begin
                    b_sel_imm = 1'b1; mem_we = 1'b1; mem_size = funct3[1:0];
                end else illegal = 1'b1;
            end
            7'b0010011: begin // OP-IMM
                reg_we = 1'b1; b_sel_imm = 1'b1;
                case (funct3)
                    3'b000: alu_op = ALU_ADD;
                    3'b010: alu_op = ALU_SLT;
                    3'b011: alu_op = ALU_SLTU;
                    3'b100: alu_op = ALU_XOR;
                    3'b110: alu_op = ALU_OR;
                    3'b111: alu_op = ALU_AND;
                    3'b001: begin // SLLI（RV64: 上位6bitが 000000）
                        alu_op = ALU_SLL;
                        if (inst[31:26] != 6'b000000) illegal = 1'b1;
                    end
                    3'b101: begin // SRLI / SRAI
                        if (inst[31:26] == 6'b000000)      alu_op = ALU_SRL;
                        else if (inst[31:26] == 6'b010000) alu_op = ALU_SRA;
                        else                               illegal = 1'b1;
                    end
                    default: illegal = 1'b1;
                endcase
            end
            7'b0110011: begin // OP
                reg_we = 1'b1;
                if (funct7 == 7'b0000000) begin
                    case (funct3)
                        3'b000: alu_op = ALU_ADD;
                        3'b001: alu_op = ALU_SLL;
                        3'b010: alu_op = ALU_SLT;
                        3'b011: alu_op = ALU_SLTU;
                        3'b100: alu_op = ALU_XOR;
                        3'b101: alu_op = ALU_SRL;
                        3'b110: alu_op = ALU_OR;
                        3'b111: alu_op = ALU_AND;
                        default: illegal = 1'b1;
                    endcase
                end else if (funct7 == 7'b0100000) begin
                    case (funct3)
                        3'b000: alu_op = ALU_SUB;
                        3'b101: alu_op = ALU_SRA;
                        default: illegal = 1'b1;
                    endcase
                end else illegal = 1'b1;
            end
            7'b0011011: begin // OP-IMM-32
                reg_we = 1'b1; b_sel_imm = 1'b1; alu_word = 1'b1;
                case (funct3)
                    3'b000: alu_op = ALU_ADD; // ADDIW
                    3'b001: begin             // SLLIW
                        alu_op = ALU_SLL;
                        if (funct7 != 7'b0000000) illegal = 1'b1;
                    end
                    3'b101: begin             // SRLIW / SRAIW
                        if (funct7 == 7'b0000000)      alu_op = ALU_SRL;
                        else if (funct7 == 7'b0100000) alu_op = ALU_SRA;
                        else                           illegal = 1'b1;
                    end
                    default: illegal = 1'b1;
                endcase
            end
            7'b0111011: begin // OP-32
                reg_we = 1'b1; alu_word = 1'b1;
                if (funct7 == 7'b0000000) begin
                    case (funct3)
                        3'b000: alu_op = ALU_ADD;
                        3'b001: alu_op = ALU_SLL;
                        3'b101: alu_op = ALU_SRL;
                        default: illegal = 1'b1;
                    endcase
                end else if (funct7 == 7'b0100000) begin
                    case (funct3)
                        3'b000: alu_op = ALU_SUB;
                        3'b101: alu_op = ALU_SRA;
                        default: illegal = 1'b1;
                    endcase
                end else illegal = 1'b1;
            end
            7'b0001111: begin // MISC-MEM: FENCE(000) / FENCE.I(001) は NOP 扱い
                if (funct3 != 3'b000 && funct3 != 3'b001) illegal = 1'b1;
            end
            default: illegal = 1'b1; // SYSTEM、圧縮命令、未定義 opcode
        endcase

        // 不正命令は副作用を持たせない
        if (illegal) begin
            reg_we       = 1'b0;
            a_sel        = A_RS1;
            b_sel_imm    = 1'b0;
            alu_op       = ALU_ADD;
            alu_word     = 1'b0;
            mem_re       = 1'b0;
            mem_we       = 1'b0;
            mem_size     = 2'd0;
            mem_unsigned = 1'b0;
            wb_sel       = WB_ALU;
            is_branch    = 1'b0;
            is_jal       = 1'b0;
            is_jalr      = 1'b0;
        end
    end
endmodule
