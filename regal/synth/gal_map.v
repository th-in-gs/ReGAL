module \$_NOT_ (A, Y);

parameter TABLE = 0;
parameter DEPTH = 0;

input A;
output Y;


generate
    GAL_XOR _TECHMAP_REPLACE_ (
        .A (A),
        .Y (Y)
    );
endgenerate

endmodule


module \$_AND_ (A, B, Y);

input A;
input B;
output Y;


generate
    GAL_SOP #(.TABLE(4'b1010), .WIDTH(2), .DEPTH(1))
    _TECHMAP_REPLACE_ (
        .I0 (A),
        .I1 (B),
        .O (Y)
    );
endgenerate

endmodule


module \$_DFF_P_ (C, D, Q);

input C;
input D;
output Q;


generate
    GAL_DFF _TECHMAP_REPLACE_ (
        .C (C),
        .D (D),
        .Q (Q)
    );
endgenerate

endmodule


module \$_TBUF_ (A, E, Y);

input A;
input E;
output Y;


generate
    GAL_TRI _TECHMAP_REPLACE_ (
        .A (A),
        .OE (E),
        .Y (Y)
    );
endgenerate

endmodule
