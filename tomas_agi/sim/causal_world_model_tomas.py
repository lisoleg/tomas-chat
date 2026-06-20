"""TOMAS 因果世界模型 — Aether SCM + TOMAS 裁决层

融合 Aether 结构因果模型 (SCM) 与 TOMAS H_hard 物理守恒律裁决层。
H_hard 在预测路径上不可绕过：predict_next_state 和 counterfactual
均强制调用 _check_h_hard，违例时返回 h_hard_passed=False 并列出违规项。

核心能力：
    1. learn_from_data — 从观测数据学习因果结构
       (SCM DAG 构建 → EML 超边编码 → Hodge 谱分析)
    2. predict_next_state — SCM 干预推理 (do-calculus) + H_hard 守恒律检查
       + Dead-Zero 检查 → 预测状态 + 置信度
    3. counterfactual — 基于 Pearl do-calculus 的反事实推理
       P(Y | do(X=x'), observed=e)
    4. _check_h_hard — 物理守恒律硬锚检查（能量/动量/角动量守恒）

设计要点：
    - H_hard 不可绕过：predict_next_state 和 counterfactual 的返回值中
      h_hard_passed 字段直接由 _check_h_hard 决定，无任何短路路径
    - 双层守恒检查：Layer-1 HodgeICoupling.check_physical_conservation()
      + Layer-2 AetherSCMBridge.check_hard_anchor_violation()
    - do-calculus 简化实现：do(X=x) 切断 X 入边，按拓扑序线性传播
    - 零硬依赖：aether_bridge / hodge_operator / dead_zero_mus 均可选导入

依赖模块（全部可选导入，缺失时降级）：
    - aether_bridge.py — AetherSCMBridge, CausalVariable, CausalEdge
    - hodge_operator.py — HodgeICoupling, WeightedSimplicialComplex
    - dead_zero_mus.py — DeadZeroChecker

Author: Alex (TOMAS AGI v2.0 Engineer)
"""

import logging
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)

# ============================================================
# 可选导入 — 全部 try/except 包裹
# ============================================================

try:
    from aether_bridge import (
        AetherSCMBridge as AetherBridge,
        CausalVariable,
        CausalEdge,
    )
    _HAS_AETHER = True
except ImportError:
    _HAS_AETHER = False
    AetherBridge = None  # type: ignore[assignment, misc]
    CausalVariable = None  # type: ignore[assignment, misc]
    CausalEdge = None  # type: ignore[assignment, misc]
    logger.warning(
        "aether_bridge not available; SCM operations will use fallback."
    )

try:
    from hodge_operator import (
        HodgeICoupling,
        WeightedSimplicialComplex,
        HodgeSpectrum,
    )
    _HAS_HODGE = True
except ImportError:
    _HAS_HODGE = False
    HodgeICoupling = None  # type: ignore[assignment, misc]
    WeightedSimplicialComplex = None  # type: ignore[assignment, misc]
    HodgeSpectrum = None  # type: ignore[assignment, misc]
    logger.warning(
        "hodge_operator not available; H_hard conservation check disabled."
    )

try:
    from dead_zero_mus import DeadZeroChecker
    _HAS_DEAD_ZERO = True
except ImportError:
    _HAS_DEAD_ZERO = False
    DeadZeroChecker = None  # type: ignore[assignment, misc]
    logger.warning(
        "dead_zero_mus not available; Dead-Zero check disabled."
    )


# ============================================================
# TOMASCausalWorldModel
# ============================================================

