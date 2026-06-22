# TOMAS AGI v2.0 — REST API 文档

> **版本**: v2.1 (编排层 + 分页 API) | **日期**: 2026-06-23
> **Base URL**: `http://localhost:5000/api/v2`

---

## 目录

1. [HNC NLU 管道](#1-hnc-nlu-管道)
2. [哥德尔智能体](#2-哥德尔智能体)
3. [向量时钟 + 因果交付](#3-向量时钟--因果交付)
4. [AgentWeb 分布式 + Fediverse](#4-agentweb-分布式--fediverse)
5. [密码学桥接（Mina + Celo）](#5-密码学桥接mina--celo)
6. [因果世界模型 + Aether + EHNN](#6-因果世界模型--aether--ehnn)
7. [通用错误格式](#7-通用错误格式)
8. [多智能体编排 API](#8-多智能体编排-api)
9. [分页 API 规范](#9-分页-api-规范)

---

## 1. HNC NLU 管道

基于 HNC（概念层次网络）24 字母概念基元编码体系，将自然语言文本解析为 EML 超边 Schema。

### 1.1 POST `/api/v2/nlu/parse`

HNC NLU 七步管道：HNC 编码 → 句类模板匹配 → ℐ 估值 → ψ 对齐 → κ-Snap → GPCT 检测 → EML 超边输出。

**请求体**
```json
{
  "text": "string (required) — 待解析的中文文本"
}
```

**响应**
```json
{
  "success": true,
  "data": {
    "template_id": "string — 匹配到的 HNC 句类模板 ID（如 'BCL.DEFAULT'）",
    "chunks": ["array<string> — 分词结果"],
    "concept_codes": ["array<string> — HNC 24 字母概念编码（如 'A.b01'）"],
    "cited_rule": "string — 触发的 HNC 规则名称",
    "i_value": 0.85,
    "psi_alignment_status": "ALIGNED | MISALIGNED | UNKNOWN",
    "snap_id": "string — κ-Snap 事件 ID",
    "gpct_emergence_detected": false,
    "gpct_new_dim": 0
  }
}
```

**错误响应**
```json
{ "success": false, "error": "NLU module not available" }  // HTTP 503
{ "success": false, "error": "text is required" }       // HTTP 400
```

**示例**
```bash
curl -X POST http://localhost:5000/api/v2/nlu/parse \
  -H "Content-Type: application/json" \
  -d '{"text": "人工智能改变世界"}'
```

---

### 1.2 GET `/api/v2/nlu/stats`

返回 NLU 管道的运行统计（处理文本数、平均 ℐ 值、GPCT 触发次数）。

**响应**
```json
{
  "success": true,
  "data": {
    "total_parsed": 128,
    "avg_i_value": 0.7823,
    "gpct_triggers": 3,
    "template_hit_count": {"BCL.DEFAULT": 45, "...": "..."}
  }
}
```

---

## 2. 哥德尔智能体

四重封边机制：PG-囚禁硬锚否决权 → 沙箱验收 → ℐ 贝叶斯评估 → MUS 双存冲突代码分支。

### 2.1 POST `/api/v2/godel/improve`

触发哥德尔智能体自改进循环（四重封边评估）。

**请求体**
```json
{
  "observation": "string (required) — 智能体观察到的环境反馈或任务描述"
}
```

**响应**
```json
{
  "success": true,
  "data": {
    "code_hash": "string — 生成代码的 SHA-256 哈希",
    "pg_result": "string — PG-囚禁评估结果",
    "i_value": 0.82,
    "mus_entry": {"tag": "...", "code_a": "...", "code_b": "..."},
    "snap_id": "string — κ-Snap 审计 ID",
    "passed": true
  }
}
```

---

### 2.2 GET `/api/v2/godel/status`

查询哥德尔智能体当前状态（H_HARD 符号集、当前 ℐ 值、MUS 双存库）。

**响应**
```json
{
  "success": true,
  "data": {
    "h_hard_symbols": ["string", "..."],
    "current_i": 0.85,
    "mus_store": [
      {"tag": "optimization_v1", "code_hash_a": "...", "code_hash_b": "...", "prefer": "A"}
    ]
  }
}
```

---

### 2.3 POST `/api/v2/godel/mus/resolve`

裁决 MUS（Mutually Unsure Set）双存条目，选择保留哪个冲突代码分支。

**请求体**
```json
{
  "tag": "string (required) — MUS 条目标签",
  "prefer_new": true
}
```

**响应**
```json
{
  "success": true,
  "data": {
    "tag": "optimization_v1",
    "selected": "A",
    "reason": "string — 裁决理由"
  }
}
```

---

## 3. 向量时钟 + 因果交付

分布式 Agent 时序一致性：向量时钟因果顺序检测 + 因果交付缓冲（级联解锁）。

### 3.1 POST `/api/v2/vector-clock/tick`

推进本地向量时钟（处理本地事件前调用）。

**请求体**
```json
{
  "node_id": "string (required) — 本节点 ID"
}
```

**响应**
```json
{
  "success": true,
  "data": {
    "node_id": "agent-001",
    "clock": {"agent-001": 3, "agent-002": 1}
  }
}
```

---

### 3.2 POST `/api/v2/vector-clock/compare"`

比较两个向量时钟的因果关系（happened-before / concurrent）。

**请求体**
```json
{
  "clock_a": {"agent-001": 2, "agent-002": 1},
  "clock_b": {"agent-001": 3, "agent-002": 1}
}
```

**响应**
```json
{
  "success": true,
  "data": {
    "happened_before": true,
    "concurrent": false,
    "relation": "A → B"
  }
}
```

---

### 3.3 POST `/api/v2/causal-delivery/deliver"`

向因果交付缓冲提交消息（自动按因果顺序级联解锁）。

**请求体**
```json
{
  "message_id": "string (required)",
  "sender": "string (required)",
  "sender_clock": {"agent-001": 3},
  "payload": {"type": "observation", "data": "..."}
}
```

**响应**
```json
{
  "success": true,
  "data": {
    "message_id": "msg-042",
    "delivered": true,
    "pending_count": 0
  }
}
```

---

### 3.4 GET `/api/v2/causal-delivery/pending"`

查询当前因果交付缓冲中待解锁的消息列表。

**响应**
```json
{
  "success": true,
  "data": {
    "pending": [
      {"message_id": "msg-043", "waiting_for": ["msg-042"]}
    ],
    "count": 1
  }
}
```

---

## 4. AgentWeb 分布式 + Fediverse

AgentWeb 运行时（G_ego + 因果检查 + κ-Snap 日志）+ Fediverse/ActivityPub 桥接。

### 4.1 POST `/api/v2/agentweb/send"`

通过 AgentWeb 运行时发送消息（自动附加向量时钟 + κ-Snap 日志）。

**请求体**
```json
{
  "sender": "string (required) — 发送者 Agent ID",
  "receiver": "string (required) — 接收者 Agent ID",
  "content": "string (required) — 消息内容"
}
```

**响应**
```json
{
  "success": true,
  "data": {
    "message_id": "aw-001-msg-007",
    "sender_clock": {"aw-001": 5, "aw-002": 2},
    "snap_id": "snap_20260620_143022"
  }
}
```

---

### 4.2 POST `/api/v2/agentweb/receive"`

Agent 接收消息（因果检查 + 向量时钟合并）。

**请求体**
```json
{
  "agent_id": "string (required) — 接收 Agent ID",
  "message_id": "string (required)"
}
```

**响应**
```json
{
  "success": true,
  "data": {
    "message_id": "aw-001-msg-007",
    "content": "...",
    "sender_clock": {"aw-001": 5, "aw-002": 2},
    "causal_ready": true
  }
}
```

---

### 4.3 GET `/api/v2/agentweb/status"`

查询 AgentWeb 运行时状态（在线 Agent 列表、消息队列长度）。

**响应**
```json
{
  "success": true,
  "data": {
    "agents": ["aw-001", "aw-002"],
    "queue_length": 3,
    "total_messages": 128
  }
}
```

---

### 4.4 POST `/api/v2/fediverse/send"`

通过 Fediverse（ActivityPub 协议）向外部实例发送消息。

**请求体**
```json
{
  "from": "string (required) — 发送者 Fediverse ID（如 '@alice@instance.social'）",
  "to": "string (required) — 接收者 Fediverse ID",
  "content": "string (required) — 消息内容（支持 Markdown）"
}
```

**响应**
```json
{
  "success": true,
  "data": {
    "activity_id": "https://instance.social/activities/123",
    "delivered": true
  }
}
```

---

### 4.5 POST `/api/v2/fediverse/receive"`

接收 Fediverse 外部实例推送的消息（ActivityPub inbox 模拟）。

**请求体**
```json
{
  "activity": {
    "type": "Create",
    "actor": "https://remote.social/users/bob",
    "object": {"type": "Note", "content": "..."}
  }
}
```

**响应**
```json
{
  "success": true,
  "data": {
    "accepted": true,
    "activity_id": "https://remote.social/activities/456"
  }
}
```

---

### 4.6 GET `/api/v2/fediverse/stats"`

查询 Fediverse 桥接统计（关注数、发文数、接收消息数）。

**响应**
```json
{
  "success": true,
  "data": {
    "following": 12,
    "followers": 5,
    "posts_sent": 48,
    "messages_received": 23
  }
}
```

---

## 5. 密码学桥接（Mina + Celo）

Mina SNARK 递归证明（22KB 恒定大小，降级 SHA-256）+ Celo 稳定币支付（cUSD/cEUR，BLS 聚合签名）。

### 5.1 POST `/api/v2/mina/wrap-snap"`

将 κ-Snap 事件包装为 Mina SNARK 递归证明（目标 22KB 证明大小）。

**请求体**
```json
{
  "snap_event": {
    "snap_id": "string (required)",
    "timestamp": "string (required)",
    "event_type": "string (required)",
    "payload": {"...": "..."},
    "i_weight": 0.85
  }
}
```

**响应**
```json
{
  "success": true,
  "data": {
    "snap_id": "snap_20260620_143022",
    "proof_hash": "a1b2c3d4...",
    "proof_size_bytes": 22528,
    "generation_time": 1.23,
    "is_degraded": false
  }
}
```

> **降级说明**：若 `mina-sdk` 未安装，自动降级为本地 SHA-256 哈希，此时 `is_degraded: true`，`proof_size_bytes` 为 32。

---

### 5.2 POST `/api/v2/mina/verify"`

验证 Mina SNARK 证明的有效性。

**请求体**
```json
{
  "snap_id": "string (required)",
  "proof_hash": "string (required)",
  "proof_size_bytes": 22528,
  "is_degraded": false
}
```

**响应**
```json
{
  "success": true,
  "data": {
    "verified": true
  }
}
```

---

### 5.3 GET `/api/v2/mina/stats"`

查询 Mina 桥接统计（生成证明数、验证次数、平均证明大小）。

**响应**
```json
{
  "success": true,
  "data": {
    "proofs_generated": 42,
    "proofs_verified": 42,
    "avg_proof_size_bytes": 22528,
    "degraded_count": 0
  }
}
```

---

### 5.4 POST `/api/v2/celo/pay"`

发起 Celo 稳定币支付（cUSD 或 cEUR，BLS 聚合签名）。

**请求体**
```json
{
  "from_address": "string (required) — 付款方 Celo 地址",
  "to_address": "string (required) — 收款方 Celo 地址",
  "amount": "number (required) — 支付金额",
  "currency": "cUSD | cEUR (default: cUSD)",
  "private_key": "string (optional) — 付款方私钥（服务端签名时用）"
}
```

**响应**
```json
{
  "success": true,
  "data": {
    "tx_hash": "0xabc123...",
    "amount": 10.5,
    "currency": "cUSD",
    "block_number": 12345678,
    "confirmations": 1
  }
}
```

> **RPC 超时降级**：若 Celo RPC 节点 3 秒内无响应，自动跳过链上广播，返回 `degraded: true` 并生成本地收据。

---

### 5.5 POST `/api/v2/celo/verify"`

验证 Celo 交易的有效性（检查链上确认数）。

**请求体**
```json
{
  "tx_hash": "string (required)",
  "confirmations_required": 1
}
```

**响应**
```json
{
  "success": true,
  "data": {
    "tx_hash": "0xabc123...",
    "confirmed": true,
    "confirmations": 12
  }
}
```

---

### 5.6 GET `/api/v2/celo/balance"`

查询 Celo 账户余额（cUSD + cEUR）。

**Query 参数**
```
?address=0xabc...
```

**响应**
```json
{
  "success": true,
  "data": {
    "address": "0xabc...",
    "cUSD": 123.45,
    "cEUR": 67.89
  }
}
```

---

## 6. 因果世界模型 + Aether + EHNN

SCM do-calculus 因果推理 + Aether 因果编码 + EML-EHNN 等变超图神经网络。

### 6.1 POST `/api/v2/world-model/learn"`

从数据学习 SCM（结构因果模型），编码为 EML 超边。

**请求体**
```json
{
  "data": [
    {"X": 1.2, "Y": 3.4, "Z": 5.6},
    {"...": "..."}
  ],
  "variables": ["X", "Y", "Z"],
  "target": "Y"
}
```

**响应**
```json
{
  "success": true,
  "data": {
    "scm_id": "scm_20260620_143022",
    "adjacency": {"X": ["Y"], "Y": ["Z"]},
    "do_support": true,
    "hard_constraints": ["energy_conservation"]
  }
}
```

---

### 6.2 POST `/api/v2/world-model/predict"`

在给定 SCM 上执行预测（支持干预 do(X=x)）。

**请求体**
```json
{
  "scm_id": "string (required)",
  "intervention": {"X": 2.0},
  "query": {"Y": "mean"}
}
```

**响应**
```json
{
  "success": true,
  "data": {
    "scm_id": "scm_20260620_143022",
    "intervention": {"X": 2.0},
    "prediction": {"Y": 4.20},
    "confidence": 0.91
  }
}
```

---

### 6.3 POST `/api/v2/world-model/counterfactual"`

计算反事实推断（"如果 X 不同，Y 会怎样？"）。

**请求体**
```json
{
  "scm_id": "string (required)",
  "factual": {"X": 1.0, "Y": 3.0},
  "counterfactual_intervention": {"X": 2.0}
}
```

**响应**
```json
{
  "success": true,
  "data": {
    "factual": {"X": 1.0, "Y": 3.0},
    "counterfactual": {"X": 2.0, "Y": 4.2},
    "contrastive_delta": 1.2
  }
}
```

---

### 6.4 GET `/api/v2/aether/scm/summary"`

返回 Aether 桥接的 SCM 摘要（变量列表、因果边、硬约束）。

**响应**
```json
{
  "success": true,
  "data": {
    "variables": ["X", "Y", "Z"],
    "edges": [{"from": "X", "to": "Y", "type": "directed"}],
    "hard_constraints": ["energy_conservation", "momentum_conservation"],
    "confounders_detected": []
  }
}
```

---

### 6.5 GET `/api/v2/aether/scm/confounders"`

检测 SCM 中的混淆因子（后门路径）。

**响应**
```json
{
  "success": true,
  "data": {
    "confounders": [
      {"path": "X ← U → Y", "type": "backdoor", "adjustment_set": ["U"]}
    ]
  }
}
```

---

### 6.6 POST `/api/v2/ehnn/forward"`

EML-EHNN 等变超图神经网络前向传播（ℐ(e) 加权超边 + MUS-Aware Pooling）。

**请求体**
```json
{
  "hyperedge_features": [
    {"vertices": [0, 1, 2], "feature": [0.1, 0.2, ...], "i_weight": 0.85}
  ],
  "target_dim": 128
}
```

**响应**
```json
{
  "success": true,
  "data": {
    "output": [[0.12, 0.34, ...]],
    "kappa_snap_loss": 0.023,
    "mus_aware_dropout_rate": 0.1
  }
}
```

---

### 6.7 POST `/api/v2/ehnn/expand-dim"`

触发 GPCT 动态输出维度扩展（层创涌现检测）。

**请求体**
```json
{
  "current_dim": 128,
  "emergence_signal": 0.92
}
```

**响应**
```json
{
  "success": true,
  "data": {
    "old_dim": 128,
    "new_dim": 192,
    "expansion_ratio": 1.5,
    "gpct_trigger": true
  }
}
```

---

## 7. 知识图谱统计

### 7.1 GET `/api/v2/knowledge/stats`（注：实际路径为 `/api/knowledge/stats`）

返回知识图谱全库真实统计（不依赖于分页子集）。

**响应**
```json
{
  "success": true,
  "cached": false,
  "data": {
    "tripleCount": 101590276,
    "conceptCount": 15358857,
    "predicateCount": 423185,
    "avgIWeight": 1.2165,
    "dbPath": "D:/tomas-data/tomas.db",
    "source": "knowledge_triples"
  }
}
```

> **缓存策略**：首次请求触发全表统计（约 20s），结果写入 `D:/tomas-data/knowledge_stats.json`。后续请求毫秒级返回缓存数据，5 分钟自动刷新。

---

## 8. 多智能体编排 API

Fugu Conductor 编排引擎（`sim/orchestrator.py`）提供多智能体任务编排能力：自适应任务分解（DAG 拓扑排序）、Agent 注册表管理、任务状态机（PENDING → RUNNING → COMPLETED/FAILED）。

### 8.1 GET `/api/orchestrator/agents`

查询已注册的 Agent 列表（含能力标签、状态、当前负载）。

**响应**
```json
{
  "success": true,
  "data": {
    "agents": [
      {
        "agent_id": "agent-001",
        "name": "Translator Agent",
        "capabilities": ["nlu", "translation", "summarization"],
        "status": "idle",
        "current_tasks": 0,
        "max_concurrent": 3,
        "registered_at": "2026-06-23T10:00:00Z"
      },
      {
        "agent_id": "agent-002",
        "name": "Writer Agent",
        "capabilities": ["creative_writing", "reasoning"],
        "status": "busy",
        "current_tasks": 2,
        "max_concurrent": 3,
        "registered_at": "2026-06-23T10:05:00Z"
      }
    ],
    "total_agents": 2,
    "idle_agents": 1,
    "busy_agents": 1
  }
}
```

---

### 8.2 POST `/api/orchestrator/orchestrate`

提交编排任务，Fugu Conductor 自动分解为 DAG 子任务图并调度执行。

**请求体**
```json
{
  "task_description": "string (required) — 自然语言任务描述",
  "preferred_agents": ["agent-001", "agent-002"],
  "priority": "low | normal | high (default: normal)",
  "max_retries": 3,
  "timeout_seconds": 300
}
```

**响应**
```json
{
  "success": true,
  "data": {
    "task_id": "task-20260623-001",
    "status": "RUNNING",
    "dag": {
      "nodes": [
        {"id": "subtask-1", "name": "解析任务", "status": "COMPLETED", "agent_id": "agent-001"},
        {"id": "subtask-2", "name": "生成方案", "status": "RUNNING", "agent_id": "agent-002"},
        {"id": "subtask-3", "name": "验证结果", "status": "PENDING", "depends_on": ["subtask-2"]}
      ],
      "edges": [
        {"from": "subtask-1", "to": "subtask-2"},
        {"from": "subtask-2", "to": "subtask-3"}
      ]
    },
    "total_subtasks": 3,
    "completed_subtasks": 1,
    "estimated_time_seconds": 45
  }
}
```

**错误响应**
```json
{ "success": false, "error": "task_description is required" }  // HTTP 400
{ "success": false, "error": "No available agents with matching capabilities" }  // HTTP 503
```

---

### 8.3 GET `/api/orchestrator/stats`

查询编排引擎统计信息（任务总数、成功率、平均延迟、活跃 Agent 数）。

**响应**
```json
{
  "success": true,
  "data": {
    "total_tasks": 156,
    "completed_tasks": 142,
    "failed_tasks": 8,
    "running_tasks": 6,
    "success_rate": 0.910,
    "avg_latency_seconds": 38.5,
    "p50_latency_seconds": 25.0,
    "p99_latency_seconds": 120.0,
    "active_agents": 5,
    "total_agents": 8,
    "total_subtasks_executed": 468
  }
}
```

---

## 9. 分页 API 规范

v3.13 P0 性能优化为 4 个重查询端点添加了分页支持，避免全量返回导致的内存峰值。

### 9.1 通用分页参数

以下分页参数适用于所有支持分页的端点：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | int | 1 | 页码（从 1 开始） |
| `page_size` | int | 20 | 每页条数（最大 100） |

**通用分页响应结构**：
```json
{
  "success": true,
  "data": {
    "items": ["... — 当前页数据条目"],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total_items": 15358857,
      "total_pages": 767943,
      "has_next": true,
      "has_prev": false
    }
  }
}
```

### 9.2 GET `/api/corpus`（分页）

获取语料条目列表（分页）。

**Query 参数**
```
?page=1&page_size=20&domain=physics
```

**响应**
```json
{
  "success": true,
  "data": {
    "items": [
      {"id": 1, "text": "...", "domain": "physics", "concepts_count": 15, "relations_count": 23},
      {"id": 2, "text": "...", "domain": "physics", "concepts_count": 8, "relations_count": 12}
    ],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total_items": 156,
      "total_pages": 8,
      "has_next": true,
      "has_prev": false
    }
  }
}
```

### 9.3 GET `/api/conflicts`（分页）

获取冲突决策记录列表（分页）。

**Query 参数**
```
?page=1&page_size=20&concept=人工智能
```

**响应**
```json
{
  "success": true,
  "data": {
    "items": [
      {"conflict_id": "c001", "concept_name": "人工智能", "domain": "AI", "decision": "merge"}
    ],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total_items": 42,
      "total_pages": 3,
      "has_next": true,
      "has_prev": false
    }
  }
}
```

### 9.4 GET `/api/sessions`（分页）

获取聊天会话列表（分页）。

**Query 参数**
```
?page=1&page_size=20
```

**响应**
```json
{
  "success": true,
  "data": {
    "items": [
      {"session_id": "s001", "title": "物理问答", "messages_count": 8, "created_at": "2026-06-23T10:00:00Z"}
    ],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total_items": 89,
      "total_pages": 5,
      "has_next": true,
      "has_prev": false
    }
  }
}
```

### 9.5 GET `/api/knowledge`（分页）

获取知识条目列表（分页，支持 `min_i_weight` 过滤）。

**Query 参数**
```
?page=1&page_size=20&min_i_weight=1.5&type=concept
```

**响应**
```json
{
  "success": true,
  "data": {
    "items": [
      {"id": 1, "concept": "牛顿第二定律", "content": "...", "source": "physics.txt", "type": "concept", "i_weight": 2.15}
    ],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total_items": 15358857,
      "total_pages": 767943,
      "has_next": true,
      "has_prev": false
    }
  }
}
```

> **性能说明**：分页查询使用 SQLite `LIMIT ... OFFSET ...` 语法，配合 `idx_triples_i_weight` 索引实现高效分页。`page_size` 上限 100，防止大页查询导致内存压力。

---

## 附录：通用错误格式

所有端点统一错误响应格式：

```json
{
  "success": false,
  "error": "string — 错误描述",
  "data": { }
}
```

**常见 HTTP 状态码**
| 状态码 | 含义 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误（如缺少必需字段）|
| 500 | 服务器内部错误 |
| 503 | 模块不可用（如 `mina-sdk` 未安装时调用 Mina 端点）|

---

## 端点总览

| # | 方法 | 路径 | 模块 |
|---|------|------|------|
| 1 | POST | `/api/v2/nlu/parse` | HNC NLU |
| 2 | GET | `/api/v2/nlu/stats` | HNC NLU |
| 3 | POST | `/api/v2/godel/improve` | 哥德尔智能体 |
| 4 | GET | `/api/v2/godel/status` | 哥德尔智能体 |
| 5 | POST | `/api/v2/godel/mus/resolve` | 哥德尔智能体 |
| 6 | POST | `/api/v2/vector-clock/tick` | 向量时钟 |
| 7 | POST | `/api/v2/vector-clock/compare` | 向量时钟 |
| 8 | POST | `/api/v2/causal-delivery/deliver` | 因果交付 |
| 9 | GET | `/api/v2/causal-delivery/pending` | 因果交付 |
| 10 | POST | `/api/v2/agentweb/send` | AgentWeb |
| 11 | POST | `/api/v2/agentweb/receive` | AgentWeb |
| 12 | GET | `/api/v2/agentweb/status` | AgentWeb |
| 13 | POST | `/api/v2/fediverse/send` | Fediverse |
| 14 | POST | `/api/v2/fediverse/receive` | Fediverse |
| 15 | GET | `/api/v2/fediverse/stats` | Fediverse |
| 16 | POST | `/api/v2/mina/wrap-snap` | Mina SNARK |
| 17 | POST | `/api/v2/mina/verify` | Mina SNARK |
| 18 | GET | `/api/v2/mina/stats` | Mina SNARK |
| 19 | POST | `/api/v2/celo/pay` | Celo 支付 |
| 20 | POST | `/api/v2/celo/verify` | Celo 支付 |
| 21 | GET | `/api/v2/celo/balance` | Celo 支付 |
| 22 | POST | `/api/v2/world-model/learn` | 因果世界模型 |
| 23 | POST | `/api/v2/world-model/predict` | 因果世界模型 |
| 24 | POST | `/api/v2/world-model/counterfactual` | 因果世界模型 |
| 25 | GET | `/api/v2/aether/scm/summary` | Aether 桥接 |
| 26 | GET | `/api/v2/aether/scm/confounders` | Aether 桥接 |
| 27 | POST | `/api/v2/ehnn/forward` | EML-EHNN |
| 28 | POST | `/api/v2/ehnn/expand-dim` | EML-EHNN |
| 29 | GET | `/api/orchestrator/agents` | Fugu Conductor 编排 |
| 30 | POST | `/api/orchestrator/orchestrate` | Fugu Conductor 编排 |
| 31 | GET | `/api/orchestrator/stats` | Fugu Conductor 编排 |

---

*文档生成时间：2026-06-23 | 对应代码版本：tomas-agi v3.13 @ `168 端点`*
