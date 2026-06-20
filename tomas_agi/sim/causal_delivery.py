"""
因果交付缓冲 (CausalDeliveryBuffer) — 收端缓冲并发消息直到因果前置到齐

基于向量时钟实现因果消息的按序交付：
- 消息的因果前置未到齐时，放入 pending 缓冲
- 前置到齐后，交付消息并级联解锁 pending 中的后续消息
- 支持超时降级强制清空缓冲区

零外部依赖（除 vector_clock.py），可独立验证。
"""

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from vector_clock import VectorClock

logger = logging.getLogger(__name__)


@dataclass
class AgentWebMessage:
    """AgentWeb 因果消息。

    在 AgentWeb 节点间传递的消息，携带向量时钟用于因果顺序检测。

    Attributes:
        msg_id: 消息唯一标识符
        source_node: 发送方节点 ID
        target_node: 接收方节点 ID
        vector_clock: 发送时刻的向量时钟快照 {node_id: logical_time}
        snap_ref: 可选的 κ-Snap 引用 ID
        content: 可选的消/息内容
        timestamp: Unix 时间戳
    """

    msg_id: str
    source_node: str
    target_node: str
    vector_clock: Dict[str, int]
    snap_ref: Optional[str] = None
    content: Optional[Dict] = None
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        """自动填充时间戳。"""
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class CausalDeliveryBuffer:
    """因果交付缓冲：收端缓冲并发消息直到因果前置到齐，级联解锁。

    每个 AgentWeb 节点维护一个 CausalDeliveryBuffer，
    用于保证消息按因果顺序交付给上层处理逻辑。

    核心算法：
        - check_ready: 检查消息的因果前置是否已全部到达
          条件：
            1. ∀i ≠ source_node: msg.vc[i] ≤ local_vc[i]
            2. msg.vc[source_node] == local_vc[source_node] + 1
        - deliver: 若前置到齐则交付 + 级联解锁，否则缓冲
        - flush: 超时降级，强制清空缓冲区

    Attributes:
        local_vc: 本地节点的向量时钟引用
        pending: 待交付消息缓冲区 {msg_id: AgentWebMessage}
        delivered_vc_snapshots: 已交付消息的向量时钟记录（用于审计）
    """

    def __init__(self, local_vc: VectorClock) -> None:
        """初始化因果交付缓冲。

        Args:
            local_vc: 本地节点的向量时钟实例
        """
        self.local_vc: VectorClock = local_vc
        self.pending: Dict[str, AgentWebMessage] = {}
        self.delivered_vc_snapshots: List[Dict[str, int]] = []
        logger.debug(
            "CausalDeliveryBuffer 初始化: node=%s, vc=%s",
            self.local_vc.node_id,
            self.local_vc.to_dict(),
        )

    def deliver(self, msg: AgentWebMessage) -> List[AgentWebMessage]:
        """尝试交付消息。

        流程：
            1. 若 check_ready(msg) → 立即交付，更新 local_vc，
               然后级联检查 pending 中所有消息（连锁解锁）
            2. 若未就绪 → 放入 pending 缓冲

        Args:
            msg: 待交付的 AgentWebMessage

        Returns:
            本次交付的消息列表（可能 > 1，因级联解锁），按因果顺序排列
        """
        delivered_messages: List[AgentWebMessage] = []

        # 先检查新消息是否就绪
        if self.check_ready(msg):
            # 交付此消息
            self._commit_delivery(msg)
            delivered_messages.append(msg)

            # 级联解锁：检查 pending 中是否有消息因本次交付而解锁
            delivered_messages.extend(self._cascade_unlock())

            logger.info(
                "CausalDeliveryBuffer 交付: msg_id=%s, source=%s → target=%s, "
                "cascade_count=%d, pending_count=%d",
                msg.msg_id,
                msg.source_node,
                msg.target_node,
                len(delivered_messages) - 1,
                len(self.pending),
            )
        else:
            # 未就绪，放入缓冲
            self.pending[msg.msg_id] = msg
            logger.debug(
                "CausalDeliveryBuffer 缓冲: msg_id=%s, source=%s, "
                "msg_vc=%s, local_vc=%s, pending_count=%d",
                msg.msg_id,
                msg.source_node,
                msg.vector_clock,
                self.local_vc.to_dict(),
                len(self.pending),
            )

        return delivered_messages

    def check_ready(self, msg: AgentWebMessage) -> bool:
        """检查消息的因果前置是否已全部到达。

        条件：
            1. 对每个节点 i ≠ source_node:
               msg.vector_clock[i] ≤ local_vc.clock[i]
               （其他节点的所有前置事件已到达）
            2. msg.vector_clock[source_node] == local_vc.clock[source_node] + 1
               （发件方的上一个事件已到达，这个消息恰好是下一个）

        Args:
            msg: 待检查的 AgentWebMessage

        Returns:
            True 若因果前置已全部到达，消息可交付
        """
        local_clock = self.local_vc.clock
        msg_vc = msg.vector_clock
        source = msg.source_node

        # 条件1：检查其他所有节点的前置条件
        for node_id in local_clock:
            if node_id == source:
                continue
            msg_val = msg_vc.get(node_id, 0)
            local_val = local_clock.get(node_id, 0)
            if msg_val > local_val:
                # 其他节点的事件尚未到达
                logger.debug(
                    "check_ready=False: msg_id=%s, node=%s 前置未到齐 "
                    "(msg_vc[%s]=%d > local_vc[%s]=%d)",
                    msg.msg_id, node_id, node_id, msg_val, node_id, local_val,
                )
                return False

        # 条件2：发件方的上一个事件已到达（恰好是下一个事件）
        msg_source_val = msg_vc.get(source, 0)
        local_source_val = local_clock.get(source, 0)
        if msg_source_val != local_source_val + 1:
            logger.debug(
                "check_ready=False: msg_id=%s, source=%s 未连续 "
                "(msg_vc[%s]=%d ≠ local_vc[%s]+1=%d)",
                msg.msg_id, source, source, msg_source_val, source, local_source_val + 1,
            )
            return False

        return True

    def flush(self) -> List[AgentWebMessage]:
        """强制清空缓冲区（超时降级）。

        当等待超时或节点需要关闭时调用，按任意顺序返回所有缓冲消息。

        Returns:
            所有缓冲中的 AgentWebMessage 列表
        """
        flushed = list(self.pending.values())
        count = len(flushed)
        self.pending.clear()
        if count > 0:
            logger.warning(
                "CausalDeliveryBuffer flush: 强制清空 %d 条缓冲消息（降级交付）",
                count,
            )
        return flushed

    def pending_count(self) -> int:
        """返回当前缓冲中的消息数。

        Returns:
            pending 中的消息数量
        """
        return len(self.pending)

    def get_pending_message(self, msg_id: str) -> Optional[AgentWebMessage]:
        """按 msg_id 获取缓冲中的消息（不触发交付）。

        Args:
            msg_id: 消息 ID

        Returns:
            AgentWebMessage 或 None（若不存在）
        """
        return self.pending.get(msg_id)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _commit_delivery(self, msg: AgentWebMessage) -> None:
        """提交单条消息的交付：更新 local_vc 并记录。

        Args:
            msg: 已交付的消息
        """
        # 更新本地向量时钟（合并远程 VC）
        self.local_vc.receive(msg.vector_clock)

        # 记录交付快照（用于审计）
        self.delivered_vc_snapshots.append(dict(self.local_vc.clock))

        # 若消息在 pending 中，移除
        self.pending.pop(msg.msg_id, None)

    def _cascade_unlock(self) -> List[AgentWebMessage]:
        """级联解锁：反复检查 pending 中是否有消息因上次交付而解锁。

        由于一次交付可能解锁多个此前被阻塞的消息（连锁反应），
        需要重复扫描 pending 直到没有新消息被解锁。

        Returns:
            本次级联解锁的消息列表，按解锁顺序排列
        """
        unlocked: List[AgentWebMessage] = []

        # 重复扫描直到没有新消息解锁
        made_progress = True
        while made_progress:
            made_progress = False
            # 收集当前就绪的消息
            ready_ids: List[str] = []
            for msg_id, pending_msg in list(self.pending.items()):
                if self.check_ready(pending_msg):
                    ready_ids.append(msg_id)

            # 按任意顺序交付就绪的消息
            for msg_id in ready_ids:
                pending_msg = self.pending.get(msg_id)
                if pending_msg is not None:
                    self._commit_delivery(pending_msg)
                    unlocked.append(pending_msg)
                    made_progress = True
                    logger.debug(
                        "CausalDeliveryBuffer 级联解锁: msg_id=%s, source=%s",
                        msg_id,
                        pending_msg.source_node,
                    )

        return unlocked


