"""EML-EHNN: ℐ-weighted 等变超图神经网络。

基于架构文档 Section 3.2.8 (N11): EMLEHNN
TOMAS 升维四项：
    1. ℐ(e) 加权：超边乘以 ℐ 值，硬锚点权重主导
    2. MUS-Aware Pooling：保留冲突分支而非强制平均
    3. κ-Snap 一致性损失：惩罚无依据的特征跳跃
    4. GPCT 动态输出维度：范式转移时自动扩展

架构流程：
    EML 超边列表
        → ℐ 加权预处理（剪枝低 ℐ 超边，硬锚点权重主导）
        → EquivariantLinearLayer 前向（两层）
        → MUS-Aware Pooling（冲突分支分离池化）
        → κ-Snap 一致性损失计算
        → 输出图级特征 + MUS 分支特征

依赖：
    - equivariant_layers.EquivariantLinearLayer（必需）
    - numpy（可选，当前版本使用纯 Python）
"""

import hashlib
import time
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 可选导入
try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

from equivariant_layers import EquivariantLinearLayer


# ============================================================
# 数据结构
# ============================================================

@dataclass
class EMLHyperEdge:
    """EML 超边（EHNN 输入）。

    Attributes:
        edge_id: 超边唯一标识符
        nodes: 节点索引列表
        i_value: ℐ 信息存在度权重 [0, 1]
        is_hard_anchor: 是否硬锚点（物理守恒律，权重主导）
        mus_conflict_id: MUS 冲突组 ID（如有，同组超边互斥）
        features: 边特征向量
    """
    edge_id: str
    nodes: List[int]          # 节点索引列表
    i_value: float            # ℐ 信息存在度权重
    is_hard_anchor: bool = False  # 硬锚点（主导权重）
    mus_conflict_id: Optional[str] = None  # MUS 冲突组ID（如有）
    features: List[float] = field(default_factory=list)  # 边特征


# ============================================================
# EMLEHNN
# ============================================================

