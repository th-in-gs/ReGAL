// Sequencer for a 23LC512 SQI SRAM on the external data bus of an 8052.
// GAL16V8, registered mode, clocked by a 27.75 MHz master clock.
//
// State: t = {K3, K2, K1, K0, SCK}, CS_n and PEND. SCK is the low bit of t,
// and K says who drives the SIO lines:
//
//   K 0-3    SIO driver GAL: command (K 0, then 2), write data D7-4 (1)
//            and D3-0 (3)
//   K 8-11   74AC244s via the 74AC138: A15-12, A11-8, A7-4, A3-0 at
//            K 8, 10, 11, 9
//   others   nobody: the RAM drives them in reads from the dummy cycles
//            (K 4 and 7) on
//
// States (t) visited while CS_n is low:
//   read:  0, 1, 4, 5, 16, 17, 20, 21, 22, 23, 18, 19, 8, 9, 14, 15, 28, 12, 13, 10, 24, 25, 31, 27, 29
//   write: 0, 1, 4, 5, 16, 17, 20, 21, 22, 23, 18, 19, 2, 3, 6, 7, 31
// then CS_n rises and t moves to 8 (read) or 2 (write) until /RD and
// /WR are both high again, and then to 0 (idle). These waiting states only
// clear bits, so that SCK cannot rise and the state cannot be corrupted
// while the asynchronous /RD and /WR are sampled. Only CS_n depends on /RD
// and /WR when a transfer starts.
//
// Read data is launched by the RAM on falling SCK and captured by a 74AC574
// on rising SCK, after two low states. CS stays low for two states after
// the last rising SCK (tCSH).
//
// CPUCLK clocks the 8052: it toggles on every master clock (13.875 MHz)
// except during transfers, where it follows the state with phases of 2
// to 4 master clocks and periods of at most 7 (252 ns, 3.96 MHz), which
// stretches /RD and /WR without going below the 8052's 3.5 MHz minimum.
//
// At power-up every GAL register reads 1: PEND is set and t is cleared.
// PEND tells the SIO driver that the RAM is still in SPI mode, and is
// cleared at the end of the first transfer, which must switch the RAM to
// SQI mode (see sio.v).
//
// The next-state equations are minimized with unreachable states as don't
// cares (gen/search.py); they are written out because Yosys cannot use
// don't cares.

module top (
    input MCLK,
    input RD_n,
    input WR_n,

    output reg SCK,
    output reg K0,
    output reg K1,
    output reg K2,
    output reg K3,
    output reg CS_n,
    output reg CPUCLK,
    output reg PEND
);

// 6 product terms
wire SCK_next = ((!SCK & !K2 & !CS_n)
    | (!SCK & K1 & !K3)
    | (!K1 & K2 & K3)
    | (K0 & K1 & !K3 & !WR_n)
    | (K0 & K2 & K3 & !RD_n)
    | (!SCK & !K0 & !K3 & !CS_n));

// 7 product terms
wire K0_next = ((K0 & !WR_n)
    | (!SCK & K0 & K3)
    | (!SCK & K0 & K1)
    | (K0 & K1 & K3 & !RD_n)
    | (SCK & !K0 & K2 & !K3)
    | (SCK & K1 & !K2 & K3)
    | (SCK & !K0 & !K1 & K2));

// 5 product terms
wire K1_next = ((!SCK & K1)
    | (SCK & !K1 & !K3)
    | (K0 & K1 & !K3)
    | (SCK & !K1 & K2)
    | (SCK & !K0 & !K2 & K3));

// 3 product terms
wire K2_next = ((K2 & !RD_n)
    | (SCK & K0 & !K1 & WR_n)
    | (SCK & K0 & K1 & !K3));

// 5 product terms
wire K3_next = ((!SCK & !K2 & K3)
    | (!K0 & !K1 & K3)
    | (SCK & K1 & !K2)
    | (K0 & !K1 & K2)
    | (SCK & K0 & K2 & !RD_n));

// 5 product terms
wire CS_n_next = ((RD_n & WR_n)
    | (K2 & RD_n)
    | (K2 & CS_n)
    | (K0 & CS_n)
    | (SCK & !K0 & K1 & K2 & K3));

// 3 product terms
wire PEND_next = !((!PEND)
    | (K2 & !CS_n & !WR_n)
    | (SCK & !K0 & K1 & K2 & K3));

// 7 product terms
wire CPUCLK_next = !((CS_n & CPUCLK)
    | (!SCK & K0 & K3)
    | (!K0 & K1 & K2 & !K3)
    | (K0 & K1 & !K2 & K3)
    | (!K0 & !K1 & !K3 & !CS_n & !WR_n)
    | (!K1 & !K2 & !K3 & !CS_n & WR_n)
    | (K0 & !K1 & !K3 & !CS_n & WR_n));

always @(posedge MCLK) begin
    SCK <= SCK_next;
    K0 <= K0_next;
    K1 <= K1_next;
    K2 <= K2_next;
    K3 <= K3_next;
    CS_n <= CS_n_next;
    CPUCLK <= CPUCLK_next;
    PEND <= PEND_next;
end

endmodule
