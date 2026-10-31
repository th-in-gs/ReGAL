module top (
    input A,
    input B,
    input E1,
    input E2,
    output Y
);

// Same as tri.v, with the high-impedance value on the other side
assign Y = (!E1 | E2) ? 1'bz : (A ^ B);

endmodule
