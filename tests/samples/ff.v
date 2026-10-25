module top (
    input Clk,
    input I0,
    input I1,
    input I2,

    output reg Clk2,
    output reg Clk4,
    output reg Clk8
);

initial Clk8 = 0;

// Register with enable
always @(posedge Clk)
  if (I0)
    Clk2 <= I1;

// Register with synchronous reset
always @(posedge Clk)
  if (I2)
    Clk4 <= 0;
  else
    Clk4 <= I1;

// Initialized register
always @(posedge Clk)
  Clk8 <= ~Clk8;

endmodule
