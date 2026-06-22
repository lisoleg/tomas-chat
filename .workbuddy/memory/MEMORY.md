# TOMAS/太极OS 项目记忆

## 架构 (v3.12)
- **"翻译官 + 作家" 混合架构**: 翻译官(LSTM/模板→事实查询) + 作家(DeepSeek LLM→创造性查询), 路由置信度≥0.5
- Python入口: `tomas_agi/sim/token_bridge.py` | 前端: `deepseek-chat/` (Vite+React+TS)
- Dashboard: `tomas-dashboard/index.html` (9页面, 深色主题)

## sim/ 模块分类 (97+ .py 文件)
- **核心数学**: nasga_core, octonion_py, spectral_laplacian_py, xi_c_measure, fold_depth_py, nasga_octonion
- **Token Bridge**: token_bridge, token_generator, llm_distiller, eml_injector, router
- **数据层**: models, server(Flask 165端点), batch_import, import_ownthink_sqlite, resume_import, compute_i_weight
- **EML降维**: eml_dimred/ (hyperedge, matroid, gpct, itc, brown_miklos, strf, pipeline)
- **MemOS**: memos_fusion, memos_integration, psi_anchor, contradiction_detector
- **Dead-Zero/MUS**: dead_zero_mus, quantum_dead_zero, spatial_dead_zero
- **DIKWP**: dikwp_mapper, semantic_math, dikwp_ac, dikwp_eml_bridge, agent_audit
- **安全审计**: semantic_firewall, scada_daap, hodge_operator
- **T-Processor/T-Shield**: tprocessor_sim, tshield_wrapper, sai_tproc, t_shield_anydepth
- **公理体系v2**: g_ego, epiplexity_engine, eml_semzip, ksnap_operator, extend_hypergraph, harness_aegis
- **评估框架**: arc_agi3_eval, swe_bench_eval, gaia_eval, tcci_huashan_test
- **v3.9**: babeltele_compressor, hypergraph_categories, kernelcat_scheduler, constitutional_agi
- **v3.10**: alignment_triad, goal_directed_agent
- **v3.11**: cognitive_health, grill_me_engine
- **v3.12**: luzhao_dna, gat_axioms, financial_world_model, tokenized_economy (Flask 25端点 + 前端4面板)

