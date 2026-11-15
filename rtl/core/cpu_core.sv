// RV64I 単一サイクル CPU コア（命令メモリ・データメモリは外部）
//
// - 命令フェッチ: imem_addr（= PC）に対し imem_rdata を同一サイクルで返すこと
// - データアクセス: 64bit ワード単位 + バイトストローブ。dmem_rdata は同一サイクルで返すこと
// - 不正命令（現状は SYSTEM/M拡張なども含む）を検出すると illegal_inst を立て、PC を止める
// - ミスアライン・アクセス、CSR、例外は未対応（2.3 節で追加）
module cpu_core #(
    parameter logic [63:0] RESET_PC = 64'h0000_0000_8000_0000
) (
    input  logic        clk,
    input  logic        rst_n,

    output logic [63:0] imem_addr,
    input  logic [31:0] imem_rdata,

    output logic [63:0] dmem_addr,
    output logic        dmem_re,
    output logic        dmem_we,
    output logic [7:0]  dmem_wstrb,
    output logic [63:0] dmem_wdata,
    input  logic [63:0] dmem_rdata,

    output logic        illegal_inst
);
    logic [63:0] pc, pc4, next_pc;
    logic [31:0] inst;

    // デコード結果
    logic        reg_we, b_sel_imm, alu_word, mem_re, mem_we, mem_unsigned;
    logic        is_branch, is_jal, is_jalr;
    logic [1:0]  a_sel, mem_size, wb_sel;
    logic [3:0]  alu_op;

    logic [63:0] imm, rs1_d, rs2_d, alu_a, alu_b, alu_y, wb_data;
    logic [63:0] load_data, lsu_wdata;
    logic [7:0]  lsu_wstrb;
    logic        br_taken;

    assign inst      = imem_rdata;
    assign imem_addr = pc;
    assign pc4       = pc + 64'd4;

    decoder u_decoder (
        .inst(inst), .reg_we(reg_we), .a_sel(a_sel), .b_sel_imm(b_sel_imm),
        .alu_op(alu_op), .alu_word(alu_word), .mem_re(mem_re), .mem_we(mem_we),
        .mem_size(mem_size), .mem_unsigned(mem_unsigned), .wb_sel(wb_sel),
        .is_branch(is_branch), .is_jal(is_jal), .is_jalr(is_jalr), .illegal(illegal_inst)
    );

    imm_gen u_imm_gen (.inst(inst), .imm(imm));

    regfile #(.BYPASS(1'b0)) u_regfile (
        .clk(clk), .we(reg_we), .waddr(inst[11:7]), .wdata(wb_data),
        .raddr1(inst[19:15]), .raddr2(inst[24:20]), .rdata1(rs1_d), .rdata2(rs2_d)
    );

    always_comb begin
        case (a_sel)
            2'd1:    alu_a = pc;
            2'd2:    alu_a = 64'd0;
            default: alu_a = rs1_d;
        endcase
        alu_b = b_sel_imm ? imm : rs2_d;
    end

    alu u_alu (.a(alu_a), .b(alu_b), .op(alu_op), .word(alu_word), .y(alu_y));

    branch_cmp u_branch_cmp (.a(rs1_d), .b(rs2_d), .funct3(inst[14:12]), .taken(br_taken));

    lsu u_lsu (
        .addr(alu_y[2:0]), .size(mem_size), .is_unsigned(mem_unsigned),
        .store_data(rs2_d), .mem_rdata(dmem_rdata),
        .load_data(load_data), .wstrb(lsu_wstrb), .wdata(lsu_wdata)
    );

    assign dmem_addr  = alu_y;
    assign dmem_re    = mem_re;
    assign dmem_we    = mem_we;
    assign dmem_wstrb = mem_we ? lsu_wstrb : 8'd0;
    assign dmem_wdata = lsu_wdata;

    always_comb begin
        case (wb_sel)
            2'd1:    wb_data = load_data;
            2'd2:    wb_data = pc4;
            default: wb_data = alu_y;
        endcase

        if (is_jal || (is_branch && br_taken)) next_pc = alu_y;
        else if (is_jalr)                      next_pc = {alu_y[63:1], 1'b0};
        else                                   next_pc = pc4;
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)             pc <= RESET_PC;
        else if (!illegal_inst) pc <= next_pc;
    end
endmodule
