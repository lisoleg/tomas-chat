# -*- coding: utf-8 -*-
"""
FediverseBridge — ActivityPub 扩展桥接 (TOMAS v2.0 T07)
=========================================================

将 AgentWeb 的因果消息（向量时钟 + κ-Snap 引用）通过标准 ActivityPub
协议在 Fediverse 实例间传递。

核心扩展点：
    标准 ActivityPub 对象的 `attachment` 数组是 JSON-LD 的官方扩展点。
    本模块将 vector_clock 和 snap_ref 放入 attachment，实现：
      1. 标准 Fediverse 客户端可正常解析（忽略未知 attachment）
      2. TOMAS 节点可提取因果元数据，恢复因果顺序

降级策略：
    - httpx 可用时使用 httpx 发送 HTTP POST
    - 否则使用标准库 urllib.request
    - 网络不可达时降级为模拟发送（返回本地生成的 activity_id）

Author: TOMAS Team
Version: v2.0
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 可选导入 httpx（优先），降级到 urllib
try:
    import httpx  # type: ignore
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False
    httpx = None  # type: ignore

# 可选导入 VectorClock（用于类型提示和本地 VC 管理）
try:
    from vector_clock import VectorClock
    _HAS_VC = True
except ImportError:
    _HAS_VC = False
    VectorClock = None  # type: ignore


class FediverseBridge:
    """ActivityPub 扩展桥接：vector_clock/snap_ref + 因果交付缓冲。

    负责：
      1. 将 AgentWebMessage 扩展为标准 ActivityPub Activity
      2. 通过 HTTP POST 发送到目标 Fediverse 实例的 inbox
      3. 接收并解析来自其他实例的 Activity
      4. 验证 JSON-LD 格式合法性

    Attributes:
        instance_url: 本实例的基础 URL（如 "https://tomas.example.com"）
        local_vc: 可选的本地向量时钟引用（用于接收时合并）
        actor_id: 本实例的 Actor ID
    """

    # ActivityPub 标准 context
    ACTIVITYPUB_CONTEXT = "https://www.w3.org/ns/activitystreams"

    def __init__(
        self,
        instance_url: str = "",
        local_vc: Optional[Any] = None,
    ) -> None:
        """初始化 Fediverse 桥接。

        Args:
            instance_url: 本实例的基础 URL，空字符串表示模拟模式
            local_vc: 可选的本地 VectorClock 实例，用于接收时合并远程 VC
        """
        self.instance_url: str = instance_url.rstrip("/") if instance_url else ""
        self.local_vc = local_vc
        # Actor ID 基于实例 URL 生成
        self.actor_id: str = (
            f"{self.instance_url}/users/tomas"
            if self.instance_url
            else "tomas:local"
        )
        # 发送/接收统计
        self._send_count: int = 0
        self._receive_count: int = 0
        self._degraded_count: int = 0

        logger.info(
            "FediverseBridge 初始化: instance=%s, actor=%s, httpx=%s",
            self.instance_url or "(simulated)",
            self.actor_id,
            _HAS_HTTPX,
        )

    def send_activity(self, activity: Dict, target: str) -> str:
        """发送 ActivityPub 活动到目标 inbox。

        流程：
          1. 验证 activity 格式（JSON-LD）
          2. 序列化为 JSON
          3. 通过 HTTP POST 发送到 target inbox
          4. 降级：网络不可达时返回模拟 activity_id

        Args:
            activity: ActivityPub 活动字典
            target: 目标 inbox URL（如 "https://other.example.com/users/x/inbox"）

        Returns:
            activity_id: 活动标识符（成功发送或模拟生成）
        """
        # 确保 activity 有 id
        activity_id = activity.get("id", f"activity_{uuid.uuid4().hex[:12]}")
        activity["id"] = activity_id

        # 验证格式
        if not self._validate_jsonld(activity):
            logger.warning("FediverseBridge: activity JSON-LD 验证失败，仍尝试发送")

        # 如果没有实例 URL，直接降级为模拟
        if not self.instance_url or not target:
            self._degraded_count += 1
            logger.info(
                "FediverseBridge 模拟发送: activity_id=%s (无实例URL或目标)",
                activity_id,
            )
            self._send_count += 1
            return activity_id

        # 尝试 HTTP 发送
        payload = json.dumps(activity, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/activity+json",
            "Accept": "application/activity+json",
        }

        sent = False
        # 优先使用 httpx
        if _HAS_HTTPX:
            try:
                with httpx.Client(timeout=10.0) as client:
                    resp = client.post(target, content=payload, headers=headers)
                    if resp.status_code in (200, 201, 202):
                        sent = True
                        logger.info(
                            "FediverseBridge httpx 发送成功: %s → %s (status=%d)",
                            activity_id,
                            target,
                            resp.status_code,
                        )
                    else:
                        logger.warning(
                            "FediverseBridge httpx 发送失败: status=%d, body=%s",
                            resp.status_code,
                            resp.text[:200],
                        )
            except Exception as e:
                logger.warning("FediverseBridge httpx 异常: %s", e)

        # 降级到 urllib
        if not sent:
            try:
                import urllib.request
                import urllib.error

                req = urllib.request.Request(
                    target,
                    data=payload,
                    headers=headers,
                    method="POST",
                )
                resp = urllib.request.urlopen(req, timeout=10.0)
                if resp.status in (200, 201, 202):
                    sent = True
                    logger.info(
                        "FediverseBridge urllib 发送成功: %s → %s (status=%d)",
                        activity_id,
                        target,
                        resp.status,
                    )
                resp.close()
            except Exception as e:
                logger.warning("FediverseBridge urllib 异常: %s", e)

        if not sent:
            self._degraded_count += 1
            logger.info(
                "FediverseBridge 降级模拟发送: activity_id=%s (网络不可达)",
                activity_id,
            )

        self._send_count += 1
        return activity_id

    def receive_activity(self, activity: Dict) -> Dict:
        """接收并解析 ActivityPub 活动。

        流程：
          1. 验证 JSON-LD 格式
          2. 从 attachment 数组提取 vector_clock 和 snap_ref
          3. 如有 local_vc，合并远程 VC
          4. 返回解析结果

        Args:
            activity: 接收到的 ActivityPub 活动字典

        Returns:
            解析结果字典，包含：
              - "valid": 是否通过验证
              - "activity_id": 活动 ID
              - "actor": 发送者
              - "type": 活动类型
              - "vector_clock": 提取的向量时钟（如有）
              - "snap_ref": 提取的 κ-Snap 引用（如有）
              - "content": 活动内容
              - "merged": 是否已合并到 local_vc
        """
        self._receive_count += 1

        result: Dict[str, Any] = {
            "valid": False,
            "activity_id": activity.get("id", ""),
            "actor": activity.get("actor", ""),
            "type": activity.get("type", ""),
            "vector_clock": None,
            "snap_ref": None,
            "content": activity.get("object", {}),
            "merged": False,
        }

        # 验证 JSON-LD
        if not self._validate_jsonld(activity):
            logger.warning(
                "FediverseBridge 接收: JSON-LD 验证失败, activity_id=%s",
                result["activity_id"],
            )
            return result

        result["valid"] = True

        # 从 attachment 提取扩展字段
        attachments = activity.get("attachment", [])
        if isinstance(attachments, list):
            for att in attachments:
                if not isinstance(att, dict):
                    continue
                att_type = att.get("type", "")
                if att_type == "VectorClock":
                    result["vector_clock"] = att.get("value", {})
                elif att_type == "SnapRef":
                    result["snap_ref"] = att.get("value")

        # 合并到本地 VC（如有）
        if (
            result["vector_clock"]
            and self.local_vc is not None
            and _HAS_VC
            and isinstance(self.local_vc, VectorClock)
        ):
            try:
                self.local_vc.receive(result["vector_clock"])
                result["merged"] = True
                logger.debug(
                    "FediverseBridge 接收: VC 已合并, local_vc=%s",
                    self.local_vc.to_dict(),
                )
            except Exception as e:
                logger.warning("FediverseBridge VC 合并失败: %s", e)

        logger.info(
            "FediverseBridge 接收: activity_id=%s, type=%s, actor=%s, "
            "has_vc=%s, snap_ref=%s",
            result["activity_id"],
            result["type"],
            result["actor"],
            result["vector_clock"] is not None,
            result["snap_ref"],
        )

        return result

    def extend_activitypub(
        self, msg: Dict, vc: Dict, snap_ref: str
    ) -> Dict:
        """扩展标准 ActivityPub 对象，添加 vector_clock 和 snap_ref 字段。

        扩展字段放入 attachment 数组（标准 JSON-LD 扩展点），
        这样标准 Fediverse 客户端会忽略未知 attachment，
        而 TOMAS 节点可提取因果元数据。

        Args:
            msg: 原始消息内容字典
            vc: 向量时钟快照 {node_id: logical_time}
            snap_ref: κ-Snap 引用 ID

        Returns:
            扩展后的 ActivityPub Activity 字典
        """
        activity: Dict[str, Any] = {
            "@context": self.ACTIVITYPUB_CONTEXT,
            "id": f"{self.instance_url}/activities/{uuid.uuid4().hex[:12]}"
            if self.instance_url
            else f"activity:{uuid.uuid4().hex[:12]}",
            "type": "Create",
            "actor": self.actor_id,
            "published": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
            ),
            "object": {
                "id": f"{self.instance_url}/objects/{uuid.uuid4().hex[:12]}"
                if self.instance_url
                else f"object:{uuid.uuid4().hex[:12]}",
                "type": "Note",
                "content": json.dumps(msg, ensure_ascii=False)
                if isinstance(msg, dict)
                else str(msg),
            },
            "attachment": [
                {
                    "type": "VectorClock",
                    "name": "tomas:vector_clock",
                    "value": dict(vc) if vc else {},
                },
                {
                    "type": "SnapRef",
                    "name": "tomas:snap_ref",
                    "value": snap_ref or "",
                },
            ],
        }

        logger.debug(
            "FediverseBridge extend_activitypub: activity_id=%s, vc=%s, snap_ref=%s",
            activity["id"],
            vc,
            snap_ref,
        )

        return activity

    def _validate_jsonld(self, activity: Dict) -> bool:
        """验证 JSON-LD 活动格式。

        检查：
          1. 必须是字典
          2. 必须有 @context 字段（或可推断）
          3. 必须有 type 字段
          4. type 应为已知的 ActivityPub 类型

        Args:
            activity: 待验证的活动字典

        Returns:
            True 若格式合法
        """
        if not isinstance(activity, dict):
            return False

        # @context 检查（宽松：允许缺失，但记录）
        has_context = "@context" in activity
        if not has_context:
            logger.debug("JSON-LD 验证: 缺少 @context（宽松通过）")

        # type 字段必须存在
        activity_type = activity.get("type")
        if activity_type is None:
            logger.warning("JSON-LD 验证: 缺少 type 字段")
            return False

        # 已知 ActivityPub 类型（宽松匹配）
        known_types = {
            "Create", "Update", "Delete", "Follow", "Accept", "Reject",
            "Announce", "Like", "Activity", "Note", "Person", "Service",
            "Application", "Group", "Organization",
        }
        if isinstance(activity_type, str):
            if activity_type not in known_types:
                logger.debug(
                    "JSON-LD 验证: 未知 type '%s'（宽松通过）", activity_type
                )
        elif isinstance(activity_type, list):
            # type 可以是数组
            for t in activity_type:
                if isinstance(t, str) and t not in known_types:
                    logger.debug("JSON-LD 验证: 未知 type '%s'（宽松通过）", t)

        return True

    def stats(self) -> Dict[str, Any]:
        """返回桥接统计信息。"""
        return {
            "instance_url": self.instance_url,
            "actor_id": self.actor_id,
            "httpx_available": _HAS_HTTPX,
            "send_count": self._send_count,
            "receive_count": self._receive_count,
            "degraded_count": self._degraded_count,
        }


# ============================================================
# Self-Test
# ============================================================
if __name__ == "__main__":
    print("=" * 64)
    print("  FediverseBridge — Self-Test Suite")
    print("=" * 64)

    # ── 1. 基本初始化 ──
    print("\n[1] Testing basic initialization...")
    bridge = FediverseBridge(instance_url="https://tomas.example.com")
    assert bridge.instance_url == "https://tomas.example.com"
    assert bridge.actor_id == "https://tomas.example.com/users/tomas"
    assert bridge._send_count == 0
    assert bridge._receive_count == 0
    print(f"  [PASS] instance_url={bridge.instance_url}, actor={bridge.actor_id}")

    # ── 2. 空实例 URL 降级模式 ──
    print("\n[2] Testing empty instance_url (simulated mode)...")
    bridge_sim = FediverseBridge(instance_url="")
    assert bridge_sim.instance_url == ""
    assert bridge_sim.actor_id == "tomas:local"
    print(f"  [PASS] simulated mode: actor={bridge_sim.actor_id}")

    # ── 3. extend_activitypub ──
    print("\n[3] Testing extend_activitypub()...")
    msg_content = {"action": "query", "target": "KB_node_1"}
    vc_snapshot = {"A": 1, "B": 0, "C": 2}
    snap_ref = "snap_abc12345"
    activity = bridge.extend_activitypub(msg_content, vc_snapshot, snap_ref)

    assert activity["@context"] == FediverseBridge.ACTIVITYPUB_CONTEXT
    assert activity["type"] == "Create"
    assert activity["actor"] == bridge.actor_id
    assert "attachment" in activity
    assert isinstance(activity["attachment"], list)
    assert len(activity["attachment"]) == 2

    # 检查 VectorClock attachment
    vc_att = activity["attachment"][0]
    assert vc_att["type"] == "VectorClock"
    assert vc_att["value"] == vc_snapshot

    # 检查 SnapRef attachment
    snap_att = activity["attachment"][1]
    assert snap_att["type"] == "SnapRef"
    assert snap_att["value"] == snap_ref

    print(f"  [PASS] activity_id={activity['id']}, type={activity['type']}")
    print(f"         attachment: vc={vc_att['value']}, snap_ref={snap_att['value']}")

    # ── 4. _validate_jsonld 合法格式 ──
    print("\n[4] Testing _validate_jsonld() with valid activity...")
    valid_activity = {
        "@context": FediverseBridge.ACTIVITYPUB_CONTEXT,
        "id": "https://example.com/activities/1",
        "type": "Create",
        "actor": "https://example.com/users/alice",
    }
    assert bridge._validate_jsonld(valid_activity), "合法活动应通过验证"
    print("  [PASS] Valid activity passed validation")

    # ── 5. _validate_jsonld 非法格式 ──
    print("\n[5] Testing _validate_jsonld() with invalid activity...")
    # 缺少 type
    invalid_no_type = {"@context": FediverseBridge.ACTIVITYPUB_CONTEXT}
    assert not bridge._validate_jsonld(invalid_no_type), "缺少 type 应失败"
    # 非字典
    assert not bridge._validate_jsonld("not a dict"), "非字典应失败"
    assert not bridge._validate_jsonld(None), "None 应失败"
    print("  [PASS] Invalid activities correctly rejected")

    # ── 6. send_activity 模拟模式 ──
    print("\n[6] Testing send_activity() in simulated mode...")
    bridge_send = FediverseBridge(instance_url="")
    test_activity = bridge_send.extend_activitypub(
        {"test": True}, {"A": 1}, "snap_test"
    )
    activity_id = bridge_send.send_activity(test_activity, target="")
    assert activity_id == test_activity["id"], "模拟模式应返回活动自身 ID"
    assert bridge_send._send_count == 1
    assert bridge_send._degraded_count == 1
    print(f"  [PASS] Simulated send: activity_id={activity_id}, degraded=True")

    # ── 7. send_activity 不可达目标（降级）──
    print("\n[7] Testing send_activity() with unreachable target...")
    bridge_unreachable = FediverseBridge(instance_url="https://tomas.example.com")
    unreachable_target = "http://192.0.2.1:9999/inbox"  # TEST-NET-1 不可达地址
    activity_id_2 = bridge_unreachable.send_activity(
        test_activity, target=unreachable_target
    )
    assert bridge_unreachable._send_count == 1
    # 网络不可达应降级
    assert bridge_unreachable._degraded_count >= 1
    print(f"  [PASS] Unreachable target degraded: activity_id={activity_id_2}")

    # ── 8. receive_activity 提取扩展字段 ──
    print("\n[8] Testing receive_activity() extracting extension fields...")
    bridge_recv = FediverseBridge(instance_url="https://tomas.example.com")
    incoming_activity = {
        "@context": FediverseBridge.ACTIVITYPUB_CONTEXT,
        "id": "https://other.example.com/activities/42",
        "type": "Create",
        "actor": "https://other.example.com/users/bob",
        "object": {"type": "Note", "content": "Hello from Bob"},
        "attachment": [
            {"type": "VectorClock", "name": "tomas:vector_clock", "value": {"A": 3, "B": 1}},
            {"type": "SnapRef", "name": "tomas:snap_ref", "value": "snap_xyz789"},
        ],
    }
    result = bridge_recv.receive_activity(incoming_activity)
    assert result["valid"] is True
    assert result["activity_id"] == "https://other.example.com/activities/42"
    assert result["actor"] == "https://other.example.com/users/bob"
    assert result["type"] == "Create"
    assert result["vector_clock"] == {"A": 3, "B": 1}
    assert result["snap_ref"] == "snap_xyz789"
    assert bridge_recv._receive_count == 1
    print(f"  [PASS] Received: vc={result['vector_clock']}, snap_ref={result['snap_ref']}")

    # ── 9. receive_activity 无扩展字段 ──
    print("\n[9] Testing receive_activity() without extension fields...")
    plain_activity = {
        "@context": FediverseBridge.ACTIVITYPUB_CONTEXT,
        "id": "https://plain.example.com/activities/1",
        "type": "Note",
        "actor": "https://plain.example.com/users/carol",
        "object": {"content": "Plain message"},
    }
    result_plain = bridge_recv.receive_activity(plain_activity)
    assert result_plain["valid"] is True
    assert result_plain["vector_clock"] is None
    assert result_plain["snap_ref"] is None
    print("  [PASS] Plain activity: no extension fields extracted")

    # ── 10. receive_activity 非法格式 ──
    print("\n[10] Testing receive_activity() with invalid format...")
    bad_activity = {"@context": FediverseBridge.ACTIVITYPUB_CONTEXT}  # 缺 type
    result_bad = bridge_recv.receive_activity(bad_activity)
    assert result_bad["valid"] is False
    print("  [PASS] Invalid activity: valid=False")

    # ── 11. 与 VectorClock 集成 ──
    print("\n[11] Testing integration with VectorClock...")
    try:
        from vector_clock import VectorClock

        local_vc = VectorClock("B", ["A", "B"])
        bridge_vc = FediverseBridge(
            instance_url="https://tomas.example.com", local_vc=local_vc
        )
        # local_vc = {A:0, B:0}
        incoming_with_vc = {
            "@context": FediverseBridge.ACTIVITYPUB_CONTEXT,
            "id": "https://other.example.com/activities/vc_test",
            "type": "Create",
            "actor": "https://other.example.com/users/alice",
            "attachment": [
                {"type": "VectorClock", "value": {"A": 1, "B": 0}},
            ],
        }
        result_vc = bridge_vc.receive_activity(incoming_with_vc)
        assert result_vc["merged"] is True, "VC 应已合并"
        # receive: max(local, remote) + self-increment
        # A: max(0,1)=1, B: max(0,0)=0, then B+1=1 → {A:1, B:1}
        assert local_vc.clock["A"] == 1, f"A should be 1, got {local_vc.clock['A']}"
        assert local_vc.clock["B"] == 1, f"B should be 1, got {local_vc.clock['B']}"
        print(f"  [PASS] VC merged: local_vc={local_vc.to_dict()}")
    except ImportError:
        print("  [SKIP] vector_clock.py 不可用，跳过集成测试")

    # ── 12. stats() ──
    print("\n[12] Testing stats()...")
    stats = bridge_recv.stats()
    assert "instance_url" in stats
    assert "send_count" in stats
    assert "receive_count" in stats
    assert "degraded_count" in stats
    assert stats["receive_count"] >= 3  # 至少接收了3次
    print(f"  [PASS] stats: {stats}")

    print("\n" + "=" * 64)
    print("  FediverseBridge — All Self-Tests Passed")
    print("=" * 64)
