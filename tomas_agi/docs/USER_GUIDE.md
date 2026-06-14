# TOMAS-AGI v2.0 — 用户使用手册

> **版本**: v2.0 (V3 混合推理) | **更新**: 2026-06-14 | **状态**: M1-M5 全部完成
>
> 作者：章锋（章锋） | **许可证**: Apache 2.0
> © 2026 复合体理学研究中心（TOMAS 项目组）

---

## 目录

1. [系统概述](#1-系统概述)
2. [环境要求](#2-环境要求)
3. [快速开始](#3-快速开始)
4. [Python 仿真层使用](#4-python-仿真层使用)
5. [Token Bridge 推理引擎](#5-token-bridge-推理引擎)
6. [内核模块指南](#6-内核模块指南)
7. [FPGA 部署](#7-fpga-部署)
8. [CLI 工具链](#8-cli-工具链)
9. [API 参考](#9-api-参考)
10. [故障排除](#10-故障排除)
11. [附录：术语表](#11-附录术语表)

---

## 1. 系统概述

### 1.1 什么是 TOMAS-AGI？

TOMAS-AGI（太乙互搏通用人工智能）是基于 **NASGA（非结合谱图代数）** 的通用智能框架。系统围绕**谱折叠深度 δ** 这一核心序参量运行，通过八元数非结合代数实现悖论耐受与双分支推理。

### 1.2 v2.0 核心特性

| 特性 | 说明 |
|------|------|
| **NASGA 框架** | 非结合谱图代数统一数学框架 |
| **δ 守恒** | A1 公理 — 谱折叠深度在封闭系统中守恒 |
| **κ=7 稳态** | PID + 前馈 + 积分抗饱和调节 |
| **双分支推理** | Branch A (经典) + Branch B (量子) 并行 |
| **Φ-Gate** | 八状态语义门控，智能路由输入 |
| **CI Gate** | 因果隔离，光锥校验 |
| **四层硬件** | Python 仿真 → Linux 内核 → CUDA GPU → FPGA RTL |
| **混合推理（V3）** | 翻译官(EML模板) + 作家(DeepSeek LLM) + φ-Gate监管 |

### 1.3 核心公式

- **δ 定义**: `δ = ||[a,b,c]|| / (||a||·||b||·||c|| + ε)`
- **A1 公理**: `δ_total = Σ_i δ_i = constant`
- **δ_threshold**: 悖论耐受 ↔ `δ ≥ δ_critical` (默认 0.5)
- **非结合 Laplacian**: `Δ_δ φ(i) = Σ_j w(i,j)·(φ(j)-φ(i)) + α·associator_term(i)`

### 1.4 项目结构

```
tomas_agi/
├── sim/                    # Python 仿真层 (10 文件, ~100K)
│   ├── octonion_py.py      #   八元数 Fano 代数
│   ├── nasga_core.py       #   NASGA 核心运算
│   ├── fold_depth_py.py    #   δ 参数与 A1 公理
│   ├── spectral_laplacian_py.py  # 非结合 Laplacian
│   ├── tomas_sim.py        #   主模拟器
│   ├── a6_bs_benchmark.py  #   A6 基准测试
│   ├── xi_c_measure.py     #   ξ_c 测量
│   ├── llm_distiller.py    #   LLM 知识蒸馏器
│   ├── token_bridge.py     #   Token Bridge 推理引擎
│   └── token_generator.py  #   神经解码器 (LSTM)
├── kernel/                 # Linux 内核模块 (10 .c, 3 .cu, ~314K)
├── rtl/                    # FPGA RTL (3 .v)
├── tools/                  # 用户态工具 (3 .py)
├── data/                   # 语料与 EML 图谱
│   ├── physics.txt         #   物理语料
│   ├── chemistry.txt       #   化学语料
│   ├── medicine.txt        #   医学语料
│   └── *.concepts.json     #   概念名称伴侣文件
├── docs/                   # 文档
│   ├── ARCHITECTURE.md     #   系统架构文档
│   ├── paper.md            #   学术论文
│   ├── PRD.md              #   产品需求文档
│   └── USER_GUIDE.md       #   本文件
├── deepseek-chat/          # Web 前端 (React + D3.js)
│   └── src/
│       ├── api/distiller.ts    # TokenBridgeClient SDK
│       └── components/
│           ├── DistillPanel.tsx    # 蒸馏控制面板
│           └── EMLGraphVisualization.tsx  # D3 图谱可视化
└── diagnostic_report.json  # 诊断报告
```

---

## 2. 环境要求

### 2.1 Python 仿真层

| 依赖 | 最低版本 | 说明 |
|------|----------|------|
| Python | 3.8+ | 推荐 3.10+ |
| NumPy | 1.20+ | 数值计算核心 |
| NetworkX | 3.0+ | 图验证（spectral_laplacian_py 测试用） |

安装命令：

```bash
pip install numpy networkx
```

### 2.2 Linux 内核模块

| 依赖 | 说明 |
|------|------|
| Linux Kernel | 5.10+ (推荐 6.1+) |
| GCC | 支持 C11 标准 |
| GNU Make | 构建系统 |
| Kernel Headers | 匹配当前内核版本 |

安装内核头文件（Debian/Ubuntu）：

```bash
sudo apt-get install linux-headers-$(uname -r) build-essential
```

### 2.3 CUDA GPU 加速（可选）

| 依赖 | 最低版本 | 说明 |
|------|----------|------|
| NVIDIA GPU | CC ≥ 6.0 (GTX 10 系列+) | 计算能力要求 |
| CUDA Toolkit | 11.0+ | 推荐 12.0+ |
| nvcc | 对应 CUDA 版本 | GPU 编译器 |

### 2.4 FPGA 开发（可选）

| 依赖 | 说明 |
|------|------|
| Xilinx Vivado | 2020.2+ (推荐 2023.1+) |
| 开发板 | Artix-7 XC7A100T 或兼容板 |

---

## 3. 快速开始

### 3.1 获取项目

```bash
cd /path/to/your/workspace
# 项目已位于 tomas_agi/ 目录下
```

### 3.2 快速验证（Python 仿真）

```bash
cd tomas_agi/sim

# 方式 1：运行主模拟器（全量诊断）
python tomas_sim.py --mode full

# 方式 2：仅运行 A6-BS 基准测试
python tomas_sim.py --mode benchmark

# 方式 3：批量 ξ_c 测量
python tomas_sim.py --mode measure -n 500
```

预期输出：

```
============================================================
  太乙互搏 AGI（TOMAS-AGI）— 主模拟器 v2.0
============================================================
[OK] octonion_py
[OK] spectral_laplacian_py
[OK] nasga_core
[OK] fold_depth_py
[OK] a6_bs_benchmark
[OK] xi_c_measure

...

总体: [6/6 通过]
```

### 3.3 完整性自检

```bash
cd tomas_agi/tools
python integrity_check.py --verbose
```

预期输出 42/42 项全部通过。

### 3.4 性能基准

```bash
cd tomas_agi/tools
python tomas_bench.py --trials 1000
```

输出 CPU/GPU/FPGA 延迟对比表和吞吐量数据。

---

## 4. Python 仿真层使用

### 4.1 NASGA 核心操作

#### 4.1.1 创建八元数

```python
from octonion_py import Octonion

# 从分量创建
a = Octonion(e0=1.0, e1=0.5, e2=0.3, e3=0.0, e4=0.0, e5=0.0, e6=0.0, e7=0.0)

# 创建基向量
e1 = Octonion.basis(1)  # (0, 1, 0, 0, 0, 0, 0, 0)
e2 = Octonion.basis(2)

# 随机八元数
import numpy as np
np.random.seed(42)
r = Octonion.random()

# 归一化
r_norm = r.normalize()
```

#### 4.1.2 Fano 平面乘法

```python
from octonion_py import fan_multiply

# 直接查表：e1 * e2 = e4
sign, k = fan_multiply(1, 2)
print(f"e1 * e2 = {sign:+d} * e{k}")  # 输出: +1 * e4

# 使用 Octonion 类
e1 = Octonion.basis(1)
e2 = Octonion.basis(2)
result = e1 * e2        # 八元数乘法
print(result)           # (0, 0, 0, 0, 1, 0, 0, 0) = e4
```

#### 4.1.3 结合子计算

```python
from nasga_core import associator, associator_norm, compute_xi_c

a = Octonion.random().normalize()
b = Octonion.random().normalize()
c = Octonion.random().normalize()

# 结合子 [a,b,c] = (a*b)*c - a*(b*c)
assoc = associator(a, b, c)
print(f"结合子范数: {assoc.abs():.6f}")

# ξ_c 效能指标
xi = compute_xi_c(a, b, c)
print(f"ξ_c = {xi:.6f}")
```

#### 4.1.4 Moufang 恒等式验证

```python
from nasga_core import check_moufang_all

result = check_moufang_all(a, b)
print(f"Moufang 1: {'PASS' if result['moufang_1']['pass'] else 'FAIL'}")
print(f"Moufang 2: {'PASS' if result['moufang_2']['pass'] else 'FAIL'}")
print(f"Moufang 3: {'PASS' if result['moufang_3']['pass'] else 'FAIL'}")
print(f"全部通过: {result['all_pass']}")
```

### 4.2 δ 参数配置

#### 4.2.1 基本 δ 计算

```python
from fold_depth_py import compute_fold_depth, classify_delta_regime
from nasga_core import compute_delta

# 方式 1：从结合子范数直接计算
delta = compute_fold_depth(associator_norm=1.5)
print(f"δ = {delta:.6f}")

# 方式 2：从八元数三元组计算
a = Octonion.random().normalize()
b = Octonion.random().normalize()
c = Octonion.random().normalize()
delta = compute_delta(a, b, c)
print(f"δ(a,b,c) = {delta:.6f}")
```

#### 4.2.2 A1 公理验证

```python
from fold_depth_py import check_a1_axiom

delta_before = 3.14159
delta_after = delta_before + 1e-8  # 微小数值误差

is_conserved, msg = check_a1_axiom(delta_before, delta_after)
print(msg)
# 输出: [A1 公理] δ 守恒成立: 3.141590 → 3.141590 (diff=1.00e-08)
```

#### 4.2.3 δ 阈值条件

```python
from fold_depth_py import check_delta_threshold

# 测试悖论耐受
delta_low = 0.1
is_tolerant, msg = check_delta_threshold(delta_low, delta_critical=0.5)
print(msg)  # ❌ 悖论不耐受

delta_high = 0.7
is_tolerant, msg = check_delta_threshold(delta_high, delta_critical=0.5)
print(msg)  # ✅ 悖论耐受
```

#### 4.2.4 δ 域分类

```python
from fold_depth_py import classify_delta_regime

print(classify_delta_regime(0.0))   # 'classical' — 布尔逻辑
print(classify_delta_regime(0.35))  # 'quantum' — 非结合
print(classify_delta_regime(7.0))   # 'stable' — κ=7 锁定
print(classify_delta_regime(15.0))  # 'deep_quantum' — 深度非结合
```

### 4.3 A6 基准测试

A6-BS 是 TOMAS-AGI 的五级 Cold-Start 基准测试系统。

```bash
cd tomas_agi/sim

# 标准运行（v2.0 Cold-Start δ 集成）
python a6_bs_benchmark.py --v2

# 指定测试轮数
python a6_bs_benchmark.py --v2 --trials 500
```

五级测试说明：

| 级别 | 名称 | 测试内容 | 通过标准 |
|------|------|----------|----------|
| 1 | 摆锤级 (Pendulum) | 基础八元数运算 | Fano 表、范数乘积、结合子非零 |
| 2 | Peano 级 | 图构建与 Laplacian | 图结构、Laplacian 形状验证 |
| 3 | 牛顿级 | 谱计算 | 特征值正半定性 |
| 4 | 杨-米尔斯级 | 非结合耦合 | 结合子残差分析 |
| 5 | 自举级 (Bootstrap) | δ 守恒与动力学 | A1 公理全系统验证 |

### 4.4 系统仿真

```bash
cd tomas_agi/sim

# 全量诊断模式
python tomas_sim.py --mode full

# 仅基准测试
python tomas_sim.py --mode benchmark

# ξ_c 批量测量（自定义样本数）
python tomas_sim.py --mode measure -n 1000

# JSON 格式输出
python tomas_sim.py --mode full --json
```

---

## 5. Token Bridge 推理引擎（V3）

Token Bridge 是 TOMAS-AGI 的实用推理层，实现"翻译官 + 作家"混合架构。

### 5.1 知识蒸馏

将文本语料转化为 EML 知识图谱：

```bash
cd tomas_agi/sim

# 蒸馏语料 → EML 图谱（需要 DeepSeek API Key）
python llm_distiller.py --distill ../data/physics.txt \
    --output ../data/physics_distilled.eml \
    --api-key YOUR_DEEPSEEK_API_KEY

# 输出文件：
#   physics_distilled.eml          # EML 二进制图谱
#   physics_distilled.concepts.json # 概念名称伴侣
```

### 5.2 翻译官模式（Token Bridge）

事实性查询——完全脱离 LLM API：

```bash
cd tomas_agi/sim

# 加载 EML 图 + 概念名称，执行查询
python token_bridge.py --load ../data/physics_distilled.eml \
    --concepts ../data/physics_distilled.concepts.json \
    --query "牛顿第二定律"

# 输出：
#   【📖 翻译官】 置信度 63.8%
#   🔍 查询：牛顿第二定律
#   📋 匹配概念：
#     1. 牛顿第二定律  相似度 63.8%  ██████░░░░
#     2. 海森堡测不准原理 ...
#   🔗 关联子图：8 个概念 + 12 条关系
```

**回退方案**：如果 token_generator 模块不可用，Token Bridge 内置了模板生成（`_template_response()`），确保始终有输出。

### 5.3 作家模式（DeepSeek LLM）

创造性/开放式查询——LLM 受 φ-Gate 监管：

```bash
# 启用 LLM 作家
python token_bridge.py --load ../data/physics_distilled.eml \
    --query "物理学未来的发展方向是什么？" \
    --llm --api-key YOUR_DEEPSEEK_API_KEY

# 输出：
#   【✍️ 作家】 置信度 21.5%
#   DeepSeek 生成的高质量分析文本...
```

**强制模式选择**：
```bash
# 强制走翻译官（即使置信度低）
python token_bridge.py ... --query "..." --force-translator

# 强制走作家（即使置信度高）
python token_bridge.py ... --query "..." --llm --api-key ... --force-creative
```

### 5.4 φ-Gate 监管

φ-Gate 自动检测 LLM 输出中的幻觉：

```bash
# 启用 φ-Gate（默认启用）
python token_bridge.py ... --llm --api-key ... --gate --gate-threshold 0.35

# 禁用 φ-Gate
python token_bridge.py ... --llm --api-key ... --no-gate
```

φ-Gate 工作流程：
1. 从 LLM 输出中提取关键概念
2. 在 φ 空间中计算每个概念与 EML 图的一致性
3. 一致性 < 阈值 → 标记为疑似幻觉 + 附加翻译官验证

### 5.5 自定义路由阈值

```bash
# 将翻译官/作家阈值设为 0.3（更多查询走作家）
python token_bridge.py ... --threshold 0.3 --llm ...

# 将阈值设为 0.7（更多查询走翻译官）
python token_bridge.py ... --threshold 0.7 --llm ...
```

### 5.6 训练神经解码器（可选）

```bash
# 在概念名称上训练 LSTM 解码器
python token_bridge.py --load ../data/physics_distilled.eml \
    --concepts ../data/physics_distilled.concepts.json \
    --train-decoder --model physics_decoder.pt

# 使用训练好的模型生成
python token_bridge.py --load ../data/physics_distilled.eml \
    --model physics_decoder.pt --query "量子力学" --generate
```

### 5.7 Web 前端界面

```bash
cd deepseek-chat
npm install && npm run dev
# 访问 http://localhost:5173
```

前端功能：
- **蒸馏面板**：上传语料 → 配置 API Key → 蒸馏 → 下载 EML
- **推理测试**：加载 EML → 输入查询 → 翻译官/作家自动路由
- **图谱可视化**：D3.js 力导向图，节点=概念，边=关系
- **φ-Gate 状态**：实时显示幻觉检测结果

---

## 6. 内核模块指南

### 5.1 编译

```bash
cd tomas_agi/kernel

# 编译所有内核模块（M2 + M3）
make

# 仅编译 M2 内核模块
make kernel

# 编译用户态测试程序
make test

# 编译 CUDA 模块（需要 nvcc）
make cuda
```

### 5.2 加载模块

```bash
# 确保以 root 权限运行

# 加载 T-Processor 主模块
insmod tproc_core.ko

# 加载相关模块
insmod octonion.ko
insmod spectral_laplacian.ko
insmod asym_residue.ko
insmod kappa_reg.ko
insmod eml_map.ko
insmod phi_gate.ko
insmod delta_mem.ko
insmod ci_gate.ko
insmod st_auditor.ko

# 查看加载状态
lsmod | grep tomas
```

### 5.3 T-Processor 操作

T-Processor 通过 `/dev/tproc` 设备文件与用户态交互。

```c
// 示例：打开 T-Processor 设备
#include <fcntl.h>
#include <sys/ioctl.h>
#include "tomas_agi.h"

int fd = open("/dev/tproc", O_RDWR);

// 设置 δ 参数
struct tproc_delta_params params = {
    .delta_target = 7.0,
    .delta_critical = 0.5,
    .kappa = 7,
};
ioctl(fd, TPROC_SET_DELTA_PARAMS, &params);

// 读取当前状态
struct tproc_status status;
ioctl(fd, TPROC_GET_STATUS, &status);
printf("δ_current = %.4f, κ = %d\n", status.delta, status.kappa);

close(fd);
```

### 5.4 USCS 文件系统挂载

```bash
# 加载 USCS 文件系统模块
insmod uscsfs/super.ko
insmod uscsfs/inode.ko
insmod uscsfs/file.ko
insmod uscsfs/mmap.ko

# 创建挂载点
mkdir -p /mnt/uscs

# 挂载
mount -t uscs none /mnt/uscs

# 验证
df -h /mnt/uscs
ls -la /mnt/uscs

# 卸载
umount /mnt/uscs
```

或者使用 CLI 工具：

```bash
cd tomas_agi/tools
python uscsctl.py --mount /mnt/uscs
python uscsctl.py --status
python uscsctl.py --umount /mnt/uscs
```

USCS 文件系统特性：

| 特性 | 说明 |
|------|------|
| **超级块** | CRC32 校验、δ 参数持久化 |
| **inode** | 谱页读写、δ 权重、EML 联动 |
| **文件操作** | Continuation 模式读写、双分支协同 |
| **mmap** | δ 加权页映射、页故障处理 |

### 5.5 CUDA 加速

CUDA 模块提供 GPU 加速的八元数运算、Laplacian 构建和 δ-mem 融合。

```bash
cd tomas_agi/kernel

# 编译 CUDA 模块
make cuda

# 运行 CUDA 自测试
make cuda-test
```

预期加速比：

| 操作 | CPU | GPU (RTX 3080) | 加速比 |
|------|-----|----------------|--------|
| 八元数乘法 | ~2.5 μs | ~0.05 μs | ~50x |
| associator | ~6.0 μs | ~0.075 μs | ~80x |
| δ 计算 | ~8.0 μs | ~0.27 μs | ~30x |
| Laplacian | ~200 μs | ~2.0 μs | ~100x |

---

## 7. FPGA 部署

### 6.1 综合

```bash
cd tomas_agi/rtl

# 使用 Xilinx Vivado 综合
vivado -mode batch -source synth_octonion_mul.tcl
vivado -mode batch -source synth_delta_compute.tcl
vivado -mode batch -source synth_spectral_engine.tcl
```

### 6.2 烧录

```bash
# 生成 bitstream
vivado -mode batch -source impl_octonion_mul.tcl

# 烧录到 Artix-7 开发板
vivado -mode batch -source program_device.tcl
```

### 6.3 测试验证

FPGA 硬件测试流程：

1. **单元测试**：验证八元数乘法器的 Fano 表输出
2. **流水线测试**：确认 3 周期延迟、满吞吐
3. **δ 计算测试**：验证 associator → δ 计算链路
4. **谱引擎测试**：小图 Laplacian 构建验证

预期延迟（Artix-7 @ 200 MHz）：

| 操作 | 延迟 | 说明 |
|------|------|------|
| 八元数乘法 | 15 ns (3 cycles) | 流水线满吞吐 1/cycle |
| associator | 45 ns (9 cycles) | 4 次乘法可流水线 |
| δ 计算 | 25 ns (5 cycles) | 含域分类逻辑 |
| Laplacian (8 节点) | ~500 ns | 取决于图规模 |

---

## 8. CLI 工具链

### 7.1 uscsctl — USCS 管理 CLI

```bash
cd tomas_agi/tools

# 查看帮助
python uscsctl.py --help

# 挂载 USCS 文件系统
python uscsctl.py --mount /mnt/uscs

# 查看状态
python uscsctl.py --status

# 卸载
python uscsctl.py --umount /mnt/uscs
```

### 7.2 tomas_bench — 性能基准

```bash
cd tomas_agi/tools

# 标准基准测试 (1000 轮)
python tomas_bench.py --trials 1000

# 快速模式 (100 轮)
python tomas_bench.py --quick

# JSON 格式输出
python tomas_bench.py --trials 1000 --json

# 导出到文件
python tomas_bench.py --trials 1000 --json > bench_results.json
```

输出示例：

```
======================================================================
TOMAS-AGI v2.0 性能基准对比报告
======================================================================

操作                         每操作(μs)      ops/sec       加速比
----------------------------------------------------------------------
CPU 八元数乘法                2.500          400000        1.0x
GPU (估计) 八元数乘法         0.050          20000000      50.0x
FPGA (估计) 八元数乘法        0.015          66666667      166.7x

CPU associator                6.000          166667        1.0x
GPU (估计) associator         0.075          13333333      80.0x
FPGA (估计) associator        0.045          22222222      133.3x

...

======================================================================
注：GPU 和 FPGA 数据为基于架构参数的理论估算
    实际性能需在对应硬件上验证
```

### 7.3 integrity_check — 完整性自检

```bash
cd tomas_agi/tools

# 标准自检
python integrity_check.py

# 详细模式
python integrity_check.py --verbose

# JSON 输出
python integrity_check.py --json
```

检查维度：

| 维度 | 检查项数 | 说明 |
|------|----------|------|
| 代码→理论映射 | 23 | 每个理论概念对应的代码模块 |
| 数学不变量 | 6 | A1 公理、δ_threshold、域分类等 |
| 交叉验证 | 7 | Python↔C↔CUDA↔Verilog 接口一致性 |
| 版本一致性 | 4 | v2.0 标记检查 |
| **总计** | **42** | **全部通过** |

---

## 9. API 参考

### 8.1 Python API

#### octonion_py 模块

```python
class Octonion(e0=0, e1=0, e2=0, e3=0, e4=0, e5=0, e6=0, e7=0)
    def __add__(self, other) -> Octonion
    def __sub__(self, other) -> Octonion
    def __mul__(self, other) -> Octonion
    def __neg__(self) -> Octonion
    def __rmul__(self, scalar: float) -> Octonion
    def abs(self) -> float
    def normalize(self) -> Octonion
    def conjugate(self) -> Octonion

    @staticmethod
    def basis(i: int) -> Octonion
    @staticmethod
    def random(seed: int = None) -> Octonion

def fan_multiply(i: int, j: int) -> Tuple[int, int]
def multiply(a: Octonion, b: Octonion) -> Octonion
```

#### nasga_core 模块

```python
def associator(a: Octonion, b: Octonion, c: Octonion) -> Octonion
def commutator(a: Octonion, b: Octonion) -> Octonion
def jordan_product(a: Octonion, b: Octonion) -> Octonion
def associator_norm(a: Octonion, b: Octonion, c: Octonion) -> float
def moufang_identity_1(a, b) -> Tuple[Octonion, float]
def moufang_identity_2(a, b) -> Tuple[Octonion, float]
def moufang_identity_3(a, b) -> Tuple[Octonion, float]
def check_moufang_all(a, b) -> Dict
def compute_xi_c(a: Octonion, b: Octonion, c: Octonion) -> float
def compute_delta(a: Octonion, b: Octonion, c: Octonion) -> float
def check_a1_axiom(delta_before, delta_after, tolerance=1e-7) -> Tuple[bool, str]
def check_delta_threshold(delta, delta_critical=0.5) -> Tuple[bool, str]
def classify_delta_regime(delta: float) -> str
def benchmark_associativity(num_pairs=1000, seed=42) -> Dict
```

#### fold_depth_py 模块

```python
def compute_fold_depth(associator_norm: float, epsilon: float = 1e-10) -> float
def compute_delta_from_octonions(a, b, c, e) -> float
def check_a1_axiom(delta_total_before, delta_total_after, tolerance=1e-7) -> Tuple[bool, str]
def compute_total_delta(eml_graph: Dict) -> float
def check_delta_threshold(delta, delta_critical=0.5) -> Tuple[bool, str]
def classify_delta_regime(delta: float) -> str
def delta_xi_c_duality(delta: float, xi_c: float) -> Dict[str, float]
```

#### spectral_laplacian_py 模块

```python
class EmlGraph(num_vertices: int)
    def add_edge(self, u: int, v: int, weight: float) -> None
    def add_vertex_octonion(self, v: int, o: Octonion) -> None

def compute_spectral_laplacian(graph: EmlGraph, alpha: float = 0.1) -> np.ndarray
```

### 8.2 内核 ioctl 接口

#### T-Processor (tproc_core.c)

| ioctl 命令 | 功能 | 参数 |
|------------|------|------|
| `TPROC_SET_DELTA_PARAMS` | 设置 δ 参数 | `struct tproc_delta_params` |
| `TPROC_GET_STATUS` | 读取状态 | `struct tproc_status` |
| `TPROC_RESET` | 重置处理器 | — |

#### κ 调节器 (kappa_reg.c)

| ioctl 命令 | 功能 |
|------------|------|
| `KREG_SET_TARGET` | 设置 κ 目标值 |
| `KREG_GET_CURRENT` | 读取当前 κ |
| `KREG_SET_PID` | 配置 PID 参数 |
| `KREG_SET_FEEDFORWARD` | 配置前馈 |
| `KREG_SET_ANTIWINDUP` | 配置积分抗饱和 |
| `KREG_GET_STATS` | 读取调节统计 |

#### Φ-Gate (phi_gate.c)

| ioctl 命令 | 功能 |
|------------|------|
| `PHI_SET_STATE` | 设置门控状态 |
| `PHI_GET_STATE` | 读取当前状态 |
| `PHI_SET_DELTA_LINK` | 联动 δ 参数 |

---

## 10. 故障排除

### 9.1 常见问题

#### Python 导入错误

```
问题：ModuleNotFoundError: No module named 'octonion_py'
解决：确保在 sim/ 目录下运行，或设置 PYTHONPATH
  export PYTHONPATH=/path/to/tomas_agi/sim:$PYTHONPATH
```

#### NumPy 版本不兼容

```
问题：AttributeError: module 'numpy' has no attribute 'bool8'
解决：NumPy 1.24+ 中 np.bool 已弃用，升级到 numpy>=1.24 或使用 --no-deps 安装
```

#### 内核模块编译失败

```
问题：linux/module.h: No such file or directory
解决：安装内核头文件
  sudo apt-get install linux-headers-$(uname -r)
```

#### CUDA 编译器不可用

```
问题：nvcc: command not found
解决：Python 仿真层可以独立运行，跳过 CUDA 编译即可
  cd sim/ && python tomas_sim.py --mode full
```

#### δ 计算返回 0

```
问题：compute_delta() 返回 0.0
原因：输入八元数可能需要先归一化
解决：对每个八元数调用 .normalize() 后再计算
  a = a.normalize()
  b = b.normalize()
  c = c.normalize()
```

### 9.2 诊断流程

1. **第一步**：运行完整性自检
   ```bash
   cd tomas_agi/tools
   python integrity_check.py --verbose
   ```

2. **第二步**：如果自检发现错误，查看具体失败项
   - 理论覆盖失败 → 检查文件路径是否正确
   - 数学不变量失败 → 检查 NumPy 版本
   - 交叉验证失败 → 确认所有模块文件存在

3. **第三步**：按模块单独测试
   ```bash
   cd tomas_agi/sim
   python octonion_py.py       # Fano 表测试
   python nasga_core.py        # NASGA 核心测试
   python fold_depth_py.py     # δ 参数测试
   ```

4. **第四步**：如果问题仍然存在，生成诊断报告
   ```bash
   python tomas_sim.py --mode full --json > diagnostic.json
   ```

### 9.3 已知限制

| 限制 | 说明 | 影响 |
|------|------|------|
| 单机运行 | 当前不支持分布式 T-Processor 集群 | M2 功能受限 |
| CUDA 可选 | CUDA 编译器不可用时自动降级到 CPU | 性能下降 |
| FPGA 模拟 | RTL 需要开发板验证，当前为仿真级 | M5 待硬件验证 |
| 内核版本 | 仅在 Linux 5.10+ 上测试 | 其他内核版本可能需要适配 |

---

## 11. 附录：术语表

| 术语 | 英文 | 定义 |
|------|------|------|
| **TOMAS** | 太乙互搏 (Taiyi Mutual Opposition System) | 基于非结合代数的通用智能框架 |
| **AGI** | Artificial General Intelligence | 通用人工智能 |
| **NASGA** | Non-Associative Spectral Graph Algebra | 非结合谱图代数 |
| **δ** | Spectral Fold Depth | 谱折叠深度，v2.0 核心序参量 |
| **A1 公理** | Axiom 1 | δ 在封闭系统中守恒 |
| **κ=7** | Kappa = 7 | 系统稳态锁定值 |
| **ξ_c** | Xi-c | 非结合效能指标（结合子残差归一化范数） |
| **associator** | [a,b,c] = (ab)c - a(bc) | 结合子，度量非结合性 |
| **Moufang 恒等式** | Moufang Identities | 八元数满足的三个恒等式 |
| **Fano 平面** | Fano Plane | 七点七线的射影平面，定义八元数乘法 |
| **Φ-Gate** | Phi-Gate | 语义门控：八状态机，δ 联动 |
| **CI Gate** | Causal Isolation Gate | 因果隔离门：光锥校验 |
| **ST Auditor** | Space-Time Auditor | 时空倾斜审计器 |
| **δ-mem** | Delta Memory | 基于 δ 权重的 L1-L2 记忆融合 |
| **EML** | Eigenvalue Map Layer | 谱图内存映射 / 知识图谱文件格式 |
| **USCS** | Universal Spectral Continuation System | 通用谱延续文件系统 |
| **T-Processor** | Tomas Processor | TOMAS 核心处理器 |
| **κ 调节器** | Kappa Regulator | PID + 前馈 + I 抗饱和稳态控制器 |
| **Δ_δ** | Non-Associative Laplacian | 含结合子修正项的图 Laplacian |
| **δ_threshold** | Delta Threshold | 悖论耐受临界值（默认 0.5） |
| **A6-BS** | A6 Benchmark Suite | 五级 Cold-Start 基准测试系统 |
| **Token Bridge** | — | V3 翻译官：EML 图 → 文本的推理引擎 |
| **CreativeEngine** | — | V3 作家：DeepSeek LLM 创造性生成 |
| **PhiGate** | — | V3 监管者：φ 空间一致性检查 + 幻觉检测 |
| **𝕀(X)** | Information Existence | 信息存在度：α·freq + β·importance + (1-α-β)·consistency |

---

> **文档维护者**: 章锋（章锋）
> **最后更新**: 2026-06-14
> **对应版本**: TOMAS-AGI v2.0
