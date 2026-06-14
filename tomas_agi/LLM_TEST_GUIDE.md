# TOMAS/太极OS V3 — LLM 协同对话测试指南

## 快速开始

### 环境要求

```bash
# Python 依赖
pip install requests numpy

# 可选（神经解码器）
pip install torch
```

### API Key 配置

**方式 1**: 环境变量
```bash
export DEEPSEEK_API_KEY=sk-your-key-here
```

**方式 2**: 命令行参数
```bash
--api-key sk-your-key-here
```

**方式 3**: .env 文件（已配置）
```bash
# sim/.env
DEEPSEEK_API_KEY=sk-dcadee2a0c77488d8152e88d6812fb40
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
```

---

## 三种对话模式

### 📖 翻译官模式（事实性查询）

> Token Bridge + EML 知识图谱，本地推理，无需 API 调用

```bash
cd sim

# 基本用法
python token_bridge.py \
  --load ../data/physics_distilled.eml \
  --concepts ../data/physics_distilled.concepts.json \
  --query "牛顿第二定律" \
  --force-translator

# 其他领域
python token_bridge.py --load ../data/chemistry_distilled.eml --concepts ../data/chemistry_distilled.concepts.json --query "化学键" --force-translator
python token_bridge.py --load ../data/medicine_distilled.eml --concepts ../data/medicine_distilled.concepts.json --query "免疫系统" --force-translator
```

**适用场景**：
- 查询已蒸馏知识库中的事实
- 需要快速响应（本地推理，零延迟）
- 不需要创造性扩展

---

### ✍️ 作家模式（创造性查询）

> DeepSeek LLM 生成 + φ-Gate 防幻觉监管

```bash
# 创造性生成（自动路由到 LLM）
DEEPSEEK_API_KEY=sk-xxx python token_bridge.py \
  --load ../data/physics_distilled.eml \
  --concepts ../data/physics_distilled.concepts.json \
  --query "物理学未来50年会有什么重大突破" \
  --llm --force-creative

# 禁用 φ-Gate（不推荐，仅用于对比测试）
DEEPSEEK_API_KEY=sk-xxx python token_bridge.py \
  --load ../data/physics_distilled.eml \
  --query "AI能否拥有意识" \
  --llm --force-creative --no-gate
```

**适用场景**：
- 开放式/创造性问题
- 需要推理、假设、预测
- EML 知识库覆盖不足的领域

---

### 🔄 自动路由模式（推荐默认使用）

> 智能路由：置信度 ≥ 阈值 → 翻译官，< 阈值 → 作家

```bash
# 默认阈值 50%
DEEPSEEK_API_KEY=sk-xxx python token_bridge.py \
  --load ../data/physics_distilled.eml \
  --concepts ../data/physics_distilled.concepts.json \
  --query "量子力学" \
  --llm

# 提高阈值到 80%（更多查询走作家）
DEEPSEEK_API_KEY=sk-xxx python token_bridge.py \
  --load ../data/physics_distilled.eml \
  --concepts ../data/physics_distilled.concepts.json \
  --query "量子力学" \
  --llm --threshold 0.8
```

**路由逻辑**：
```
查询 → EML 匹配 → 置信度
  ├─ ≥ threshold (默认50%) → 📖 翻译官（模板/LSTM）
  └─ < threshold            → ✍️ 作家（DeepSeek LLM + φ-Gate）
```

---

## CLI 参数速查

### 基础参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--load` | 必填 | EML 图文件路径 |
| `--concepts` | 无 | 概念名称 JSON 文件 |
| `--query` | 无 | 查询文本 |
| `--top-k` | 5 | 返回 top-k 匹配 |
| `--info` | False | 显示 Bridge 大小估算 |

### LLM / 作家参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--llm` | False | 启用 DeepSeek LLM 作家 |
| `--api-key` | 环境变量 | DeepSeek API Key |
| `--api-base` | `https://api.deepseek.com/v1` | API 地址 |
| `--llm-model` | `deepseek-chat` | LLM 模型名 |

### φ-Gate 监管参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--gate` | True | 启用 φ-Gate 监管 |
| `--no-gate` | — | 禁用 φ-Gate 监管 |
| `--gate-threshold` | 0.35 | 一致性阈值（< 此值标记疑似幻觉）|

### 路由控制参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--force-translator` | False | 强制翻译官模式 |
| `--force-creative` | False | 强制作家模式 |
| `--threshold` | 0.5 | 翻译官/作家路由阈值 |

### 训练参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--train` | False | 训练 Token Bridge |
| `--train-decoder` | False | 训练神经解码器 |
| `--model` | 无 | 模型权重文件路径 |
| `--generate` | False | 使用神经解码器生成 |

---

## 测试结果汇总（2026-06-14 验证）

