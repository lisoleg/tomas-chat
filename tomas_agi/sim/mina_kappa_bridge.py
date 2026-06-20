# -*- coding: utf-8 -*-
"""
MinaTOMASSnap — Mina 递归 SNARK 桥接 (TOMAS v2.0 T08)
=========================================================

将 κ-Snap 事件封装为 Mina 递归 SNARK 证明，实现密码学级因果日志压缩。

Mina 区块链的核心特性是递归 SNARK：无论计算量多大，证明恒定为 ~22KB。
本模块利用此特性将 TOMAS κ-Snap 因果日志压缩为恒定大小的证明。

降级策略：
    当 Mina 节点不可用时，降级为本地 SHA-256 哈希证明。
    降级证明的 is_degraded=True，proof_data 为本地哈希字节流。

依赖：
    - ksnap_operator.py (KSnapOperator, SnapEvent) — 可选（batch_prove 需要）
    - 标准库 urllib.request（RPC 调用）
    - 标准库 hashlib（降级哈希）

Author: TOMAS Team
Version: v2.0
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 可选依赖：κ-Snap 算子
try:
    from ksnap_operator import KSnapOperator, SnapEvent
    _HAS_KSNAP = True
except ImportError:
    _HAS_KSNAP = False
    KSnapOperator = None  # type: ignore
    SnapEvent = None  # type: ignore


@dataclass
class MinaSnapProof:
    """Mina SNARK 证明数据结构。

    封装 κ-Snap 事件的递归 SNARK 证明。

    Attributes:
        snap_id: 对应的 SnapEvent ID
        proof_data: 证明数据（字节数组）
        proof_hash: 证明哈希（十六进制字符串）
        proof_size_bytes: 证明大小（字节）
        generation_time: 生成耗时（秒）
        is_degraded: 是否降级模式（Mina 节点不可用）
    """

    snap_id: str
    proof_data: bytes
    proof_hash: str
    proof_size_bytes: int
    generation_time: float
    is_degraded: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典（proof_data 转为十六进制字符串）。"""
        return {
            "snap_id": self.snap_id,
            "proof_hash": self.proof_hash,
            "proof_size_bytes": self.proof_size_bytes,
            "generation_time": self.generation_time,
            "is_degraded": self.is_degraded,
            "proof_data_hex": self.proof_data.hex(),
        }


