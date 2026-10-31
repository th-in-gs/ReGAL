// Sequencer for a 23LC512 SQI SRAM on the external data bus of an 8052.
// GAL16V8, registered mode, clocked by a 27.75 MHz master clock.
//
// State: t = {K3, K2, K1, K0, SCK}, CS_n and PEND. SCK is the low bit of t,
// and K says who drives the SIO lines:
//
//   K 0-3    SIO driver GAL: command (K 0, then @c1@), write data D7-4 (@dH@)
//            and D3-0 (@dL@)
//   K 8-11   74AC244s via the 74AC138: A15-12, A11-8, A7-4, A3-0 at
//            K @A@
//   others   nobody: the RAM drives them in reads from the dummy cycles
//            (K @DUMMY@) on
//
// States (t) visited while CS_n is low:
//   read:  @READ@
//   write: @WRITE@
// then CS_n rises and t moves to @FR@ (read) or @FW@ (write) until /RD and
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

@EQS@

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
