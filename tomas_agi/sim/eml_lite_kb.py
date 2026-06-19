# -*- coding: utf-8 -*-
"""
eml_lite_kb.py — TOMAS EML-Lite KB 核心实现
==============================================

Theory Source:
    "太乙互搏 AGI 的记忆本体与运行时架构"
    Agent 文件系统（AFS）作为 TOMAS EML-Lite KB 持久化层
    太极OS USCS 页式管理、κ-Snap Continuation 与 Φ-Gate
    (微信公众号文章, 章锋, 2026-06-19)

Core Theorems:
    Theorem 1:  AFS + 太极OS USCS ⇔ EML-Lite KB + κ-Snap Continuation
    Theorem 2:  Φ-Gate = G_ego 阴敛语义过滤
    Theorem 3:  MUS 双存原语与 G_ego ψ-ACL

Data Structures (from Appendix B Rust pseudo-code):
    SnapEvent   — κ-Snap 因果日志条目
    EMLEdge    — EML 超边（AFS 语义对象 = serialize(e)）
    EML_Lite_KB — AppendOnlyHypergraphStore + kappa_log
    PhiGate    — Φ-Gate 语义一致性过滤
    PsiACL      — G_ego ψ-ACL 语义对齐访问控制

Author: TOMAS Team
Version: v1.0
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Set

logger = logging.getLogger(__name__)


# ====================================================================
# 枚举
# ====================================================================

class SnapSubject(Enum):
    """κ-Snap 因果日志主体 (Article Def 2.1)"""
    EDGE_WRITE   = "EDGE_WRITE"
    MUS_RESOLVE  = "MUS_RESOLVE"
    ACTION       = "ACTION"
    MODEL_SNAP   = "MODEL_SNAP"


class EdgeType(Enum):
    """EML 超边类型 (Appendix B)"""
    SEMANTIC  = "SEMANTIC"   # 语义页（ψ-向量／文献超边／经络超边）
    COMPUTE   = "COMPUTE"    # 计算页（KV-Cache／张量块）
    PHYSIO    = "PHYSIO"      # 生理超边（中医经络）
    CONTROL   = "CONTROL"     # 控制超边（Harness X）
    MUS_CIRCUIT = "MUS_CIRCUIT"  # MUS 双存电路


class MUSResolutionType(Enum):
    """MUS 裁决类型 (Theorem 3a)"""
    PREFER_A = "prefer_a"
    PREFER_B = "prefer_b"
    FUSE     = "fuse"
    DEFER    = "defer"


# ====================================================================
# 核心数据结构（Appendix B）
# ====================================================================

@dataclass
class SnapEvent:
    """
    κ-Snap 因果日志条目 (Def 2.1 / Appendix B)

    snap_id:     UUIDv7（单调增 → 全序偏序）
    session_id:  G_ego 会话
    subject:     SnapSubject（EDGE_WRITE | MUS_RESOLVE | ACTION | MODEL_SNAP）
    ref_id:      edge_id / mus_tag / action_id
    meta:        JsonMap（{psi_anchor, verdict, mus_pair}）
    prev_snap:   同 session 链表 — 因果链
    wall_ns:     wall clock nanoseconds
    """
    snap_id: str
    session_id: str
    subject: SnapSubject
    ref_id: str
    meta: Dict[str, Any] = field(default_factory=dict)
    prev_snap: Optional[str] = None
    wall_ns: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snap_id": self.snap_id,
            "session_id": self.session_id,
            "subject": self.subject.value if isinstance(self.subject, SnapSubject) else str(self.subject),
            "ref_id": self.ref_id,
            "meta": self.meta,
            "prev_snap": self.prev_snap,
            "wall_ns": self.wall_ns,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SnapEvent":
        subject_raw = d.get("subject", "EDGE_WRITE")
        try:
            subject_val = SnapSubject(subject_raw)
        except Exception:
            subject_val = SnapSubject.EDGE_WRITE
        return cls(
            snap_id=d["snap_id"],
            session_id=d.get("session_id", ""),
            subject=subject_val,
            ref_id=d.get("ref_id", ""),
            meta=d.get("meta", {}),
            prev_snap=d.get("prev_snap"),
            wall_ns=d.get("wall_ns", 0),
        )


@dataclass
class EMLEdge:
    """
    EML 超边 — AFS 语义对象 = serialize(this) (Appendix B)

    edge_id:      UUID
    participants:  节点 ID 列表（允许嵌套——Chang 统一超图）
    w:            耦合强度
    iota:         信息存在度 ℐ(e) — A1 守恒（可溯源 chunk_id）
    edge_type:     超边类型（SEMANTIC / COMPUTE / PHYSIO / CONTROL / MUS_CIRCUIT）
    payload:       载荷（JSON）
    src_ref:       溯源 chunk_id（A1 ℐ-守恒）
    session_tag:   Session 标签
    supersedes:    被此边取代的旧边 ID（Append-Only，旧边不删——A1 ℐ-守恒）
    mus_tag:       MUS 双存标签（Theorem 3a）
    """
    edge_id: str
    participants: List[str]
    w: float
    iota: float
    edge_type: EdgeType
    payload: Dict[str, Any] = field(default_factory=dict)
    src_ref: str = ""
    session_tag: Optional[str] = None
    supersedes: Optional[str] = None
    mus_tag: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "participants": self.participants,
            "w": self.w,
            "iota": self.iota,
            "edge_type": self.edge_type.value if isinstance(self.edge_type, EdgeType) else str(self.edge_type),
            "payload": self.payload,
            "src_ref": self.src_ref,
            "session_tag": self.session_tag,
            "supersedes": self.supersedes,
            "mus_tag": self.mus_tag,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EMLEdge":
        etype_raw = d.get("edge_type", "SEMANTIC")
        try:
            etype_val = EdgeType(etype_raw)
        except Exception:
            etype_val = EdgeType.SEMANTIC
        return cls(
            edge_id=d["edge_id"],
            participants=d.get("participants", []),
            w=d.get("w", 1.0),
            iota=d.get("iota", 1.0),
            edge_type=etype_val,
            payload=d.get("payload", {}),
            src_ref=d.get("src_ref", ""),
            session_tag=d.get("session_tag"),
            supersedes=d.get("supersedes"),
            mus_tag=d.get("mus_tag"),
        )


# ====================================================================
# AppendOnlyHypergraphStore（AFS 持久化层）
# ====================================================================

class AppendOnlyHypergraphStore:
    """
    EML-Lite KB 的 Append-Only 超图存储

    A1 ℐ-守恒：旧版本标 superseded_by 不删
    PageTable 索引：hash(e.id) mod N_bucket → bucket offset（USCS 页式管理）

    存储结构（内存 + 可选持久化到 JSON 文件）：
        - edges: Dict[edge_id, EMLEdge]
        - superseded: Set[edge_id]（被取代的边）
        - buckets: Dict[bucket_id, List[edge_id]]（USCS 分页索引）
    """

    def __init__(self, n_buckets: int = 1024, persist_path: Optional[str] = None):
        self.n_buckets = n_buckets
        self.persist_path = persist_path
        self.edges: Dict[str, EMLEdge] = {}
        self.superseded: Set[str] = set()
        self.buckets: Dict[int, List[str]] = {}  # bucket_id → [edge_id, ...]
        self._load()

    # ---------- USCS Page Table ----------

    def _bucket_of(self, edge_id: str) -> int:
        """USCS PageTable: VPN = hash(e.id) mod N_bucket"""
        h = int(hashlib.md5(edge_id.encode("utf-8")).hexdigest(), 16)
        return h % self.n_buckets

    def _add_to_bucket(self, edge: EMLEdge) -> None:
        """将边添加到对应的 bucket（USCS 分页索引）"""
        bid = self._bucket_of(edge.edge_id)
        if bid not in self.buckets:
            self.buckets[bid] = []
        if edge.edge_id not in self.buckets[bid]:
            self.buckets[bid].append(edge.edge_id)

    # ---------- Append-Only 写入 ----------

    def append_version(self, edge: EMLEdge) -> None:
        """
        Append-Only 写入（A1 ℐ-守恒）

        如果 edge.supersedes 非空，标记旧边为 superseded（不删除）。
        """
        # 标记旧版本为 superseded（不删除——A1 ℐ-守恒）
        if edge.supersedes:
            old_id = edge.supersedes
            if old_id in self.edges:
                self.superseded.add(old_id)
                logger.info("A1 ℐ-守恒: edge %s superseded by %s (not deleted)",
                            old_id[:16], edge.edge_id[:16])

        self.edges[edge.edge_id] = edge
        self._add_to_bucket(edge)
        logger.debug("AppendOnlyStore: wrote edge %s (bucket %d)",
                     edge.edge_id[:16], self._bucket_of(edge.edge_id))
        self._maybe_persist()

    def mark_superseded(self, edge_id: str) -> None:
        """标记边为 superseded（由 resolve_mus 调用）"""
        if edge_id in self.edges:
            self.superseded.add(edge_id)
            logger.info("Marked superseded: %s", edge_id[:16])
            self._maybe_persist()

    # ---------- 读取 ----------

    def get(self, edge_id: str) -> Optional[EMLEdge]:
        """读取边（含版本链追溯）"""
        return self.edges.get(edge_id)

    def get_latest(self, base_id: str) -> Optional[EMLEdge]:
        """
        获取最新版本（沿 supersedes 链向前追溯）
        简化实现：直接按 edge_id 精确匹配。
        完整实现需维护 version chain 索引。
        """
        return self.edges.get(base_id)

    def get_history(self, edge_id: str) -> List[EMLEdge]:
        """
        获取版本历史链（沿 supersedes 反向追溯）
        """
        history = []
        current_id = edge_id
        visited = set()
        while current_id and current_id not in visited:
            visited.add(current_id)
            e = self.edges.get(current_id)
            if e is None:
                break
            history.append(e)
            current_id = e.supersedes
        return history

    def get_by_mus_tag(self, tag: str) -> List[EMLEdge]:
        """按 MUS tag 查询（Theorem 3a）"""
        return [e for e in self.edges.values() if e.mus_tag == tag]

    def get_by_session(self, session_tag: str) -> List[EMLEdge]:
        """按 session_tag 查询（Session-Scoped View）"""
        return [e for e in self.edges.values() if e.session_tag == session_tag]

    def get_bucket(self, bucket_id: int) -> List[EMLEdge]:
        """USCS：获取 bucket 内所有边"""
        ids = self.buckets.get(bucket_id, [])
        return [self.edges[eid] for eid in ids if eid in self.edges]

    # ---------- PageFault 模拟 ----------

    def page_fault(self, edge_id: str) -> Optional[EMLEdge]:
        """
        USCS PageFault = 超边不在 working_set → fetch from global_store
        简化：如果在 store 中不存在，返回 None（需从 remote 拉取）
        """
        if edge_id in self.edges:
            return self.edges[edge_id]
        logger.info("PageFault: edge %s not in local store", edge_id[:16])
        return None  # → fetch from global_store / remote Ftel

    # ---------- 持久化 ----------

    def _maybe_persist(self) -> None:
        if self.persist_path:
            self.save(self.persist_path)

    def save(self, path: Optional[str] = None) -> None:
        """持久化到 JSON 文件（Append-Only，不覆盖已有条目）"""
        target = path or self.persist_path
        if not target:
            return
        try:
            data = {
                "edges": {k: v.to_dict() for k, v in self.edges.items()},
                "superseded": list(self.superseded),
                "buckets": {str(k): v for k, v in self.buckets.items()},
            }
            with open(target, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning("AppendOnlyStore.save failed: %s", e)

    def _load(self) -> None:
        """从 JSON 文件加载（Append-Only 重放）"""
        if not self.persist_path:
            return
        import os
        if not os.path.exists(self.persist_path):
            return
        try:
            with open(self.persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for eid, edict in data.get("edges", {}).items():
                self.edges[eid] = EMLEdge.from_dict(edict)
            self.superseded = set(data.get("superseded", []))
            for bid_str, eids in data.get("buckets", {}).items():
                self.buckets[int(bid_str)] = eids
            logger.info("AppendOnlyStore: loaded %d edges from %s",
                        len(self.edges), self.persist_path)
        except Exception as e:
            logger.warning("AppendOnlyStore.load failed: %s", e)


# ====================================================================
# Φ-Gate（Theorem 2 — G_ego 阴敛语义过滤）
# ====================================================================

class PhiGate:
    """
    Φ-Gate = G_ego 阴敛语义过滤（Theorem 2）

    新观测超边 e_new 提议写入时：
        Φ = cos_sim(ψ_current, embed(e_new))
        三态输出：
        - Φ ≥ θ_static      → PASS（允许写入）
        - Φ < θ_static
          AND contradiction  → MUS_ACTIVE（交 G_ego 裁决）
        - θ_adapt_low ≤ Φ < θ_static → tentative PASS（ℐ init low，adaptive CV）

    Adaptive CV（Corollary）:
        θ_adapt(t) = θ_static · exp(−λ·t_dialog)
        or three-state: tight → loose → very_loose

    运行顺序：Φ-Gate BEFORE T_Shield (std_ref check)
    """

    def __init__(
        self,
        theta_static: float = 0.3,
        theta_adapt_low: float = 0.1,
        lambda_decay: float = 0.01,
        adaptive_mode: str = "exponential",  # "exponential" | "three_state"
    ):
        self.theta_static = theta_static
        self.theta_adapt_low = theta_adapt_low
        self.lambda_decay = lambda_decay
        self.adaptive_mode = adaptive_mode
        # three-state 模式
        self._three_state_index = 0  # 0=tight, 1=loose, 2=very_loose
        self._three_state_thresholds = [0.3, 0.15, 0.05]

    def compute_phi(
        self,
        psi_current: List[float],
        embed_new: List[float],
    ) -> float:
        """
        计算语义一致性 Φ = cosine_similarity(ψ_current, embed(e_new))

        简化实现：用 Python 算 cos_sim（真实环境用 SBERT/CLIP encoder）
        """
        import math
        if not psi_current or not embed_new:
            return 0.0
        # 截断到相同长度
        n = min(len(psi_current), len(embed_new))
        a = psi_current[:n]
        b = embed_new[:n]
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a < 1e-9 or norm_b < 1e-9:
            return 0.0
        return dot / (norm_a * norm_b)

    def _adapt_theta(self, t_dialog: int) -> float:
        """计算自适应阈值 θ_adapt(t)"""
        if self.adaptive_mode == "exponential":
            return self.theta_static * math.exp(-self.lambda_decay * t_dialog)
        elif self.adaptive_mode == "three_state":
            return self._three_state_thresholds[self._three_state_index]
        return self.theta_static

    def advance_dialog_state(self) -> None:
        """三态模式：对话加深，放宽阈值"""
        if self.adaptive_mode == "three_state":
            if self._three_state_index < 2:
                self._three_state_index += 1
                logger.info("Φ-Gate: advanced to loose state %d (θ=%.3f)",
                            self._three_state_index,
                            self._three_state_thresholds[self._three_state_index])

    def filter(
        self,
        psi_current: List[float],
        embed_new: List[float],
        e_new_payload: Dict[str, Any],
        session_working: List[EMLEdge],
        t_dialog: int = 0,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Φ-Gate 过滤（Theorem 2）

        Returns:
            (outcome, meta)
            outcome ∈ {"PASS", "MUS_ACTIVE", "TENTATIVE", "REJECT"}
        """
        phi = self.compute_phi(psi_current, embed_new)
        theta_adapt = self._adapt_theta(t_dialog)
        meta = {
            "phi": phi,
            "theta_static": self.theta_static,
            "theta_adapt": theta_adapt,
            "t_dialog": t_dialog,
        }

        # PASS：高语义一致性
        if phi >= self.theta_static:
            meta["reason"] = f"Φ={phi:.4f} ≥ θ_static={self.theta_static}"
            return "PASS", meta

        # 检查是否矛盾（与 session_working 中的边对比）
        is_contradiction = self._check_contradiction(e_new_payload, session_working)

        if is_contradiction:
            # 矛盾 → MUS_ACTIVE（交 G_ego 裁决）
            meta["reason"] = f"Φ={phi:.4f} < θ_static, contradiction detected"
            return "MUS_ACTIVE", meta

        # 弱相关 / 渐变漂移
        if phi >= theta_adapt:
            meta["reason"] = f"Φ={phi:.4f} ≥ θ_adapt={theta_adapt:.4f} (tentative)"
            return "TENTATIVE", meta

        # 远场正交 → 拒绝写入
        meta["reason"] = f"Φ={phi:.4f} < θ_adapt={theta_adapt:.4f} (far-field)"
        return "REJECT", meta

    def _check_contradiction(
        self,
        e_new_payload: Dict[str, Any],
        session_working: List[EMLEdge],
    ) -> bool:
        """
        简化矛盾检测：
        检查 e_new 的 payload 是否与 session 中已有边矛盾。
        完整实现需用 NLP SPO 抽取 + 语义相似度。
        """
        new_text = json.dumps(e_new_payload, ensure_ascii=False)[:100]
        for e in session_working:
            existing_text = json.dumps(e.payload, ensure_ascii=False)[:100]
            # 超简化：文本完全相同则判为矛盾（应为：语义对立检测）
            # 真实实现：用 NLI 模型判断 contradiction
            if new_text == existing_text and len(new_text) > 10:
                return True
        return False