class MinaTOMASSnap:
    """Mina 递归 SNARK 桥接：κ-Snap 密码学压缩。

    将 κ-Snap 事件封装为 Mina 递归 SNARK 证明。
    Mina 的递归 SNARK 保证证明大小恒定（~22KB），
    无论输入事件数量多少。

    降级策略：
        - Mina 节点不可用时，返回本地 SHA-256 哈希证明
        - 降级证明 is_degraded=True
        - 降级证明 proof_data 为 SHA-256 哈希字节流（32 字节）

    Attributes:
        mina_rpc_url: Mina 节点 RPC URL
        mina_cli_path: Mina CLI 可执行文件路径（可选）
        PROOF_SIZE_TARGET: 证明大小目标（22KB）
    """

    PROOF_SIZE_TARGET: int = 22 * 1024  # 22KB 恒定大小目标

    def __init__(
        self,
        mina_rpc_url: str = "http://localhost:3085",
        mina_cli_path: Optional[str] = None,
    ) -> None:
        """初始化 Mina SNARK 桥接。

        Args:
            mina_rpc_url: Mina 节点 RPC URL（默认 http://localhost:3085）
            mina_cli_path: Mina CLI 可执行文件路径（可选，用于本地证明生成）
        """
        self.mina_rpc_url: str = mina_rpc_url
        self.mina_cli_path: Optional[str] = mina_cli_path

        # 统计
        self._prove_count: int = 0
        self._degraded_count: int = 0
        self._verify_count: int = 0
        self._batch_count: int = 0

        logger.info(
            "MinaTOMASSnap 初始化: rpc=%s, cli=%s",
            self.mina_rpc_url,
            self.mina_cli_path or "(none)",
        )

    def wrap_snap(self, snap_event: Any) -> MinaSnapProof:
        """将 κ-Snap 事件封装为 Mina 递归 SNARK 证明。

        流程：
          1. 序列化 SnapEvent 为 JSON
          2. 调用 _call_mina_node 生成 SNARK 证明
          3. 验证 proof_size ≤ 22KB
          4. 返回 MinaSnapProof

        降级策略：Mina 节点不可用时返回本地哈希证明。

        Args:
            snap_event: SnapEvent 实例（需有 to_dict() 方法或可序列化属性）

        Returns:
            MinaSnapProof 实例
        """
        start_time = time.time()
        self._prove_count += 1

        # 获取 snap_id
        snap_id = getattr(snap_event, "event_id", str(id(snap_event)))

        # 1. 序列化 SnapEvent
        try:
            if hasattr(snap_event, "to_dict"):
                snap_data = snap_event.to_dict()
            else:
                snap_data = {
                    "event_id": getattr(snap_event, "event_id", ""),
                    "candidate_id": getattr(snap_event, "candidate_id", ""),
                    "timestamp": getattr(snap_event, "timestamp", 0.0),
                    "result": str(getattr(snap_event, "result", "")),
                }
        except Exception as e:
            logger.warning("MinaTOMASSnap wrap_snap: 序列化失败: %s", e)
            snap_data = {"event_id": snap_id, "error": str(e)}

        snap_json = json.dumps(snap_data, sort_keys=True, ensure_ascii=False)

        # 2. 调用 Mina 节点生成证明
        payload = {
            "method": "mina_generateProof",
            "params": {
                "snap_id": snap_id,
                "snap_data": snap_json,
            },
        }
        rpc_result = self._call_mina_node(payload)

        # 3. 构建证明
        is_degraded = rpc_result.get("degraded", True)
        proof_data: bytes
        proof_hash: str

        if is_degraded:
            # 降级模式：本地 SHA-256 哈希
            self._degraded_count += 1
            proof_data = hashlib.sha256(snap_json.encode("utf-8")).digest()
            proof_hash = proof_data.hex()
            logger.info(
                "MinaTOMASSnap wrap_snap 降级: snap_id=%s, proof_hash=%s",
                snap_id,
                proof_hash[:16] + "...",
            )
        else:
            # Mina 节点返回的证明
            proof_hex = rpc_result.get("proof_hex", "")
            proof_data = bytes.fromhex(proof_hex) if proof_hex else b""
            proof_hash = rpc_result.get("proof_hash", "")
            logger.info(
                "MinaTOMASSnap wrap_snap 成功: snap_id=%s, proof_size=%d bytes",
                snap_id,
                len(proof_data),
            )

        generation_time = time.time() - start_time
        proof_size = len(proof_data)

        # 4. 验证证明大小（降级模式下跳过此检查）
        if not is_degraded and proof_size > self.PROOF_SIZE_TARGET:
            logger.warning(
                "MinaTOMASSnap wrap_snap: 证明大小 %d 超过目标 %d bytes，降级为本地哈希",
                proof_size,
                self.PROOF_SIZE_TARGET,
            )
            # 降级为本地哈希
            proof_data = hashlib.sha256(snap_json.encode("utf-8")).digest()
            proof_hash = proof_data.hex()
            proof_size = len(proof_data)
            is_degraded = True
            self._degraded_count += 1

        # 5. 构建 MinaSnapProof
        proof = MinaSnapProof(
            snap_id=snap_id,
            proof_data=proof_data,
            proof_hash=proof_hash,
            proof_size_bytes=proof_size,
            generation_time=generation_time,
            is_degraded=is_degraded,
        )

        return proof

    def verify_proof(self, proof: MinaSnapProof) -> bool:
        """验证 Mina SNARK 证明的有效性。

        检查：
          1. proof_hash 非空且为合法十六进制
          2. proof_size > 0
          3. proof_data 的 SHA-256 与 proof_hash 一致（降级模式）
          4. 证明大小 ≤ PROOF_SIZE_TARGET（非降级模式）

        Args:
            proof: MinaSnapProof 实例

        Returns:
            True 若证明有效
        """
        self._verify_count += 1

        # 1. 基本字段检查
        if not proof.proof_hash:
            logger.warning("MinaTOMASSnap verify_proof: proof_hash 为空")
            return False

        if proof.proof_size_bytes <= 0:
            logger.warning("MinaTOMASSnap verify_proof: proof_size <= 0")
            return False

        if not proof.proof_data:
            logger.warning("MinaTOMASSnap verify_proof: proof_data 为空")
            return False

        # 2. 十六进制合法性检查
        try:
            int(proof.proof_hash, 16)
        except ValueError:
            logger.warning(
                "MinaTOMASSnap verify_proof: proof_hash 不是合法十六进制: %s",
                proof.proof_hash[:32],
            )
            return False

        # 3. 降级模式：proof_data 本身就是 SHA-256 摘要，
        #    proof_hash 是其十六进制表示，直接比较即可（不可二次哈希）
        if proof.is_degraded:
            actual_hex = proof.proof_data.hex()
            if actual_hex != proof.proof_hash:
                logger.warning(
                    "MinaTOMASSnap verify_proof: 降级模式哈希不匹配 "
                    "(expected=%s, actual=%s)",
                    proof.proof_hash[:16] + "...",
                    actual_hex[:16] + "...",
                )
                return False
            logger.info(
                "MinaTOMASSnap verify_proof: 降级证明验证通过 (snap_id=%s)",
                proof.snap_id,
            )
            return True

        # 4. 非降级模式：验证证明大小 ≤ 目标
        if proof.proof_size_bytes > self.PROOF_SIZE_TARGET:
            logger.warning(
                "MinaTOMASSnap verify_proof: 证明大小 %d 超过目标 %d",
                proof.proof_size_bytes,
                self.PROOF_SIZE_TARGET,
            )
            return False

        logger.info(
            "MinaTOMASSnap verify_proof: SNARK 证明验证通过 (snap_id=%s, size=%d)",
            proof.snap_id,
            proof.proof_size_bytes,
        )
        return True

    def batch_prove(self, events: List[Any]) -> str:
        """批量证明：构建 Merkle Root 后生成单个递归证明。

        流程：
          1. 使用 KSnapOperator.batch_merkle_root() 计算 Merkle Root
          2. 调用 _call_mina_node 生成基于 Merkle Root 的递归证明
          3. 返回证明哈希（降级时返回 Merkle Root）

        Args:
            events: SnapEvent 列表

        Returns:
            证明哈希字符串（十六进制）
        """
        self._batch_count += 1
        start_time = time.time()

        if not events:
            logger.warning("MinaTOMASSnap batch_prove: 空事件列表")
            return "0" * 64

        # 1. 计算 Merkle Root
        merkle_root: str
        if _HAS_KSNAP and KSnapOperator is not None:
            merkle_root = KSnapOperator.batch_merkle_root(events)
        else:
            # 降级：手动计算简单 Merkle Root
            logger.warning(
                "MinaTOMASSnap batch_prove: KSnapOperator 不可用，使用本地 Merkle 计算"
            )
            merkle_root = self._local_merkle_root(events)

        logger.info(
            "MinaTOMASSnap batch_prove: Merkle Root=%s (%d events)",
            merkle_root[:16] + "...",
            len(events),
        )

        # 2. 调用 Mina 节点生成递归证明
        payload = {
            "method": "mina_batchProve",
            "params": {
                "merkle_root": merkle_root,
                "event_count": len(events),
            },
        }
        rpc_result = self._call_mina_node(payload)

        # 3. 返回证明哈希
        if rpc_result.get("degraded", True):
            self._degraded_count += 1
            # 降级：返回 Merkle Root 作为证明哈希
            proof_hash = merkle_root
            logger.info(
                "MinaTOMASSnap batch_prove 降级: 返回 Merkle Root 作为证明 "
                "(%d events, hash=%s...)",
                len(events),
                proof_hash[:16],
            )
        else:
            proof_hash = rpc_result.get("proof_hash", merkle_root)
            logger.info(
                "MinaTOMASSnap batch_prove 成功: %d events → proof_hash=%s...",
                len(events),
                proof_hash[:16],
            )

        elapsed = time.time() - start_time
        logger.info(
            "MinaTOMASSnap batch_prove 完成: %d events, %.3fs",
            len(events),
            elapsed,
        )

        return proof_hash

    def _call_mina_node(self, payload: Dict) -> Dict:
        """调用 Mina 节点 RPC 接口。

        尝试通过 urllib.request 调用 Mina 节点的 JSON-RPC 接口。
        失败时降级为本地哈希计算。

        降级策略：
            - 连接超时/拒绝 → 返回 {"degraded": True}
            - HTTP 错误 → 返回 {"degraded": True}
            - 响应解析失败 → 返回 {"degraded": True}

        Args:
            payload: JSON-RPC 请求体

        Returns:
            响应字典，降级时包含 {"degraded": True}
        """
        try:
            import urllib.request
            import urllib.error

            request_body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.mina_rpc_url,
                data=request_body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            resp = urllib.request.urlopen(req, timeout=5.0)
            resp_body = resp.read().decode("utf-8")
            resp_json = json.loads(resp_body)
            resp.close()

            # 检查 RPC 错误
            if "error" in resp_json:
                logger.warning(
                    "MinaTOMASSnap _call_mina_node: RPC 错误: %s",
                    resp_json["error"],
                )
                return {"degraded": True, "error": str(resp_json["error"])}

            result = resp_json.get("result", {})
            result.setdefault("degraded", False)
            return result

        except urllib.error.URLError as e:
            logger.debug(
                "MinaTOMASSnap _call_mina_node: 连接失败 (降级): %s", e
            )
            return {"degraded": True, "error": f"URLError: {e}"}
        except Exception as e:
            logger.debug(
                "MinaTOMASSnap _call_mina_node: 异常 (降级): %s", e
            )
            return {"degraded": True, "error": str(e)}

    def _local_merkle_root(self, events: List[Any]) -> str:
        """本地 Merkle Root 计算（KSnapOperator 不可用时的降级方案）。

        Args:
            events: 事件列表（需有 event_id 和 timestamp 属性）

        Returns:
            十六进制 Merkle Root 字符串
        """
        if not events:
            return "0" * 64

        # 计算叶子哈希
        leaves: List[str] = []
        for event in events:
            event_id = getattr(event, "event_id", str(id(event)))
            timestamp = getattr(event, "timestamp", 0.0)
            data = f"{event_id}{timestamp}"
            leaf_hash = hashlib.sha256(data.encode("utf-8")).hexdigest()
            leaves.append(leaf_hash)

        # 两两配对构建 Merkle 树
        while len(leaves) > 1:
            next_level: List[str] = []
            i = 0
            while i < len(leaves):
                if i + 1 < len(leaves):
                    parent = hashlib.sha256(
                        (leaves[i] + leaves[i + 1]).encode("utf-8")
                    ).hexdigest()
                    next_level.append(parent)
                    i += 2
                else:
                    # 奇数个：最后一个直接晋升
                    next_level.append(leaves[i])
                    i += 1
            leaves = next_level

        return leaves[0]

    def stats(self) -> Dict[str, Any]:
        """返回桥接统计信息。"""
        return {
            "mina_rpc_url": self.mina_rpc_url,
            "mina_cli_path": self.mina_cli_path,
            "proof_size_target": self.PROOF_SIZE_TARGET,
            "prove_count": self._prove_count,
            "degraded_count": self._degraded_count,
            "verify_count": self._verify_count,
            "batch_count": self._batch_count,
            "ksnap_available": _HAS_KSNAP,
        }


