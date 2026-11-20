// RV64I 単一サイクル CPU コア（命令メモリ・データメモリは外部）+ M-mode 例外
//
// - 命令フェッチ: imem_addr（= PC）に対し imem_rdata を同一サイクルで返すこと
// - データアクセス: 64bit ワード単位 + バイトストローブ。dmem_rdata は同一サイクルで返すこと
// - 例外（M-mode のみ）: 不正命令(2)、ブレークポイント(3)、ecall(11)、
//   命令/ロード/ストアのミスアライン(0/4/6)。mepc/mcause/mtval を設定して mtvec へ飛ぶ。
//   例外を起こした命令は、レジスタ・メモリ・CSR を一切更新しない。
// - CSR 命令（Zicsr）と mret に対応。割り込みは未対応（3.2 節の CLINT で追加）。
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

    output logic        illegal_inst,  // デコーダが不正命令と判定（デバッグ用）
    output logic        trap_taken     // このサイクルで例外が発生（デバッグ用）
);
    localparam logic [63:0] CAUSE_MISALIGNED_FETCH = 64'd0;
    localparam logic [63:0] CAUSE_ILLEGAL          = 64'd2;
    localparam logic [63:0] CAUSE_BREAKPOINT       = 64'd3;
    localparam logic [63:0] CAUSE_LOAD_MISALIGNED  = 64'd4;
    localparam logic [63:0] CAUSE_STORE_MISALIGNED = 64'd6;
    localparam logic [63:0] CAUSE_ECALL_M          = 64'd11;

    logic [63:0] pc, pc4, next_pc;
    logic [31:0] inst;

    // デコード結果
    logic        reg_we, b_sel_imm, alu_word, mem_re, mem_we, mem_unsigned;
    logic        is_branch, is_jal, is_jalr, is_csr, is_ecall, is_ebreak, is_mret;
    logic [1:0]  a_sel, mem_size, wb_sel;
    logic [3:0]  alu_op;

    logic [63:0] imm, rs1_d, rs2_d, alu_a, alu_b, alu_y, wb_data;
    logic [63:0] load_data, lsu_wdata;
    logic [7:0]  lsu_wstrb;
    logic        br_taken;

    // CSR
    logic [63:0] csr_rdata, csr_src, csr_new, mtvec_target, mepc_out;
    logic        csr_illegal, csr_write_attempt, csr_fault;

    // 例外
    logic [63:0] jump_target, exc_cause, exc_tval;
    logic        jump_taken, fetch_misaligned, misaligned_addr, load_misaligned, store_misaligned, trap;

    assign inst      = imem_rdata;
    assign imem_addr = pc;
    assign pc4       = pc + 64'd4;

    decoder u_decoder (
        .inst(inst), .reg_we(reg_we), .a_sel(a_sel), .b_sel_imm(b_sel_imm),
        .alu_op(alu_op), .alu_word(alu_word), .mem_re(mem_re), .mem_we(mem_we),
        .mem_size(mem_size), .mem_unsigned(mem_unsigned), .wb_sel(wb_sel),
        .is_branch(is_branch), .is_jal(is_jal), .is_jalr(is_jalr),
        .is_csr(is_csr), .is_ecall(is_ecall), .is_ebreak(is_ebreak), .is_mret(is_mret),
        .illegal(illegal_inst)
    );

    imm_gen u_imm_gen (.inst(inst), .imm(imm));

    // 単一サイクルでは BYPASS=0 必須（転送すると組み合わせループになる）
    regfile #(.BYPASS(1'b0)) u_regfile (
        .clk(clk), .we(reg_we & ~trap), .waddr(inst[11:7]), .wdata(wb_data),
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

    // ---- CSR 命令 ----
    // funct3[2]=1 は即値版（uimm = inst[19:15]）。funct3[1:0]: 01=RW, 10=RS, 11=RC
    assign csr_src = inst[14] ? {59'd0, inst[19:15]} : rs1_d;
    // CSRRS/CSRRC は rs1(uimm)=0 のとき書き込まない
    assign csr_write_attempt = is_csr & ((inst[13:12] == 2'b01) | (inst[19:15] != 5'd0));
    always_comb begin
        case (inst[13:12])
            2'b01:   csr_new = csr_src;
            2'b10:   csr_new = csr_rdata | csr_src;
            default: csr_new = csr_rdata & ~csr_src;
        endcase
    end
    assign csr_fault = is_csr & csr_illegal;

    csr_file u_csr (
        .clk(clk), .rst_n(rst_n),
        .csr_addr(inst[31:20]), .csr_write_attempt(csr_write_attempt),
        .csr_wen(csr_write_attempt & ~trap), .csr_wdata(csr_new),
        .csr_rdata(csr_rdata), .csr_illegal(csr_illegal),
        .trap_en(trap), .trap_pc(pc), .trap_cause(exc_cause), .trap_tval(exc_tval),
        .mret_en(is_mret & ~trap),
        .mtvec_target(mtvec_target), .mepc_out(mepc_out)
    );

    // ---- 例外の検出 ----
    assign jump_taken       = is_jal | is_jalr | (is_branch & br_taken);
    assign jump_target      = is_jalr ? {alu_y[63:1], 1'b0} : alu_y;
    assign fetch_misaligned = jump_taken & (jump_target[1:0] != 2'b00);

    always_comb begin
        case (mem_size)
            2'd1:    misaligned_addr = alu_y[0];
            2'd2:    misaligned_addr = |alu_y[1:0];
            2'd3:    misaligned_addr = |alu_y[2:0];
            default: misaligned_addr = 1'b0;
        endcase
        load_misaligned  = mem_re & misaligned_addr;
        store_misaligned = mem_we & misaligned_addr;
    end

    always_comb begin
        trap      = 1'b1;
        exc_cause = CAUSE_ILLEGAL;
        exc_tval  = 64'd0;
        if (illegal_inst || csr_fault) begin
            exc_cause = CAUSE_ILLEGAL;          exc_tval = {32'd0, inst};
        end else if (is_ecall) begin
            exc_cause = CAUSE_ECALL_M;          exc_tval = 64'd0;
        end else if (is_ebreak) begin
            exc_cause = CAUSE_BREAKPOINT;       exc_tval = pc;
        end else if (fetch_misaligned) begin
            exc_cause = CAUSE_MISALIGNED_FETCH; exc_tval = jump_target;
        end else if (load_misaligned) begin
            exc_cause = CAUSE_LOAD_MISALIGNED;  exc_tval = alu_y;
        end else if (store_misaligned) begin
            exc_cause = CAUSE_STORE_MISALIGNED; exc_tval = alu_y;
        end else begin
            trap = 1'b0;
        end
    end

    assign trap_taken = trap;

    // ---- メモリ、書き戻し、次の PC ----
    assign dmem_addr  = alu_y;
    assign dmem_re    = mem_re & ~trap;
    assign dmem_we    = mem_we & ~trap;
    assign dmem_wstrb = dmem_we ? lsu_wstrb : 8'd0;
    assign dmem_wdata = lsu_wdata;

    always_comb begin
        case (wb_sel)
            2'd1:    wb_data = load_data;
            2'd2:    wb_data = pc4;
            2'd3:    wb_data = csr_rdata;
            default: wb_data = alu_y;
        endcase

        if (trap)           next_pc = mtvec_target;
        else if (is_mret)   next_pc = mepc_out;
        else if (jump_taken) next_pc = jump_target;
        else                next_pc = pc4;
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) pc <= RESET_PC;
        else        pc <= next_pc;
    end
endmodule