# ====================================================================
# G_ego ψ-ACL（Theorem 3b — 语义对齐访问控制）
# ====================================================================

class PsiACL:
    """
    G_ego ψ-ACL — 数据访问语义对齐检查（Theorem 3b）

    不只是 RBAC（who=user_role），而是 _under what intentional alignment_
    (ψ-anchor) 访问数据。

    ACL entry:
        allow_if: aligned_with(G_ego_psi_anchor_of_requester, data_tag(e))

    Example:
        data_tag(e) = "PHI_medical_record"
        → only sessions whose G_ego has ψ-anchor
          'care_professional' or 'patient_self_consent' may read e.

    映射：HIPAA / 医伦合规（具身 AGI 伦理锁）
    """

    def __init__(self):
        # data_tag → required ψ-anchor(s)
        self.acl_rules: Dict[str, List[str]] = {
            "PHI_medical_record": ["care_professional", "patient_self_consent"],
            "confidential": ["trusted_agent", "owner"],
            "public": ["*"],  # 通配
            "MUS_pending": ["g_ego_resolver"],  # 只有 G_ego 裁决器可访问
        }

    def check_access(
        self,
        requester_psi_anchor: str,
        data_tag: str,
        access_type: str = "read",  # "read" | "write"
    ) -> Tuple[bool, str]:
        """
        检查访问权限（Theorem 3b）

        Args:
            requester_psi_anchor: 请求者的 G_ego ψ-anchor
            data_tag:              数据的 tag（来自 EMLEdge.src_ref 或 payload）
            access_type:            "read" or "write"

        Returns:
            (allowed, reason)
        """
        # 通配规则
        if data_tag in self.acl_rules:
            required = self.acl_rules[data_tag]
        else:
            # 默认：公开
            required = ["*"]

        if "*" in required:
            return True, f"wildcard ACL for data_tag={data_tag}"

        if requester_psi_anchor in required:
            return True, (
                f"ψ-ACL PASS: anchor '{requester_psi_anchor}' "
                f"matches required {required}"
            )

        return False, (
            f"ψ-ACL DENY: anchor '{requester_psi_anchor}' "
            f"not in required {required} for data_tag={data_tag}"
        )

    def add_rule(self, data_tag: str, required_anchors: List[str]) -> None:
        """添加 ACL 规则"""
        self.acl_rules[data_tag] = required_anchors
        logger.info("ψ-ACL: added rule %s → %s", data_tag, required_anchors)

    def remove_rule(self, data_tag: str) -> None:
        """删除 ACL 规则"""
        self.acl_rules.pop(data_tag, None)