# ---------------------------------------------------------------------------
# 自测 (__main__)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("CausalDeliveryBuffer 自测")
    print("=" * 60)

    # ---- 测试1: 消息就绪 → 直接交付 ----
    print("\n[测试1] 消息因果前置到齐 → 直接交付...")
    vc_b = VectorClock("B", ["A", "B"])
    # B 已经收到过 A 的消息，再 tick 一次使 local_vc = {A:1, B:1}
    vc_b.receive({"A": 1, "B": 0})
    buf = CausalDeliveryBuffer(vc_b)

    # B 的 local_vc 现在是 {A:1, B:1}
    # 构造来自 A 的第 2 条消息（msg.vc = {A:2, B:0}）
    # check_ready 条件：
    #   ∀i≠A: msg.vc[B]=0 ≤ local[B]=1 ✓
    #   msg.vc[A]=2 == local[A]+1=1+1=2 ✓
    msg_ready = AgentWebMessage(
        msg_id="m1",
        source_node="A",
        target_node="B",
        vector_clock={"A": 2, "B": 0},
    )
    delivered = buf.deliver(msg_ready)
    assert len(delivered) == 1, f"应交付 1 条: 实际 {len(delivered)}"
    assert delivered[0].msg_id == "m1"
    assert buf.pending_count() == 0
    print("  通过 ✓")

    # ---- 测试2: 消息前置未到齐 → 缓冲 ----
    print("\n[测试2] 消息前置未到齐 → 缓冲...")
    vc_b2 = VectorClock("B", ["A", "B"])
    buf2 = CausalDeliveryBuffer(vc_b2)

    # 发送来自 A 的消息，A 的时钟是 2（跳过 A:1），B 还没收到 A:1
    # local={A:0, B:0}, msg.vc={A:2, B:0}
    # A:2 != local[A]+1=1 → 不可交付
    msg_pending = AgentWebMessage(
        msg_id="m2",
        source_node="A",
        target_node="B",
        vector_clock={"A": 2, "B": 0},
    )
    delivered2 = buf2.deliver(msg_pending)
    assert len(delivered2) == 0, (
        f"A:2 != local[A]+1=1，前置未到齐不应交付，但交付了 {len(delivered2)} 条"
    )
    assert buf2.pending_count() == 1, f"应有 1 条缓冲: 实际 {buf2.pending_count()}"
    assert buf2.get_pending_message("m2") is not None
    print("  通过 ✓")

    # ---- 测试3: 级联解锁 ----
    print("\n[测试3] 级联解锁...")
    vc_b3 = VectorClock("B", ["A", "B"])
    buf3 = CausalDeliveryBuffer(vc_b3)

    # B 此时 local_vc = {A:0, B:0}
    # a1: A:1 == local[A]+1=1 ✓ → 就绪，直接交付
    msg_a1 = AgentWebMessage(
        msg_id="a1",
        source_node="A",
        target_node="B",
        vector_clock={"A": 1, "B": 0},
    )
    delivered_all = buf3.deliver(msg_a1)
    assert len(delivered_all) == 1, f"应该只交付 a1: {[m.msg_id for m in delivered_all]}"
    assert delivered_all[0].msg_id == "a1"
    # a1 交付后 local_vc = {A:1, B:1}

    # a2: A:2 == local[A]+1=2 ✓ → 就绪，直接交付
    msg_a2 = AgentWebMessage(
        msg_id="a2",
        source_node="A",
        target_node="B",
        vector_clock={"A": 2, "B": 0},
    )
    delivered_a2 = buf3.deliver(msg_a2)
    assert len(delivered_a2) == 1
    assert delivered_a2[0].msg_id == "a2"
    # a2 交付后 local_vc = {A:2, B:2}

    # a3: A:3 == local[A]+1=3 ✓ → 就绪，直接交付
    msg_a3 = AgentWebMessage(
        msg_id="a3",
        source_node="A",
        target_node="B",
        vector_clock={"A": 3, "B": 0},
    )
    delivered_a3 = buf3.deliver(msg_a3)
    assert len(delivered_a3) == 1
    assert delivered_a3[0].msg_id == "a3"
    # 连续的消息全部就绪 → 无需缓冲
    assert buf3.pending_count() == 0

    print("  连续顺序消息全部直接交付 ✓")

    # ---- 测试3b: 乱序到达触发缓冲 + 级联解锁 ----
    print("\n[测试3b] 乱序到达 → 缓冲 + 级联解锁...")
    vc_b3b = VectorClock("B", ["A", "B"])
    buf3b = CausalDeliveryBuffer(vc_b3b)

    # 先到达 A 的第 3 条消息（跳过 1 和 2）
    msg_a3b = AgentWebMessage("a3b", "A", "B", {"A": 3, "B": 0})
    r3 = buf3b.deliver(msg_a3b)
    assert len(r3) == 0, "A:3 != local[A]+1=1，应缓冲"
    assert buf3b.pending_count() == 1

    # 再到达 A 的第 2 条消息
    msg_a2b = AgentWebMessage("a2b", "A", "B", {"A": 2, "B": 0})
    r2 = buf3b.deliver(msg_a2b)
    assert len(r2) == 0, "A:2 != local[A]+1=1，应缓冲"
    assert buf3b.pending_count() == 2

    # 现在到达 A 的第 1 条消息 → 应该级联解锁全部 3 条
    msg_a1b = AgentWebMessage("a1b", "A", "B", {"A": 1, "B": 0})
    r1 = buf3b.deliver(msg_a1b)
    delivered_ids = [m.msg_id for m in r1]
    print(f"  级联解锁: {delivered_ids}")
    assert len(r1) == 3, f"应级联解锁 3 条: 实际 {len(r1)} ({delivered_ids})"
    assert "a1b" in delivered_ids
    assert "a2b" in delivered_ids
    assert "a3b" in delivered_ids
    assert buf3b.pending_count() == 0
    print("  通过 ✓")

    # ---- 测试4: check_ready 来源节点不连续 ----
    print("\n[测试4] check_ready 来源节点不连续 → False...")
    vc_b4 = VectorClock("B", ["A", "B", "C"])
    vc_b4.clock = {"A": 0, "B": 0, "C": 0}  # 重置
    buf4 = CausalDeliveryBuffer(vc_b4)

    # 消息来自 A，但 A 的时钟是 3（跳过了 1 和 2）
    msg_skip = AgentWebMessage(
        msg_id="skip",
        source_node="A",
        target_node="B",
        vector_clock={"A": 3, "B": 0, "C": 0},
    )
    assert not buf4.check_ready(msg_skip), (
        "A:3 != local[A]+1=1，应该不可交付"
    )
    print("  通过 ✓")

    # ---- 测试5: check_ready 其他节点前置未到达 ----
    print("\n[测试5] check_ready 其他节点前置未到达 → False...")
    vc_b5 = VectorClock("B", ["A", "B", "C"])
    vc_b5.clock = {"A": 0, "B": 0, "C": 0}
    buf5 = CausalDeliveryBuffer(vc_b5)

    # 消息来自 A，但引用了 C 的一个未来事件
    msg_c_future = AgentWebMessage(
        msg_id="c_future",
        source_node="A",
        target_node="B",
        vector_clock={"A": 1, "B": 0, "C": 5},  # C:5 > local[C]=0
    )
    assert not buf5.check_ready(msg_c_future), (
        "C 的前置事件未到达，应该不可交付"
    )
    print("  通过 ✓")

    # ---- 测试6: flush 强制清空 ----
    print("\n[测试6] flush 强制清空...")
    vc_b6 = VectorClock("B", ["A", "B"])
    buf6 = CausalDeliveryBuffer(vc_b6)

    # 发送乱序消息，它们会被缓冲
    msg_p1 = AgentWebMessage("p1", "A", "B", {"A": 3, "B": 0})  # A:3 != 0+1
    msg_p2 = AgentWebMessage("p2", "A", "B", {"A": 5, "B": 0})  # A:5 != 0+1

    buf6.deliver(msg_p1)  # 缓冲
    buf6.deliver(msg_p2)  # 缓冲
    assert buf6.pending_count() == 2, f"应有 2 条缓冲: 实际 {buf6.pending_count()}"

    flushed = buf6.flush()
    assert len(flushed) == 2, f"应清空 2 条: 实际 {len(flushed)}"
    assert buf6.pending_count() == 0
    print("  通过 ✓")

    # ---- 测试7: pending_count 准确性 ----
    print("\n[测试7] pending_count 准确性...")
    vc_b7 = VectorClock("B", ["A", "B"])
    buf7 = CausalDeliveryBuffer(vc_b7)

    assert buf7.pending_count() == 0
    # c1: A:1 == local[A]+1=1 → 直接交付（不缓冲）
    buf7.deliver(AgentWebMessage("c1", "A", "B", {"A": 1, "B": 0}))
    assert buf7.pending_count() == 0, f"c1 被交付后应为 0: 实际 {buf7.pending_count()}"
    # c2: A:1 != local[A]+1=2（c1 已交付, local[A]=1）→ 缓冲
    buf7.deliver(AgentWebMessage("c2", "A", "B", {"A": 1, "B": 0}))
    assert buf7.pending_count() == 1, f"c2 被缓冲后应为 1: 实际 {buf7.pending_count()}"
    buf7.flush()
    assert buf7.pending_count() == 0
    print("  通过 ✓")

    # ---- 测试8: get_pending_message ----
    print("\n[测试8] get_pending_message...")
    vc_b8 = VectorClock("B", ["A", "B"])
    buf8 = CausalDeliveryBuffer(vc_b8)

    # x1: A:3 != local[A]+1=1 → 缓冲
    msg_x = AgentWebMessage("x1", "A", "B", {"A": 3, "B": 0})
    buf8.deliver(msg_x)
    assert buf8.get_pending_message("x1") is not None
    assert buf8.get_pending_message("no_such") is None
    print("  通过 ✓")

    # ---- 测试9: 来自本节点的消息 ----
    print("\n[测试9] 来自本节点的消息（应正常处理）...")
    vc_b9 = VectorClock("B", ["A", "B"])
    vc_b9.tick()  # B:1
    buf9 = CausalDeliveryBuffer(vc_b9)

    # B 自己的消息，local_vc = {A:0, B:1}
    # source=B, msg.vc={A:0, B:2}
    # 条件：∀i≠B: msg.vc[A]=0 ≤ local[A]=0 ✓
    #       msg.vc[B]=2 == local[B]+1=2 ✓
    msg_self = AgentWebMessage(
        msg_id="self1",
        source_node="B",
        target_node="B",
        vector_clock={"A": 0, "B": 2},
    )
    assert buf9.check_ready(msg_self), "本节点的消息应该就绪"
    print("  通过 ✓")

    # ---- 测试10: 多节点场景 ----
    print("\n[测试10] 三节点场景...")
    vc_b10 = VectorClock("B", ["A", "B", "C"])
    vc_b10.clock = {"A": 2, "B": 3, "C": 1}  # 模拟已收到多个事件
    buf10 = CausalDeliveryBuffer(vc_b10)

    # 来自 C 的消息需要：C:2 == local[C]+1=2 ✓，其他节点 ≤ local ✓
    msg_c = AgentWebMessage(
        msg_id="c_msg",
        source_node="C",
        target_node="B",
        vector_clock={"A": 1, "B": 2, "C": 2},  # A:1≤2✓, B:2≤3✓, C:2==1+1✓
    )
    assert buf10.check_ready(msg_c), "C 的消息前置应全部到齐"
    print("  通过 ✓")

    print("\n" + "=" * 60)
    print("所有 CausalDeliveryBuffer 测试通过！ ✓")
    print("=" * 60)
