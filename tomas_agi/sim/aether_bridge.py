"""Aether SCM 编码器桥接 — 将物理关系提取为结构因果模型(SCM)。

基于架构文档 Section 3.2.7: AetherSCMBridge
SCM → EML 超边因果编码，支持混淆因子检测。

TOMAS v2.0 因果世界模型子系统：
    物理观测 → SCM 有向无环图 → EML 超边因果编码 → Hodge 硬锚检查

核心能力：
    1. 因果变量管理（连续/离散/二值）
    2. 因果边管理（DAG 环检测，物理守恒律硬锚标记）
    3. 混淆因子检测（X→A, X→B, A⟛B）
    4. EML 超边编码（因果边 → causal_relation schema）
    5. 硬锚违例检查（守恒律约束验证）

零硬依赖；networkx 为可选依赖，缺失时降级为纯 Python BFS。
"""

import hashlib
import time
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 可选导入 networkx
try:
    import networkx as nx
    _HAS_NETWORKX = True
except ImportError:
    _HAS_NETWORKX = False
    logger.warning("networkx not installed. SCM graph operations will use fallback.")


# ============================================================
# 数据结构
# ============================================================

@dataclass
class CausalVariable:
    """因果变量。

    Attributes:
        var_id: 变量唯一标识符
        name: 人类可读名称
        var_type: 变量类型 ("continuous" / "discrete" / "binary")
        domain: 取值范围（连续变量为 [min, max]，离散变量为枚举值列表）
    """
    var_id: str
    name: str
    var_type: str = "continuous"  # continuous / discrete / binary
    domain: Optional[List[float]] = None  # 取值范围


@dataclass
class CausalEdge:
    """因果边（SCM 中的有向边）。

    Attributes:
        source: 源变量 ID
        target: 目标变量 ID
        edge_type: 因果类型 ("direct" / "confounded" / "mediated")
        mechanism: 因果机制描述（如 "Newton's 2nd law"）
        strength: 因果强度 [0, 1]
        is_hard_anchor: 是否物理守恒律硬锚
    """
    source: str  # source var_id
    target: str  # target var_id
    edge_type: str = "direct"  # direct / confounded / mediated
    mechanism: Optional[str] = None  # 因果机制描述
    strength: float = 1.0  # 因果强度 [0, 1]
    is_hard_anchor: bool = False  # 是否物理守恒律硬锚


# ============================================================
# AetherSCMBridge
# ============================================================

