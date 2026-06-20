"""
向量时钟 (Vector Clock) — 分布式因果顺序检测

VC_a < VC_b (happened-before) ⟺ ∀i: VC_a[i] ≤ VC_b[i] ∧ ∃j: VC_a[j] < VC_b[j]

用于 AgentWeb 多节点通信中确定事件的因果顺序，支持：
- 本地事件自增 (tick)
- 发送消息时返回快照 (send)
- 接收消息时合并远程时钟 (receive)
- 判断 happened-before 关系
- 判断并发 (无因果关系)
- 合并两个向量时钟 (merge)

零外部依赖，可独立验证。
"""

import copy
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class VectorClock:
    """向量时钟：分布式因果顺序检测

    每个节点维护一个向量 clock[node_id] = logical_time，
    通过 happened-before 关系判断事件的因果顺序。

    Attributes:
        clock: 向量时钟字典 {node_id: logical_time}
        node_id: 当前节点 ID
        all_node_ids: 所有已知节点 ID 列表（有序，用于稳定迭代）
    """

    def __init__(self, node_id: str, all_node_ids: List[str]) -> None:
        """初始化向量时钟。

        所有节点时钟归零，记录本节点 ID 和全部已知节点列表。

        Args:
            node_id: 当前节点 ID
            all_node_ids: 所有已知节点 ID 列表

        Raises:
            ValueError: 若 node_id 不在 all_node_ids 中
        """
        if node_id not in all_node_ids:
            raise ValueError(
                f"node_id '{node_id}' must be in all_node_ids ({all_node_ids})"
            )
        self.node_id: str = node_id
        self.all_node_ids: List[str] = list(all_node_ids)  # 保持稳定顺序
        self.clock: Dict[str, int] = {nid: 0 for nid in self.all_node_ids}
        logger.debug(
            "VectorClock 初始化: node=%s, nodes=%s", self.node_id, self.all_node_ids
        )

    def tick(self) -> None:
        """本地事件：自增本节点的逻辑时钟。

        self.clock[self.node_id] += 1

        应在任何本地事件（计算、状态变更）后调用。
        """
        self.clock[self.node_id] += 1
        logger.debug("VectorClock tick: node=%s → %d", self.node_id, self.clock[self.node_id])

    def send(self) -> Dict[str, int]:
        """发送事件：先 tick 再返回当前快照副本。

        发送消息时调用此方法，获取当前向量时钟快照附加到消息中。

        Returns:
            向量时钟快照字典 {node_id: logical_time, ...}
        """
        self.tick()
        snapshot = self.to_dict()
        logger.debug("VectorClock send: node=%s, snapshot=%s", self.node_id, snapshot)
        return snapshot

    def receive(self, remote_vc: Dict[str, int]) -> None:
        """接收事件：合并远程向量时钟。

        算法：
            1. local[i] = max(local[i], remote[i]) for all i
            2. local[self.node_id] += 1  （接收本身也是一个事件）

        Args:
            remote_vc: 远程向量时钟快照 {node_id: logical_time}
        """
        # 逐元素取 max
        for node_id in self.all_node_ids:
            remote_val = remote_vc.get(node_id, 0)
            if remote_val > self.clock[node_id]:
                self.clock[node_id] = remote_val

        # 自增本节点（接收事件）
        self.clock[self.node_id] += 1

        logger.debug(
            "VectorClock receive: remote=%s → local=%s", remote_vc, self.clock
        )

    def happened_before(self, other: "VectorClock") -> bool:
        """判断 self 是否 happened-before other（严格小于）。

        VC_a < VC_b (happened-before) ⟺
            ∀i: VC_a[i] ≤ VC_b[i]  ∧  ∃j: VC_a[j] < VC_b[j]

        Args:
            other: 另一个 VectorClock 实例

        Returns:
            True 若 self 严格 happened-before other
        """
        # 确保两组时钟的节点集一致
        all_nodes = set(self.clock.keys()) | set(other.clock.keys())

        all_less_or_equal = True
        has_strict_less = False

        for node_id in all_nodes:
            a_val = self.clock.get(node_id, 0)
            b_val = other.clock.get(node_id, 0)
            if a_val > b_val:
                return False  # 存在 self[i] > other[i]，不满足 ≤ 条件
            if a_val < b_val:
                has_strict_less = True

        return all_less_or_equal and has_strict_less

    def concurrent_with(self, other: "VectorClock") -> bool:
        """判断两个事件是否并发（无因果关系）。

        两个事件并发 ⟺ 既不是 self → other，也不是 other → self，
        且两者的时钟不完全相同（相同时钟 = 同一因果状态，非并发）。

        Args:
            other: 另一个 VectorClock 实例

        Returns:
            True 若两个事件无因果关系（并发）
        """
        # 相同时钟 = 同一因果状态，不是并发事件
        if self.clock == other.clock:
            return False
        return (not self.happened_before(other)) and (not other.happened_before(self))

    def less_or_equal(self, other: "VectorClock") -> bool:
        """helper: 判断 self 是否 ≤ other（每个分量都 ≤）。

        ∀i: self[i] ≤ other[i]

        这是 happened_before 的宽松版本（允许相等）。

        Args:
            other: 另一个 VectorClock 实例

        Returns:
            True 若 ∀i: self[i] ≤ other[i]
        """
        all_nodes = set(self.clock.keys()) | set(other.clock.keys())
        for node_id in all_nodes:
            if self.clock.get(node_id, 0) > other.clock.get(node_id, 0):
                return False
        return True

    def merge(self, other: "VectorClock") -> "VectorClock":
        """合并两个向量时钟，返回新的 VectorClock。

        result[i] = max(self[i], other[i]) for all i

        Args:
            other: 另一个 VectorClock 实例

        Returns:
            新的 VectorClock 实例，各分量取两者最大值
        """
        all_node_ids = list(set(self.all_node_ids) | set(other.all_node_ids))
        # 使用 self 的 node_id 创建新实例（合并后的时钟以当前节点身份）
        merged = VectorClock(self.node_id, all_node_ids)
        for node_id in all_node_ids:
            merged.clock[node_id] = max(
                self.clock.get(node_id, 0),
                other.clock.get(node_id, 0),
            )
        return merged

    def to_dict(self) -> Dict[str, int]:
        """返回当前时钟快照（副本）。

        Returns:
            向量时钟字典 {node_id: logical_time, ...}
        """
        return dict(self.clock)

    def __repr__(self) -> str:
        """可读表示。"""
        entries = ", ".join(
            f"{nid}:{self.clock[nid]}" for nid in self.all_node_ids
        )
        return f"VectorClock(node={self.node_id}, {{{entries}}})"

    def __eq__(self, other: object) -> bool:
        """判断两个向量时钟是否完全相等。"""
        if not isinstance(other, VectorClock):
            return NotImplemented
        return self.clock == other.clock and self.node_id == other.node_id

    def __getitem__(self, node_id: str) -> int:
        """通过下标访问 clock[node_id]。"""
        return self.clock[node_id]


