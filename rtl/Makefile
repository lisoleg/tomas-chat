# ============================================================
# TOMAS-AGI v2.0 M5 FPGA RTL 编译框架
# ============================================================

# 仿真器（Icarus Verilog 或 Verilator）
IVERILOG ?= iverilog
VVP     ?= vvp

# 源文件
RTL_SRC := octonion_mul.v delta_compute.v spectral_engine.v

# 测试模块
TB_OCT   := tb_octonion_mul
TB_DELTA := tb_delta_compute
TB_SPEC  := tb_spectral_engine

# 输出目录
BUILD := build

.PHONY: all sim-oct sim-delta sim-spec clean

all: $(BUILD)
	@echo "M5 FPGA RTL 就绪。运行 'make sim-oct' 启动仿真。"

$(BUILD):
	mkdir -p $(BUILD)

# ---- 八元数乘法器仿真 ----
sim-oct: $(BUILD)/$(TB_OCT).vvp
	$(VVP) $<

$(BUILD)/$(TB_OCT).vvp: octonion_mul.v | $(BUILD)
	$(IVERILOG) -o $@ $<

# ---- δ 计算单元仿真 ----
sim-delta: $(BUILD)/$(TB_DELTA).vvp
	$(VVP) $<

$(BUILD)/$(TB_DELTA).vvp: octonion_mul.v delta_compute.v | $(BUILD)
	$(IVERILOG) -o $@ $^

# ---- 谱计算引擎仿真 ----
sim-spec: $(BUILD)/$(TB_SPEC).vvp
	$(VVP) $<

$(BUILD)/$(TB_SPEC).vvp: octonion_mul.v delta_compute.v spectral_engine.v | $(BUILD)
	$(IVERILOG) -o $@ $^

# ---- 综合估算（需要 Vivado/Yosys）----
synth:
	@echo "请使用 Vivado 或 Yosys 进行综合"
	@echo "  Vivado: create_project → add_files → launch_runs impl_1"
	@echo "  Yosys:  yosys > read_verilog $(RTL_SRC); synth_xilinx -top tomas_fpga_top"

# ---- 清理 ----
clean:
	rm -rf $(BUILD)
