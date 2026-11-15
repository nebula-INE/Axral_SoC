// 分岐条件の比較器（BEQ/BNE/BLT/BGE/BLTU/BGEU）。funct3 は命令の funct3 をそのまま入れる。
module branch_cmp (
    input  logic [63:0] a,
    input  logic [63:0] b,
    input  logic [2:0]  funct3,
    output logic        taken
);
    always_comb begin
        case (funct3)
            3'b000:  taken = (a == b);
            3'b001:  taken = (a != b);
            3'b100:  taken = ($signed(a) <  $signed(b));
            3'b101:  taken = ($signed(a) >= $signed(b));
            3'b110:  taken = (a <  b);
            3'b111:  taken = (a >= b);
            default: taken = 1'b0;
        endcase
    end
endmodule
