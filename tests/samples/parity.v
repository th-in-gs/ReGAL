module top (
    input I0,
    input I1,
    input I2,
    input I3,
    input I4,
    output O
);

// 16 product terms when flattened, more than a macro cell can hold
assign O = I0 ^ I1 ^ I2 ^ I3 ^ I4;

endmodule
