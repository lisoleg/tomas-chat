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
- `eml_dimred/` — **数学降维工具箱（2026-06-15 新增）**
  - `hyperedge.py` — HypEdge/EMLVertex + EML 加载
  - `matroid.py` — 拟阵贪心剪枝（κ-Gate 最优独立集）
  - `gpct.py` — GPCT 边界层分解（FPT 判定）
  - `itc.py` — ITC 虚时退火（Wick 旋转基态搜索）
  - `brown_miklos.py` — Brown-Miklós FPT 度类压缩
  - `strf.py` — STR-F 四大等价变换
  - `pipeline.py` — slim_eml 四合一流水线
- `distiller.ts` — 前端 TokenBridgeClient + EML 加载/序列化
- `DistillPanel.tsx` — 蒸馏 UI + Token Bridge 推理面板
- `EMLGraphVisualization.tsx` — D3.js 力导向图
- `router.py` — **TOMAS Router 多模型路由器（2026-06-15 新增）**
- `eml_injector.py` — **EML 执行上下文注入器 v2.0（2026-06-15 新增）**
- `model_pool.json` — 12 家开源模型池配置
- `dead_zero_mus.py` — **死零/MUS/κ-Snap 机制（2026-06-16 新增）**
- `nasga_octonion.py` — **NASGA 八元数运算模块（2026-06-16 新增）**
- `tcci_huashan_test.py` — TCCI-华山测试 v1 独立运行器
- `memos_fusion.py` — **TOMAS-MemOS 融合层（五点升维 + ContradictionDetector 集成，2026-06-16）**
- `psi_anchor.py` — ψ-锚数据结构与管理器
- `memos_integration.py` — Token Bridge 集成包装器
- `contradiction_detector.py` — 三层矛盾检测器（否定词/NLP/EML）
- `dikwp_mapper.py` — **DIKWP 五层映射器**
- `semantic_math.py` — 语义数学运算
- `dikwp_ac.py` — 人工意识（AC）模块
- `agent_audit.py` — DAAP 审计代理
- `dikwp_eml_bridge.py` — DIKWP↔EML 桥接
- `causet_bridge.py` — **Wolfram超图↔EML桥接（DPO死零守卫 + ℐ-Sprinkling，2026-06-16）**
- `hodge_operator.py` — TOMAS-WSC融合算子 L+λΠ
- `semantic_firewall.py` — 输入/输出语义防火墙（6 ADC高风险模式）
- `palantir_mapper.py` — 本体→EML超图映射（4阶Palantir流水线）
- `scada_daap.py` — 真实SCADA环境DAAP审计
- `hyworld_bridge.py` — **HY World 2.0 四阶段管道↔TOMAS EML桥接（2026-06-16）**
- `sai_tproc.py` — **T-Processor 后审计层（Dead-Zero/MUS/G_ego，2026-06-16）**
- `spatial_dead_zero.py` — **3D几何物理接地审计（GravityValidator/SpatialMUS/IotaLoss，2026-06-16）**

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
- 前端: `deepseek-chat/src/test/` — Vitest + RTL，17/17 通过
- 后端: `tomas_agi/tests/` — pytest，**366 passed + 2 skipped（需要 API Key），0 failed**
  - `test_token_bridge.py`: 8 passed
  - `test_eml_dimred.py`: 20 passed
  - `test_router.py`: 27 passed
  - `test_tcci.py`: 15 passed
  - `test_nasga.py`: 17 passed
  - `test_memos.py`: 16 passed
  - `test_contradiction.py`: 19 passed
  - `test_causet_wsc.py`: 57 passed
  - `test_hyworld_sai.py`: 76 passed
  - DIKWP/AC 测试: 54 passed
- Python 测试: 系统 Python 3.10 + pytest

## 前端功能模块 (deepseek-chat/)
- **仪表盘 (Dashboard)**: 8 子系统状态卡片 + 活动时间线 + 面板跳转
- **世界模型 (WorldModelViewer)**: Three.js 3D 场景查看器 — DIKWP 颜色映射 + ℐ值球体大小 + 死零灰色半透明 + 空间边
- **审计监控 (AuditMonitor)**: T-Proc 死零审计 / Spatial Dead-Zero / G_ego 三标签
- **记忆浏览器 (MemoryBrowser)**: MemOS 记忆记录搜索 + ψ-锚详情 + MUS 双存指示
- **防火墙·路由 (LogsAndRouterPanel)**: 语义防火墙日志 + 12 模型路由器双标签
- **聊天 (ChatArea)**: 保留，支持 EML 路由 + 太乙互博推理链路
- **蒸馏 (DistillPanel)**: 保留，LLM 蒸馏 + 冲突检测 + 图谱 + DIKWP 饼图
- **文档 (TechDocs)**: 保留，TOMAS 技术文档
- 置信度反馈: MessageBubble 显示 `📡 EML路由 · XX%` 标签 + 👍/👎 互斥按钮
- 知识冲突检测: DistillPanel 蒸馏完成后检测同领域语料重叠 → 用户四选一决策
- 冲突决策持久化: `tomas_conflict_decisions` localStorage key
- 语料列表: `tomas_corpus_entries` localStorage 持久化
- **导航**: 侧边栏分三区（核心功能/TOMAS监控/信息），8 面板切换
- **依赖新增**: three + @types/three (3D 渲染)

## 常用命令
```bash
# 蒸馏
python llm_distiller.py --distill data/physics.txt --output data/physics_distilled.eml --api-key sk-xxx

# 推理（自动路由）
python token_bridge.py --load data/physics_distilled.eml --concepts data/physics_distilled.concepts.json --query "xxx" --llm --api-key sk-xxx

# 推理 + 数学降维
python token_bridge.py --load data/physics_distilled.eml --concepts data/physics_distilled.concepts.json --dimred --query "xxx" --llm --api-key sk-xxx

# 数学降维（独立运行）
python -m eml_dimred.pipeline --eml data/physics_distilled.eml --concepts data/physics_distilled.concepts.json

# 前端
cd deepseek-chat && npm run dev

# 测试
pytest tests/ -v
```