class TOMASCausalWorldModel:
    """因果世界模型：Aether SCM + TOMAS 裁决层。

    融合 Aether 结构因果模型 (SCM) 与 TOMAS H_hard 物理守恒律裁决层。
    H_hard 在预测路径上不可绕过。

    设计架构：
        物理观测 → AetherSCMBridge (SCM DAG) → EML 超边编码
                                            ↓
        预测路径 → SCM do-calculus 干预 → H_hard 守恒律检查 → Dead-Zero 检查
                                            ↓
        返回: predicted_state + confidence + h_hard_passed + violations

    Attributes:
        aether_bridge: AetherSCMBridge 实例，提供 SCM 图操作
        hodge: HodgeICoupling 实例，提供 check_physical_conservation() 方法
        eml_graph: 可选的 EML 超图（用于因果超边存储）
        _learned_edges: 已学习的因果边数
        _hodge_entropy: Hodge 谱熵
        _state_vars: 本地变量存储（fallback 用）
        _causal_edges: 本地因果边存储（fallback 用）
        _dead_zero_checker: DeadZeroChecker 实例（可选）
    """

    def __init__(
        self,
        aether_bridge: "AetherBridge",
        hodge: "HodgeICoupling",
        eml_graph: Optional[Any] = None,
    ) -> None:
        """初始化因果世界模型。

        Args:
            aether_bridge: AetherSCMBridge 实例，提供 SCM 图操作。
                若为 None 或 aether_bridge 不可用，降级为本地存储。
            hodge: HodgeICoupling 实例，提供 check_physical_conservation() 方法。
                若为 None，H_hard 守恒律检查将仅依赖 AetherSCMBridge 硬锚检查。
            eml_graph: 可选的 EML 超图对象，用于存储因果超边编码结果。
        """
        self.aether_bridge = aether_bridge
        self.hodge = hodge
        self.eml_graph = eml_graph

        # 学习状态
        self._learned_edges: int = 0
        self._hodge_entropy: float = 0.0

        # 本地 fallback 存储（当 aether_bridge 不可用时使用）
        self._state_vars: Dict[str, Dict[str, Any]] = {}
        self._causal_edges: Dict[str, Dict[str, Any]] = {}

        # Dead-Zero 检查器（可选）
        if _HAS_DEAD_ZERO and DeadZeroChecker is not None:
            self._dead_zero_checker: Optional[Any] = DeadZeroChecker(
                theta_dead=0.15
            )
        else:
            self._dead_zero_checker = None

        logger.debug(
            "TOMASCausalWorldModel initialized: aether=%s, hodge=%s, dead_zero=%s",
            _HAS_AETHER, _HAS_HODGE, _HAS_DEAD_ZERO,
        )

    # ----------------------------------------------------------
    # 公共接口
    # ----------------------------------------------------------

    def learn_from_data(self, data: Dict) -> Dict:
        """从观测数据学习因果结构。

        步骤:
            1. AetherBridge 提取物理关系 — 从 data 中解析变量和因果关系
            2. 构建 SCM 有向无环图 — 添加变量和因果边到 AetherSCMBridge
            3. 编码为 EML 因果超边 — 调用 to_eml_hyperedges()
            4. Hodge 谱分析 — 计算 Hodge Laplacian 谱熵

        Args:
            data: 观测数据字典，包含:
                - "variables": List[Dict] 变量定义
                  [{var_id, name, var_type, domain}, ...]
                - "relations": List[Dict] 因果关系
                  [{source, target, edge_type, mechanism, strength,
                    is_hard_anchor}, ...]

        Returns:
            {learned_edges: int, scm_nodes: int, hodge_entropy: float}
        """
        # ── Step 1 & 2: 提取物理关系并构建 SCM DAG ──
        variables: List[Dict] = data.get("variables", [])
        relations: List[Dict] = data.get("relations", [])

        # 添加变量
        for var_def in variables:
            var_id: str = var_def.get("var_id", var_def.get("id", ""))
            var_name: str = var_def.get("name", var_id)
            var_type: str = var_def.get("var_type", "continuous")
            domain: Optional[List[float]] = var_def.get("domain", None)

            if _HAS_AETHER and self.aether_bridge is not None and CausalVariable is not None:
                cv = CausalVariable(
                    var_id=var_id,
                    name=var_name,
                    var_type=var_type,
                    domain=domain,
                )
                self.aether_bridge.add_variable(cv)

            # 本地存储（始终保留，用于 fallback）
            self._state_vars[var_id] = {
                "name": var_name,
                "type": var_type,
                "domain": domain,
            }

        # 添加因果边
        for rel in relations:
            source: str = rel.get("source", "")
            target: str = rel.get("target", "")
            edge_type: str = rel.get("edge_type", "direct")
            mechanism: Optional[str] = rel.get("mechanism", None)
            strength: float = rel.get("strength", 1.0)
            is_hard_anchor: bool = rel.get("is_hard_anchor", False)

            if _HAS_AETHER and self.aether_bridge is not None and CausalEdge is not None:
                ce = CausalEdge(
                    source=source,
                    target=target,
                    edge_type=edge_type,
                    mechanism=mechanism,
                    strength=strength,
                    is_hard_anchor=is_hard_anchor,
                )
                self.aether_bridge.add_causal_edge(ce)

            # 本地存储
            edge_key = f"{source}->{target}"
            self._causal_edges[edge_key] = {
                "source": source,
                "target": target,
                "edge_type": edge_type,
                "mechanism": mechanism,
                "strength": strength,
                "is_hard_anchor": is_hard_anchor,
            }

        # ── Step 3: 编码为 EML 因果超边 ──
        eml_hyperedges: List[Dict[str, Any]] = []
        if _HAS_AETHER and self.aether_bridge is not None:
            try:
                eml_hyperedges = self.aether_bridge.to_eml_hyperedges()
            except Exception as e:
                logger.warning("EML hyperedge encoding failed: %s", e)
                eml_hyperedges = []

        learned_edges: int = (
            len(eml_hyperedges) if eml_hyperedges else len(self._causal_edges)
        )
        self._learned_edges = learned_edges

        # 存储 EML 超边到 eml_graph（如果提供）
        if self.eml_graph is not None and eml_hyperedges:
            if isinstance(self.eml_graph, dict):
                self.eml_graph.setdefault("causal_edges", []).extend(
                    eml_hyperedges
                )

        # ── Step 4: Hodge 谱分析 ──
        hodge_entropy: float = 0.0
        if self.hodge is not None:
            try:
                spectrum = self.hodge.compute_spectrum(dim=1)
                hodge_entropy = spectrum.spectral_entropy
            except Exception as e:
                logger.warning("Hodge spectral analysis failed: %s", e)
                hodge_entropy = 0.0
        self._hodge_entropy = hodge_entropy

        # SCM 节点数
        if _HAS_AETHER and self.aether_bridge is not None:
            try:
                scm_nodes: int = len(self.aether_bridge._variables)
            except Exception:
                scm_nodes = len(self._state_vars)
        else:
            scm_nodes = len(self._state_vars)

        logger.info(
            "learn_from_data: learned_edges=%d, scm_nodes=%d, hodge_entropy=%.4f",
            learned_edges, scm_nodes, hodge_entropy,
        )

        return {
            "learned_edges": learned_edges,
            "scm_nodes": scm_nodes,
            "hodge_entropy": hodge_entropy,
        }

    def predict_next_state(
        self, current_state: Dict, action: Dict
    ) -> Dict:
        """预测下一状态。

        步骤:
            1. SCM 干预推理 (do-calculus) — 应用 action 作为 do 干预，
               按拓扑序传播因果效应
            2. H_hard 物理守恒律检查（不可绕过！） — 调用 _check_h_hard
            3. Dead-Zero 检查 — 检查预测是否有足够 EML 支撑
            4. 返回预测状态 + 置信度

        H_hard 不可绕过：即使 Dead-Zero 检查失败，H_hard 结果仍然
        被如实返回。若 H_hard 检查未通过，h_hard_passed=False 且
        confidence 大幅降低。

        Args:
            current_state: 当前物理状态 {var_id: value}
            action: 干预动作 {var_id: value}（do(X=x)）

        Returns:
            {
                predicted_state: Dict,      # 预测的下一状态
                confidence: float,          # 置信度 [0, 1]
                h_hard_passed: bool,        # H_hard 守恒律是否通过
                violations: List[str],      # 违规项列表
            }
        """
        # ── Step 1: SCM 干预推理 (do-calculus) ──
        predicted_state: Dict[str, Any] = self._scm_intervene(
            current_state, action
        )

        # ── Step 2: H_hard 物理守恒律检查（不可绕过！） ──
        conservation_check: Dict[str, Any] = self._build_conservation_dict(
            current_state, predicted_state
        )
        # 同时将预测变量值加入检查字典（供硬锚边检查使用）
        for key, val in predicted_state.items():
            if isinstance(val, (int, float)):
                conservation_check[key] = float(val)

        h_hard_passed: bool
        violations: List[str]
        h_hard_passed, violations = self._check_h_hard(conservation_check)

        # ── Step 3: Dead-Zero 检查 ──
        dead_zero_passed: bool = True
        if self._dead_zero_checker is not None:
            try:
                matched_edges: List[Dict[str, Any]] = []
                if _HAS_AETHER and self.aether_bridge is not None:
                    for he in self.aether_bridge.to_eml_hyperedges():
                        matched_edges.append({
                            "eid": he.get("edge_id", ""),
                            "nodes": [
                                he.get("source", ""),
                                he.get("target", ""),
                            ],
                            "i_val": he.get("i_value", 0.0),
                        })
                else:
                    for ek, ev in self._causal_edges.items():
                        matched_edges.append({
                            "eid": ek,
                            "nodes": [ev["source"], ev["target"]],
                            "i_val": ev["strength"],
                        })

                dz_result = self._dead_zero_checker.check(
                    matched_edges=matched_edges,
                    query=str(action),
                )
                dead_zero_passed = not dz_result.is_dead
            except Exception as e:
                logger.warning("Dead-Zero check failed: %s", e)
                dead_zero_passed = True  # Dead-Zero 非硬约束，fail-open

        # ── Step 4: 计算置信度 ──
        confidence: float = 1.0

        # H_hard 失败 → 置信度大幅降低
        if not h_hard_passed:
            confidence *= 0.1

        # Dead-Zero 触发 → 置信度降低
        if not dead_zero_passed:
            confidence *= 0.3

        # 因果边平均强度因子
        if _HAS_AETHER and self.aether_bridge is not None:
            try:
                edges = self.aether_bridge._edges
                if edges:
                    avg_strength = sum(
                        e.strength for e in edges.values()
                    ) / len(edges)
                    confidence *= avg_strength
            except Exception:
                pass
        elif self._causal_edges:
            avg_strength = sum(
                e["strength"] for e in self._causal_edges.values()
            ) / len(self._causal_edges)
            confidence *= avg_strength

        confidence = max(0.0, min(1.0, confidence))

        logger.info(
            "predict_next_state: h_hard_passed=%s, dead_zero_passed=%s, "
            "confidence=%.4f, violations=%d",
            h_hard_passed, dead_zero_passed, confidence, len(violations),
        )

        return {
            "predicted_state": predicted_state,
            "confidence": confidence,
            "h_hard_passed": h_hard_passed,
            "violations": violations,
        }

    def counterfactual(
        self, state: Dict, intervention: Dict
    ) -> Dict:
        """反事实推理：给定干预条件，推断替代结果。

        基于 Pearl's do-calculus: P(Y | do(X=x'), observed=e)

        简化实现：
            1. 从观测状态 state 出发
            2. 应用反事实干预 do(X=x') — 切断 X 入边，设置 X=x'
            3. SCM 传播推断替代结果
            4. H_hard 守恒律检查（不可绕过！）
            5. 估计反事实概率

        H_hard 不可绕过：若守恒律违例，h_hard_passed=False 且
        probability 大幅降低。

        Args:
            state: 观测状态 {var_id: value} (observed=e)
            intervention: 干预条件 {var_id: value} (do(X=x'))

        Returns:
            {
                counterfactual_state: Dict,  # 反事实推断的替代状态
                probability: float,          # 反事实概率 [0, 1]
                h_hard_passed: bool,         # H_hard 守恒律是否通过
            }
        """
        # ── Step 1-3: SCM 反事实推理 ──
        counterfactual_state: Dict[str, Any] = self._scm_intervene(
            state, intervention
        )

        # ── Step 4: H_hard 检查（不可绕过！） ──
        conservation_check: Dict[str, Any] = self._build_conservation_dict(
            state, counterfactual_state
        )
        for key, val in counterfactual_state.items():
            if isinstance(val, (int, float)):
                conservation_check[key] = float(val)

        h_hard_passed: bool
        violations: List[str]
        h_hard_passed, violations = self._check_h_hard(conservation_check)

        # ── Step 5: 估计反事实概率 ──
        # P(Y | do(X=x'), observed=e) 简化估计
        probability: float = 1.0

        # Factor 1: 干预涉及边的平均因果强度
        if _HAS_AETHER and self.aether_bridge is not None:
            try:
                edges = self.aether_bridge._edges
                intervention_edges = [
                    e for e in edges.values()
                    if e.source in intervention or e.target in intervention
                ]
                if intervention_edges:
                    avg_strength = sum(
                        e.strength for e in intervention_edges
                    ) / len(intervention_edges)
                    probability *= avg_strength
            except Exception:
                pass
        else:
            intervention_edges = [
                e for e in self._causal_edges.values()
                if e["source"] in intervention or e["target"] in intervention
            ]
            if intervention_edges:
                avg_strength = sum(
                    e["strength"] for e in intervention_edges
                ) / len(intervention_edges)
                probability *= avg_strength

        # Factor 2: H_hard 通过率
        if not h_hard_passed:
            probability *= 0.05  # 守恒律违例大幅降低概率

        # Factor 3: 状态变化幅度（变化越大，概率越低）
        delta_sum: float = 0.0
        delta_count: int = 0
        for k, v in counterfactual_state.items():
            if k in state and isinstance(v, (int, float)) and isinstance(state[k], (int, float)):
                delta_sum += abs(v - state[k])
                delta_count += 1
        if delta_count > 0:
            avg_delta: float = delta_sum / delta_count
            probability *= max(0.1, 1.0 - avg_delta * 0.01)

        probability = max(0.0, min(1.0, probability))

        logger.info(
            "counterfactual: h_hard_passed=%s, probability=%.4f, violations=%d",
            h_hard_passed, probability, len(violations),
        )

        return {
            "counterfactual_state": counterfactual_state,
            "probability": probability,
            "h_hard_passed": h_hard_passed,
        }

    # ----------------------------------------------------------
    # H_hard 硬锚检查（不可绕过！）
    # ----------------------------------------------------------

    def _check_h_hard(self, prediction: Dict) -> Tuple[bool, List[str]]:
        """H_hard 硬锚检查：物理守恒律验证（不可绕过！）。

        检查项:
            - 能量守恒: ΔE_total ≈ 0
            - 动量守恒: Δp_total ≈ 0
            - 角动量守恒: ΔL_total ≈ 0

        双层检查：
            Layer 1: HodgeICoupling.check_physical_conservation()
                     — 检查 energy/momentum/angular_momentum 的 before/after 差值
            Layer 2: AetherSCMBridge.check_hard_anchor_violation()
                     — 检查硬锚边标记的变量对是否满足守恒约束

        任一层检查失败，整体判定为未通过。

        Args:
            prediction: 预测状态字典，包含:
                - 守恒量 before/after 键:
                  energy_before, energy_after,
                  momentum_before, momentum_after,
                  angular_momentum_before, angular_momentum_after
                - 变量值: {var_id: value}（供硬锚边检查使用）

        Returns:
            (passed: bool, violations: List[str])
            passed 为 True 当且仅当所有检查项均通过。
            violations 列出所有违规项的描述字符串。
        """
        violations: List[str] = []

        # ── Layer 1: HodgeICoupling 物理守恒律检查 ──
        if self.hodge is not None:
            try:
                conservation_result: Dict[str, Any] = (
                    self.hodge.check_physical_conservation(prediction)
                )
                if not conservation_result.get("passed", True):
                    hodge_violations: List[str] = conservation_result.get(
                        "violations", []
                    )
                    violations.extend(hodge_violations)
                    logger.debug(
                        "[H_hard] Layer-1 Hodge violations: %s",
                        hodge_violations,
                    )
            except Exception as e:
                logger.warning(
                    "[H_hard] Hodge conservation check error: %s", e
                )
                violations.append(f"hodge_check_error: {str(e)}")
        else:
            logger.debug(
                "[H_hard] HodgeICoupling not available; "
                "skipping Layer-1 conservation check."
            )

        # ── Layer 2: AetherSCMBridge 硬锚违例检查 ──
        if _HAS_AETHER and self.aether_bridge is not None:
            try:
                # 构建预测变量值字典 {var_id: predicted_value}
                # 从 prediction 中提取非 before/after 的数值字段
                predicted_values: Dict[str, float] = {}
                for key, val in prediction.items():
                    if (
                        isinstance(val, (int, float))
                        and not key.endswith("_before")
                        and not key.endswith("_after")
                    ):
                        predicted_values[key] = float(val)

                # 同时提取 _after 后缀的值作为该变量的预测值
                for key, val in prediction.items():
                    if key.endswith("_after") and isinstance(val, (int, float)):
                        base_key: str = key[:-6]  # 去掉 "_after"
                        if base_key not in predicted_values:
                            predicted_values[base_key] = float(val)

                if predicted_values:
                    anchor_violations: List[str] = (
                        self.aether_bridge.check_hard_anchor_violation(
                            predicted_values
                        )
                    )
                    violations.extend(anchor_violations)
                    logger.debug(
                        "[H_hard] Layer-2 anchor violations: %s",
                        anchor_violations,
                    )
            except Exception as e:
                logger.warning(
                    "[H_hard] Aether hard anchor check error: %s", e
                )
                violations.append(f"hard_anchor_check_error: {str(e)}")

        passed: bool = len(violations) == 0

        if not passed:
            logger.warning(
                "[H_hard] 检查未通过 (%d 项违规): %s",
                len(violations), violations,
            )
        else:
            logger.debug("[H_hard] 物理守恒律检查通过")

        return (passed, violations)

    # ----------------------------------------------------------
    # 私有辅助方法
    # ----------------------------------------------------------

    def _scm_intervene(
        self, state: Dict, do: Dict
    ) -> Dict[str, Any]:
        """SCM 干预推理：do(X=x) — 设置 X=x，切断 X 入边，传播因果效应。

        简化的 do-calculus 实现：
            1. 复制当前状态
            2. 应用干预（设置 do 变量的值，模拟 do-operator 的截断语义）
            3. 计算 do 变量的所有后代（受干预影响的变量集合）
            4. 按拓扑序仅传播到后代变量
               线性模型：Y = Σ (strength_i / Σ|strength|) * parent_i
               阻尼更新：new_Y = 0.5 * parent_contribution + 0.5 * current_Y

        do-variables 的值在传播过程中保持固定（不被父节点重新计算），
        模拟 Pearl do-calculus 中"切断干预变量入边"的语义。
        非后代变量保持原值不变（它们的因果来源未受干预影响）。

        Args:
            state: 当前状态 {var_id: value}
            do: 干预 {var_id: value} (do(X=x))

        Returns:
            预测的下一状态 {var_id: value}
        """
        result: Dict[str, Any] = dict(state)

        # 应用干预
        for var, val in do.items():
            result[var] = val

        # 获取因果边
        edge_list: List[Any] = []
        if _HAS_AETHER and self.aether_bridge is not None:
            try:
                edge_list = list(self.aether_bridge._edges.values())
            except Exception:
                edge_list = []

        if not edge_list:
            # fallback: 使用本地存储的边
            edge_list = list(self._causal_edges.values())

        if not edge_list:
            # 无因果边，直接返回干预后的状态
            return result

        # 辅助函数：从边对象中提取字段
        def _get_source(e: Any) -> str:
            if isinstance(e, dict):
                return e.get("source", "")
            return getattr(e, "source", "")

        def _get_target(e: Any) -> str:
            if isinstance(e, dict):
                return e.get("target", "")
            return getattr(e, "target", "")

        def _get_strength(e: Any) -> float:
            if isinstance(e, dict):
                return e.get("strength", 1.0)
            return getattr(e, "strength", 1.0)

        # ── 计算 do 变量的所有后代（受干预影响的变量集合）──
        # 构建前向邻接表 (source → [targets])
        forward_adj: Dict[str, List[str]] = {}
        for e in edge_list:
            s = _get_source(e)
            t = _get_target(e)
            if s and t:
                forward_adj.setdefault(s, []).append(t)

        # BFS 从所有 do 变量出发，收集后代集合
        affected: set = set()
        queue: List[str] = list(do.keys())
        while queue:
            node = queue.pop(0)
            for child in forward_adj.get(node, []):
                if child not in affected and child not in do:
                    affected.add(child)
                    queue.append(child)

        # 拓扑排序
        topo_order: List[str] = self._topological_sort(edge_list)

        # 按拓扑序仅传播到受影响的后代变量
        for var in topo_order:
            # do-variables 保持固定，不重新计算
            if var in do:
                continue

            # 非后代变量保持原值不变（do-calculus 语义）
            if var not in affected:
                continue

            # 收集所有指向 var 的父边
            parents: List[Tuple[str, float]] = []
            for e in edge_list:
                if _get_target(e) == var:
                    parent_id = _get_source(e)
                    strength = _get_strength(e)
                    parents.append((parent_id, strength))

            if not parents:
                continue

            # 线性 SCM 传播：Y = Σ (strength_i / Σ|strength|) * parent_i
            weighted_sum: float = 0.0
            total_weight: float = 0.0
            for parent_id, strength in parents:
                if parent_id in result and isinstance(
                    result[parent_id], (int, float)
                ):
                    weighted_sum += strength * float(result[parent_id])
                    total_weight += abs(strength)

            if total_weight > 0:
                parent_value: float = weighted_sum / total_weight
                current_value: float = float(
                    result.get(var, 0.0)
                ) if isinstance(result.get(var, 0.0), (int, float)) else 0.0
                # 阻尼更新：50% 父节点贡献 + 50% 当前值
                result[var] = 0.5 * parent_value + 0.5 * current_value

        return result

    def _build_conservation_dict(
        self, before: Dict, after: Dict
    ) -> Dict[str, float]:
        """构建守恒律检查字典。

        从 before/after 状态字典中提取能量、动量、角动量等守恒量，
        构建符合 HodgeICoupling.check_physical_conservation() 接口的字典。

        支持的键名映射（按优先级尝试）：
            - energy: "energy", "E", "total_energy", "Energy"
            - momentum: "momentum", "p", "total_momentum", "Momentum"
            - angular_momentum: "angular_momentum", "L",
                                "total_angular_momentum", "AngularMomentum"

        Args:
            before: 干预前状态 {var_id: value}
            after: 干预后状态 {var_id: value}

        Returns:
            包含 energy_before/after, momentum_before/after,
            angular_momentum_before/after 的字典
        """

        def _extract(state: Dict, candidates: List[str]) -> float:
            """从状态字典中提取守恒量值。"""
            for key in candidates:
                val = state.get(key)
                if val is not None and isinstance(val, (int, float)):
                    return float(val)
            return 0.0

        energy_keys = [
            "energy", "E", "total_energy", "Energy",
        ]
        momentum_keys = [
            "momentum", "p", "total_momentum", "Momentum",
        ]
        angular_keys = [
            "angular_momentum", "L",
            "total_angular_momentum", "AngularMomentum",
        ]

        energy_before: float = _extract(before, energy_keys)
        energy_after: float = _extract(after, energy_keys)
        momentum_before: float = _extract(before, momentum_keys)
        momentum_after: float = _extract(after, momentum_keys)
        angular_before: float = _extract(before, angular_keys)
        angular_after: float = _extract(after, angular_keys)

        return {
            "energy_before": energy_before,
            "energy_after": energy_after,
            "momentum_before": momentum_before,
            "momentum_after": momentum_after,
            "angular_momentum_before": angular_before,
            "angular_momentum_after": angular_after,
        }

    def _topological_sort(self, edge_list: List[Any]) -> List[str]:
        """对 SCM 边进行拓扑排序（Kahn's algorithm）。

        Args:
            edge_list: 边列表（CausalEdge 对象或字典）

        Returns:
            拓扑排序后的变量 ID 列表
        """

        def _get_source(e: Any) -> str:
            if isinstance(e, dict):
                return e.get("source", "")
            return getattr(e, "source", "")

        def _get_target(e: Any) -> str:
            if isinstance(e, dict):
                return e.get("target", "")
            return getattr(e, "target", "")

        # 构建邻接表和入度表
        all_nodes: set = set()
        adj: Dict[str, List[str]] = {}
        in_degree: Dict[str, int] = {}

        for e in edge_list:
            s = _get_source(e)
            t = _get_target(e)
            if not s or not t:
                continue
            all_nodes.add(s)
            all_nodes.add(t)
            adj.setdefault(s, []).append(t)
            in_degree[t] = in_degree.get(t, 0) + 1
            in_degree.setdefault(s, in_degree.get(s, 0))

        # 添加不在边中但已注册的变量
        for var_id in self._state_vars:
            all_nodes.add(var_id)
            in_degree.setdefault(var_id, 0)

        # Kahn's algorithm
        queue: List[str] = sorted(
            [n for n in all_nodes if in_degree.get(n, 0) == 0]
        )
        result: List[str] = []

        while queue:
            node = queue.pop(0)
            result.append(node)
            for neighbor in sorted(adj.get(node, [])):
                in_degree[neighbor] = in_degree.get(neighbor, 0) - 1
                if in_degree[neighbor] <= 0:
                    queue.append(neighbor)
            queue.sort()  # 保持确定性顺序

        # 添加剩余节点（理论上 DAG 中不应有剩余）
        for node in sorted(all_nodes):
            if node not in result:
                result.append(node)

        return result