## v3.11 升级 (2026-06-22, 2新模块+6测试文件+10端点+2前端面板)
- 参考: 双引擎成瘾模型 + grill-me需求审问 (微信公众号文章)
- **sim/cognitive_health.py** (1550行, 104 self-test): 双引擎成瘾模型(Must-Do/Feel-Better), Gan偏误惩罚, 习惯回路检测(≥3 κ-Snap→MUS反思), HealthAgentState状态机(NORMAL/BIAS_WARNING/MUS_REFLECTION/PAUSED), ALLOWED_REPEAT_PATTERNS白名单, CognitiveHealthTheorem, FalsifiablePredictions
- **sim/grill_me_engine.py** (1954行, 135 self-test): DIKWPGapAnalyzer(D/I/K/W/P五层缺口), GrillExecutionGate(全缺口关闭检查), RequirementTracer(κ-Snap链+SHA-256防篡改), PsiNoSilentAssumption(LLM脑补检测)
- **集成**: alignment_triad.py (+cognitive_health阶段), goal_directed_agent.py (+grill_interrogate非阻塞模式)
- **Flask**: +10 /api/v3/* → 140 endpoints (4 cognitive-health + 6 grill-me)
- **前端**: CognitiveHealthPanel.tsx + GrillMePanel.tsx, 2新图标, TS零错误
- **测试**: 155 tests (51+46+15+16+8+14), 全量回归603/603 passed (v3.7-v3.11)
- **Bug修复**: ①循环导入(cognitive_health→alignment_triad, 删除未使用import) ②gate-status属性名错误(_gates→_registry) ③grill_precheck阻断v3.10(改为非阻塞模式)
- Commit: 待推送

## v3.12 升级 (2026-06-22, 4新模块+148自测)
- 参考4篇微信公众号文章: 代币化市场经济/TOMAS v2.0流体智能/GAT公理体系/金融市场鲁兆现象
- **sim/luzhao_dna.py**: 鲁兆DNA基因库(斐波那契/鲁加斯/八卦数拓扑不变量, 35 self-test)
- **sim/gat_axioms.py**: GAT广义代数理论(GATTheory/ArcDSL_GAT/OctonionGAT, 30 self-test)
- **sim/financial_world_model.py**: 金融市场世界模型(LOB/做市商/滑点相位/ENPV/熔断, 17 self-test)
- **sim/tokenized_economy.py**: 代币化经济(Token/AgentEconomy/HomoEconomicus2Agent, 66 self-test)
- **Bug修复**: ①gat_axioms is_associative()忽略符号比较 ②tokenized_economy _self_test()为中文非代码,重写66测试 ③T12/T61断言边界值
- 全量pytest: 1368 passed, 2 skipped, 0 failed
- Flask API: +25 端点 (luzhao 5 + gat 6 + financial 7 + tokenized 7)
- 前端集成: 4个新面板 (LuZhaoPanel/GATPanel/FinancialWorldPanel/TokenizedEconomyPanel)
- Commit: 待推送
- 路径: `D:/tomas-data/tomas.db` (SQLite)
- knowledge_triples: 101,590,276行 (101.6M, OwnThink导入可能仍在进行)
- i_weight: 已全部计算完成 (compute_i_weight_v8.py, 耗时978s, 9.6M subjects)

## 测试
- 后端 pytest: 1,368 passed, 2 skipped (v3.6:+57, v3.7:+108, v3.8:+110, v3.9:+116, v3.10:+114, v3.11:+155)
- v3.7-v3.11 联合回归: 603/603 passed
- v3.12 自测: 148 tests (35+30+17+66) all passed
- 前端 Vitest: 17/17 + 16/16 通过
- 前端 TypeScript: tsc --noEmit 零错误 (v3.12集成后)
- Flask 端点: 165 endpoints (140 + 25 v3.12新增)
- venv: Python 3.13 + pytest (从 `tomas_agi/` 目录运行)

## 前端功能模块 (deepseek-chat/)
- 仪表盘/世界模型(Three.js)/审计监控/记忆浏览器/防火墙路由/聊天/蒸馏/文档
- T-Processor/T-Shield/IDO桥接/FDE本体/双时间维度/IT-OT翻译
- AlignmentTriad/GoalAgent/CognitiveHealth/GrillMe 面板
- v3.12: LuZhaoDNA/GATAxioms/FinancialWorld/TokenizedEconomy 面板
- 导航: 侧边栏四区，18+ 面板切换

## 历史版本摘要
- v3.6 (06-21): 8模块+57测试, ψ-Gate/EML本体/解释坩埚/WM超边/DIKWP桥接/太极周期/MNQ冻结核/治疗师
- v3.7 (06-22): 3模块+108测试, HTD仿真/拓扑孤子/Gan-PGW
- v3.8 (06-22): 2模块+110测试, GaussEx-EML/认知压缩
- v3.9 (06-22): 4模块+116测试, BabelTele/超图范畴/KernelCAT/Constitutional AI
- v3.10 (06-22): 2模块+114测试, 对齐三范式/Goal-Directed Agent
- v2.0 (06-20): 14新建+8修改, HNC NLU/哥德尔智能体/因果世界模型/AgentWeb/Mina/Celo/EML-EHNN

## API配置
- DeepSeek API Key: `tomas_agi/sim/.env` 或环境变量 `DEEPSEEK_API_KEY`
- Git: `git@github.com:lisoleg/tomas-agi.git` / `git@github.com:lisoleg/tomas-chat.git`

## RTL代码 (tomas_agi/rtl/)
- Dead-Zone比较器, MUS相似度引擎, AXI4-Lite从设备, BRAM阈值存储
- NASGA: octonion_mul.v, delta_compute.v, spectral_engine.v (Zynq-7020)

## 遗留事项
- v3.9-v3.12 已 git commit + push 完成 (commit 1691907 + 1e14e03)
- ARC-AGI-3 真实数据集需 ARC_API_KEY
- GAIA 真实数据集需 HUGGINGFACE_TOKEN
- 前端新面板单元测试待补充
- LOB会话持久化(当前内存存储,重启丢失)
