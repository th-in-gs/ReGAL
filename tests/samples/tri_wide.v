module top (
    input A,
    input E1,
    input E2,
    output Y
);

// The output enable needs two product terms
assign Y = (E1 | E2) ? A : 1'bz;

endmodule