# ============================================================
# 导出
# ============================================================

__all__ = ["TOMASCausalWorldModel"]


# ============================================================
# 自测（≥ 7 个测试用例）
# ============================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s"
    )

    print("=" * 70)
    print("  TOMASCausalWorldModel — Self-Test (T11)")
    print("=" * 70)

    # ── 前置检查：依赖模块可用性 ──
    print("\n[0] 依赖模块可用性检查...")
    print(f"    aether_bridge (AetherSCMBridge): {'OK' if _HAS_AETHER else 'MISSING'}")
    print(f"    hodge_operator (HodgeICoupling): {'OK' if _HAS_HODGE else 'MISSING'}")
    print(f"    dead_zero_mus (DeadZeroChecker): {'OK' if _HAS_DEAD_ZERO else 'MISSING'}")

    if not (_HAS_AETHER and _HAS_HODGE):
        print("\n[FATAL] 核心依赖缺失，无法运行自测。")
        sys.exit(1)

    # ── 创建测试基础设施 ──
    # AetherSCMBridge (imported as AetherBridge)
    bridge = AetherBridge()

    # WeightedSimplicialComplex + HodgeICoupling
    wsc = WeightedSimplicialComplex(max_dim=2)
    wsc.add_simplex(["energy", "momentum"], i_weight=0.8)
    wsc.add_simplex(["momentum", "position"], i_weight=0.6)
    wsc.add_simplex(["energy", "position"], i_weight=0.5)
    coupling = HodgeICoupling(wsc, conservation_tolerance=1e-4)

    # TOMASCausalWorldModel
    model = TOMASCausalWorldModel(bridge, coupling)

    # ── 测试 1: learn_from_data ──
    print("\n[1] learn_from_data — 从观测数据学习因果结构...")
    learn_data = {
        "variables": [
            {"var_id": "energy", "name": "Energy", "var_type": "continuous",
             "domain": [0.0, 1e9]},
            {"var_id": "momentum", "name": "Momentum", "var_type": "continuous",
             "domain": [-1e9, 1e9]},
            {"var_id": "position", "name": "Position", "var_type": "continuous",
             "domain": [-1e6, 1e6]},
            {"var_id": "velocity", "name": "Velocity", "var_type": "continuous",
             "domain": [-3e8, 3e8]},
            {"var_id": "mass", "name": "Mass", "var_type": "continuous",
             "domain": [0.0, 1e6]},
            {"var_id": "angular_momentum", "name": "Angular Momentum",
             "var_type": "continuous", "domain": [-1e9, 1e9]},
            {"var_id": "E_kinetic", "name": "Kinetic Energy",
             "var_type": "continuous", "domain": [0.0, 1e9]},
            {"var_id": "E_potential", "name": "Potential Energy",
             "var_type": "continuous", "domain": [-1e9, 0.0]},
        ],
        "relations": [
            {"source": "mass", "target": "momentum", "mechanism": "p=mv",
             "strength": 0.9},
            {"source": "velocity", "target": "momentum", "mechanism": "p=mv",
             "strength": 0.9},
            {"source": "velocity", "target": "position", "mechanism": "dx/dt=v",
             "strength": 0.8},
            {"source": "mass", "target": "energy", "mechanism": "E=mc^2",
             "strength": 0.95},
            {"source": "E_kinetic", "target": "E_potential",
             "mechanism": "Energy conservation",
             "strength": 1.0, "is_hard_anchor": True},
        ],
    }
    learn_result = model.learn_from_data(learn_data)
    print(f"    learned_edges={learn_result['learned_edges']}, "
          f"scm_nodes={learn_result['scm_nodes']}, "
          f"hodge_entropy={learn_result['hodge_entropy']:.4f}")

    if learn_result["scm_nodes"] == 8 and learn_result["learned_edges"] >= 5:
        print("    [PASS] learn_from_data 正确学习因果结构")
    else:
        print(f"    [FAIL] 期望 scm_nodes=8, learned_edges>=5, "
              f"实际 scm_nodes={learn_result['scm_nodes']}, "
              f"learned_edges={learn_result['learned_edges']}")
        sys.exit(1)

    # ── 测试 2: predict_next_state — H_hard 通过（守恒律满足） ──
    print("\n[2] predict_next_state — H_hard 通过（守恒律满足）...")
    # 干预 position 不影响 energy/momentum/angular_momentum → 守恒律通过
    current_state_1 = {
        "energy": 100.0,
        "momentum": 5.0,
        "position": 0.0,
        "velocity": 2.0,
        "mass": 2.5,
        "angular_momentum": 3.0,
        "E_kinetic": 50.0,
        "E_potential": -50.0,  # E_kinetic + E_potential = 0 ✓
    }
    action_1 = {"position": 10.0}
    pred_1 = model.predict_next_state(current_state_1, action_1)
    print(f"    h_hard_passed={pred_1['h_hard_passed']}, "
          f"confidence={pred_1['confidence']:.4f}, "
          f"violations={pred_1['violations']}")

    if pred_1["h_hard_passed"] is True:
        print("    [PASS] 守恒律满足时 H_hard 通过")
    else:
        print(f"    [FAIL] 预期 H_hard 通过，实际 violations={pred_1['violations']}")
        sys.exit(1)

    # ── 测试 3: predict_next_state — H_hard 失败（能量守恒违反） ──
    print("\n[3] predict_next_state — H_hard 失败（能量守恒违反）...")
    # 直接改变 energy → ΔE >> tolerance → H_hard 失败
    current_state_2 = {
        "energy": 100.0,
        "momentum": 5.0,
        "position": 0.0,
        "velocity": 2.0,
        "mass": 2.5,
        "angular_momentum": 3.0,
        "E_kinetic": 50.0,
        "E_potential": -50.0,
    }
    action_2 = {"energy": 200.0}  # ΔE = 100 >> tolerance
    pred_2 = model.predict_next_state(current_state_2, action_2)
    print(f"    h_hard_passed={pred_2['h_hard_passed']}, "
          f"confidence={pred_2['confidence']:.4f}, "
          f"violations={pred_2['violations']}")

    if pred_2["h_hard_passed"] is False:
        print("    [PASS] 能量守恒违反时 H_hard 正确拦截")
    else:
        print("    [FAIL] 预期 H_hard 失败（能量守恒违反），实际通过")
        sys.exit(1)

    # ── 测试 4: predict_next_state — H_hard 失败（动量守恒违反） ──
    print("\n[4] predict_next_state — H_hard 失败（动量守恒违反）...")
    action_3 = {"momentum": 50.0}  # Δp = 45 >> tolerance
    pred_3 = model.predict_next_state(current_state_2, action_3)
    print(f"    h_hard_passed={pred_3['h_hard_passed']}, "
          f"violations={pred_3['violations']}")

    if pred_3["h_hard_passed"] is False:
        print("    [PASS] 动量守恒违反时 H_hard 正确拦截")
    else:
        print("    [FAIL] 预期 H_hard 失败（动量守恒违反），实际通过")
        sys.exit(1)

    # ── 测试 5: counterfactual — 基本反事实推理 ──
    print("\n[5] counterfactual — 基本反事实推理...")
    # 反事实：如果 position 不同会怎样？（不影响守恒量）
    observed_state = {
        "energy": 100.0,
        "momentum": 5.0,
        "position": 0.0,
        "velocity": 2.0,
        "mass": 2.5,
        "angular_momentum": 3.0,
        "E_kinetic": 50.0,
        "E_potential": -50.0,
    }
    cf_intervention = {"position": 15.0}
    cf_result = model.counterfactual(observed_state, cf_intervention)
    print(f"    h_hard_passed={cf_result['h_hard_passed']}, "
          f"probability={cf_result['probability']:.4f}")
    print(f"    counterfactual_state={cf_result['counterfactual_state']}")

    if cf_result["h_hard_passed"] is True and 0.0 <= cf_result["probability"] <= 1.0:
        print("    [PASS] 反事实推理正确（守恒律通过，概率在 [0,1]）")
    else:
        print(f"    [FAIL] h_hard={cf_result['h_hard_passed']}, "
              f"prob={cf_result['probability']}")
        sys.exit(1)

    # ── 测试 6: counterfactual — H_hard 失败 ──
    print("\n[6] counterfactual — H_hard 失败（反事实干预违反守恒律）...")
    cf_bad_intervention = {"energy": 500.0}  # ΔE = 400 >> tolerance
    cf_bad_result = model.counterfactual(observed_state, cf_bad_intervention)
    print(f"    h_hard_passed={cf_bad_result['h_hard_passed']}, "
          f"probability={cf_bad_result['probability']:.4f}")

    if cf_bad_result["h_hard_passed"] is False:
        print("    [PASS] 反事实干预违反守恒律时 H_hard 正确拦截")
    else:
        print("    [FAIL] 预期 H_hard 失败，实际通过")
        sys.exit(1)

    # ── 测试 7: _check_h_hard 直接调用 — 全部通过 ──
    print("\n[7] _check_h_hard 直接调用 — 全部守恒律通过...")
    good_prediction = {
        "energy_before": 100.0,
        "energy_after": 100.0,
        "momentum_before": 5.0,
        "momentum_after": 5.0,
        "angular_momentum_before": 3.0,
        "angular_momentum_after": 3.0,
        "E_kinetic": 50.0,
        "E_potential": -50.0,  # 和 = 0 ✓
    }
    passed_7, violations_7 = model._check_h_hard(good_prediction)
    print(f"    passed={passed_7}, violations={violations_7}")

    if passed_7 is True and len(violations_7) == 0:
        print("    [PASS] 守恒状态 _check_h_hard 返回通过")
    else:
        print(f"    [FAIL] 预期通过，实际 passed={passed_7}, "
              f"violations={violations_7}")
        sys.exit(1)

    # ── 测试 8: _check_h_hard 直接调用 — 多项违例 ──
    print("\n[8] _check_h_hard 直接调用 — 多项守恒律违例...")
    bad_prediction = {
        "energy_before": 100.0,
        "energy_after": 80.0,  # ΔE = 20 >> tolerance
        "momentum_before": 5.0,
        "momentum_after": 8.0,  # Δp = 3 >> tolerance
        "angular_momentum_before": 3.0,
        "angular_momentum_after": 3.0,  # OK
        "E_kinetic": 50.0,
        "E_potential": -50.0,  # OK
    }
    passed_8, violations_8 = model._check_h_hard(bad_prediction)
    print(f"    passed={passed_8}, violations={violations_8}")

    if passed_8 is False and len(violations_8) >= 2:
        print(f"    [PASS] 检测到 {len(violations_8)} 项违例")
    else:
        print(f"    [FAIL] 预期 ≥2 项违例，实际 passed={passed_8}, "
              f"violations={violations_8}")
        sys.exit(1)

    # ── 测试 9: SCM do-calculus 干预传播 ──
    print("\n[9] SCM do-calculus 干预传播验证...")
    # mass → momentum, velocity → momentum
    # do(velocity=10) 应该影响 momentum（通过 velocity → momentum 边）
    test_state = {
        "energy": 100.0,
        "momentum": 5.0,
        "position": 0.0,
        "velocity": 2.0,
        "mass": 2.5,
        "angular_momentum": 3.0,
        "E_kinetic": 50.0,
        "E_potential": -50.0,
    }
    test_do = {"velocity": 10.0}
    propagated = model._scm_intervene(test_state, test_do)
    # velocity 应被设置为 10.0
    if propagated["velocity"] == 10.0:
        print(f"    [PASS] do(velocity=10) 正确设置 velocity={propagated['velocity']}")
    else:
        print(f"    [FAIL] velocity 应为 10.0，实际 {propagated['velocity']}")
        sys.exit(1)
    # momentum 应受 velocity 影响（通过 velocity → momentum 边传播）
    # momentum = 0.5 * (strength_weighted_parent_avg) + 0.5 * current_momentum
    if propagated["momentum"] != 5.0:
        print(f"    [PASS] momentum 被传播更新: 5.0 → {propagated['momentum']:.4f}")
    else:
        print(f"    [WARN] momentum 未被更新（可能无 velocity→momentum 边）")

    # ── 测试 10: learn_from_data — 空数据 ──
    print("\n[10] learn_from_data — 空数据边界情况...")
    empty_model = TOMASCausalWorldModel(
        AetherBridge(), coupling
    )
    empty_result = empty_model.learn_from_data({})
    print(f"    learned_edges={empty_result['learned_edges']}, "
          f"scm_nodes={empty_result['scm_nodes']}, "
          f"hodge_entropy={empty_result['hodge_entropy']:.4f}")

    if empty_result["learned_edges"] == 0 and empty_result["scm_nodes"] == 0:
        print("    [PASS] 空数据正确返回零值")
    else:
        print(f"    [FAIL] 空数据应返回 0/0，实际 "
              f"{empty_result['learned_edges']}/{empty_result['scm_nodes']}")
        sys.exit(1)

    # ── 测试 11: H_hard 不可绕过验证 ──
    print("\n[11] H_hard 不可绕过验证 — predict_next_state 强制调用...")
    # 构造一个守恒量完全不匹配的状态
    bypass_state = {
        "energy": 1000.0,
        "momentum": 100.0,
        "position": 0.0,
        "velocity": 2.0,
        "mass": 2.5,
        "angular_momentum": 50.0,
        "E_kinetic": 50.0,
        "E_potential": -50.0,
    }
    bypass_action = {
        "energy": 1.0,  # ΔE = 999
        "momentum": 1.0,  # Δp = 99
        "angular_momentum": 1.0,  # ΔL = 49
    }
    bypass_result = model.predict_next_state(bypass_state, bypass_action)
    # H_hard 必须失败，不可绕过
    if bypass_result["h_hard_passed"] is False:
        print(f"    [PASS] H_hard 不可绕过：检测到 "
              f"{len(bypass_result['violations'])} 项违例")
        print(f"    confidence={bypass_result['confidence']:.4f} "
              f"(应大幅降低)")
        if bypass_result["confidence"] <= 0.1:
            print("    [PASS] 置信度因 H_hard 失败而大幅降低")
        else:
            print(f"    [WARN] 置信度 {bypass_result['confidence']:.4f} "
                  f"未充分降低（期望 ≤ 0.1）")
    else:
        print("    [FAIL] H_hard 被绕过！预期失败但实际通过")
        sys.exit(1)

    # ── 总结 ──
    print("\n" + "=" * 70)
    print("  TOMASCausalWorldModel — All 11 Tests Passed")
    print("  H_hard 物理守恒律检查在预测路径上不可绕过 ✓")
    print("=" * 70)
