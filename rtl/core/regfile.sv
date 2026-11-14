// 64bit x 32本のレジスタファイル（読み出し2ポート、書き込み1ポート）
// - x0 は常に 0（書き込み無視）
// - 読み出しは組み合わせ。同一サイクルの書き込みを読み出しへ転送する（WB→ID のバイパス）
module regfile (
    input  logic        clk,
    input  logic        we,
    input  logic [4:0]  waddr,
    input  logic [63:0] wdata,
    input  logic [4:0]  raddr1,
    input  logic [4:0]  raddr2,
    output logic [63:0] rdata1,
    output logic [63:0] rdata2
);
    logic [63:0] regs [1:31];

    always_ff @(posedge clk) begin
        if (we && waddr != 5'd0) regs[waddr] <= wdata;
    end

    always_comb begin
        if (raddr1 == 5'd0)                    rdata1 = 64'd0;
        else if (we && waddr == raddr1)        rdata1 = wdata;
        else                                   rdata1 = regs[raddr1];

        if (raddr2 == 5'd0)                    rdata2 = 64'd0;
        else if (we && waddr == raddr2)        rdata2 = wdata;
        else                                   rdata2 = regs[raddr2];
    end
endmodule
