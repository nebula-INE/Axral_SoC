// M1 用 Hello World: 8bit カウンタ。Verilator + FST 波形出力の動作確認用。
module hello_counter (
    input  logic       clk,
    input  logic       rst_n,
    output logic [7:0] count
);
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) count <= 8'd0;
        else        count <= count + 8'd1;
    end
endmodule
