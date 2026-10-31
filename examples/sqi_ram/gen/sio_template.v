// SIO driver for the 23LC512: command nibbles and write data. GAL16V8,
// complex mode. Drives the SIO lines while K (the sequencer's nibble
// number) is 0-3. The address buffers drive them for K 8-11, and nobody
// does for the other K, where the RAM may drive them (read dummy cycles
// and data).
//
// While PEND is set (from power-up to the end of the first transfer) the
// RAM is still in SPI mode, where it only reads SI (SIO0) and HOLD (SIO3):
// the command nibbles are then 1110, so that the first transfer, a write of
// 0x88 to 0x9998, sends EQIO (0x38) on SIO0 with HOLD high.

module top (
    input K0,
    input K1,
    input K2,
    input K3,
    input PEND,
    input WR_n,
    input D0, input D1, input D2, input D3,
    input D4, input D5, input D6, input D7,

    output SIO0,
    output SIO1,
    output SIO2,
    output SIO3
);

wire [1:0] k = {K1, K0};
reg [3:0] sio;

always @(*) begin
    case (k)
        @dH@: sio = {D7, D6, D5, D4};
        @dL@: sio = {D3, D2, D1, D0};
        @c1@: sio = PEND ? 4'b1110 : {3'b001, WR_n};   // READ 0x03, WRITE 0x02
        default: sio = PEND ? 4'b1110 : 4'b0000;     // command, high nibble
    endcase
end

assign SIO0 = K3 | K2 ? 1'bz : sio[0];
assign SIO1 = K3 | K2 ? 1'bz : sio[1];
assign SIO2 = K3 | K2 ? 1'bz : sio[2];
assign SIO3 = K3 | K2 ? 1'bz : sio[3];

endmodule
