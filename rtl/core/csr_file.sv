// M-mode 専用の最小 CSR ファイル（RV64）
//
// 実装する CSR:
//   mstatus(0x300) misa(0x301) mie(0x304) mtvec(0x305) mscratch(0x340) mepc(0x341)
//   mcause(0x342) mtval(0x343) mip(0x344) mvendorid(0xF11) marchid(0xF12) mimpid(0xF13) mhartid(0xF14)
//
// 仕様上の割り切り（WARL）:
//   - mstatus: MIE(3)/MPIE(7) のみ書き込み可。MPP は M-mode のみのため常に 2'b11。
//   - mie: MSIE(3)/MTIE(7)/MEIE(11) のみ。mip は現時点では常に 0（割り込みは 3.2 節の CLINT で追加）。
//   - mtvec: MODE は 0(direct) / 1(vectored) のみ。例外の飛び先は常に BASE。
//   - mepc: 下位 2bit は 0（C 拡張なし = IALIGN=32）。
//   - misa は RV64I 固定（書き込み無視）。mhartid/mvendorid/marchid/mimpid は 0 の読み出し専用。
module csr_file (
    input  logic        clk,
    input  logic        rst_n,

    // CSR 命令からのアクセス
    input  logic [11:0] csr_addr,
    input  logic        csr_write_attempt,  // 書き込みを伴う命令か（不正判定用。トラップで止めない値）
    input  logic        csr_wen,            // 実際に書き込む（トラップ時は 0）
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [63:0] csr_wdata,   // [1] は mtvec/mepc で未使用
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [63:0] csr_rdata,
    output logic        csr_illegal,        // 未実装 CSR、または読み出し専用への書き込み

    // トラップ / mret
    input  logic        trap_en,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [63:0] trap_pc,     // [1:0] は未使用（IALIGN=32）
    /* verilator lint_on UNUSEDSIGNAL */
    input  logic [63:0] trap_cause,
    input  logic [63:0] trap_tval,
    input  logic        mret_en,

    output logic [63:0] mtvec_target,
    output logic [63:0] mepc_out
);
    localparam logic [11:0] CSR_MSTATUS   = 12'h300;
    localparam logic [11:0] CSR_MISA      = 12'h301;
    localparam logic [11:0] CSR_MIE       = 12'h304;
    localparam logic [11:0] CSR_MTVEC     = 12'h305;
    localparam logic [11:0] CSR_MSCRATCH  = 12'h340;
    localparam logic [11:0] CSR_MEPC      = 12'h341;
    localparam logic [11:0] CSR_MCAUSE    = 12'h342;
    localparam logic [11:0] CSR_MTVAL     = 12'h343;
    localparam logic [11:0] CSR_MIP       = 12'h344;
    localparam logic [11:0] CSR_MVENDORID = 12'hF11;
    localparam logic [11:0] CSR_MARCHID   = 12'hF12;
    localparam logic [11:0] CSR_MIMPID    = 12'hF13;
    localparam logic [11:0] CSR_MHARTID   = 12'hF14;

    localparam logic [63:0] MISA_VALUE = 64'h8000_0000_0000_0100;  // MXL=2 (RV64), I
    localparam logic [63:0] MIE_MASK   = 64'h0000_0000_0000_0888;  // MSIE | MTIE | MEIE

    logic        mie_q, mpie_q;
    logic [63:0] mie_reg_q, mtvec_q, mscratch_q, mepc_q, mcause_q, mtval_q;
    logic [63:0] mstatus_val;

    assign mstatus_val  = {51'd0, 2'b11, 3'd0, mpie_q, 3'd0, mie_q, 3'd0};
    assign mtvec_target = {mtvec_q[63:2], 2'b00};
    assign mepc_out     = mepc_q;

    always_comb begin
        csr_illegal = 1'b0;
        csr_rdata   = 64'd0;
        case (csr_addr)
            CSR_MSTATUS:   csr_rdata = mstatus_val;
            CSR_MISA:      csr_rdata = MISA_VALUE;
            CSR_MIE:       csr_rdata = mie_reg_q;
            CSR_MTVEC:     csr_rdata = mtvec_q;
            CSR_MSCRATCH:  csr_rdata = mscratch_q;
            CSR_MEPC:      csr_rdata = mepc_q;
            CSR_MCAUSE:    csr_rdata = mcause_q;
            CSR_MTVAL:     csr_rdata = mtval_q;
            CSR_MIP:       csr_rdata = 64'd0;
            CSR_MVENDORID, CSR_MARCHID, CSR_MIMPID, CSR_MHARTID: csr_rdata = 64'd0;
            default:       csr_illegal = 1'b1;
        endcase
        // アドレス上位2bitが 11 の CSR は読み出し専用
        if (csr_write_attempt && csr_addr[11:10] == 2'b11) csr_illegal = 1'b1;
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mie_q      <= 1'b0;
            mpie_q     <= 1'b0;
            mie_reg_q  <= 64'd0;
            mtvec_q    <= 64'd0;
            mscratch_q <= 64'd0;
            mepc_q     <= 64'd0;
            mcause_q   <= 64'd0;
            mtval_q    <= 64'd0;
        end else if (trap_en) begin
            mepc_q   <= {trap_pc[63:2], 2'b00};
            mcause_q <= trap_cause;
            mtval_q  <= trap_tval;
            mpie_q   <= mie_q;
            mie_q    <= 1'b0;
        end else if (mret_en) begin
            mie_q  <= mpie_q;
            mpie_q <= 1'b1;
        end else if (csr_wen) begin
            case (csr_addr)
                CSR_MSTATUS: begin
                    mie_q  <= csr_wdata[3];
                    mpie_q <= csr_wdata[7];
                end
                CSR_MIE:      mie_reg_q  <= csr_wdata & MIE_MASK;
                CSR_MTVEC:    mtvec_q    <= {csr_wdata[63:2], 1'b0, csr_wdata[0]};
                CSR_MSCRATCH: mscratch_q <= csr_wdata;
                CSR_MEPC:     mepc_q     <= {csr_wdata[63:2], 2'b00};
                CSR_MCAUSE:   mcause_q   <= csr_wdata;
                CSR_MTVAL:    mtval_q    <= csr_wdata;
                default: ;  // misa/mip は書き込み無視、読み出し専用は不正命令側で処理
            endcase
        end
    end
endmodule
