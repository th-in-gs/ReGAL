module top (
    input Clk,
    output reg Clk8
);

// Divide-by-8 with the lower counter bits kept internal
reg Clk2, Clk4;

always @(posedge Clk) begin
    Clk2 <= ~Clk2;
    Clk4 <= Clk4 ^ Clk2;
    Clk8 <= Clk8 ^ (Clk4 & Clk2);
end

endmodule
