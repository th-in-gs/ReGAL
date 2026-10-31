module top (
    input A,
    input B,
    input E1,
    input E2,
    output Y
);

assign Y = (E1 & !E2) ? (A ^ B) : 1'bz;

endmodule
