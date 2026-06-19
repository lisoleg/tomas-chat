# TOMAS/太极OS 项目记忆

## 架构
- **V3 (当前):** "翻译官 + 作家" 混合架构，v3.4
  - 翻译官: LSTM/模板 → 事实性查询（EML 图检索→精确回答）
  - 作家: DeepSeek LLM → 创造性查询（带 EML 上下文 + φ-Gate 监管）
  - 路由: 置信度 ≥0.5 → 翻译官，<0.5 → 作家
- Python 入口: `tomas_agi/sim/token_bridge.py`
- 前端: `deepseek-chat/` (Vite + React + TypeScript)
- Dashboard 设计稿: `tomas-dashboard/index.html` (9页面, 深色主题)

## sim/ 模块分类 (79 .py 文件)
- **核心数学**: nasga_core, octonion_py, spectral_laplacian_py, xi_c_measure, fold_depth_py, nasga_octonion
- **Token Bridge**: token_bridge, token_generator, llm_distiller, eml_injector, router
- **数据层**: models, server(Flask 56端点), batch_import, import_ownthink_sqlite, resume_import, compute_i_weight, post_import
- **EML降维**: eml_dimred/ (hyperedge, matroid, gpct, itc, brown_miklos, strf, pipeline)
- **MemOS**: memos_fusion, memos_integration, psi_anchor, contradiction_detector
- **Dead-Zero/MUS**: dead_zero_mus, quantum_dead_zero, spatial_dead_zero
- **DIKWP**: dikwp_mapper, semantic_math, dikwp_ac, dikwp_eml_bridge, agent_audit
- **桥接模块**: causet_bridge, hyworld_bridge, ido_bridge, fde_builder, dual_timeline, itot_bridge, palantir_mapper
- **安全审计**: semantic_firewall, scada_daap, hodge_operator
- **T-Processor/T-Shield**: tprocessor_sim, tshield_wrapper, processor_tshield_integration, tproc_if, sai_tproc, t_shield_anydepth, heuristic_learn
- **公理体系v2**: g_ego, epiplexity_engine, eml_semzip, ksnap_operator, extend_hypergraph, nau_liu_mechanism, dual_chain_consensus, eml_hardware_codesign, harness_aegis
- **评估框架**: arc_agi3_eval, arc_api_client, swe_bench_eval, gaia_eval, gaia_fetcher, tcci_huashan_test
- **其他**: tomas_sim, extract_pdf_text, uscs_fs_test, demo_memos, adc_test, test_tcci_livis, drift_detector, a6_bs_benchmark, delta_mem_py

## RTL 代码 (tomas_agi/rtl/)
- Dead-Zone 比较器阵列, MUS 相似度引擎, AXI4-Lite 从设备, BRAM 阈值存储
- NASGA: octonion_mul.v, delta_compute.v, spectral_engine.v
- Vivado 自动化脚本 (Zynq-7020), PS 端 C HAL

## 数据库
- **路径**: `D:/tomas-data/tomas.db`（SQLite）
- **knowledge_triples**: ~86M 行（OwnThink 导入进行中，原始CSV ~140M行）
- **Schema**: 7 张表 — api_keys, chat_sessions, conflict_decisions, corpus_entries, knowledge_items, knowledge_triples, settings
- **i_weight**: κ-Gate 语义剪枝权重列，NOT NULL DEFAULT 1.0，导入完成后需运行 compute_i_weight.py

## API 配置
- DeepSeek API Key: `tomas_agi/sim/.env` 或环境变量 `DEEPSEEK_API_KEY`
- Git SSH: `git@github.com:lisoleg/tomas-agi.git` / `git@github.com:lisoleg/tomas-chat.git`

## 测试
- 后端 pytest: **727 passed + 2 skipped, 0 failed** (20 test files, 729 test functions)
- 前端 Vitest: 17/17 + 16/16 (distillCache) 通过
- Flask 端点: 14/14 通过 (test_endpoints.py)
- venv: Python 3.13 + pytest (从 `tomas_agi/` 上级目录运行)

## 前端功能模块 (deepseek-chat/)
- 仪表盘/世界模型(Three.js)/审计监控/记忆浏览器/防火墙路由/聊天/蒸馏/文档
- IDO桥接/FDE本体/双时间维度/IT-OT翻译 (2026-06-16新增)
- T-Processor/T-Shield 面板 (真实API接入)
- 导航: 侧边栏三区，12+ 面板切换

## 常用命令
```bash
# 蒸馏
python llm_distiller.py --distill data/physics.txt --output data/
# 推理
python token_bridge.py --load data/physics_distilled.eml --concepts data/physics_distilled.concepts.json --query "xxx" --llm
# 测试
pytest tests/ -v
# OwnThink 断点续传导入
python resume_import.py --skip 80000000
# i_weight 后计算
python compute_i_weight.py [--recalculate]
```

## 遗留事项
- OwnThink 导入完成后运行 compute_i_weight.py
- ARC-AGI-3 真实数据集需 ARC_API_KEY
- GAIA 真实数据集需 HUGGINGFACE_TOKEN

## 2026-06-19 HarnessX + AEGIS 升级
- 参考：微信公众号文章《HarnessX作为太乙互搏 AGI 具身壳与 PG-Gate 可编程接口》
- 新建 sim/harness_aegis.py：TOMAS_HarnessEdge / AEGISEngine / VariantIsolationManager / KSnapDualRail / CausalLog
- eml_semzip.py 集成：EMLiteKB 添加 harness_edges 字典 + add/revise 方法
- 集成测试 6/6 通过
- ✅ extend_hypergraph.py：添加 GroundingCheck() 方法（std_ref + ψ-alignment 校验）
- ✅ tshield_wrapper.py：添加 check_std_ref() 和 validate_psi_alignment() 方法
- 遗留：g_ego.py 集成 ψ-alignment 检查；Flask 重启；运行 post_import.py
