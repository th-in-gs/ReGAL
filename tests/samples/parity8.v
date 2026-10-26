module top (
    input I0,
    input I1,
    input I2,
    input I3,
    input I4,
    input I5,
    input I6,
    input I7,
    output O
);

// 128 product terms when flattened, too many to split over macro cells
assign O = I0 ^ I1 ^ I2 ^ I3 ^ I4 ^ I5 ^ I6 ^ I7;

endmodule
