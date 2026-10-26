module top (
    input Clk,
    input I0,
    output reg Clk8,
    output O0,
    output O1,
    output O2,
    output O3,
    output O4,
    output O5,
    output O6
);

// Hidden counter bits, with every macro cell already taken by an output
reg Clk2, Clk4;

always @(posedge Clk) begin
    Clk2 <= ~Clk2;
    Clk4 <= Clk4 ^ Clk2;
    Clk8 <= Clk8 ^ (Clk4 & Clk2);
end

assign {O0, O1, O2, O3, O4, O5, O6} = {7{I0}};

endmodule