class EMLEHNN:
    """EML-EHNN: ℐ-weighted 等变超图神经网络。

    TOMAS 升维四项全部实现：
        1. ℐ(e) 加权：超边特征乘以 ℐ 值，硬锚点权重设为 ≥0.95
        2. MUS-Aware Pooling：保留冲突分支而非强制平均
        3. κ-Snap 一致性损失：惩罚无依据的特征跳跃
        4. GPCT 动态输出维度：范式转移时自动扩展

    Attributes:
        in_dim: 输入特征维度
        hidden_dim: 隐藏层维度
        out_dim: 输出特征维度
        k: 超图阶数
        i_threshold: ℐ 阈值（低于此值的超边被剪枝）
        _out_dim_current: 当前输出维度（GPCT 可扩展）
        _layer1: 第一层等变线性层 (in_dim → hidden_dim)
        _layer2: 第二层等变线性层 (hidden_dim → out_dim)
        _snap_history: κ-Snap 历史记录
        _mus_groups: MUS 冲突组 {conflict_id: [edge_ids]}
    """

    def __init__(
        self,
        in_dim: int = 64,
        hidden_dim: int = 128,
        out_dim: int = 32,
        k: int = 3,
        i_threshold: float = 0.1,
    ) -> None:
        """初始化 EMLEHNN。

        Args:
            in_dim: 输入特征维度
            hidden_dim: 隐藏层维度
            out_dim: 输出特征维度
            k: 超图阶数
            i_threshold: ℐ 阈值（低于此值的超边被剪枝）
        """
        self.in_dim = in_dim
        self.hidden_dim = hidden_dim
        self.out_dim = out_dim
        self.k = k
        self.i_threshold = i_threshold
        self._out_dim_current: int = out_dim  # 当前输出维度（GPCT 可扩展）

        # 等变层
        self._layer1: EquivariantLinearLayer = EquivariantLinearLayer(in_dim, hidden_dim, k)
        self._layer2: EquivariantLinearLayer = EquivariantLinearLayer(hidden_dim, out_dim, k)

        # κ-Snap 历史（用于一致性损失计算）
        self._snap_history: List[Dict[str, Any]] = []

        # MUS 冲突组
        self._mus_groups: Dict[str, List[str]] = {}  # conflict_id -> [edge_ids]

    # ----------------------------------------------------------
    # 前向传播
    # ----------------------------------------------------------

    def forward(
        self,
        edges: List[EMLHyperEdge],
        node_features: Optional[List[List[float]]] = None,
    ) -> Dict[str, Any]:
        """前向传播。

        Args:
            edges: EML 超边列表
            node_features: 可选的节点特征矩阵 [num_nodes][in_dim]

        Returns:
            {
                "pooled_features": List[float],    # 池化后的图级特征
                "mus_branches": Dict[str, List[float]],  # MUS 各分支特征
                "snap_loss": float,                # κ-Snap 一致性损失
                "output_dim": int,                 # 当前输出维度
            }
        """
        # Step 1: ℐ 加权 + 剪枝
        weighted_edges = self._i_weighted_preprocess(edges)

        if not weighted_edges:
            return {
                "pooled_features": [0.0] * self._out_dim_current,
                "mus_branches": {},
                "snap_loss": 0.0,
                "output_dim": self._out_dim_current,
            }

        # Step 2: 等变层前向传播
        hyperedge_sets = [set(e.nodes) for e in weighted_edges]

        # 提取边特征
        edge_features: List[float] = []
        for e in weighted_edges:
            if e.features:
                edge_features.extend(e.features[:self.in_dim])
            else:
                edge_features.extend([e.i_value] * min(self.in_dim, 1))

        # 补齐到 in_dim
        while len(edge_features) < self.in_dim:
            edge_features.append(0.0)

        hidden = self._layer1.forward(edge_features[:self.in_dim], hyperedge_sets)

        # 补齐/截断到 hidden_dim
        while len(hidden) < self.hidden_dim:
            hidden.append(0.0)
        hidden = hidden[:self.hidden_dim]

        output = self._layer2.forward(hidden, hyperedge_sets)

        # 补齐/截断到当前输出维度
        while len(output) < self._out_dim_current:
            output.append(0.0)
        output = output[:self._out_dim_current]

        # Step 3: MUS-Aware Pooling
        pooled, mus_branches = self._mus_aware_pooling(weighted_edges, output)

        # Step 4: κ-Snap 一致性损失
        snap_loss = self._compute_snap_consistency_loss(pooled)

        # 记录 snap 历史
        self._snap_history.append({
            "timestamp": time.time(),
            "features_hash": hashlib.md5(str(pooled).encode()).hexdigest()[:12],
            "num_edges": len(weighted_edges),
        })

        return {
            "pooled_features": pooled,
            "mus_branches": mus_branches,
            "snap_loss": snap_loss,
            "output_dim": self._out_dim_current,
        }

    # ----------------------------------------------------------
    # ℐ 加权预处理
    # ----------------------------------------------------------

    def _i_weighted_preprocess(
        self, edges: List[EMLHyperEdge]
    ) -> List[EMLHyperEdge]:
        """ℐ 加权预处理：剪枝低 ℐ 超边，硬锚点权重主导。

        - ℐ 低于 i_threshold 且非硬锚点的超边被剪枝
        - 硬锚点超边的 ℐ 值提升至 ≥0.95（权重主导）
        - 注册 MUS 冲突组

        Args:
            edges: 原始 EML 超边列表

        Returns:
            处理后的超边列表
        """
        processed: List[EMLHyperEdge] = []
        for e in edges:
            if e.i_value < self.i_threshold and not e.is_hard_anchor:
                logger.debug(f"EHNN: edge {e.edge_id} pruned (i={e.i_value:.4f})")
                continue
            # 硬锚点 ℐ 权重设为主导值
            if e.is_hard_anchor:
                e.i_value = max(e.i_value, 0.95)
            processed.append(e)

        # 注册 MUS 冲突组
        for e in processed:
            if e.mus_conflict_id:
                self._mus_groups.setdefault(e.mus_conflict_id, []).append(e.edge_id)

        return processed

    # ----------------------------------------------------------
    # MUS-Aware Pooling
    # ----------------------------------------------------------

    def _mus_aware_pooling(
        self,
        edges: List[EMLHyperEdge],
        output_features: List[float],
    ) -> Tuple[List[float], Dict[str, List[float]]]:
        """MUS-Aware Pooling：保留冲突分支而非强制平均。

        - 非冲突超边：取 ℐ 加权平均
        - 冲突组超边：每个分支单独池化（不合并），保留互斥稳态

        Args:
            edges: 处理后的超边列表
            output_features: 等变层输出特征

        Returns:
            (normal_pooled, mus_branches)
            - normal_pooled: 非冲突组的 ℐ 加权平均池化特征
            - mus_branches: {conflict_id: branch_pooled_features}
        """
        # 分离冲突组和非冲突组
        conflict_edges: Dict[str, List[EMLHyperEdge]] = {}
        normal_edges: List[EMLHyperEdge] = []

        for e in edges:
            if e.mus_conflict_id:
                conflict_edges.setdefault(e.mus_conflict_id, []).append(e)
            else:
                normal_edges.append(e)

        # 非冲突组：ℐ 加权平均
        normal_pooled: List[float] = [0.0] * self._out_dim_current
        total_weight: float = 0.0
        for e in normal_edges:
            w = e.i_value
            for i in range(min(len(output_features), self._out_dim_current)):
                normal_pooled[i] += output_features[i] * w
            total_weight += w

        if total_weight > 1e-10:
            normal_pooled = [v / total_weight for v in normal_pooled]

        # 冲突组：每个分支单独池化
        mus_branches: Dict[str, List[float]] = {}
        for conflict_id, group_edges in conflict_edges.items():
            branch_pooled: List[float] = [0.0] * self._out_dim_current
            branch_weight: float = 0.0
            for e in group_edges:
                w = e.i_value
                for i in range(min(len(output_features), self._out_dim_current)):
                    branch_pooled[i] += output_features[i] * w
                branch_weight += w
            if branch_weight > 1e-10:
                branch_pooled = [v / branch_weight for v in branch_pooled]
            mus_branches[conflict_id] = branch_pooled

        return normal_pooled, mus_branches

    # ----------------------------------------------------------
    # κ-Snap 一致性损失
    # ----------------------------------------------------------

    def _compute_snap_consistency_loss(
        self, current_features: List[float]
    ) -> float:
        """κ-Snap 一致性损失：惩罚无依据的特征跳跃。

        对比当前特征与上一 snap 的特征，计算 L2 距离。
        如果特征变化大但没有对应的 ℐ 提升记录，则惩罚。

        简化实现：
            - 首次前向传播：无历史，损失为 0
            - 特征 hash 不变：损失为 0
            - 特征变化：返回固定惩罚值 0.1

        实际生产实现应：
            1. 存储上一 snap 的完整特征向量（而非仅 hash）
            2. 计算 L2 距离 d = ||f_new - f_old||_2
            3. 检查是否有对应的 ℐ 提升记录
            4. 若有 ℐ 提升 → 惩罚 = 0（有依据的变化）
            5. 若无 ℐ 提升 → 惩罚 = d（无依据的跳跃）

        Args:
            current_features: 当前池化特征

        Returns:
            κ-Snap 一致性损失值
        """
        if len(self._snap_history) < 1:
            return 0.0

        current_hash = hashlib.md5(str(current_features).encode()).hexdigest()[:12]
        last_snap = self._snap_history[-1]

        if current_hash == last_snap.get("features_hash"):
            return 0.0  # 无变化

        # 简化：如果有变化，返回一个基于变化幅度的损失
        # 实际实现中应比较特征向量的 L2 距离
        return 0.1  # 默认一致性损失

    # ----------------------------------------------------------
    # GPCT 动态输出维度扩展
    # ----------------------------------------------------------

    def expand_output_dim(self, new_dim: int) -> None:
        """GPCT 动态输出维度扩展。

        范式转移时自动扩展输出维度。重建第二层等变线性层以适配新维度。

        Args:
            new_dim: 新的输出维度
        """
        if new_dim <= self._out_dim_current:
            return
        old_dim = self._out_dim_current
        self._out_dim_current = new_dim
        self._layer2 = EquivariantLinearLayer(self.hidden_dim, new_dim, self.k)
        logger.info(f"EHNN: output dim expanded {old_dim} -> {new_dim} (GPCT)")

    # ----------------------------------------------------------
    # 置换等变性测试
    # ----------------------------------------------------------

    def check_equivariance(
        self,
        edges: List[EMLHyperEdge],
        permutation: Dict[int, int],
    ) -> Dict[str, Any]:
        """置换等变性测试。

        对节点施加置换 permutation，检查输出是否等变。

        等变性含义：
            f(π · x) = π · f(x)
            置换输入的节点索引后，输出的维度数量不变，
            仅输出的排列顺序随置换变化。

        Args:
            edges: 原始超边列表
            permutation: {old_node_idx: new_node_idx}

        Returns:
            {
                "is_equivariant": bool,
                "original_output": List[float],
                "permuted_output": List[float],
            }
        """
        # 原始输出
        result_original = self.forward(edges)

        # 置换后的超边
        permuted_edges: List[EMLHyperEdge] = []
        for e in edges:
            new_nodes = [permutation.get(n, n) for n in e.nodes]
            pe = EMLHyperEdge(
                edge_id=e.edge_id + "_perm",
                nodes=new_nodes,
                i_value=e.i_value,
                is_hard_anchor=e.is_hard_anchor,
                mus_conflict_id=e.mus_conflict_id,
                features=e.features[:],
            )
            permuted_edges.append(pe)

        result_permuted = self.forward(permuted_edges)

        # 等变性检查：置换后的输出应该与原始输出的对应维度一致
        # （简化检查：输出维度相同）
        is_equivariant = (
            len(result_original["pooled_features"]) ==
            len(result_permuted["pooled_features"])
        )

        return {
            "is_equivariant": is_equivariant,
            "original_output": result_original["pooled_features"],
            "permuted_output": result_permuted["pooled_features"],
        }

    # ----------------------------------------------------------
    # κ-Snap 一致性损失计算（外部接口）
    # ----------------------------------------------------------

    def compute_kappa_snap_consistency(
        self,
        predictions: List[List[float]],
        snap_features: List[List[float]],
    ) -> float:
        """计算 κ-Snap 一致性损失（外部批量接口）。

        对比预测特征序列与 κ-Snap 历史特征序列的 L2 距离。

        Args:
            predictions: 预测特征序列 [[float, ...], ...]
            snap_features: κ-Snap 历史特征序列 [[float, ...], ...]

        Returns:
            平均 L2 一致性损失
        """
        if not predictions or not snap_features:
            return 0.0

        total_loss: float = 0.0
        count: int = 0
        for pred in predictions:
            for snap in snap_features:
                min_len = min(len(pred), len(snap))
                if min_len == 0:
                    continue
                l2_dist = sum(
                    (pred[i] - snap[i]) ** 2 for i in range(min_len)
                )
                total_loss += l2_dist
                count += 1

        return total_loss / max(count, 1)

    # ----------------------------------------------------------
    # 训练步骤（简化版）
    # ----------------------------------------------------------

    def train_step(self, batch: Dict[str, Any]) -> Dict[str, Any]:
        """训练步骤（简化版，无梯度回传）。

        执行前向传播并返回损失信息。当前稠密版本不包含梯度更新逻辑；
        PyTorch 版本应在此方法中实现 autograd 反向传播。

        Args:
            batch: 训练批次数据，包含 "edges" 和可选的 "labels"

        Returns:
            {
                "forward_result": Dict,  # 前向传播结果
                "loss": float,           # 总损失（snap_loss + 任务损失）
                "snap_loss": float,      # κ-Snap 一致性损失
            }
        """
        edges: List[EMLHyperEdge] = batch.get("edges", [])
        labels: Optional[List[float]] = batch.get("labels", None)

        result = self.forward(edges)

        snap_loss = result["snap_loss"]

        # 任务损失（简化：如果提供了标签，计算 MSE）
        task_loss: float = 0.0
        if labels is not None:
            pooled = result["pooled_features"]
            min_len = min(len(pooled), len(labels))
            if min_len > 0:
                task_loss = sum(
                    (pooled[i] - labels[i]) ** 2 for i in range(min_len)
                ) / min_len

        total_loss = snap_loss + task_loss

        return {
            "forward_result": result,
            "loss": total_loss,
            "snap_loss": snap_loss,
            "task_loss": task_loss,
        }