# ---------------------------------------------------------------------------
# 自测 (__main__)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("VectorClock 自测")
    print("=" * 60)

    # ---- 测试1: 基本初始化与 tick ----
    print("\n[测试1] 基本初始化与 tick...")
    vc_a = VectorClock("A", ["A", "B", "C"])
    assert vc_a.to_dict() == {"A": 0, "B": 0, "C": 0}, f"初始化失败: {vc_a.to_dict()}"

    vc_a.tick()  # A:1
    assert vc_a.to_dict() == {"A": 1, "B": 0, "C": 0}, f"tick 后失败: {vc_a.to_dict()}"
    print("  通过 ✓")

    # ---- 测试2: send 返回快照 ----
    print("\n[测试2] send 返回快照...")
    vc_b = VectorClock("B", ["A", "B", "C"])
    snapshot = vc_b.send()  # tick + snapshot → B:1
    assert snapshot == {"A": 0, "B": 1, "C": 0}, f"send 快照错误: {snapshot}"
    assert vc_b.to_dict() == {"A": 0, "B": 1, "C": 0}
    print("  通过 ✓")

    # ---- 测试3: receive 合并远程时钟 ----
    print("\n[测试3] receive 合并远程时钟...")
    vc_c = VectorClock("C", ["A", "B", "C"])
    # C 接收 B 发来的消息（B 的时钟快照: {A:0, B:1, C:0}）
    vc_c.receive({"A": 0, "B": 1, "C": 0})
    # 合并后：C 取各分量 max，然后 C 自增
    assert vc_c.to_dict() == {"A": 0, "B": 1, "C": 1}, f"receive 后失败: {vc_c.to_dict()}"
    print("  通过 ✓")

    # ---- 测试4: happened_before 基本判断 ----
    print("\n[测试4] happened_before 基本判断...")
    vc_x = VectorClock("A", ["A", "B", "C"])
    vc_y = VectorClock("B", ["A", "B", "C"])

    vc_x.tick()  # A:1
    assert vc_x.to_dict() == {"A": 1, "B": 0, "C": 0}

    vc_y.receive(vc_x.to_dict())  # B 接收 A 的消息: max + self-increment
    assert vc_y.to_dict() == {"A": 1, "B": 1, "C": 0}, f"receive 后: {vc_y.to_dict()}"

    vc_x_before = copy.deepcopy(vc_x)  # {A:1, B:0, C:0}
    vc_x.tick()  # A:2

    assert vc_x_before.happened_before(vc_x), (
        f"vc_x_before={vc_x_before} 应该 happened-before vc_x={vc_x}"
    )
    assert not vc_x.happened_before(vc_x_before), "反方向不应成立"
    print("  通过 ✓")

    # ---- 测试5: 并发检测 ----
    print("\n[测试5] 并发检测...")
    vc_p = VectorClock("A", ["A", "B"])
    vc_q = VectorClock("B", ["A", "B"])

    vc_p.tick()  # {A:1, B:0}
    vc_q.tick()  # {A:0, B:1}

    assert vc_p.concurrent_with(vc_q), (
        f"vc_p={vc_p} 和 vc_q={vc_q} 应该是并发的"
    )
    assert vc_q.concurrent_with(vc_p), "并发关系应该对称"
    print("  通过 ✓")

    # ---- 测试6: happened_before 传递性 ----
    print("\n[测试6] happened_before 传递性...")
    vc_1 = VectorClock("A", ["A", "B", "C"])
    vc_2 = VectorClock("A", ["A", "B", "C"])
    vc_3 = VectorClock("A", ["A", "B", "C"])

    vc_1.tick()  # A:1
    vc_2.clock = {"A": 1, "B": 1, "C": 0}  # 模拟 B 的事件
    vc_3.clock = {"A": 2, "B": 1, "C": 1}  # 模拟后续事件

    assert vc_1.happened_before(vc_2), f"vc_1={vc_1} 应该 happened-before vc_2={vc_2}"
    assert vc_2.happened_before(vc_3), f"vc_2={vc_2} 应该 happened-before vc_3={vc_3}"
    assert vc_1.happened_before(vc_3), f"传递性: vc_1={vc_1} 应该 happened-before vc_3={vc_3}"
    print("  通过 ✓")

    # ---- 测试7: 相同时钟不满足 happened-before ----
    print("\n[测试7] 相同时钟不应 happened-before...")
    vc_same1 = VectorClock("A", ["A", "B"])
    vc_same2 = VectorClock("A", ["A", "B"])
    vc_same1.tick()
    vc_same2.tick()
    # 两者都是 {A:1, B:0}，完全相同
    assert not vc_same1.happened_before(vc_same2), "相同时钟不应该 happened-before"
    assert not vc_same2.happened_before(vc_same1), "相同时钟反向也不应成立"
    assert not vc_same1.concurrent_with(vc_same2), "相同时钟不是并发（是完全相同的因果状态）"
    print("  通过 ✓")

    # ---- 测试8: less_or_equal 辅助方法 ----
    print("\n[测试8] less_or_equal 辅助方法...")
    vc_le_a = VectorClock("A", ["A", "B"])
    vc_le_b = VectorClock("A", ["A", "B"])
    vc_le_a.tick()        # {A:1, B:0}
    vc_le_b.tick()        # {A:1, B:0}
    vc_le_b.tick()        # {A:2, B:0}

    assert vc_le_a.less_or_equal(vc_le_b), f"{vc_le_a} 应该 ≤ {vc_le_b}"
    assert vc_le_a.less_or_equal(vc_le_a), "自己应该 ≤ 自己"
    assert not vc_le_b.less_or_equal(vc_le_a), f"{vc_le_b} 不应该 ≤ {vc_le_a}"
    print("  通过 ✓")

    # ---- 测试9: merge 合并 ----
    print("\n[测试9] merge 合并...")
    vc_m1 = VectorClock("A", ["A", "B", "C"])
    vc_m2 = VectorClock("B", ["A", "B", "C"])

    vc_m1.tick()  # {A:1, B:0, C:0}
    vc_m2.tick()  # {A:0, B:1, C:0}

    merged = vc_m1.merge(vc_m2)
    assert merged.clock == {"A": 1, "B": 1, "C": 0}, f"merge 结果错误: {merged.clock}"
    # 合并使用 self 的 node_id
    assert merged.node_id == "A"
    print("  通过 ✓")

    # ---- 测试10: ValueError on invalid node_id ----
    print("\n[测试10] 无效 node_id 应抛出 ValueError...")
    try:
        VectorClock("X", ["A", "B"])
        assert False, "应该抛出 ValueError"
    except ValueError:
        pass
    print("  通过 ✓")

    # ---- 测试11: __repr__ ----
    print("\n[测试11] __repr__ 可读性...")
    vc_repr = VectorClock("A", ["A", "B"])
    vc_repr.tick()
    r = repr(vc_repr)
    assert "VectorClock" in r
    assert "A" in r
    assert "1" in r
    print(f"  repr: {r}")
    print("  通过 ✓")

    # ---- 测试12: receive 中缺失节点默认值为 0 ----
    print("\n[测试12] receive 中缺失节点默认值...")
    vc_d = VectorClock("A", ["A", "B", "C"])
    # remote_vc 中缺少某些节点
    vc_d.receive({"A": 3})  # 只有 A
    # receive: max(local, remote) → A=max(0,3)=3, B=max(0,0)=0, C=max(0,0)=0
    # 然后 self_increment → A=4
    assert vc_d.to_dict()["A"] == 4, (
        f"A: receive 先取 max(0,3)=3，再自增 +1=4: {vc_d.to_dict()}"
    )
    assert vc_d.to_dict()["B"] == 0, f"B 默认为 0: {vc_d.to_dict()}"
    assert vc_d.to_dict()["C"] == 0, f"C 默认为 0: {vc_d.to_dict()}"
    print("  通过 ✓")

    print("\n" + "=" * 60)
    print("所有 VectorClock 测试通过！ ✓")
    print("=" * 60)