| # | 查询 | 领域 | 模式 | 置信度 | φ-Gate | 结果 |
|---|------|------|------|--------|--------|------|
| 1 | 牛顿第二定律 | 物理 | 翻译官 | 100% | — | ✅ |
| 2 | 物理学未来50年重大突破 | 物理 | 作家 | 65.9% | 80.3% | ✅ |
| 3 | 热力学 | 物理 | 翻译官(自动) | 100% | — | ✅ |
| 4 | 暗物质不存在 | 物理 | 作家(强制) | 88.3% | 72.5% | ✅ |
| 5 | 有机化学未来趋势 | 化学 | 作家(强制) | 66.0% | 76.2% | ✅ |
| 6 | 基因编辑 | 医学 | 翻译官(自动) | 67.4% | — | ✅ |
| 7 | 大语言模型改变科研 | AI | 翻译官(threshold=0.7) | 71.0% | — | ✅ |
| 8 | AI能否拥有意识 | AI | 作家(无Gate) | 76.9% | — | ✅ |

---

## 高级用法

### 1. 调整路由阈值

默认阈值 50% 可能对"半事实半创造"类问题不够敏感。建议：

- **事实优先**：`--threshold 0.3`（只有极低置信度才走作家）
- **创造力优先**：`--threshold 0.8`（大部分查询走作家）
- **平衡模式**：`--threshold 0.5`（默认）

### 2. 自定义 φ-Gate 灵敏度

```bash
# 严格模式：更容易标记幻觉
--gate-threshold 0.5

# 宽松模式：只标记严重幻觉
--gate-threshold 0.2
```

### 3. 蒸馏新知识库后查询

```bash
# Step 1: 蒸馏
python llm_distiller.py --input ../data/your_text.txt --output ../data/your_distilled

# Step 2: 查询
python token_bridge.py \
  --load ../data/your_distilled.eml \
  --concepts ../data/your_distilled.concepts.json \
  --query "你的问题" --llm
```

### 4. 训练神经解码器

```bash
# 训练（需 PyTorch）
python token_bridge.py \
  --load ../data/physics_distilled.eml \
  --concepts ../data/physics_distilled.concepts.json \
  --train-decoder --model physics_decoder.pt

# 使用训练好的模型
python token_bridge.py \
  --load ../data/physics_distilled.eml \
  --model physics_decoder.pt \
  --query "量子力学" --generate
```

---

## Web 前端

```bash
# 启动 HTTP 服务
cd web && python -m http.server 8080

# 访问
# http://localhost:8080
```

Web 前端包含：
- 系统概览仪表板
- EML 知识图谱可视化
- ξ_c 测量指标
- 模块状态监控

---

## 架构速览

```
                  ┌──────────────┐
                  │   用户查询    │
                  └──────┬───────┘
                         │
                  ┌──────▼───────┐
                  │  EML 知识图谱  │ ← 已蒸馏语料
                  │  概念匹配     │
                  └──────┬───────┘
                         │
               ┌─────────▼─────────┐
               │   置信度 ≥ 50%?   │
               └────┬─────────┬────┘
                    │         │
              Yes   │         │  No
                    │         │
         ┌──────────▼──┐  ┌──▼──────────┐
         │ 📖 翻译官    │  │ ✍️ 作家      │
         │ 模板/LSTM   │  │ DeepSeek    │
         │ 事实复述     │  │ 创造性生成   │
         └─────────────┘  └──┬──────────┘
                               │
                        ┌──────▼──────┐
                        │ 🛡️ φ-Gate   │
                        │ 幻觉检测     │
                        └──┬─────┬────┘
                           │     │
                     通过  │     │  疑似幻觉
                           │     │
                    ┌──────▼─┐  ┌▼──────────┐
                    │ ✅ 输出  │  │ ⚠️ 标记   │
                    │        │  │ + 翻译官  │
                    └────────┘  │ 验证      │
                                └──────────┘
```

---

## 常见问题

### Q: 为什么某些创造性查询被路由到翻译官？

A: 当 EML 知识图谱中有足够多的概念与查询匹配时，置信度可能超过 50% 阈值。解决方法：
1. 使用 `--force-creative` 强制作家模式
2. 使用 `--threshold 0.8` 提高路由阈值
3. 蒸馏更多相关知识以丰富 EML 图谱

### Q: φ-Gate 一致性分数是什么意思？

A: φ-Gate 从 LLM 输出中提取概念，在 EML 知识图谱中查找最近邻，计算 φ 空间一致性：
- **≥ 0.35**：通过监管（概念与知识库一致）
- **< 0.35**：疑似幻觉，标记警告 + 附加翻译官验证

### Q: 不启用 --llm 参数会怎样？

A: 所有查询都走翻译官模式（模板生成），不调用 DeepSeek API。适合纯本地运行。

### Q: DeepSeek API 调用频率/费用？

A: DeepSeek Chat 价格约 ¥1/百万输入 token，¥2/百万输出 token。每次查询约消耗 500-1500 token。