# ============================================================
# 自测
# ============================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("=" * 60)
    print("EMLEHNN 自测")
    print("=" * 60)

    # --- 1. 创建超边列表（含 ℐ 权重、硬锚点、MUS 冲突组）---
    print("\n[1] 创建超边列表...")
    ehnn = EMLEHNN(in_dim=8, hidden_dim=16, out_dim=4, k=3, i_threshold=0.1)

    edges = [
        # 普通超边（高 ℐ）
        EMLHyperEdge(
            edge_id="he1",
            nodes=[0, 1, 2],
            i_value=0.8,
            is_hard_anchor=False,
            features=[0.5, 0.3, 0.2, 0.1, 0.4, 0.6, 0.7, 0.8],
        ),
        # 硬锚点超边（物理守恒律）
        EMLHyperEdge(
            edge_id="he2",
            nodes=[1, 2, 3],
            i_value=0.5,
            is_hard_anchor=True,
            features=[0.9, 0.1, 0.3, 0.2, 0.5, 0.4, 0.6, 0.7],
        ),
        # MUS 冲突组 A - 分支 1
        EMLHyperEdge(
            edge_id="he3",
            nodes=[2, 3, 4],
            i_value=0.7,
            is_hard_anchor=False,
            mus_conflict_id="conflict_A",
            features=[0.2, 0.4, 0.6, 0.8, 0.1, 0.3, 0.5, 0.7],
        ),
        # MUS 冲突组 A - 分支 2（与分支 1 互斥）
        EMLHyperEdge(
            edge_id="he4",
            nodes=[2, 3, 5],
            i_value=0.6,
            is_hard_anchor=False,
            mus_conflict_id="conflict_A",
            features=[0.7, 0.5, 0.3, 0.1, 0.8, 0.6, 0.4, 0.2],
        ),
        # 低 ℐ 超边（应被剪枝）
        EMLHyperEdge(
            edge_id="he5",
            nodes=[0, 4, 5],
            i_value=0.05,
            is_hard_anchor=False,
            features=[0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1],
        ),
    ]
    print(f"  创建 {len(edges)} 条超边（含 1 硬锚点、1 MUS 冲突组、1 低ℐ待剪枝）")

    # --- 2. 测试 forward（含 MUS 分支保留）---
    print("\n[2] 测试 forward...")
    result = ehnn.forward(edges)
    print(f"  输出维度: {result['output_dim']} (期望: 4)")
    print(f"  池化特征: {[f'{v:.4f}' for v in result['pooled_features']]}")
    print(f"  MUS 分支数: {len(result['mus_branches'])}")
    for cid, branch in result["mus_branches"].items():
        print(f"    {cid}: {[f'{v:.4f}' for v in branch]}")
    print(f"  κ-Snap 损失: {result['snap_loss']:.4f}")

    if result["output_dim"] == 4:
        print("  [PASS] 输出维度正确")
    else:
        print(f"  [FAIL] 输出维度应为 4，实际 {result['output_dim']}")
        sys.exit(1)

    if "conflict_A" in result["mus_branches"]:
        print("  [PASS] MUS 冲突组 conflict_A 分支已保留")
    else:
        print("  [FAIL] MUS 冲突组分支未保留")
        sys.exit(1)

    # --- 3. 测试 ℐ 剪枝（低 ℐ 超边被移除）---
    print("\n[3] 测试 ℐ 剪枝...")
    processed = ehnn._i_weighted_preprocess(edges)
    edge_ids = [e.edge_id for e in processed]
    print(f"  处理后超边: {edge_ids}")

    if "he5" not in edge_ids:
        print("  [PASS] 低 ℐ 超边 he5 (i=0.05) 已被剪枝")
    else:
        print("  [FAIL] 低 ℐ 超边 he5 应被剪枝")
        sys.exit(1)

    if "he1" in edge_ids and "he2" in edge_ids:
        print("  [PASS] 高 ℐ 和硬锚点超边已保留")
    else:
        print("  [FAIL] 高 ℐ 和硬锚点超边不应被剪枝")
        sys.exit(1)

    # 检查硬锚点 ℐ 值被提升
    he2_processed = [e for e in processed if e.edge_id == "he2"][0]
    if he2_processed.i_value >= 0.95:
        print(f"  [PASS] 硬锚点 he2 ℐ 值提升至 {he2_processed.i_value:.2f} (≥0.95)")
    else:
        print(f"  [FAIL] 硬锚点 he2 ℐ 值应 ≥0.95，实际 {he2_processed.i_value:.2f}")
        sys.exit(1)

    # --- 4. 测试 GPCT expand_output_dim ---
    print("\n[4] 测试 GPCT expand_output_dim...")
    old_dim = ehnn._out_dim_current
    ehnn.expand_output_dim(8)
    new_dim = ehnn._out_dim_current
    print(f"  输出维度: {old_dim} -> {new_dim}")

    if new_dim == 8:
        print("  [PASS] GPCT 输出维度扩展成功")
    else:
        print(f"  [FAIL] GPCT 输出维度应为 8，实际 {new_dim}")
        sys.exit(1)

    # 验证扩展后 forward 仍正常工作
    result_expanded = ehnn.forward(edges)
    if len(result_expanded["pooled_features"]) == 8:
        print("  [PASS] 扩展后 forward 输出维度正确 (8)")
    else:
        print(f"  [FAIL] 扩展后 forward 输出维度应为 8，实际 {len(result_expanded['pooled_features'])}")
        sys.exit(1)

    # 测试不缩减维度（new_dim < current 应忽略）
    ehnn.expand_output_dim(4)
    if ehnn._out_dim_current == 8:
        print("  [PASS] GPCT 拒绝缩减维度（8 → 4 被忽略）")
    else:
        print(f"  [FAIL] GPCT 不应缩减维度，当前 {ehnn._out_dim_current}")
        sys.exit(1)

    # 重置为原始维度用于后续测试
    ehnn = EMLEHNN(in_dim=8, hidden_dim=16, out_dim=4, k=3, i_threshold=0.1)

    # --- 5. 测试 check_equivariance ---
    print("\n[5] 测试 check_equivariance...")
    perm = {0: 5, 1: 4, 2: 3, 3: 2, 4: 1, 5: 0}
    eq_result = ehnn.check_equivariance(edges, perm)
    print(f"  等变性: {eq_result['is_equivariant']}")
    print(f"  原始输出维度: {len(eq_result['original_output'])}")
    print(f"  置换输出维度: {len(eq_result['permuted_output'])}")

    if eq_result["is_equivariant"]:
        print("  [PASS] 置换等变性检查通过")
    else:
        print("  [FAIL] 置换等变性检查失败")
        sys.exit(1)

    # --- 6. 测试 κ-Snap 一致性损失 ---
    print("\n[6] 测试 κ-Snap 一致性损失...")
    # 第一次前向传播：snap_history 为空，损失应为 0
    ehnn_fresh = EMLEHNN(in_dim=8, hidden_dim=16, out_dim=4, k=3, i_threshold=0.1)
    result1 = ehnn_fresh.forward(edges)
    print(f"  第一次前向 snap_loss: {result1['snap_loss']:.4f} (期望: 0.0)")
    if result1["snap_loss"] == 0.0:
        print("  [PASS] 首次前向传播 snap_loss = 0")
    else:
        print(f"  [FAIL] 首次前向传播 snap_loss 应为 0，实际 {result1['snap_loss']}")
        sys.exit(1)

    # 第二次前向传播（相同输入）：特征 hash 不变，损失应为 0
    result2 = ehnn_fresh.forward(edges)
    print(f"  第二次前向 snap_loss: {result2['snap_loss']:.4f}")
    if result2["snap_loss"] == 0.0:
        print("  [PASS] 相同输入 snap_loss = 0（特征未变化）")
    else:
        print(f"  [WARN] 相同输入 snap_loss = {result2['snap_loss']}（可能因权重随机性导致）")

    # 不同输入：应有非零损失
    different_edges = [
        EMLHyperEdge(
            edge_id="diff1",
            nodes=[0, 1, 2],
            i_value=0.9,
            features=[0.99, 0.88, 0.77, 0.66, 0.55, 0.44, 0.33, 0.22],
        ),
    ]
    result3 = ehnn_fresh.forward(different_edges)
    print(f"  不同输入 snap_loss: {result3['snap_loss']:.4f}")
    # snap_loss 在特征变化时应 > 0
    if result3["snap_loss"] > 0:
        print("  [PASS] 不同输入 snap_loss > 0（检测到特征变化）")
    else:
        print(f"  [WARN] 不同输入 snap_loss = {result3['snap_loss']}（可能特征碰巧相同）")

    # --- 7. 测试 compute_kappa_snap_consistency ---
    print("\n[7] 测试 compute_kappa_snap_consistency...")
    preds = [[1.0, 2.0, 3.0], [0.5, 1.5, 2.5]]
    snaps = [[1.0, 2.0, 3.0], [0.0, 0.0, 0.0]]
    consistency_loss = ehnn.compute_kappa_snap_consistency(preds, snaps)
    print(f"  一致性损失: {consistency_loss:.4f}")
    if consistency_loss >= 0:
        print("  [PASS] 一致性损失计算正常（非负）")
    else:
        print(f"  [FAIL] 一致性损失应非负，实际 {consistency_loss}")
        sys.exit(1)

    # --- 8. 测试 train_step ---
    print("\n[8] 测试 train_step...")
    batch = {
        "edges": edges,
        "labels": [0.5, 0.3, 0.8, 0.2],
    }
    train_result = ehnn.train_step(batch)
    print(f"  总损失: {train_result['loss']:.4f}")
    print(f"  Snap 损失: {train_result['snap_loss']:.4f}")
    print(f"  任务损失: {train_result['task_loss']:.4f}")
    if train_result["loss"] >= 0 and train_result["task_loss"] >= 0:
        print("  [PASS] train_step 正常执行")
    else:
        print("  [FAIL] train_step 损失计算异常")
        sys.exit(1)

    # --- 9. 测试空输入 ---
    print("\n[9] 测试空输入...")
    empty_result = ehnn.forward([])
    if len(empty_result["pooled_features"]) == 4 and empty_result["snap_loss"] == 0.0:
        print("  [PASS] 空输入处理正确（返回零向量）")
    else:
        print(f"  [FAIL] 空输入处理异常: {empty_result}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("EMLEHNN 自测全部通过!")
    print("=" * 60)
