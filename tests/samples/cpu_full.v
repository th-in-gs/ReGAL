// MC14500B-style 1-bit ICU with a return output: one output too many for a
// GAL16V8, since RR needs a spare macro cell
module top (
    input Clk,
    input I0, I1, I2, I3,   // opcode
    input DIN,              // data bus in
    output reg RR,          // result register
    output reg IEN,         // input enable
    output reg OEN,         // output enable
    output reg SKIP,        // skip next instruction
    output WRITE,           // store strobe
    output DOUT,            // data to store
    output JMP,
    output RTN
);
wire [3:0] op = {I3, I2, I1, I0};
wire d = DIN & IEN;         // masked data
wire run = ~SKIP;

always @(posedge Clk) begin
    if (run) case (op)
        4'h1: RR <= d;          // LD
        4'h2: RR <= ~d;         // LDC
        4'h3: RR <= RR & d;     // AND
        4'h4: RR <= RR & ~d;    // ANDC
        4'h5: RR <= RR | d;     // OR
        4'h6: RR <= RR | ~d;    // ORC
        4'h7: RR <= ~(RR ^ d);  // XNOR
    endcase
    if (run && op == 4'hA) IEN <= DIN;
    if (run && op == 4'hB) OEN <= DIN;
    SKIP <= run && op == 4'hE && ~RR;   // SKZ
end

assign WRITE = run & OEN & (op == 4'h8 | op == 4'h9);
assign DOUT  = (op == 4'h9) ? ~RR : RR;
assign JMP   = run & (op == 4'hC);
assign RTN   = run & (op == 4'hD);
endmodule