class AetherSCMBridge:
    """Aether SCM 编码器桥接。

    将物理数据/关系提取为 SCM 有向无环图，
    编码为 EML 超边因果边，支持混淆因子检测。

    设计要点：
        - DAG 完整性：所有 add_causal_edge 自动检测环，拒绝成环边
        - 物理硬锚：标记 is_hard_anchor 的因果边代表守恒律约束，
          check_hard_anchor_violation 验证预测状态是否满足守恒
        - 混淆因子检测：自动发现 X→A 且 X→B 但 A⟛B 的结构
        - EML 编码：因果边映射为 causal_relation schema 超边

    Attributes:
        _graph: networkx.DiGraph（或 None，降级时为 None）
        _variables: {var_id: CausalVariable}
        _edges: {edge_key: CausalEdge}
        _hard_anchors: 物理守恒律硬锚边 key 列表
    """

    def __init__(self) -> None:
        """初始化 SCM 图。"""
        if _HAS_NETWORKX:
            self._graph: Optional[Any] = nx.DiGraph()
        else:
            self._graph = None  # fallback: 用 dict 存储
        self._variables: Dict[str, CausalVariable] = {}
        self._edges: Dict[str, CausalEdge] = {}
        self._hard_anchors: List[str] = []  # 物理守恒律硬锚变量

    # ----------------------------------------------------------
    # 变量管理
    # ----------------------------------------------------------

    def add_variable(self, var: CausalVariable) -> None:
        """添加因果变量。

        Args:
            var: CausalVariable 实例
        """
        self._variables[var.var_id] = var
        if self._graph:
            self._graph.add_node(var.var_id, **{"name": var.name, "type": var.var_type})

    def get_variable(self, var_id: str) -> Optional[CausalVariable]:
        """获取因果变量。

        Args:
            var_id: 变量 ID

        Returns:
            CausalVariable 或 None（不存在时）
        """
        return self._variables.get(var_id)

    # ----------------------------------------------------------
    # 因果边管理
    # ----------------------------------------------------------

    def add_causal_edge(self, edge: CausalEdge) -> None:
        """添加因果边。

        如果引入环，拒绝添加（SCM 必须是 DAG）。

        Args:
            edge: CausalEdge 实例
        """
        # 检查是否形成环
        if self._would_create_cycle(edge.source, edge.target):
            logger.warning(
                f"AetherSCM: edge {edge.source}->{edge.target} "
                "would create cycle, rejected"
            )
            return
        edge_key = f"{edge.source}->{edge.target}"
        self._edges[edge_key] = edge
        if self._graph:
            self._graph.add_edge(edge.source, edge.target, **{
                "type": edge.edge_type, "strength": edge.strength,
                "is_hard_anchor": edge.is_hard_anchor
            })
        if edge.is_hard_anchor:
            self._hard_anchors.append(edge_key)

    def _would_create_cycle(self, source: str, target: str) -> bool:
        """检查添加 source->target 是否会形成环。

        通过检测 target 是否已有路径到达 source 来判断。
        若存在 target→...→source 路径，则添加 source→target 会成环。

        Args:
            source: 源变量 ID
            target: 目标变量 ID

        Returns:
            True 表示会形成环
        """
        if source == target:
            return True
        if self._graph and _HAS_NETWORKX:
            # 检查 target 是否能到达 source（如果能，则添加 source->target 会形成环）
            try:
                return nx.has_path(self._graph, target, source)
            except nx.NodeNotFound:
                return False
        else:
            # fallback: BFS 检查
            visited: set = set()
            queue: List[str] = [target]
            while queue:
                node = queue.pop(0)
                if node == source:
                    return True
                if node in visited:
                    continue
                visited.add(node)
                for ek, ev in self._edges.items():
                    if ev.source == node:
                        queue.append(ev.target)
            return False

    # ----------------------------------------------------------
    # 混淆因子检测
    # ----------------------------------------------------------

    def detect_confounders(self) -> List[Tuple[str, str, str]]:
        """检测混淆因子。

        混淆因子 X：X→A 且 X→B，但 A 和 B 之间无直接因果边。

        Returns:
            [(confounder_id, var_a_id, var_b_id), ...]
        """
        confounders: List[Tuple[str, str, str]] = []
        if self._graph and _HAS_NETWORKX:
            for node in self._graph.nodes():
                successors = list(self._graph.successors(node))
                if len(successors) >= 2:
                    # 检查每对后继之间是否有直接边
                    for i, a in enumerate(successors):
                        for b in successors[i + 1:]:
                            if not self._graph.has_edge(a, b) and not self._graph.has_edge(b, a):
                                confounders.append((node, a, b))
        else:
            # fallback
            out_edges: Dict[str, List[str]] = {}
            for ek, ev in self._edges.items():
                out_edges.setdefault(ev.source, []).append(ev.target)
            for node, targets in out_edges.items():
                if len(targets) >= 2:
                    for i, a in enumerate(targets):
                        for b in targets[i + 1:]:
                            if f"{a}->{b}" not in self._edges and f"{b}->{a}" not in self._edges:
                                confounders.append((node, a, b))
        return confounders

    def get_confounders(self, var_x: str, var_y: str) -> List[str]:
        """获取两个变量之间的混淆因子。

        找出所有同时指向 var_x 和 var_y 的变量 Z，
        且 Z→var_x、Z→var_y 均存在，var_x⟛var_y 无直接边。

        Args:
            var_x: 变量 X 的 ID
            var_y: 变量 Y 的 ID

        Returns:
            混淆因子变量 ID 列表
        """
        confounder_ids: List[str] = []
        all_conf = self.detect_confounders()
        for conf_id, a, b in all_conf:
            if {a, b} == {var_x, var_y}:
                confounder_ids.append(conf_id)
        return confounder_ids

    # ----------------------------------------------------------
    # EML 超边编码
    # ----------------------------------------------------------

    def to_eml_hyperedges(self) -> List[Dict[str, Any]]:
        """将 SCM 因果边编码为 EML 超边格式。

        每条因果边 source->target 映射为一个 EML 超边：
            - schema_type: "causal_relation"
            - nodes: [source_var, target_var]
            - edge_type: 因果类型
            - i_value: 因果强度 (strength)
            - is_hard_anchor: 是否物理守恒律

        Returns:
            EML 超边字典列表
        """
        hyperedges: List[Dict[str, Any]] = []
        for edge_key, edge in self._edges.items():
            he: Dict[str, Any] = {
                "edge_id": f"causal_{hashlib.md5(edge_key.encode()).hexdigest()[:12]}",
                "schema_type": "causal_relation",
                "source": edge.source,
                "target": edge.target,
                "edge_type": edge.edge_type,
                "mechanism": edge.mechanism,
                "i_value": edge.strength,
                "is_hard_anchor": edge.is_hard_anchor,
                "timestamp": time.time(),
            }
            hyperedges.append(he)
        return hyperedges

    # ----------------------------------------------------------
    # 硬锚违例检查
    # ----------------------------------------------------------

    def check_hard_anchor_violation(
        self, predicted_state: Dict[str, float]
    ) -> List[str]:
        """检查预测状态是否违反物理守恒律硬锚。

        对每个标记为 is_hard_anchor 的因果边，
        检查预测值是否满足守恒约束。

        简化守恒检查逻辑：
            - 硬锚边 source→target 表示 source + target 应守恒（和为常数）
            - 若 |source + target| > |source| × 10%，则判定违规

        Args:
            predicted_state: {var_id: predicted_value}

        Returns:
            违规列表 ["edge_key: violation description", ...]
        """
        violations: List[str] = []
        for edge_key in self._hard_anchors:
            edge = self._edges[edge_key]
            s_val = predicted_state.get(edge.source)
            t_val = predicted_state.get(edge.target)
            if s_val is not None and t_val is not None:
                # 守恒律：source 和 target 的和应保持不变（简化检查）
                # 实际应用中应根据具体物理定律检查
                # 这里做简化：如果两者符号相反且绝对值差距 > 10%，则违规
                if abs(s_val + t_val) > abs(s_val) * 0.1 + 1e-10:
                    violations.append(
                        f"{edge_key}: conservation violated "
                        f"({edge.source}={s_val:.4f} + {edge.target}={t_val:.4f} "
                        f"= {s_val + t_val:.4f} != 0)"
                    )
        return violations

    # ----------------------------------------------------------
    # 图摘要
    # ----------------------------------------------------------

    def get_graph_summary(self) -> Dict[str, Any]:
        """返回 SCM 图摘要。

        Returns:
            包含变量数、边数、硬锚数、networkx 可用性、变量名列表的字典
        """
        return {
            "num_variables": len(self._variables),
            "num_edges": len(self._edges),
            "num_hard_anchors": len(self._hard_anchors),
            "has_networkx": _HAS_NETWORKX,
            "variables": [v.name for v in self._variables.values()],
        }


