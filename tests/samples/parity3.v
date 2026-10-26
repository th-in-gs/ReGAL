module top (
    input I0,
    input I1,
    input I2,
    input I3,
    input I4,
    input I5,
    input I6,
    output O0,
    output O1,
    output O2
);

// Each output needs 16 product terms: more than the spare macro cells left
assign O0 = I0 ^ I1 ^ I2 ^ I3 ^ I4;
assign O1 = I1 ^ I2 ^ I3 ^ I4 ^ I5;
assign O2 = I2 ^ I3 ^ I4 ^ I5 ^ I6;

endmodule
