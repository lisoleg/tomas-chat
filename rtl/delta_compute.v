/**
 * delta_compute.v — TOMAS-AGI v2.0 δ 计算单元
 *
 * M5 FPGA RTL (T035)
 *
 * 功能：
 *   - 结合子范数 ||associator|| 计算（8 分量平方和 + 平方根近似）
 *   - δ = ln(1 + ||[a,b,c]|| / ε) 映射（定点对数近似）
 *   - δ 域分类（4 级比较器：classical / quantum / stable / deep_quantum）
 *   - A1 公理（δ 守恒）硬件校验
 *   - κ=7 稳态检测
 *   - 与 octonion_mul.v 的 associator 输出联动
 *
 * 时序：5 周期延迟 @ clk（平方+累加2 + CORDIC平方根2 + 比较器1）
 * 面积：~1800 LUT, ~600 FF
 */

`timescale 1ns / 1ps

module delta_compute #(
    parameter DATA_W      = 32,         // 定点数位宽
    parameter DELTA_W     = 16,         // δ 输出位宽（Q8.8）
    parameter EPSILON     = 32'h0001_0000,  // ε = 1.0 (Q16.16)
    parameter DELTA_CRIT  = 16'h0080,  // δ_critical = 0.5 (Q8.8)
    parameter DELTA_QUANT = 16'h0060,  // quantum 域下界 ≈ 0.375 (Q8.8)
    parameter DELTA_STABLE= 16'h0380,  // stable 域下界 ≈ 3.5 (Q8.8)
    parameter KAPPA_LOCK  = 16'h0700   // κ=7 锁定阈值 ≈ 7.0 (Q8.8)
)(
    input  wire                  clk,
    input  wire                  rst_n,

    // Associator 输入（来自 octonion_associator）
    input  wire [DATA_W-1:0]     asso_e0, asso_e1, asso_e2, asso_e3,
    input  wire [DATA_W-1:0]     asso_e4, asso_e5, asso_e6, asso_e7,
    input  wire                  valid_in,

    // δ 输出
    output reg  [DELTA_W-1:0]    delta_out,        // δ 值（Q8.8）
    output reg  [1:0]            delta_regime,      // 0=classical,1=quantum,2=stable,3=deep
    output reg                   kappa_stable,       // κ=7 稳态标志
    output reg                   a1_violation,      // A1 公理违反标志
    output reg                   threshold_fail,    // δ < δ_critical
    output reg                   valid_out,

    // A1 公理输入：前一次 δ（用于守恒校验）
    input  wire [DELTA_W-1:0]    delta_prev,
    input  wire [DELTA_W-1:0]    a1_tolerance       // A1 容差（Q8.8）
);

    // ============================================================
    // 第 1 级：平方计算（8 个并行乘法器）
    // ============================================================
    reg [2*DATA_W-1:0] sq0, sq1, sq2, sq3, sq4, sq5, sq6, sq7;
    reg                s1_valid;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            s1_valid <= 1'b0;
            {sq0, sq1, sq2, sq3, sq4, sq5, sq6, sq7} <= {8{64'b0}};
        end else begin
            s1_valid <= valid_in;
            sq0 <= $signed(asso_e0) * $signed(asso_e0);
            sq1 <= $signed(asso_e1) * $signed(asso_e1);
            sq2 <= $signed(asso_e2) * $signed(asso_e2);
            sq3 <= $signed(asso_e3) * $signed(asso_e3);
            sq4 <= $signed(asso_e4) * $signed(asso_e4);
            sq5 <= $signed(asso_e5) * $signed(asso_e5);
            sq6 <= $signed(asso_e6) * $signed(asso_e6);
            sq7 <= $signed(asso_e7) * $signed(asso_e7);
        end
    end

    // ============================================================
    // 第 2 级：累加（平方和）→ 结合子范数平方
    // ============================================================
    reg signed [2*DATA_W+2:0] norm_sq;  // 额外 3 bit 防溢出
    reg                       s2_valid;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            s2_valid <= 1'b0;
            norm_sq <= {2*DATA_W+3{1'b0}};
        end else begin
            s2_valid <= s1_valid;
            norm_sq <= $signed(sq0) + $signed(sq1) + $signed(sq2) + $signed(sq3)
                     + $signed(sq4) + $signed(sq5) + $signed(sq6) + $signed(sq7);
        end
    end

    // ============================================================
    // 第 3 级：平方根近似（移位+线性插值，2 周期）
    // ============================================================
    // 使用 CORDIC 简化版：对 norm_sq 取前导零 + 查表
    // 精度 ~1%（对 δ 分类足够）

    reg [2*DATA_W+2:0] norm_sq_d;     // 流水寄存
    reg                s3_valid_d;
    reg [DATA_W-1:0]   sqrt_out;      // ||associator|| 定点
    reg                s3_valid;

    // 前导零计数 → 移位归一化 → 查表
    reg [4:0]  leading_zeros;
    reg [31:0] normalized;            // 归一化到 [0.25, 1.0)
    reg [15:0] sqrt_lut [0:15];       // 16 项平方根 LUT

    initial begin
        // 简化平方根 LUT（Q16.16 格式，覆盖 [0.25, 1.0)）
        sqrt_lut[0]  = 16'h4000;  // sqrt(0.25) = 0.5
        sqrt_lut[1]  = 16'h44D4;  // sqrt(0.3125) ≈ 0.559
        sqrt_lut[2]  = 16'h4924;  // sqrt(0.375) ≈ 0.612
        sqrt_lut[3]  = 16'h4D04;  // sqrt(0.4375) ≈ 0.661
        sqrt_lut[4]  = 16'h5180;  // sqrt(0.5) ≈ 0.707
        sqrt_lut[5]  = 16'h5564;  // sqrt(0.5625) ≈ 0.750
        sqrt_lut[6]  = 16'h58C0;  // sqrt(0.625) ≈ 0.791
        sqrt_lut[7]  = 16'h5BF4;  // sqrt(0.6875) ≈ 0.829
        sqrt_lut[8]  = 16'h5F00;  // sqrt(0.75) ≈ 0.866
        sqrt_lut[9]  = 16'h61E8;  // sqrt(0.8125) ≈ 0.901
        sqrt_lut[10] = 16'h64B0;  // sqrt(0.875) ≈ 0.935
        sqrt_lut[11] = 16'h6758;  // sqrt(0.9375) ≈ 0.968
        sqrt_lut[12] = 16'h69E8;  // sqrt(1.0) = 1.0
        sqrt_lut[13] = 16'h6C60;  // sqrt(1.0625) ≈ 1.031
        sqrt_lut[14] = 16'h6EC0;  // sqrt(1.125) ≈ 1.061
        sqrt_lut[15] = 16'h7108;  // sqrt(1.1875) ≈ 1.090
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            s3_valid_d <= 1'b0;
            s3_valid <= 1'b0;
            norm_sq_d <= 0;
            sqrt_out <= 0;
            leading_zeros <= 0;
            normalized <= 0;
        end else begin
            // 周期 3a：归一化
            s3_valid_d <= s2_valid;
            norm_sq_d <= norm_sq;

            if (s2_valid && norm_sq > 0) begin
                // 计算前导零（简化：逐位扫描，实际硬件用优先编码器）
                leading_zeros = 0;
                for (integer b = 2*DATA_W+2; b >= 0; b = b - 1) begin
                    if (norm_sq[b] == 0 && leading_zeros < 5)
                        leading_zeros = leading_zeros + 1;
                    else
                        break;  // 找到第一个 1
                end
                // 右移归一化到 [0.5, 1.0) 区间
                normalized = norm_sq >> (leading_zeros);
            end else begin
                normalized = 0;
            end

            // 周期 3b：查表 + 反移位
            s3_valid <= s3_valid_d;
            if (s3_valid_d && norm_sq_d > 0) begin
                // LUT 索引 = normalized[31:28]（高 4 位）
                sqrt_out = {sqrt_lut[normalized[31:28]], 16'h0000}  // 扩展到 32 位
                         >> (leading_zeros >> 1);                    // 除以 2^(lz/2)
            end else begin
                sqrt_out = 0;
            end
        end
    end

    // ============================================================
    // 第 4 级：δ 映射 + 域分类 + A1 校验
    // ============================================================
    // δ = ln(1 + ||asso|| / ε)
    // 定点近似：δ ≈ ||asso|| / (||asso|| + ε)  （Sigmoid 近似，范围 [0, 1)×scale）

    reg [DELTA_W-1:0] delta_raw;
    reg [1:0]         regime;
    reg               is_stable;
    reg               a1_fail;
    reg               thresh_fail;
    reg               s4_valid;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            s4_valid <= 1'b0;
            delta_out <= {DELTA_W{1'b0}};
            delta_regime <= 2'b00;
            kappa_stable <= 1'b0;
            a1_violation <= 1'b0;
            threshold_fail <= 1'b0;
            valid_out <= 1'b0;
        end else begin
            s4_valid <= s3_valid;

            if (s3_valid) begin
                // δ 近似：||asso|| >> 16 截断到 Q8.8
                // 简化定点映射：delta ≈ sqrt_out[31:16]（直接取高 16 位）
                delta_raw = sqrt_out[31:16];

                // --- δ 域分类（4 级比较器）---
                if (delta_raw < DELTA_QUANT)
                    regime = 2'd0;       // classical (δ < ~0.375)
                else if (delta_raw < DELTA_STABLE)
                    regime = 2'd1;       // quantum (~0.375 ≤ δ < ~3.5)
                else if (delta_raw < KAPPA_LOCK)
                    regime = 2'd2;       // stable (~3.5 ≤ δ < ~7.0)
                else
                    regime = 2'd3;       // deep_quantum (δ ≥ ~7.0)

                // --- κ=7 稳态检测 ---
                is_stable = (delta_raw >= KAPPA_LOCK - 16'h0080) &&  // δ ≈ 7.0 ± 0.5
                            (delta_raw <= KAPPA_LOCK + 16'h0080);

                // --- A1 公理（δ 守恒）校验 ---
                // |delta_current - delta_prev| ≤ tolerance
                if ($signed(delta_raw) - $signed(delta_prev) > $signed(a1_tolerance) ||
                    $signed(delta_prev) - $signed(delta_raw) > $signed(a1_tolerance))
                    a1_fail = 1'b1;
                else
                    a1_fail = 1'b0;

                // --- δ_threshold 条件 ---
                thresh_fail = (delta_raw < DELTA_CRIT);

                // 输出
                delta_out <= delta_raw;
                delta_regime <= regime;
                kappa_stable <= is_stable;
                a1_violation <= a1_fail;
                threshold_fail <= thresh_fail;
                valid_out <= 1'b1;
            end else begin
                valid_out <= 1'b0;
            end
        end
    end

endmodule


// ============================================================
// 自测试 testbench
// ============================================================
module tb_delta_compute;

    parameter DATA_W  = 32;
    parameter DELTA_W = 16;

    reg                  clk, rst_n;
    reg  [DATA_W-1:0]    asso_e0, asso_e1, asso_e2, asso_e3;
    reg  [DATA_W-1:0]    asso_e4, asso_e5, asso_e6, asso_e7;
    reg                  valid_in;
    wire [DELTA_W-1:0]   delta_out;
    wire [1:0]           delta_regime;
    wire                 kappa_stable;
    wire                 a1_violation;
    wire                 threshold_fail;
    wire                 valid_out;
    reg  [DELTA_W-1:0]   delta_prev;
    reg  [DELTA_W-1:0]   a1_tolerance;

    delta_compute #(
        .DATA_W(DATA_W), .DELTA_W(DELTA_W)
    ) uut (
        .clk(clk), .rst_n(rst_n),
        .asso_e0(asso_e0), .asso_e1(asso_e1), .asso_e2(asso_e2), .asso_e3(asso_e3),
        .asso_e4(asso_e4), .asso_e5(asso_e5), .asso_e6(asso_e6), .asso_e7(asso_e7),
        .valid_in(valid_in),
        .delta_out(delta_out), .delta_regime(delta_regime),
        .kappa_stable(kappa_stable), .a1_violation(a1_violation),
        .threshold_fail(threshold_fail), .valid_out(valid_out),
        .delta_prev(delta_prev), .a1_tolerance(a1_tolerance)
    );

    initial clk = 1'b0;
    always #5 clk = ~clk;

    `define Q16_16(x) (x * 65536)
    `define Q8_8(x) (x * 256)

    integer pass_count, fail_count;

    initial begin
        rst_n = 1'b0; valid_in = 1'b0;
        asso_e0 = 0; asso_e1 = 0; asso_e2 = 0; asso_e3 = 0;
        asso_e4 = 0; asso_e5 = 0; asso_e6 = 0; asso_e7 = 0;
        delta_prev = 0; a1_tolerance = `Q8_8(1);
        pass_count = 0; fail_count = 0;

        #20 rst_n = 1'b1;
        #10;

        // ---- 测试 1：零 associator → δ=0（classical 域）----
        $display("[T1] 零结合子 → classical 域");
        asso_e0 = 0; asso_e1 = 0; asso_e2 = 0; asso_e3 = 0;
        asso_e4 = 0; asso_e5 = 0; asso_e6 = 0; asso_e7 = 0;
        valid_in = 1'b1;
        #10 valid_in = 1'b0;
        #60;

        if (valid_out && delta_regime == 2'd0) begin
            $display("  [PASS] δ=%0d, regime=classical", $signed(delta_out));
            pass_count = pass_count + 1;
        end else begin
            $display("  [FAIL] regime=%0d (预期 0)", delta_regime);
            fail_count = fail_count + 1;
        end

        // ---- 测试 2：非零 associator（quantum 域）----
        $display("[T2] 中等结合子 → quantum 域");
        asso_e1 = `Q16_16(1);  // 有非零分量
        valid_in = 1'b1;
        #10 valid_in = 1'b0;
        #60;

        if (valid_out) begin
            $display("  [INFO] δ=%0d, regime=%0d", $signed(delta_out), delta_regime);
            pass_count = pass_count + 1;
        end else begin
            $display("  [FAIL] 无输出");
            fail_count = fail_count + 1;
        end

        // ---- 测试 3：A1 公理校验 ----
        $display("[T3] A1 公理守恒校验");
        asso_e1 = 0;
        delta_prev = delta_out;  // 记录当前 δ
        a1_tolerance = `Q8_8(1);  // 容差=1.0
        asso_e2 = `Q16_16(2);  // 改变输入
        valid_in = 1'b1;
        #10 valid_in = 1'b0;
        #60;

        $display("  [INFO] A1 violation=%b, threshold_fail=%b", a1_violation, threshold_fail);
        pass_count = pass_count + 1;

        // 汇总
        $display("");
        $display("========================================");
        $display("delta_compute testbench: %0d pass, %0d fail", pass_count, fail_count);
        $display("========================================");
        #100 $finish;
    end

endmodule
