// ロード/ストアのデータ整形（64bit ワード単位のメモリ向け）
// - ロード : mem_rdata（アドレスを含む 64bit ワード）から該当バイトを取り出し、符号/ゼロ拡張
// - ストア : store_data を該当レーンへ寄せ、バイトストローブ wstrb を作る
// ミスアライン・アクセスは未対応（2.3 節の例外対応で扱う）。
module lsu (
    input  logic [2:0]  addr,         // アドレスの下位3bit（ワード内バイト位置）
    input  logic [1:0]  size,         // 0: B, 1: H, 2: W, 3: D
    input  logic        is_unsigned,  // ロードをゼロ拡張
    input  logic [63:0] store_data,
    input  logic [63:0] mem_rdata,
    output logic [63:0] load_data,
    output logic [7:0]  wstrb,
    output logic [63:0] wdata
);
    logic [63:0] raw;
    logic [7:0]  mask;

    assign raw = mem_rdata >> {addr, 3'b000};

    always_comb begin
        case (size)
            2'd0:    load_data = is_unsigned ? {56'd0, raw[7:0]}  : {{56{raw[7]}},  raw[7:0]};
            2'd1:    load_data = is_unsigned ? {48'd0, raw[15:0]} : {{48{raw[15]}}, raw[15:0]};
            2'd2:    load_data = is_unsigned ? {32'd0, raw[31:0]} : {{32{raw[31]}}, raw[31:0]};
            default: load_data = raw;
        endcase

        case (size)
            2'd0:    mask = 8'h01;
            2'd1:    mask = 8'h03;
            2'd2:    mask = 8'h0F;
            default: mask = 8'hFF;
        endcase
    end

    assign wstrb = mask << addr;
    assign wdata = store_data << {addr, 3'b000};
endmodule
