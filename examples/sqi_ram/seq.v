// Sequencer for a 23LC512 SQI SRAM on the external data bus of an 8052.
// GAL16V8, registered mode, clocked by a 27.75 MHz master clock.
//
// State: t = {K3, K2, K1, K0, SCK}, CS_n and PEND. SCK is the low bit of t,
// and K is the nibble on the SIO lines, decoded by the SIO driver GAL and a
// 74AC138:
//
//   K 0-7    SIO driver GAL: command (K 0, then 3 for READ, 5 for
//            WRITE), write data D7-4 (2) and D3-0 (1), read dummy cycles
//            (also 2 and 1), and EQIO during initialization
//   K 8-11   74AC244s via the 74AC138: A15-12, A11-8, A7-4, A3-0 at
//            K 10, 11, 8, 9
//   K 12-15  nobody: read data from the RAM
//
// States (t) visited while CS_n is low:
//   read:  0, 1, 6, 7, 20, 21, 22, 23, 16, 17, 18, 19, 4, 5, 2, 3, 26, 24, 27, 28, 30, 29, 31
//   write: 0, 1, 10, 11, 20, 21, 22, 23, 16, 17, 18, 19, 4, 5, 2, 3, 25
//   init:  0, 1, 2, 3, 10, 11, 14, 15, 6, 7, 8, 9, 12, 13, 4, 5, 31
// then CS_n rises and t moves to 16 (read), 16 (write) or 0 (init)
// until /RD and /WR are both high again, and then to 0 (idle). These
// waiting states only clear bits, so that SCK cannot rise and the state
// cannot be corrupted while the asynchronous /RD and /WR are sampled. Only
// CS_n depends on /RD, /WR and RST when a transaction starts.
//
// Read data is launched by the RAM on falling SCK and captured by a 74AC574
// on rising SCK, after two low states. CS stays low for two states after
// the last rising SCK (tCSH).
//
// CPUCLK clocks the 8052: it toggles on every master clock (13.875 MHz)
// except during transactions, where it follows the state with phases of 2
// to 4 master clocks and periods of at most 7 (252 ns, 3.96 MHz), which
// stretches /RD and /WR without going below the 8052's 3.5 MHz minimum.
//
// At power-up every GAL register reads 1: PEND is set and t is cleared.
// When the 8052 leaves reset, EQIO (0x38) is sent in SPI mode to switch the
// RAM to SQI mode, and PEND is cleared.
//
// The next-state equations are minimized with unreachable states as don't
// cares (see README.md); they are written out because Yosys cannot use
// don't cares.

module top (
    input MCLK,
    input RD_n,
    input WR_n,
    input RST,

    output reg SCK,
    output reg K0,
    output reg K1,
    output reg K2,
    output reg K3,
    output reg CS_n,
    output reg CPUCLK,
    output reg PEND
);

// 7 product terms
wire SCK_next = ((!SCK & !CS_n & RD_n)
    | (!SCK & !K2 & !CS_n)
    | (!SCK & K0 & K1)
    | (K0 & !K2 & !K3 & !WR_n)
    | (SCK & !K0 & K2 & !RD_n)
    | (!SCK & !K0 & !K1 & !CS_n)
    | (!K0 & K1 & !K2 & RD_n & WR_n));

// 6 product terms
wire K0_next = ((!K0 & K2 & !RD_n)
    | (!SCK & K0 & RD_n)
    | (SCK & !K0 & !K2)
    | (!SCK & K0 & !K2)
    | (K0 & K2 & !K3 & WR_n)
    | (K0 & !K1 & !K3 & WR_n));

// 7 product terms
wire K1_next = ((!SCK & K1)
    | (SCK & K2 & !K3)
    | (!K0 & K1 & K3)
    | (!K0 & K1 & RD_n & WR_n)
    | (K0 & K1 & !K3 & !RD_n)
    | (SCK & K0 & !K1 & K3)
    | (SCK & !K0 & !K1 & !K3 & !RD_n));

// 6 product terms
wire K2_next = ((!SCK & K2)
    | (!K1 & K2 & WR_n)
    | (!K0 & K2 & !RD_n)
    | (SCK & !K1 & !K2 & !K3 & !WR_n)
    | (SCK & K1 & !K2 & RD_n & WR_n)
    | (SCK & K0 & !K1 & !K3 & WR_n));

// 6 product terms
wire K3_next = !((!SCK & !K3)
    | (K2 & RD_n & WR_n)
    | (!K1 & RD_n & WR_n)
    | (K0 & RD_n & WR_n)
    | (!K0 & !K3 & !PEND)
    | (SCK & K0 & !K1 & !K2 & K3));

// 5 product terms
wire CS_n_next = ((K3 & CS_n)
    | (!PEND & RD_n & WR_n)
    | (K2 & K3 & RD_n)
    | (CS_n & RD_n & WR_n & RST)
    | (SCK & K0 & K1 & K2 & !RD_n));

// 2 product terms
wire PEND_next = ((CS_n & PEND)
    | (!K3 & PEND));

// 8 product terms
wire CPUCLK_next = ((CS_n & !CPUCLK)
    | (K2 & !WR_n)
    | (RD_n & WR_n & !CPUCLK)
    | (!K1 & K2 & !RD_n)
    | (K0 & !K1 & K3)
    | (SCK & !K1 & K3)
    | (K0 & K1 & !K3 & !RD_n)
    | (!SCK & !K0 & K1 & !K2 & K3));

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
