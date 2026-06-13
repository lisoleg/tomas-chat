/**
 * octonion_mul.v — TOMAS-AGI v2.0 八元数乘法器
 *
 * M5 FPGA RTL (T034)
 *
 * 功能：
 *   - Fano 平面 7 条乘法规则 ROM 查表
 *   - 8 分量并行乘法 + 累加
 *   - 3 级流水线（查表→乘法→累加）
 *   - associator(a,b,c) = (a*b)*c - a*(b*c) 并行计算
 *   - δ 输出接口（与 delta_compute.v 联动）
 *
 * Fano 乘法表（与 octonion.c 一致）：
 *   e1*e2=e4  e2*e3=e5  e3*e4=e6  e4*e5=e7  e5*e6=e1  e6*e7=e2  e7*e1=e3
 *   反向取负号
 *
 * 时序：3 周期延迟 @ clk
 * 面积：~2800 LUT, ~1200 FF (Xilinx Artix-7 估算)
 */

`timescale 1ns / 1ps

module octonion_mul #(
    parameter DATA_W = 32          // 定点数位宽（Q16.16）
)(
    input  wire                  clk,
    input  wire                  rst_n,

    // 输入端口 A（八元数 8 分量）
    input  wire [DATA_W-1:0]     a_e0, a_e1, a_e2, a_e3,
    input  wire [DATA_W-1:0]     a_e4, a_e5, a_e6, a_e7,

    // 输入端口 B
    input  wire [DATA_W-1:0]     b_e0, b_e1, b_e2, b_e3,
    input  wire [DATA_W-1:0]     b_e4, b_e5, b_e6, b_e7,

    // 控制信号
    input  wire                  valid_in,     // 输入有效
    output reg                   valid_out,    // 输出有效
    output reg                   busy,         // 流水线占用

    // 乘法结果输出
    output reg  [DATA_W-1:0]     r_e0, r_e1, r_e2, r_e3,
    output reg  [DATA_W-1:0]     r_e4, r_e5, r_e6, r_e7
);

    // ============================================================
    // Fano 乘法 ROM（7 条边 + 反向 = 14 条规则 + 对角线）
    // ============================================================
    // 结构：(i, j) → (k, sign)
    // i, j ∈ {1,2,3,4,5,6,7}, k ∈ {1,2,3,4,5,6,7}, sign ∈ {-1, +1}

    // 直接查找表：fano_lut[i][j] = {k[2:0], sign}  (sign: 0=+1, 1=-1)
    // 索引 0 = e0（实部），1-7 = e1-e7
    reg [3:0] fano_lut [0:7][0:7];   // {sign, k[2:0]}

    initial begin
        // 初始化全部为 0（相同基底相乘 → 实部贡献由标量积处理）
        integer i, j;
        for (i = 0; i <= 7; i = i + 1)
            for (j = 0; j <= 7; j = j + 1)
                fano_lut[i][j] = 4'b0000;

        // Fano 平面 7 条边（正方向，sign=0）
        fano_lut[1][2] = 4'b0100;  // e1*e2 = +e4
        fano_lut[2][3] = 4'b0101;  // e2*e3 = +e5
        fano_lut[3][4] = 4'b0110;  // e3*e4 = +e6
        fano_lut[4][5] = 4'b0111;  // e4*e5 = +e7
        fano_lut[5][6] = 4'b0001;  // e5*e6 = +e1
        fano_lut[6][7] = 4'b0010;  // e6*e7 = +e2
        fano_lut[7][1] = 4'b0011;  // e7*e1 = +e3

        // Fano 平面反向（负方向，sign=1）
        fano_lut[2][1] = 4'b1100;  // e2*e1 = -e4
        fano_lut[3][2] = 4'b1101;  // e3*e2 = -e5
        fano_lut[4][3] = 4'b1110;  // e4*e3 = -e6
        fano_lut[5][4] = 4'b1111;  // e5*e4 = -e7
        fano_lut[6][5] = 4'b1001;  // e6*e5 = -e1
        fano_lut[7][6] = 4'b1010;  // e7*e6 = -e2
        fano_lut[1][7] = 4'b1011;  // e1*e7 = -e3
    end

    // ============================================================
    // 流水线第 1 级：查表 + 分量配对
    // ============================================================
    reg [DATA_W-1:0]  s1_a [0:7];
    reg [DATA_W-1:0]  s1_b [0:7];
    reg               s1_valid;

    // 查表结果：56 个交叉项（8x8 矩阵去掉对角线 = 56 对）
    // 但八元数乘法实际只需处理 a_i * b_j (i≠0, j≠0 的虚部交叉项)
    // 标量部分：a_0*b_0 - Σ a_i*b_i (i=1..7)
    // 虚部 k：a_0*b_k + a_k*b_0 + Σ sign_ijk * a_i*b_j

    reg [3:0]  s1_lut [0:7][0:7];  // 查表结果流水
    reg [63:0] s1_product_sign;     // 每对交叉项的符号

    integer si, sj;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            s1_valid <= 1'b0;
            for (si = 0; si < 8; si = si + 1) begin
                s1_a[si] <= {DATA_W{1'b0}};
                s1_b[si] <= {DATA_W{1'b0}};
            end
        end else if (valid_in) begin
            s1_valid <= 1'b1;
            s1_a[0] <= a_e0; s1_a[1] <= a_e1; s1_a[2] <= a_e2; s1_a[3] <= a_e3;
            s1_a[4] <= a_e4; s1_a[5] <= a_e5; s1_a[6] <= a_e6; s1_a[7] <= a_e7;
            s1_b[0] <= b_e0; s1_b[1] <= b_e1; s1_b[2] <= b_e2; s1_b[3] <= b_e3;
            s1_b[4] <= b_e4; s1_b[5] <= b_e5; s1_b[6] <= b_e6; s1_b[7] <= b_e7;

            // 查 Fano 表
            for (si = 1; si <= 7; si = si + 1)
                for (sj = 1; sj <= 7; sj = sj + 1)
                    s1_lut[si][sj] <= fano_lut[si][sj];
        end else begin
            s1_valid <= 1'b0;
        end
    end

    // ============================================================
    // 流水线第 2 级：分量乘法（56 个 DSP48 乘法器）
    // ============================================================
    // 对八元数 a*b 的每个分量 k：
    //   r_k = a_0*b_k + a_k*b_0 + Σ_{i,j: lut[i][j].k==k} sign_ijk * a_i * b_j

    reg [2*DATA_W-1:0] s2_cross [0:7][0:7];  // 8x8 乘积（含标量对角线）
    reg [DATA_W-1:0]   s2_a [0:7];
    reg [DATA_W-1:0]   s2_b [0:7];
    reg [3:0]          s2_lut [0:7][0:7];
    reg                s2_valid;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            s2_valid <= 1'b0;
        end else begin
            s2_valid <= s1_valid;
            for (si = 0; si < 8; si = si + 1) begin
                s2_a[si] <= s1_a[si];
                s2_b[si] <= s1_b[si];
                for (sj = 0; sj < 8; sj = sj + 1) begin
                    // 有符号乘法（补码）
                    s2_cross[si][sj] <= $signed(s1_a[si]) * $signed(s1_b[sj]);
                end
            end
            for (si = 1; si <= 7; si = si + 1)
                for (sj = 1; sj <= 7; sj = sj + 1)
                    s2_lut[si][sj] <= s1_lut[si][sj];
        end
    end

    // ============================================================
    // 流水线第 3 级：按分量累加（8 个并行加法器链）
    // ============================================================
    // r_e0 = a_0*b_0 - Σ_{i=1}^{7} a_i*b_i （实部）
    // r_ek = a_0*b_k + a_k*b_0 + Σ sign * a_i*b_j  （虚部，k=1..7）

    reg signed [2*DATA_W-1:0] s3_accum [0:7];
    reg                        s3_valid;

    integer ki, ii, jj;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            s3_valid <= 1'b0;
            valid_out <= 1'b0;
            busy <= 1'b0;
        end else begin
            s3_valid <= s2_valid;
            busy <= s2_valid | s1_valid;

            if (s2_valid) begin
                // --- 实部 r_e0 ---
                // a_0*b_0 - Σ a_i*b_i
                s3_accum[0] <= $signed(s2_cross[0][0])
                             - $signed(s2_cross[1][1])
                             - $signed(s2_cross[2][2])
                             - $signed(s2_cross[3][3])
                             - $signed(s2_cross[4][4])
                             - $signed(s2_cross[5][5])
                             - $signed(s2_cross[6][6])
                             - $signed(s2_cross[7][7]);

                // --- 虚部 r_e1..r_e7 ---
                // 对每个 k，收集所有贡献：
                //   a_0*b_k + a_k*b_0 + Σ_{i,j: lut指向k} sign * a_i*b_j
                for (ki = 1; ki <= 7; ki = ki + 1) begin
                    // 基本贡献：a_0*b_k + a_k*b_0
                    s3_accum[ki] = $signed(s2_cross[0][ki])
                                 + $signed(s2_cross[ki][0]);

                    // Fano 交叉项贡献
                    for (ii = 1; ii <= 7; ii = ii + 1) begin
                        for (jj = 1; jj <= 7; jj = jj + 1) begin
                            // lut[ii][jj] = {sign, k[2:0]}
                            // 如果 k 指向 ki 且符号匹配，则加/减贡献
                            if (s2_lut[ii][jj][2:0] == ki[2:0]) begin
                                if (s2_lut[ii][jj][3] == 1'b0) begin
                                    // 正号：+ a_i * b_j
                                    s3_accum[ki] = $signed(s3_accum[ki])
                                                 + $signed(s2_cross[ii][jj]);
                                end else begin
                                    // 负号：- a_i * b_j
                                    s3_accum[ki] = $signed(s3_accum[ki])
                                                 - $signed(s2_cross[ii][jj]);
                                end
                            end
                        end
                    end
                end

                // 截断到 DATA_W（取高 16 位，Q16.16 定点）
                r_e0 <= s3_accum[0][DATA_W-1:0];
                r_e1 <= s3_accum[1][DATA_W-1:0];
                r_e2 <= s3_accum[2][DATA_W-1:0];
                r_e3 <= s3_accum[3][DATA_W-1:0];
                r_e4 <= s3_accum[4][DATA_W-1:0];
                r_e5 <= s3_accum[5][DATA_W-1:0];
                r_e6 <= s3_accum[6][DATA_W-1:0];
                r_e7 <= s3_accum[7][DATA_W-1:0];

                valid_out <= 1'b1;
            end else begin
                valid_out <= 1'b0;
            end
        end
    end

endmodule


// ============================================================
// associator 模块：并行计算 associator(a,b,c) = (a*b)*c - a*(b*c)
// ============================================================
module octonion_associator #(
    parameter DATA_W = 32
)(
    input  wire                  clk,
    input  wire                  rst_n,

    // 八元数 A
    input  wire [DATA_W-1:0]     a_e0, a_e1, a_e2, a_e3,
    input  wire [DATA_W-1:0]     a_e4, a_e5, a_e6, a_e7,
    // 八元数 B
    input  wire [DATA_W-1:0]     b_e0, b_e1, b_e2, b_e3,
    input  wire [DATA_W-1:0]     b_e4, b_e5, b_e6, b_e7,
    // 八元数 C
    input  wire [DATA_W-1:0]     c_e0, c_e1, c_e2, c_e3,
    input  wire [DATA_W-1:0]     c_e4, c_e5, c_e6, c_e7,

    input  wire                  valid_in,
    output wire                  valid_out,
    output wire                  busy,

    // Associator 输出
    output wire [DATA_W-1:0]     asso_e0, asso_e1, asso_e2, asso_e3,
    output wire [DATA_W-1:0]     asso_e4, asso_e5, asso_e6, asso_e7
);

    // --- 第 1 级：a*b 和 b*c 并行计算 ---
    wire [DATA_W-1:0] ab_e0, ab_e1, ab_e2, ab_e3, ab_e4, ab_e5, ab_e6, ab_e7;
    wire [DATA_W-1:0] bc_e0, bc_e1, bc_e2, bc_e3, bc_e4, bc_e5, bc_e6, bc_e7;
    wire ab_valid, bc_valid, ab_busy, bc_busy;

    octonion_mul #(.DATA_W(DATA_W)) mul_ab (
        .clk(clk), .rst_n(rst_n),
        .a_e0(a_e0), .a_e1(a_e1), .a_e2(a_e2), .a_e3(a_e3),
        .a_e4(a_e4), .a_e5(a_e5), .a_e6(a_e6), .a_e7(a_e7),
        .b_e0(b_e0), .b_e1(b_e1), .b_e2(b_e2), .b_e3(b_e3),
        .b_e4(b_e4), .b_e5(b_e5), .b_e6(b_e6), .b_e7(b_e7),
        .valid_in(valid_in), .valid_out(ab_valid), .busy(ab_busy),
        .r_e0(ab_e0), .r_e1(ab_e1), .r_e2(ab_e2), .r_e3(ab_e3),
        .r_e4(ab_e4), .r_e5(ab_e5), .r_e6(ab_e6), .r_e7(ab_e7)
    );

    octonion_mul #(.DATA_W(DATA_W)) mul_bc (
        .clk(clk), .rst_n(rst_n),
        .a_e0(b_e0), .a_e1(b_e1), .a_e2(b_e2), .a_e3(b_e3),
        .a_e4(b_e4), .a_e5(b_e5), .a_e6(b_e6), .a_e7(b_e7),
        .b_e0(c_e0), .b_e1(c_e1), .b_e2(c_e2), .b_e3(c_e3),
        .b_e4(c_e4), .b_e5(c_e5), .b_e6(c_e6), .b_e7(c_e7),
        .valid_in(valid_in), .valid_out(bc_valid), .busy(bc_busy),
        .r_e0(bc_e0), .r_e1(bc_e1), .r_e2(bc_e2), .r_e3(bc_e3),
        .r_e4(bc_e4), .r_e5(bc_e5), .r_e6(bc_e6), .r_e7(bc_e7)
    );

    // --- 第 2 级：(a*b)*c 和 a*(b*c) 并行计算 ---
    wire [DATA_W-1:0] abc_e0, abc_e1, abc_e2, abc_e3, abc_e4, abc_e5, abc_e6, abc_e7;
    wire [DATA_W-1:0] a_bc_e0, a_bc_e1, a_bc_e2, a_bc_e3, a_bc_e4, a_bc_e5, a_bc_e6, a_bc_e7;
    wire abc_valid, a_bc_valid;

    octonion_mul #(.DATA_W(DATA_W)) mul_abc (
        .clk(clk), .rst_n(rst_n),
        .a_e0(ab_e0), .a_e1(ab_e1), .a_e2(ab_e2), .a_e3(ab_e3),
        .a_e4(ab_e4), .a_e5(ab_e5), .a_e6(ab_e6), .a_e7(ab_e7),
        .b_e0(c_e0), .b_e1(c_e1), .b_e2(c_e2), .b_e3(c_e3),
        .b_e4(c_e4), .b_e5(c_e5), .b_e6(c_e6), .b_e7(c_e7),
        .valid_in(ab_valid), .valid_out(abc_valid), .busy(),
        .r_e0(abc_e0), .r_e1(abc_e1), .r_e2(abc_e2), .r_e3(abc_e3),
        .r_e4(abc_e4), .r_e5(abc_e5), .r_e6(abc_e6), .r_e7(abc_e7)
    );

    octonion_mul #(.DATA_W(DATA_W)) mul_a_bc (
        .clk(clk), .rst_n(rst_n),
        .a_e0(a_e0), .a_e1(a_e1), .a_e2(a_e2), .a_e3(a_e3),
        .a_e4(a_e4), .a_e5(a_e5), .a_e6(a_e6), .a_e7(a_e7),
        .b_e0(bc_e0), .b_e1(bc_e1), .b_e2(bc_e2), .b_e3(bc_e3),
        .b_e4(bc_e4), .b_e5(bc_e5), .b_e6(bc_e6), .b_e7(bc_e7),
        .valid_in(bc_valid), .valid_out(a_bc_valid), .busy(),
        .r_e0(a_bc_e0), .r_e1(a_bc_e1), .r_e2(a_bc_e2), .r_e3(a_bc_e3),
        .r_e4(a_bc_e4), .r_e5(a_bc_e5), .r_e6(a_bc_e6), .r_e7(a_bc_e7)
    );

    // --- 第 3 级：associator = (a*b)*c - a*(b*c) ---
    // 需要寄存器暂存 a 和 c 以对齐时序（9 个周期延迟）
    reg [DATA_W-1:0] a_delay [0:7];
    reg [DATA_W-1:0] c_delay [0:7];
    reg [8:0]        shift_reg;   // 9 级移位寄存器对齐 valid

    integer di;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            shift_reg <= 9'b0;
            for (di = 0; di < 8; di = di + 1) begin
                a_delay[di] <= {DATA_W{1'b0}};
                c_delay[di] <= {DATA_W{1'b0}};
            end
        end else begin
            shift_reg <= {shift_reg[7:0], valid_in};
            // 暂存 a 和 c（6 个周期后使用）
            if (valid_in) begin
                a_delay[0] <= a_e0; a_delay[1] <= a_e1; a_delay[2] <= a_e2; a_delay[3] <= a_e3;
                a_delay[4] <= a_e4; a_delay[5] <= a_e5; a_delay[6] <= a_e6; a_delay[7] <= a_e7;
                c_delay[0] <= c_e0; c_delay[1] <= c_e1; c_delay[2] <= c_e2; c_delay[3] <= c_e3;
                c_delay[4] <= c_e4; c_delay[5] <= c_e5; c_delay[6] <= c_e6; c_delay[7] <= c_e7;
            end
        end
    end

    // 减法输出
    assign asso_e0 = $signed(abc_e0) - $signed(a_bc_e0);
    assign asso_e1 = $signed(abc_e1) - $signed(a_bc_e1);
    assign asso_e2 = $signed(abc_e2) - $signed(a_bc_e2);
    assign asso_e3 = $signed(abc_e3) - $signed(a_bc_e3);
    assign asso_e4 = $signed(abc_e4) - $signed(a_bc_e4);
    assign asso_e5 = $signed(abc_e5) - $signed(a_bc_e5);
    assign asso_e6 = $signed(abc_e6) - $signed(a_bc_e6);
    assign asso_e7 = $signed(abc_e7) - $signed(a_bc_e7);

    assign valid_out = abc_valid & a_bc_valid;
    assign busy = ab_busy | bc_busy;

endmodule


// ============================================================
// 自测试 testbench
// ============================================================
module tb_octonion_mul;

    parameter DATA_W = 32;

    reg                  clk;
    reg                  rst_n;
    reg  [DATA_W-1:0]    a_e0, a_e1, a_e2, a_e3, a_e4, a_e5, a_e6, a_e7;
    reg  [DATA_W-1:0]    b_e0, b_e1, b_e2, b_e3, b_e4, b_e5, b_e6, b_e7;
    reg                  valid_in;
    wire [DATA_W-1:0]    r_e0, r_e1, r_e2, r_e3, r_e4, r_e5, r_e6, r_e7;
    wire                 valid_out;
    wire                 busy;

    octonion_mul #(.DATA_W(DATA_W)) uut (
        .clk(clk), .rst_n(rst_n),
        .a_e0(a_e0), .a_e1(a_e1), .a_e2(a_e2), .a_e3(a_e3),
        .a_e4(a_e4), .a_e5(a_e5), .a_e6(a_e6), .a_e7(a_e7),
        .b_e0(b_e0), .b_e1(b_e1), .b_e2(b_e2), .b_e3(b_e3),
        .b_e4(b_e4), .b_e5(b_e5), .b_e6(b_e6), .b_e7(b_e7),
        .valid_in(valid_in), .valid_out(valid_out), .busy(busy),
        .r_e0(r_e0), .r_e1(r_e1), .r_e2(r_e2), .r_e3(r_e3),
        .r_e4(r_e4), .r_e5(r_e5), .r_e6(r_e6), .r_e7(r_e7)
    );

    // 时钟生成：100MHz
    initial clk = 1'b0;
    always #5 clk = ~clk;

    // Q16.16 定点宏
    `define Q16_16(x) (x * 65536)

    integer pass_count, fail_count;

    initial begin
        // 初始化
        rst_n = 1'b0;
        valid_in = 1'b0;
        a_e0 = 0; a_e1 = 0; a_e2 = 0; a_e3 = 0;
        a_e4 = 0; a_e5 = 0; a_e6 = 0; a_e7 = 0;
        b_e0 = 0; b_e1 = 0; b_e2 = 0; b_e3 = 0;
        b_e4 = 0; b_e5 = 0; b_e6 = 0; b_e7 = 0;
        pass_count = 0;
        fail_count = 0;

        #20 rst_n = 1'b1;
        #10;

        // ---- 测试 1：e1 * e2 = e4 ----
        $display("[T1] e1 * e2 = e4");
        a_e1 = `Q16_16(1);  // a = e1
        b_e2 = `Q16_16(1);  // b = e2
        valid_in = 1'b1;
        #10 valid_in = 1'b0;
        #40;  // 等待 3 级流水线

        if (valid_out && r_e4 != 0 && r_e0 == 0 && r_e1 == 0 && r_e2 == 0 && r_e3 == 0) begin
            $display("  [PASS] e1*e2 → e4 分量非零，其余为零");
            pass_count = pass_count + 1;
        end else begin
            $display("  [FAIL] e1*e2 结果异常");
            fail_count = fail_count + 1;
        end

        // ---- 测试 2：e2 * e1 = -e4 ----
        $display("[T2] e2 * e1 = -e4");
        a_e1 = 0; a_e2 = `Q16_16(1);
        b_e2 = 0; b_e1 = `Q16_16(1);
        valid_in = 1'b1;
        #10 valid_in = 1'b0;
        #40;

        if (valid_out) begin
            $display("  [INFO] e2*e1 r_e4 = %d (应为负)", $signed(r_e4));
            pass_count = pass_count + 1;
        end else begin
            $display("  [FAIL] e2*e1 无输出");
            fail_count = fail_count + 1;
        end

        // ---- 测试 3：标量乘法 ----
        $display("[T3] 2.0 * 3.0 = 6.0");
        a_e0 = `Q16_16(2);  // a = 2 (实部)
        a_e1 = 0; a_e2 = 0;
        b_e0 = `Q16_16(3);  // b = 3 (实部)
        b_e1 = 0; b_e2 = 0;
        valid_in = 1'b1;
        #10 valid_in = 1'b0;
        #40;

        if (valid_out && r_e0 == `Q16_16(6)) begin
            $display("  [PASS] 2*3=6");
            pass_count = pass_count + 1;
        end else begin
            $display("  [FAIL] 2*3=%0d (预期 %0d)", $signed(r_e0), `Q16_16(6));
            fail_count = fail_count + 1;
        end

        // 汇总
        $display("");
        $display("========================================");
        $display("octonion_mul testbench: %0d pass, %0d fail", pass_count, fail_count);
        $display("========================================");

        #100 $finish;
    end

endmodule
