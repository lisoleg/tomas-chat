# TOMAS/太极OS 项目记忆

## 架构
- **V3 (当前):** "翻译官 + 作家" 混合架构
  - 翻译官: LSTM/模板 → 事实性查询（EML 图检索→精确回答）
  - 作家: DeepSeek LLM → 创造性查询（带 EML 上下文 + φ-Gate 监管）
  - 路由: 置信度 ≥0.5 → 翻译官，<0.5 → 作家
- Python 入口: `tomas_agi/sim/token_bridge.py`
- 前端: `deepseek-chat/` (Vite + React + TypeScript)

## 关键文件
- `token_bridge.py` — TokenBridge, InferenceEngine, CreativeEngine, PhiGate, EMLFileLoader
- `token_generator.py` — 模板生成 + LSTM PhiToTokenDecoder
- `llm_distiller.py` — EML 蒸馏器（文本→概念+关系→.eml二进制）
- `distiller.ts` — 前端 TokenBridgeClient + EML 加载/序列化
- `DistillPanel.tsx` — 蒸馏 UI + Token Bridge 推理面板
- `EMLGraphVisualization.tsx` — D3.js 力导向图

## 数据文件
- 语料: `tomas_agi/data/physics.txt`, `chemistry.txt`, `medicine.txt`
- EML 图: `*_distilled.eml` (被 .gitignore 忽略，需重新蒸馏)
- 概念名称: `*_distilled.concepts.json`

## API 配置
- DeepSeek API Key: 在 `tomas_agi/sim/.env` 或环境变量 `DEEPSEEK_API_KEY`
- 默认 base: `https://api.deepseek.com/v1`

## 数据库
- **路径**: `D:/tomas-data/tomas.db`（SQLite，24.7 GB）
- **knowledge_triples**: ~72,840,353 行（OwnThink 导入，约 52% 完成）
- **Schema**: 7 张表 — `api_keys`, `chat_sessions`, `conflict_decisions`, `corpus_entries`, `knowledge_items`, `knowledge_triples`, `settings`
- **i_weight**: κ-Gate 语义剪枝权重列，范围 [1.0, ~3.0]
- **原始 CSV**: `D:/ownthink_v2/ownthink_v2.csv`（~140M 行）

## 测试
- 前端: `deepseek-chat/src/test/Toast.test.tsx` — Vitest + RTL，4/4 通过
- 后端: `tomas_agi/tests/test_token_bridge.py` — pytest，7/7 通过
- Python 测试: 系统 Python 3.10 + pytest

## 前端功能模块 (deepseek-chat/)
- 置信度反馈: MessageBubble 显示 `📡 EML路由 · XX%` 标签 + 👍/👎 互斥按钮
- 知识冲突检测: DistillPanel 蒸馏完成后检测同领域语料重叠 → 用户四选一决策 (保留旧/保留新/合并/忽略)
- 冲突决策持久化: `tomas_conflict_decisions` localStorage key
- 语料列表: `tomas_corpus_entries` localStorage 持久化

## 常用命令
```bash
# 蒸馏
python llm_distiller.py --distill data/physics.txt --output data/physics_distilled.eml --api-key sk-xxx

# 推理（自动路由）
python token_bridge.py --load data/physics_distilled.eml --concepts data/physics_distilled.concepts.json --query "xxx" --llm --api-key sk-xxx

# 前端
cd deepseek-chat && npm run dev
```
