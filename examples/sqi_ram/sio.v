// SIO driver for the 23LC512: command nibbles, write data, and EQIO after
// power-up. GAL16V8, complex mode. Drives the SIO lines while K (the
// sequencer's nibble number) is 0-7; the address buffers drive them for
// K 8-11 and the RAM for K 12-15.

module top (
    input K0,
    input K1,
    input K2,
    input K3,
    input PEND,
    input D0, input D1, input D2, input D3,
    input D4, input D5, input D6, input D7,

    output SIO0,
    output SIO1,
    output SIO2,
    output SIO3
);

wire [2:0] k = {K2, K1, K0};
reg [3:0] sio;

always @(*) begin
    if (PEND)
        // EQIO (0x38) in SPI mode, on SI (SIO0), with HOLD (SIO3) high
        sio = {3'b111, k == 3 || k == 5 || k == 7};
    else
        case (k)
            3: sio = 4'b0011;                // READ (0x03), low nibble
            5: sio = 4'b0010;                // WRITE (0x02), low nibble
            2: sio = {D7, D6, D5, D4};
            1: sio = {D3, D2, D1, D0};
            default: sio = 4'b0000;             // command, high nibble
        endcase
end

assign SIO0 = K3 ? 1'bz : sio[0];
assign SIO1 = K3 ? 1'bz : sio[1];
assign SIO2 = K3 ? 1'bz : sio[2];
assign SIO3 = K3 ? 1'bz : sio[3];

endmodule