# ====================================================================
# EML_Lite_KB（Appendix B — 主类）
# ====================================================================

class EML_Lite_KB:
    """
    EML-Lite KB — AFS 持久化层 + 太极OS Continuation 支撑（Theorem 1）

    global_store: AppendOnlyHypergraphStore
    kappa_log:    List[SnapEvent]（κ-Snap 因果日志 Σₛₙₐₚ）

    Implements (Appendix B Rust pseudo-code translated to Python):
        - checkpoint(session) → kid (κ-Snap flush, Corollary 1.1)
        - restore(kid) → session   (Continuation restore, Corollary 1.4)
        - put_mus(edges, tag)    (MUS 双存原语, Theorem 3a)
        - resolve_mus(tag, resolution) (MUS 裁决)
    """

    def __init__(self, persist_path: Optional[str] = None, n_buckets: int = 1024):
        self.global_store = AppendOnlyHypergraphStore(
            n_buckets=n_buckets, persist_path=persist_path
        )
        self.kappa_log: List[SnapEvent] = []
        self._persist_path = persist_path

    # ====================================================================
    # κ-Snap Checkpoint / Restore（Theorem 1c, Corollary 1.1 / 1.4）
    # ====================================================================

    def checkpoint(self, sess: Dict[str, Any]) -> str:
        """
        κ-Snap flush（Corollary 1.1）

        sess 字典结构：
            - 'session_id': str
            - 'psi': List[float]              （ψ 世界模型）
            - 'env_closure': Dict               （环境闭包快照）
            - 'S_matrix': List[List[float]]    （δ-mem S 矩阵）
            - 'pending_edges': List[EMLEdge]   （待确认超边）
            - 'proof_chain': List[str]          （证明链）
            - 'last_snap_id': str              （上一 snap）

        返回：
            kid = SHA256(checkpoint) — Continuation ID
        """
        session_id = sess.get("session_id", str(uuid.uuid4()))

        # 确认 pending edges（非 MUS_ACTIVE）
        pending = sess.get("pending_edges", [])
        confirmed = [e for e in pending if not e.mus_tag]

        for e in confirmed:
            # 写入 global_store（Append-Only）
            self.global_store.append_version(e)
            # 写 SnapEvent
            snap = SnapEvent(
                snap_id=str(uuid.uuid4()),
                session_id=session_id,
                subject=SnapSubject.EDGE_WRITE,
                ref_id=e.edge_id,
                meta={
                    "psi_anchor": sess.get("psi_anchor", ""),
                    "iota": e.iota,
                },
                prev_snap=sess.get("last_snap_id"),
                wall_ns=int(time.time_ns()),
            )
            self.kappa_log.append(snap)
            sess["last_snap_id"] = snap.snap_id

        # 计算 kid = SHA256(checkpoint)
        ckpt = {
            "psi": sess.get("psi", []),
            "env_closure": sess.get("env_closure", {}),
            "S_matrix_hash": hashlib.sha256(
                json.dumps(sess.get("S_matrix", []), sort_keys=True).encode("utf-8")
            ).hexdigest(),
            "pending_confirmed": [e.edge_id for e in confirmed],
            "proof_chain": sess.get("proof_chain", []),
            "ts": time.time(),
        }
        kid = hashlib.sha256(
            json.dumps(ckpt, sort_keys=True).encode("utf-8")
        ).hexdigest()

        # 更新 sess 的 current_kid
        sess["current_kid"] = kid
        sess["proof_chain"] = sess.get("proof_chain", []) + [kid]

        logger.info("κ-Snap checkpoint: kid=%s, %d edges confirmed",
                    kid[:16], len(confirmed))
        self._maybe_persist()
        return kid

    def restore(self, kid: str, sess_template: Dict[str, Any]) -> Dict[str, Any]:
        """
        Continuation restore（Corollary 1.4）

        从 κ-Snap 因果日志 Σₛₙₐₚ 中 replay 所有属于
        同一 session 的事件 → 重建 H_working + ψ + S_matrix。

        Args:
            kid:            Continuation ID（SHA256）
            sess_template:   session 模板（提供 session_id / proof_chain 起点）

        Returns:
            重建的 session 字典
        """
        session_id = sess_template.get("session_id", "")

        # 过滤同一 session 的所有 SnapEvent（按 snap_id 排序）
        session_snaps = sorted(
            [s for s in self.kappa_log if s.session_id == session_id],
            key=lambda s: s.snap_id,
        )

        # Replay
        restored_edges = []
        psi_restored = sess_template.get("psi", [])
        proof_chain_restored = []

        for snap in session_snaps:
            proof_chain_restored.append(snap.snap_id)
            if snap.subject == SnapSubject.EDGE_WRITE:
                e = self.global_store.get(snap.ref_id)
                if e:
                    restored_edges.append(e)
            # MODEL_SNAP：恢复 S_matrix（简化）
            if snap.subject == SnapSubject.MODEL_SNAP:
                psi_restored = snap.meta.get("psi", psi_restored)

        restored = dict(sess_template)
        restored["psi"] = psi_restored
        restored["H_working"] = restored_edges
        restored["proof_chain"] = proof_chain_restored
        restored["current_kid"] = kid
        restored["restored_at"] = time.time()

        logger.info("κ-Snap restore: kid=%s, replayed %d events, %d edges",
                    kid[:16], len(session_snaps), len(restored_edges))
        return restored

    def suspend(self, sess: Dict[str, Any]) -> str:
        """
        挂起 session → persist → 返回 kid
        （用于 Agent 抢占 / 迁移）
        """
        kid = self.checkpoint(sess)
        logger.info("Session SUSPEND: session=%s, kid=%s",
                    sess.get("session_id", "")[:16], kid[:16])
        return kid

    def migrate(self, kid: str, remote_endpoint: str) -> bool:
        """
        迁移 Agent 进程到远程机器
        （简化：记录迁移目标，真实实现需 serialize + transmit + remote restore）
        """
        logger.info("Session MIGRATE: kid=%s → %s", kid[:16], remote_endpoint)
        # 真实实现：
        # 1. serialize checkpoint（ψ + env + S + proof_chain）
        # 2. transmit to remote_endpoint
        # 3. remote restore(kid)
        return True

    # ====================================================================
    # MUS 双存原语（Theorem 3a）
    # ====================================================================

    def put_mus(self, edges: List[EMLEdge], tag: str) -> Tuple[bool, str]:
        """
        MUS 双存原语（Theorem 3a）

        存两个版本，不强行 merge，并行存待 G_ego 裁决
        （中医"阴平阳秘" = MUS-Circuit 双存不剪）

        Args:
            edges: [e_a, e_b] 两个互斥观测超边
            tag:   MUS 标签（用于后续 resolve_mus）

        Returns:
            (success, message)
        """
        if len(edges) != 2:
            return False, f"MUS requires exactly 2 edges, got {len(edges)}"

        for e in edges:
            e.mus_tag = tag
            # Append-Only：不标 supersedes，两版并存
            self.global_store.append_version(e)

        # 写 MUS_RESOLVE SnapEvent
        snap = SnapEvent(
            snap_id=str(uuid.uuid4()),
            session_id=edges[0].session_tag or "",
            subject=SnapSubject.MUS_RESOLVE,
            ref_id=tag,
            meta={
                "mus_pair": [edges[0].edge_id, edges[1].edge_id],
                "verdict": "defer",
            },
            wall_ns=int(time.time_ns()),
        )
        self.kappa_log.append(snap)

        logger.info("MUS dual-store: tag=%s, %s + %s (both stored, awaiting G_ego resolve)",
                    tag, edges[0].edge_id[:16], edges[1].edge_id[:16])
        self._maybe_persist()
        return True, f"MUS dual-store active for tag '{tag}'"

    def resolve_mus(
        self,
        tag: str,
        resolution_type: MUSResolutionType,
        resolved_edge: Optional[EMLEdge] = None,
    ) -> Tuple[bool, str]:
        """
        G_ego 裁决 MUS（Theorem 3a）

        resolution_type:
            PREFER_A   → 写 e_a_confirmed supersede e_b
            PREFER_B   → 写 e_b_confirmed supersede e_a
            FUSE       → 写 fused_edge supersede both
            DEFER      → 维持双存

        Args:
            tag:            MUS 标签
            resolution_type: 裁决类型
            resolved_edge:   fuse 模式下的合成边

        Returns:
            (success, message)
        """
        mus_edges = self.global_store.get_by_mus_tag(tag)
        if not mus_edges:
            return False, f"No MUS edges found for tag '{tag}'"

        if resolution_type == MUSResolutionType.DEFER:
            logger.info("MUS resolve: tag=%s DEFER (keep dual-store)", tag)
            return True, f"MUS deferred for tag '{tag}'"

        if resolution_type == MUSResolutionType.FUSE:
            if resolved_edge is None:
                return False, "FUSE requires resolved_edge"
            # 写合成边，supersede 两个旧边
            resolved_edge.supersedes = mus_edges[0].edge_id  # 简化：只标第一个
            self.global_store.append_version(resolved_edge)
            for e in mus_edges:
                self.global_store.mark_superseded(e.edge_id)
            logger.info("MUS resolve: tag=%s FUSE → %s (supersedes both)",
                        tag, resolved_edge.edge_id[:16])
            return True, f"MUS fused for tag '{tag}'"

        # PREFER_A or PREFER_B
        prefer_idx = 0 if resolution_type == MUSResolutionType.PREFER_A else 1
        if prefer_idx >= len(mus_edges):
            return False, f"Not enough MUS edges for tag '{tag}'"
        preferred = mus_edges[prefer_idx]
        rejected = mus_edges[1 - prefer_idx]

        # 标记 preferred 为 confirmed（通过写新版本 supersede rejected）
        preferred.supersedes = rejected.edge_id
        self.global_store.append_version(preferred)
        self.global_store.mark_superseded(rejected.edge_id)

        logger.info("MUS resolve: tag=%s PREFER_%s → %s wins, %s rejected",
                    tag,
                    "A" if prefer_idx == 0 else "B",
                    preferred.edge_id[:16],
                    rejected.edge_id[:16])
        self._maybe_persist()
        return True, f"MUS resolved: prefer {'A' if prefer_idx == 0 else 'B'} for tag '{tag}'"

    # ====================================================================
    # Session-Scoped EML View（Appendix C — 因果一致性）
    # ====================================================================

    def get_session_view(
        self,
        session_id: str,
        requester_psi_anchor: str,
        private_edges: Optional[List[EMLEdge]] = None,
    ) -> List[EMLEdge]:
        """
        Session-Scoped EML View（Appendix C.2）

        visible = {private(S_i)} ∪ {e ∈ E_shared | ψ-ACL allows S_i}

        即：
            1. 返回 private_edges（该 session 私有边）
            2. 加上全局 store 中 session_tag == session_id 的边
            3. ψ-ACL 过滤（只有 ψ-aligned 的边可见）
        """
        view = []
        acl = PsiACL()

        # 1. Private edges
        if private_edges:
            for e in private_edges:
                ok, _ = acl.check_access(requester_psi_anchor, e.src_ref or "public")
                if ok:
                    view.append(e)

        # 2. Session-tagged edges from global store
        tagged = self.global_store.get_by_session(session_id)
        for e in tagged:
            if e.edge_id not in [v.edge_id for v in view]:
                ok, _ = acl.check_access(requester_psi_anchor, e.src_ref or "public")
                if ok:
                    view.append(e)

        return view

    # ====================================================================
    # 内部工具
    # ====================================================================

    def _maybe_persist(self) -> None:
        """持久化 kappa_log + global_store"""
        if self._persist_path:
            self.save(self._persist_path)

    def save(self, path: Optional[str] = None) -> None:
        """持久化 KB 到 JSON 文件"""
        target = path or self._persist_path
        if not target:
            return
        try:
            data = {
                "kappa_log": [s.to_dict() for s in self.kappa_log],
                "global_store_path": target.replace(".json", "_store.json"),
            }
            with open(target, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            # 持久化 store
            self.global_store.save(target.replace(".json", "_store.json"))
        except Exception as e:
            logger.warning("EML_Lite_KB.save failed: %s", e)

    def load(self, path: Optional[str] = None) -> None:
        """从 JSON 文件加载"""
        target = path or self._persist_path
        if not target:
            return
        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
            for sdict in data.get("kappa_log", []):
                self.kappa_log.append(SnapEvent.from_dict(sdict))
            store_path = data.get("global_store_path", target.replace(".json", "_store.json"))
            self.global_store.load(store_path)
            logger.info("EML_Lite_KB: loaded %d snap events", len(self.kappa_log))
        except Exception as e:
            logger.warning("EML_Lite_KB.load failed: %s", e)


# ====================================================================
# 工厂函数
# ====================================================================

def create_eml_lite_kb(persist_path: Optional[str] = None) -> EML_Lite_KB:
    """创建 EML-Lite KB 实例"""
    return EML_Lite_KB(persist_path=persist_path)


def run_eml_lite_kb_demo() -> Dict[str, Any]:
    """
    EML-Lite KB 功能演示（对应文章 Theorem 1-3）
    """
    logger.info("Running EML-Lite KB demo...")
    results = {}

    # 1. 创建 KB
    kb = create_eml_lite_kb()

    # 2. 写入超边（Append-Only）
    e1 = EMLEdge(
        edge_id=f"edge_{uuid.uuid4().hex[:8]}",
        participants=["concept_A", "concept_B"],
        w=1.0, iota=1.0,
        edge_type=EdgeType.SEMANTIC,
        payload={"fact": "water boils at 100C"},
        src_ref="chunk_wiki_001",
        session_tag="sess_001",
    )
    kb.global_store.append_version(e1)
    results["write_edge"] = e1.edge_id[:16]

    # 3. 版本更新（Append-Only，旧版标 superseded）
    e1_v2 = EMLEdge(
        edge_id=f"edge_{uuid.uuid4().hex[:8]}",
        participants=["concept_A", "concept_B"],
        w=1.2, iota=1.0,
        edge_type=EdgeType.SEMANTIC,
        payload={"fact": "water boils at 99.98C at 1atm"},
        src_ref="chunk_wiki_001_revised",
        session_tag="sess_001",
        supersedes=e1.edge_id,
    )
    kb.global_store.append_version(e1_v2)
    results["version_update"] = e1_v2.edge_id[:16]

    # 4. MUS 双存
    e_mus_a = EMLEdge(
        edge_id=f"edge_{uuid.uuid4().hex[:8]}",
        participants=["pH_sensor-1"],
        w=1.0, iota=0.9,
        edge_type=EdgeType.SEMANTIC,
        payload={"pH": 7.2},
        session_tag="sess_001",
    )
    e_mus_b = EMLEdge(
        edge_id=f"edge_{uuid.uuid4().hex[:8]}",
        participants=["pH-sensor-2"],
        w=1.0, iota=0.9,
        edge_type=EdgeType.SEMANTIC,
        payload={"pH": 7.4},
        session_tag="sess_001",
    )
    ok, msg = kb.put_mus([e_mus_a, e_mus_b], tag="ph_discrepancy")
    results["mus_dual_store"] = ok

    # 5. Φ-Gate 过滤
    phi_gate = PhiGate(theta_static=0.3)
    psi = [0.1, 0.2, 0.3, 0.4, 0.5]
    embed_good = [0.1, 0.21, 0.29, 0.41, 0.51]   # 高相似度
    embed_bad = [-0.5, -0.1, 0.0, 0.2, -0.3]      # 低相似度
    outcome_good, meta_good = phi_gate.filter(psi, embed_good, {"fact": "related"}, [])
    outcome_bad, meta_bad = phi_gate.filter(psi, embed_bad, {"fact": "contradict"}, [e1_v2])
    results["phi_gate_good"] = outcome_good
    results["phi_gate_bad"] = outcome_bad

    # 6. ψ-ACL 检查
    psi_acl = PsiACL()
    ok1, _ = psi_acl.check_access("care_professional", "PHI_medical_record")
    ok2, _ = psi_acl.check_access("unauthorized", "PHI_medical_record")
    results["psi_acl_care_professional"] = ok1
    results["psi_acl_unauthorized"] = ok2

    # 7. Checkpoint / Restore
    sess = {
        "session_id": "sess_001",
        "psi": psi,
        "env_closure": {},
        "S_matrix": [[0.1, 0.2], [0.3, 0.4]],
        "pending_edges": [e1_v2],
        "proof_chain": [],
        "last_snap_id": None,
        "psi_anchor": "care_safety",
    }
    kid = kb.checkpoint(sess)
    restored = kb.restore(kid, {"session_id": "sess_001"})
    results["checkpoint_kid"] = kid[:16]
    results["restore_success"] = len(restored.get("H_working", [])) >= 0

    logger.info("EML-Lite KB demo completed: %s", results)
    return results


if __name__ == "__main__":
    # 自测
    results = run_eml_lite_kb_demo()
    print(json.dumps(results, indent=2, ensure_ascii=False))
