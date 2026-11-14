// RV64I ALU（組み合わせ回路）
// op の符号化は tb/cocotb/test_alu.py と一致させること。
// word=1 のとき W 系命令（ADDW/SUBW/SLLW/SRLW/SRAW 等）として下位32bitで演算し、
// 結果を64bitへ符号拡張する。ADD/SUB/SLL/SRL/SRA 以外では word は無視される。
module alu (
    input  logic [63:0] a,
    input  logic [63:0] b,
    input  logic [3:0]  op,
    input  logic        word,
    output logic [63:0] y
);
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

    logic [31:0] a32, b32, w32;
    logic [5:0]  shamt;

    assign a32   = a[31:0];
    assign b32   = b[31:0];
    // シフト量: 64bit 命令は 6bit、W 系は 5bit
    assign shamt = word ? {1'b0, b[4:0]} : b[5:0];

    always_comb begin
        w32 = 32'd0;
        y   = 64'd0;
        case (op)
            ALU_ADD: begin
                w32 = a32 + b32;
                y   = word ? {{32{w32[31]}}, w32} : a + b;
            end
            ALU_SUB: begin
                w32 = a32 - b32;
                y   = word ? {{32{w32[31]}}, w32} : a - b;
            end
            ALU_SLL: begin
                w32 = a32 << shamt[4:0];
                y   = word ? {{32{w32[31]}}, w32} : a << shamt;
            end
            ALU_SRL: begin
                w32 = a32 >> shamt[4:0];
                y   = word ? {{32{w32[31]}}, w32} : a >> shamt;
            end
            ALU_SRA: begin
                w32 = 32'($signed(a32) >>> shamt[4:0]);
                y   = word ? {{32{w32[31]}}, w32} : 64'($signed(a) >>> shamt);
            end
            ALU_SLT:  y = {63'd0, $signed(a) < $signed(b)};
            ALU_SLTU: y = {63'd0, a < b};
            ALU_XOR:  y = a ^ b;
            ALU_OR:   y = a | b;
            ALU_AND:  y = a & b;
            default:  y = 64'd0;
        endcase
    end
endmodule
