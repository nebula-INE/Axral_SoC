// シミュレーション専用: cpu_core + 単純な RAM（命令・データ共用、非同期読み出し）
// RAM は 0x8000_0000 から。範囲外の読み出しは 0、書き込みは無視。
// プログラムはリセット中にローダ（load_*）で書き込む。デバッグ用にレジスタ・メモリ・PC を読める。
module cpu_tb_top #(
    parameter int RAM_DWORDS = 4096
) (
    input  logic        clk,
    input  logic        rst_n,

    // プログラムローダ（32bit ワード単位、load_addr はワード番号）
    input  logic        load_we,
    input  logic [31:0] load_addr,
    input  logic [31:0] load_data,

    // デバッグ
    input  logic [4:0]  dbg_reg_addr,
    output logic [63:0] dbg_reg_data,
    input  logic [31:0] dbg_mem_idx,     // 64bit ワード番号（RAM 先頭から）
    output logic [63:0] dbg_mem_data,
    output logic [63:0] dbg_pc,
    output logic        illegal_inst
);
    localparam logic [63:0] RAM_BASE = 64'h0000_0000_8000_0000;
    localparam int AW = $clog2(RAM_DWORDS);

    logic [63:0] mem [0:RAM_DWORDS-1];

    initial begin
        for (int i = 0; i < RAM_DWORDS; i++) mem[i] = 64'd0;
    end

    logic [63:0] imem_addr, dmem_addr, dmem_wdata, dmem_rdata;
    logic [31:0] imem_rdata;
    logic [7:0]  dmem_wstrb;
    logic        dmem_re, dmem_we;

    cpu_core u_cpu (
        .clk(clk), .rst_n(rst_n),
        .imem_addr(imem_addr), .imem_rdata(imem_rdata),
        .dmem_addr(dmem_addr), .dmem_re(dmem_re), .dmem_we(dmem_we),
        .dmem_wstrb(dmem_wstrb), .dmem_wdata(dmem_wdata), .dmem_rdata(dmem_rdata),
        .illegal_inst(illegal_inst)
    );

    // 命令フェッチ
    logic [63:0] i_off, i_dw;
    logic        i_ok;
    assign i_off      = imem_addr - RAM_BASE;
    assign i_ok       = (i_off < 64'(RAM_DWORDS * 8));
    assign i_dw       = i_ok ? mem[i_off[AW+2:3]] : 64'd0;
    assign imem_rdata = imem_addr[2] ? i_dw[63:32] : i_dw[31:0];

    // データ読み出し
    logic [63:0] d_off;
    logic        d_ok;
    assign d_off      = dmem_addr - RAM_BASE;
    assign d_ok       = (d_off < 64'(RAM_DWORDS * 8));
    assign dmem_rdata = d_ok ? mem[d_off[AW+2:3]] : 64'd0;

    // 書き込み（ローダ + CPU）
    always_ff @(posedge clk) begin
        if (load_we) begin
            if (load_addr[0]) mem[load_addr[AW:1]][63:32] <= load_data;
            else              mem[load_addr[AW:1]][31:0]  <= load_data;
        end
        if (dmem_we && d_ok) begin
            for (int i = 0; i < 8; i++)
                if (dmem_wstrb[i]) mem[d_off[AW+2:3]][8*i +: 8] <= dmem_wdata[8*i +: 8];
        end
    end

    assign dbg_pc       = imem_addr;
    assign dbg_mem_data = mem[dbg_mem_idx[AW-1:0]];
    assign dbg_reg_data = (dbg_reg_addr == 5'd0) ? 64'd0 : u_cpu.u_regfile.regs[dbg_reg_addr];
endmodule