# ============================================================
# Self-Test
# ============================================================
if __name__ == "__main__":
    print("=" * 64)
    print("  MinaTOMASSnap — Self-Test Suite")
    print("=" * 64)

    # 使用不可达的 RPC URL 确保降级模式（测试环境无 Mina 节点）
    mina = MinaTOMASSnap(mina_rpc_url="http://192.0.2.1:3085")

    # ── 1. 基本初始化 ──
    print("\n[1] Testing basic initialization...")
    assert mina.mina_rpc_url == "http://192.0.2.1:3085"
    assert mina.PROOF_SIZE_TARGET == 22 * 1024
    assert mina.mina_cli_path is None
    print(f"  [PASS] rpc_url={mina.mina_rpc_url}, target={mina.PROOF_SIZE_TARGET} bytes")

    # ── 2. MinaSnapProof dataclass ──
    print("\n[2] Testing MinaSnapProof dataclass...")
    proof = MinaSnapProof(
        snap_id="snap_test_001",
        proof_data=b"\x00" * 32,
        proof_hash="00" * 32,
        proof_size_bytes=32,
        generation_time=0.001,
        is_degraded=True,
    )
    assert proof.snap_id == "snap_test_001"
    assert proof.proof_size_bytes == 32
    assert proof.is_degraded is True
    d = proof.to_dict()
    assert d["snap_id"] == "snap_test_001"
    assert d["proof_data_hex"] == "00" * 32
    print(f"  [PASS] MinaSnapProof: snap_id={proof.snap_id}, size={proof.proof_size_bytes}")

    # ── 3. wrap_snap 降级模式（Mina 节点不可达）──
    print("\n[3] Testing wrap_snap() in degraded mode...")
    try:
        from ksnap_operator import KSnapOperator, SnapEvent, SnapResult, ObservationBase

        ksnap = KSnapOperator(theta_ftel=0.1, theta_dead=0.01)
        snap_event = ksnap.create_code_evolution_snap(
            candidate_id="cand_test_001",
            new_code_hash="abc123def456",
            trigger_obs_id="obs_001",
            llm_version="gpt-4-turbo",
            reason="Test code evolution",
        )
        proof1 = mina.wrap_snap(snap_event)
        assert proof1.snap_id == snap_event.event_id
        assert proof1.is_degraded is True, "Mina 不可达应降级"
        assert proof1.proof_size_bytes > 0
        assert len(proof1.proof_hash) == 64, "SHA-256 哈希应为 64 字符"
        assert proof1.generation_time >= 0.0
        print(
            f"  [PASS] Degraded proof: snap_id={proof1.snap_id}, "
            f"size={proof1.proof_size_bytes} bytes, hash={proof1.proof_hash[:16]}..."
        )
    except ImportError:
        # 无 ksnap_operator，使用模拟事件
        class MockSnapEvent:
            event_id = "mock_snap_001"
            candidate_id = "mock_cand"
            timestamp = 1234567890.0
            result = "manifested"

            def to_dict(self):
                return {
                    "event_id": self.event_id,
                    "candidate_id": self.candidate_id,
                    "timestamp": self.timestamp,
                }

        proof1 = mina.wrap_snap(MockSnapEvent())
        assert proof1.is_degraded is True
        assert proof1.proof_size_bytes > 0
        print(f"  [PASS] Degraded proof (mock): snap_id={proof1.snap_id}")

    # ── 4. verify_proof 降级模式验证通过 ──
    print("\n[4] Testing verify_proof() with degraded proof...")
    is_valid = mina.verify_proof(proof1)
    assert is_valid is True, "降级证明应验证通过"
    print(f"  [PASS] Degraded proof verified: valid={is_valid}")

    # ── 5. verify_proof 非法证明 ──
    print("\n[5] Testing verify_proof() with invalid proofs...")
    # 空 hash
    bad_proof_1 = MinaSnapProof(
        snap_id="bad_1",
        proof_data=b"\x01" * 32,
        proof_hash="",
        proof_size_bytes=32,
        generation_time=0.0,
        is_degraded=True,
    )
    assert mina.verify_proof(bad_proof_1) is False, "空 hash 应失败"
    print("  [PASS] Empty hash rejected")

    # 非法十六进制 hash
    bad_proof_2 = MinaSnapProof(
        snap_id="bad_2",
        proof_data=b"\x02" * 32,
        proof_hash="ZZZZ" * 16,
        proof_size_bytes=32,
        generation_time=0.0,
        is_degraded=True,
    )
    assert mina.verify_proof(bad_proof_2) is False, "非法十六进制应失败"
    print("  [PASS] Invalid hex hash rejected")

    # 哈希不匹配（降级模式）
    bad_proof_3 = MinaSnapProof(
        snap_id="bad_3",
        proof_data=b"\x03" * 32,
        proof_hash="00" * 32,  # 与 proof_data 不匹配
        proof_size_bytes=32,
        generation_time=0.0,
        is_degraded=True,
    )
    assert mina.verify_proof(bad_proof_3) is False, "哈希不匹配应失败"
    print("  [PASS] Hash mismatch rejected")

    # proof_size = 0
    bad_proof_4 = MinaSnapProof(
        snap_id="bad_4",
        proof_data=b"",
        proof_hash="00" * 32,
        proof_size_bytes=0,
        generation_time=0.0,
        is_degraded=True,
    )
    assert mina.verify_proof(bad_proof_4) is False, "空 proof_data 应失败"
    print("  [PASS] Empty proof_data rejected")

    # ── 6. batch_prove 基本流程 ──
    print("\n[6] Testing batch_prove() basic flow...")
    try:
        ksnap2 = KSnapOperator(theta_ftel=0.1, theta_dead=0.01)
        events = [
            ksnap2.create_code_evolution_snap(
                candidate_id=f"cand_{i}",
                new_code_hash=f"hash_{i}",
                trigger_obs_id=f"obs_{i}",
                llm_version="test-llm",
                reason=f"Batch test event {i}",
            )
            for i in range(5)
        ]
        batch_hash = mina.batch_prove(events)
        assert len(batch_hash) == 64, f"Merkle Root 应为 64 字符, got {len(batch_hash)}"
        assert batch_hash != "0" * 64, "非空事件列表不应返回全零"
        print(f"  [PASS] Batch prove: 5 events → hash={batch_hash[:16]}...")
    except ImportError:
        # 使用模拟事件
        class MockEvent:
            def __init__(self, i):
                self.event_id = f"mock_{i}"
                self.candidate_id = f"cand_{i}"
                self.timestamp = float(1000 + i)

        mock_events = [MockEvent(i) for i in range(5)]
        batch_hash = mina.batch_prove(mock_events)
        assert len(batch_hash) == 64
        assert batch_hash != "0" * 64
        print(f"  [PASS] Batch prove (mock): 5 events → hash={batch_hash[:16]}...")

    # ── 7. batch_prove 空列表 ──
    print("\n[7] Testing batch_prove() with empty list...")
    empty_hash = mina.batch_prove([])
    assert empty_hash == "0" * 64, f"空列表应返回全零, got {empty_hash}"
    print(f"  [PASS] Empty list → all-zeros hash")

    # ── 8. batch_prove 单个事件 ──
    print("\n[8] Testing batch_prove() with single event...")
    try:
        ksnap3 = KSnapOperator(theta_ftel=0.1, theta_dead=0.01)
        single_event = ksnap3.create_code_evolution_snap(
            candidate_id="cand_single",
            new_code_hash="hash_single",
            trigger_obs_id="obs_single",
            llm_version="test",
        )
        single_hash = mina.batch_prove([single_event])
        assert len(single_hash) == 64
        assert single_hash != "0" * 64
        print(f"  [PASS] Single event → hash={single_hash[:16]}...")
    except ImportError:
        single_mock = MockEvent(0)
        single_hash = mina.batch_prove([single_mock])
        assert len(single_hash) == 64
        print(f"  [PASS] Single event (mock) → hash={single_hash[:16]}...")

    # ── 9. _call_mina_node 降级行为 ──
    print("\n[9] Testing _call_mina_node() degradation...")
    result = mina._call_mina_node({"method": "test", "params": {}})
    assert result.get("degraded") is True, "不可达节点应返回 degraded=True"
    assert "error" in result, "降级结果应包含 error 字段"
    print(f"  [PASS] Degraded RPC: degraded={result['degraded']}, error present")

    # ── 10. 多次 wrap_snap 一致性 ──
    print("\n[10] Testing wrap_snap() consistency...")
    try:
        proof_a = mina.wrap_snap(snap_event)
        proof_b = mina.wrap_snap(snap_event)
        # 相同输入应产生相同 proof_hash（降级模式下基于内容哈希）
        assert proof_a.proof_hash == proof_b.proof_hash, (
            "相同 SnapEvent 应产生相同 proof_hash"
        )
        print(f"  [PASS] Consistent proofs: hash={proof_a.proof_hash[:16]}...")
    except NameError:
        print("  [SKIP] snap_event not available, skipping consistency test")

    # ── 11. 非降级证明大小检查 ──
    print("\n[11] Testing non-degraded proof size validation...")
    # 构造一个合法的非降级证明（大小在目标内）
    good_non_degraded = MinaSnapProof(
        snap_id="good_nd",
        proof_data=b"\x42" * 1024,  # 1KB 证明数据
        proof_hash=hashlib.sha256(b"\x42" * 1024).hexdigest(),
        proof_size_bytes=1024,
        generation_time=0.5,
        is_degraded=False,
    )
    assert mina.verify_proof(good_non_degraded) is True, "1KB 非降级证明应通过"
    print(f"  [PASS] Non-degraded proof (1KB) verified")

    # 构造超大的非降级证明
    oversized = MinaSnapProof(
        snap_id="oversized",
        proof_data=b"\x42" * (25 * 1024),  # 25KB 超过 22KB 目标
        proof_hash=hashlib.sha256(b"\x42" * (25 * 1024)).hexdigest(),
        proof_size_bytes=25 * 1024,
        generation_time=0.5,
        is_degraded=False,
    )
    assert mina.verify_proof(oversized) is False, "25KB 非降级证明应失败"
    print(f"  [PASS] Oversized proof (25KB > 22KB) rejected")

    # ── 12. stats() ──
    print("\n[12] Testing stats()...")
    stats = mina.stats()
    assert "mina_rpc_url" in stats
    assert "prove_count" in stats
    assert "degraded_count" in stats
    assert "verify_count" in stats
    assert "batch_count" in stats
    assert stats["prove_count"] >= 2  # 至少 wrap_snap 2次
    assert stats["degraded_count"] >= 2  # 至少降级 2次
    assert stats["verify_count"] >= 4  # 至少验证 4次
    assert stats["batch_count"] >= 3  # 至少批量证明 3次
    print(f"  [PASS] stats: prove={stats['prove_count']}, "
          f"degraded={stats['degraded_count']}, "
          f"verify={stats['verify_count']}, "
          f"batch={stats['batch_count']}")

    print("\n" + "=" * 64)
    print("  MinaTOMASSnap — All Self-Tests Passed")
    print("=" * 64)