# ============================================================
# 自测
# ============================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("=" * 60)
    print("AetherSCMBridge 自测")
    print("=" * 60)

    bridge = AetherSCMBridge()

    # --- 1. 创建变量（能量、动量、位置等物理量）---
    print("\n[1] 创建物理因果变量...")
    energy = CausalVariable(var_id="E", name="Energy", var_type="continuous",
                            domain=[0.0, 1e9])
    momentum = CausalVariable(var_id="p", name="Momentum", var_type="continuous",
                              domain=[-1e9, 1e9])
    position = CausalVariable(var_id="x", name="Position", var_type="continuous",
                              domain=[-1e6, 1e6])
    velocity = CausalVariable(var_id="v", name="Velocity", var_type="continuous",
                              domain=[-3e8, 3e8])
    mass = CausalVariable(var_id="m", name="Mass", var_type="continuous",
                          domain=[0.0, 1e6])
    temperature = CausalVariable(var_id="T", name="Temperature", var_type="continuous",
                                 domain=[0.0, 1e6])

    for var in [energy, momentum, position, velocity, mass, temperature]:
        bridge.add_variable(var)
    print(f"  已添加 {len(bridge._variables)} 个变量")

    # --- 2. 添加因果边（含硬锚标记的能量守恒边）---
    print("\n[2] 添加因果边（含硬锚标记）...")
    # 能量守恒：动能 ↔ 势能（硬锚）
    bridge.add_causal_edge(CausalEdge(
        source="E_kinetic", target="E_potential",
        edge_type="direct", mechanism="Energy conservation",
        strength=1.0, is_hard_anchor=True
    ))
    # 动量守恒：p1 ↔ p2（硬锚）
    bridge.add_causal_edge(CausalEdge(
        source="p1", target="p2",
        edge_type="direct", mechanism="Momentum conservation",
        strength=1.0, is_hard_anchor=True
    ))
    # 质量 → 动量
    bridge.add_causal_edge(CausalEdge(
        source="m", target="p",
        edge_type="direct", mechanism="p = mv",
        strength=0.9, is_hard_anchor=False
    ))
    # 速度 → 动量
    bridge.add_causal_edge(CausalEdge(
        source="v", target="p",
        edge_type="direct", mechanism="p = mv",
        strength=0.9, is_hard_anchor=False
    ))
    # 速度 → 位置
    bridge.add_causal_edge(CausalEdge(
        source="v", target="x",
        edge_type="direct", mechanism="dx/dt = v",
        strength=0.8, is_hard_anchor=False
    ))
    # 温度 → 能量
    bridge.add_causal_edge(CausalEdge(
        source="T", target="E",
        edge_type="direct", mechanism="E = kT",
        strength=0.7, is_hard_anchor=False
    ))
    # 质量 → 能量（E=mc²）
    bridge.add_causal_edge(CausalEdge(
        source="m", target="E",
        edge_type="direct", mechanism="E = mc^2",
        strength=0.95, is_hard_anchor=False
    ))
    print(f"  已添加 {len(bridge._edges)} 条因果边")
    print(f"  硬锚边数: {len(bridge._hard_anchors)}")

    # --- 3. 测试环检测 ---
    print("\n[3] 测试环检测...")
    # 尝试添加 p -> m（会形成 m->p->m 环）
    bridge.add_causal_edge(CausalEdge(
        source="p", target="m",
        edge_type="direct", mechanism="reverse (should be rejected)",
        strength=0.5, is_hard_anchor=False
    ))
    if "p->m" not in bridge._edges:
        print("  [PASS] 环检测成功拒绝 p->m（m->p 已存在）")
    else:
        print("  [FAIL] 环检测失败：p->m 不应被添加")
        sys.exit(1)

    # 尝试自环
    bridge.add_causal_edge(CausalEdge(
        source="x", target="x",
        edge_type="direct", mechanism="self-loop (should be rejected)",
        strength=0.5, is_hard_anchor=False
    ))
    if "x->x" not in bridge._edges:
        print("  [PASS] 自环检测成功拒绝 x->x")
    else:
        print("  [FAIL] 自环检测失败")
        sys.exit(1)

    # --- 4. 测试混淆因子检测 ---
    print("\n[4] 测试混淆因子检测...")
    confounders = bridge.detect_confounders()
    print(f"  检测到 {len(confounders)} 组混淆因子:")
    for conf_id, a, b in confounders:
        var_names = {
            "E": "Energy", "p": "Momentum", "x": "Position",
            "v": "Velocity", "m": "Mass", "T": "Temperature",
            "E_kinetic": "KineticE", "E_potential": "PotentialE",
            "p1": "Momentum1", "p2": "Momentum2",
        }
        print(f"    {var_names.get(conf_id, conf_id)} -> "
              f"({var_names.get(a, a)}, {var_names.get(b, b)})")

    # m 同时指向 p 和 E，p 和 E 之间无直接边 → m 是混淆因子
    m_conf = [c for c in confounders if c[0] == "m"]
    if len(m_conf) > 0:
        print(f"  [PASS] 质量(m)被正确检测为混淆因子（{len(m_conf)} 组）")
    else:
        print("  [FAIL] 未检测到质量(m)为混淆因子")
        sys.exit(1)

    # v 同时指向 p 和 x，p 和 x 之间无直接边 → v 是混淆因子
    v_conf = [c for c in confounders if c[0] == "v"]
    if len(v_conf) > 0:
        print(f"  [PASS] 速度(v)被正确检测为混淆因子（{len(v_conf)} 组）")
    else:
        print("  [FAIL] 未检测到速度(v)为混淆因子")
        sys.exit(1)

    # 测试 get_confounders
    confs_for_p_e = bridge.get_confounders("p", "E")
    if "m" in confs_for_p_e:
        print(f"  [PASS] get_confounders(p, E) 正确返回 m: {confs_for_p_e}")
    else:
        print(f"  [FAIL] get_confounders(p, E) 应包含 m，实际: {confs_for_p_e}")
        sys.exit(1)

    # --- 5. 测试 to_eml_hyperedges ---
    print("\n[5] 测试 to_eml_hyperedges 编码...")
    hyperedges = bridge.to_eml_hyperedges()
    print(f"  生成 {len(hyperedges)} 条 EML 超边")
    for he in hyperedges[:3]:
        print(f"    {he['edge_id']}: {he['source']}->{he['target']} "
              f"(type={he['edge_type']}, i={he['i_value']:.2f}, "
              f"hard_anchor={he['is_hard_anchor']})")
    if len(hyperedges) == len(bridge._edges):
        print(f"  [PASS] 超边数 ({len(hyperedges)}) = 因果边数 ({len(bridge._edges)})")
    else:
        print(f"  [FAIL] 超边数 ({len(hyperedges)}) != 因果边数 ({len(bridge._edges)})")
        sys.exit(1)

    # 检查 schema_type
    all_causal = all(he["schema_type"] == "causal_relation" for he in hyperedges)
    if all_causal:
        print("  [PASS] 所有超边 schema_type = 'causal_relation'")
    else:
        print("  [FAIL] 部分超边 schema_type 不正确")
        sys.exit(1)

    # --- 6. 测试 check_hard_anchor_violation ---
    print("\n[6] 测试 check_hard_anchor_violation...")
    # 6a: 守恒情况（E_kinetic + E_potential = 0, p1 + p2 = 0）
    conserved_state = {
        "E_kinetic": 100.0,
        "E_potential": -100.0,  # 和 = 0 ✓
        "p1": 50.0,
        "p2": -50.0,  # 和 = 0 ✓
    }
    violations_ok = bridge.check_hard_anchor_violation(conserved_state)
    if len(violations_ok) == 0:
        print("  [PASS] 守恒状态无违例")
    else:
        print(f"  [FAIL] 守恒状态不应有违例，实际: {violations_ok}")
        sys.exit(1)

    # 6b: 不守恒情况
    violated_state = {
        "E_kinetic": 100.0,
        "E_potential": -80.0,  # 和 = 20 ≠ 0 ✗
        "p1": 50.0,
        "p2": -50.0,  # 和 = 0 ✓
    }
    violations_bad = bridge.check_hard_anchor_violation(violated_state)
    if len(violations_bad) >= 1:
        print(f"  [PASS] 不守恒状态检测到 {len(violations_bad)} 个违例:")
        for v in violations_bad:
            print(f"    {v}")
    else:
        print("  [FAIL] 不守恒状态应检测到违例")
        sys.exit(1)

    # --- 图摘要 ---
    print("\n[7] 图摘要:")
    summary = bridge.get_graph_summary()
    for k, v in summary.items():
        print(f"    {k}: {v}")

    print("\n" + "=" * 60)
    print("AetherSCMBridge 自测全部通过!")
    print("=" * 60)
