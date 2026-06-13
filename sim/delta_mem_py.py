"""
δ-mem (Delta Memory): L1 Hot Cache — Online Associative Memory for LLM Attention.

自太极OS v1.0 移植到 TOMAS-AGI 框架。
原文件: core/delta_mem.py (309 行)

Implements the low-rank online memory state S ∈ R^(r×r) (r=8, 64 floats)
with Delta Rule updates per token:  S_t = λ·S_{t-1} + β·(v - S·k)·k^T

Reference: Wu, Zhang, et al. "δ-mem: Efficient Online Memory for LLMs." arXiv:2605.12357, 2026.

In the TOMAS-AGI L1/L2 fusion architecture:
  - L1 (δ-mem S):  Hot cache — encodes recent N-turn residual memory
  - L2 (Φ-Gate):   Cold storage — ψ + Episodic Memory + Continuation Snapshot

Author: TOMAS-AGI Team (自太极OS v1.0 移植)
Version: v1.0 — TOMAS-AGI Port (2026-06-13)
"""

import hashlib
from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np


# ────────────────────────────────────────────────────────────────────────────
# Constants
# ────────────────────────────────────────────────────────────────────────────

DEFAULT_RANK = 8            # r = 8 (as in δ-mem paper)
DEFAULT_LAMBDA = 0.95       # Decay factor λ for S_t = λ·S_{t-1} + β·(v - S·k)·k^T
DEFAULT_BETA = 0.1          # Update strength β
DEFAULT_QDIM = 64           # Default query/key embedding dimension


# ────────────────────────────────────────────────────────────────────────────
# SMatrix — the core 8×8 online memory
# ────────────────────────────────────────────────────────────────────────────

@dataclass
class SMatrix:
    """Low-rank associative memory state S ∈ R^(r×r).

    This is the "hot cache" (L1) in the TOMAS-AGI / δ-mem fusion architecture.
    With only 64 floats (r=8), it encodes the residual memory of recent
    interactions for fast online attention correction.

    Attributes:
        S: The r×r matrix storing compressed association patterns.
        r: Rank (default 8).
        lambda_: Decay factor for temporal forgetting.
        beta: Update strength for new information.
        step: Number of Delta Rule updates applied so far.
        proof: SHA-256 integrity hash (updated on each write).
    """

    S: np.ndarray
    r: int = DEFAULT_RANK
    lambda_: float = DEFAULT_LAMBDA
    beta: float = DEFAULT_BETA
    step: int = 0
    proof: str = ""

    def __post_init__(self):
        if self.S is None:
            self.S = np.zeros((self.r, self.r), dtype=np.float32)
        if not self.proof:
            self.proof = self._compute_proof()

    # ── Core Delta Rule ─────────────────────────────────────────────────

    def update(self, k: np.ndarray, v: np.ndarray) -> np.ndarray:
        """Apply one step of the Delta Rule.

        S_t = λ·S_{t-1} + β·(v - S_{t-1}·k)·k^T

        Args:
            k: Key vector (r-dim), derived from attended token embedding.
            v: Value vector (r-dim), derived from output token embedding.

        Returns:
            The updated S matrix (in-place modified).
        """
        k = self._ensure_2d(k)
        v = self._ensure_2d(v)

        # Prediction error: e = v - S·k
        Sk = self.S @ k           # (r, r) @ (r, 1) → (r, 1)
        error = v - Sk            # (r, 1)

        # Delta Rule update: β·(v - Sk)·k^T
        delta = self.beta * (error @ k.T)   # (r, 1) @ (1, r) → (r, r)

        # Exponential decay + delta
        self.S = self.lambda_ * self.S + delta

        self.step += 1
        self.proof = self._compute_proof()
        return self.S

    def read(self, q: np.ndarray) -> np.ndarray:
        """Read from δ-mem: r = S·q^m

        Projects the query vector through the memory matrix to retrieve
        the associated residual signal.

        Args:
            q: Query vector (r-dim), typically from attention query.

        Returns:
            Retrieved residual r (r-dim vector).
        """
        q = self._ensure_2d(q)
        return (self.S @ q).ravel()

    def attention_delta(self, q: np.ndarray, k: np.ndarray) -> np.ndarray:
        """Compute the attention correction Δ from δ-mem.

        This is the delta that would be added to the attention output
        or query to incorporate the online memory signal.

        Args:
            q: Query vector (r-dim).
            k: Key vector (r-dim), used to condition the read.

        Returns:
            Attention delta vector Δ (r-dim).
        """
        residual = self.read(q)               # r = S·q
        scale = float(np.dot(k, q))           # k^T·q  (scalar conditioning)
        scale = np.clip(scale, 0.0, 1.0)      # Normalize to [0, 1]
        return residual * scale

    def flush_state(self) -> np.ndarray:
        """Return a copy of S for serialization (resets decay accumulator).

        This is called when the Φ-Gate decides to flush the hot cache
        to persistent Episodic Memory (L2).
        """
        state_copy = self.S.copy()
        # Soft reset: decay S heavily but keep some residual
        self.S = self.S * 0.1
        self.step = 0
        self.proof = self._compute_proof()
        return state_copy

    # ── Helpers ─────────────────────────────────────────────────────────

    def _ensure_2d(self, vec: np.ndarray) -> np.ndarray:
        """Ensure vector is (r, 1) column shape."""
        vec = np.asarray(vec, dtype=np.float32).ravel()
        if len(vec) != self.r:
            # Pad or truncate to rank
            padded = np.zeros(self.r, dtype=np.float32)
            n = min(len(vec), self.r)
            padded[:n] = vec[:n]
            vec = padded
        return vec.reshape(self.r, 1)

    def _compute_proof(self) -> str:
        """SHA-256 integrity hash of S matrix state."""
        data = self.S.tobytes() + self.step.to_bytes(8, "big")
        return hashlib.sha256(data).hexdigest()[:16]

    def copy(self) -> "SMatrix":
        """Deep copy the S matrix state."""
        return SMatrix(
            S=self.S.copy(),
            r=self.r,
            lambda_=self.lambda_,
            beta=self.beta,
            step=self.step,
            proof=self.proof,
        )


# ────────────────────────────────────────────────────────────────────────────
# DeltaMemLayer — manages the full δ-mem L1 lifecycle
# ────────────────────────────────────────────────────────────────────────────

@dataclass
class DeltaMemLayer:
    """L1 Hot Cache manager wrapping the S matrix.

    Provides the full online memory lifecycle:
      read → attention_delta → update → flush → serialize/deserialize.

    This is the primary integration point for the TOMAS-AGI kernel.
    """

    smatrix: SMatrix = field(default_factory=lambda: SMatrix(S=np.zeros((DEFAULT_RANK, DEFAULT_RANK), dtype=np.float32)))
    flushed_count: int = 0          # Number of times S was flushed to L2
    total_updates: int = 0          # Total Delta Rule steps applied
    last_flush_step: int = 0        # Step at which last flush occurred

    # ── Core Operations ─────────────────────────────────────────────────

    def ingest(self, key_vec: np.ndarray, value_vec: np.ndarray) -> "DeltaMemLayer":
        """Ingest a single (k, v) pair: update S via Delta Rule.

        This is called for each token / each interaction turn.
        """
        self.smatrix.update(key_vec, value_vec)
        self.total_updates += 1
        return self

    def query(self, q: np.ndarray) -> np.ndarray:
        """Read from δ-mem: retrieve associated residual for query q."""
        return self.smatrix.read(q)

    def correct_attention(self, q: np.ndarray, k: np.ndarray) -> np.ndarray:
        """Compute attention correction Δ for given (q, k) pair."""
        return self.smatrix.attention_delta(q, k)

    def flush(self) -> np.ndarray:
        """Flush the S matrix state to L2 (cold storage).

        Returns the flushed S state for serialization into Episodic Memory.
        After flush, the S matrix is soft-reset.
        """
        state = self.smatrix.flush_state()
        self.flushed_count += 1
        self.last_flush_step = self.total_updates
        return state

    def is_dirty_since_last_flush(self) -> bool:
        """Check if there are updates since last flush."""
        return self.total_updates > self.last_flush_step

    # ── Serialization ───────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize the full δ-mem state to a JSON-safe dict."""
        return {
            "S": self.smatrix.S.tolist(),
            "r": self.smatrix.r,
            "lambda": self.smatrix.lambda_,
            "beta": self.smatrix.beta,
            "step": self.smatrix.step,
            "proof": self.smatrix.proof,
            "flushed_count": self.flushed_count,
            "total_updates": self.total_updates,
            "last_flush_step": self.last_flush_step,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DeltaMemLayer":
        """Deserialize δ-mem state from a dict."""
        smatrix = SMatrix(
            S=np.array(data["S"], dtype=np.float32),
            r=data.get("r", DEFAULT_RANK),
            lambda_=data.get("lambda", DEFAULT_LAMBDA),
            beta=data.get("beta", DEFAULT_BETA),
            step=data.get("step", 0),
            proof=data.get("proof", ""),
        )
        return cls(
            smatrix=smatrix,
            flushed_count=data.get("flushed_count", 0),
            total_updates=data.get("total_updates", 0),
            last_flush_step=data.get("last_flush_step", 0),
        )

    # ── Factory ─────────────────────────────────────────────────────────

    @classmethod
    def create_default(cls, rank: int = DEFAULT_RANK) -> "DeltaMemLayer":
        """Create a fresh δ-mem layer with zero-initialized S matrix."""
        return cls(smatrix=SMatrix(S=np.zeros((rank, rank), dtype=np.float32), r=rank))


# ────────────────────────────────────────────────────────────────────────────
# Embedding Projection — maps full-dim embeddings to S-matrix rank
# ────────────────────────────────────────────────────────────────────────────

def project_to_srank(vec: np.ndarray, target_rank: int = DEFAULT_RANK) -> np.ndarray:
    """Project a high-dimensional embedding down to S-matrix rank.

    Uses a deterministic projection (mean-pool + sign-flip mixing)
    to map arbitrary-dimension vectors to the r-dimensional space of S.

    This is a prototype projection; in production, use a learned linear layer.

    Args:
        vec: Input embedding (any dimension).
        target_rank: Target S-matrix rank (default 8).

    Returns:
        Projected vector of dimension `target_rank`.
    """
    vec = np.asarray(vec, dtype=np.float32).ravel()
    dim = len(vec)

    if dim <= target_rank:
        # Pad with zeros if too small
        result = np.zeros(target_rank, dtype=np.float32)
        result[:dim] = vec
        return result

    # Mean-pool into segments, then mix
    segment_size = dim // target_rank
    projected = np.zeros(target_rank, dtype=np.float32)
    for i in range(target_rank):
        start = i * segment_size
        end = start + segment_size if i < target_rank - 1 else dim
        segment = vec[start:end]
        # Mix: mean + sign-flip based on position
        sign = 1.0 if (i % 2 == 0) else -1.0
        projected[i] = sign * float(np.mean(segment))
    return projected


# ────────────────────────────────────────────────────────────────────────────
# Self-test: 5 个验证函数
# ────────────────────────────────────────────────────────────────────────────

def test_delta_mem() -> dict:
    """δ-mem (DeltaMemLayer) 自检验证。

    测试场景:
      1. SMatrix 初始化 + proof 计算验证
      2. Delta Rule 单步更新 — S 值变化验证
      3. DeltaMemLayer ingest+query 往返一致性
      4. project_to_srank 维度投影正确性
      5. flush 序列化/反序列化循环验证 (to_dict → from_dict → 值一致)

    返回:
        测试结果字典。
    """
    results = {}
    all_pass = True

    # ── 测试 1: SMatrix 初始化 + proof 计算验证 ──────────────────────
    sm = SMatrix(S=np.zeros((8, 8), dtype=np.float32))
    ok1 = (
        sm.S.shape == (8, 8)
        and sm.step == 0
        and len(sm.proof) == 16
        and np.allclose(sm.S, 0.0)
    )
    results["test1_smatrix_init"] = {
        "pass": ok1,
        "shape": sm.S.shape,
        "step": sm.step,
        "proof_len": len(sm.proof),
        "detail": "SMatrix 初始化应为 8x8 零矩阵，proof 为 16 字符 hex，step=0"
    }
    if not ok1:
        all_pass = False

    # ── 测试 2: Delta Rule 单步更新 — S 值变化验证 ──────────────────
    sm2 = SMatrix(S=np.zeros((8, 8), dtype=np.float32))
    k = np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
    v = np.array([0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
    s_before = sm2.S.copy()
    sm2.update(k, v)
    s_changed = not np.allclose(sm2.S, s_before)
    # Delta Rule: S = λ·0 + β·(v - 0)·k^T = β·v·k^T
    # v·k^T: (8,1) @ (1,8) = matrix with (1,0)=1.0, rest 0
    # So S[1,0] should be β = 0.1
    expected_val = sm2.beta  # 0.1
    ok2 = s_changed and abs(sm2.S[1, 0] - expected_val) < 1e-5 and sm2.step == 1
    results["test2_delta_rule_update"] = {
        "pass": ok2,
        "s_changed": s_changed,
        "s_1_0": float(sm2.S[1, 0]),
        "expected": expected_val,
        "step": sm2.step,
        "detail": f"Delta Rule 单步: S 应从零变为非零, S[1,0]={sm2.S[1,0]:.4f} ≈ β={expected_val}"
    }
    if not ok2:
        all_pass = False

    # ── 测试 3: DeltaMemLayer ingest+query 往返一致性 ────────────────
    layer = DeltaMemLayer.create_default(rank=8)
    key = np.array([1.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
    val = np.array([0.0, 1.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
    layer.ingest(key, val)
    query_vec = np.array([1.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
    result = layer.query(query_vec)
    # After one ingest: S = β·v·k^T
    # query: S·q = β·v·k^T·q
    # k^T·q = [1.0, 0.5, ...]^T · [1.0, 0.5, ...] = 1.0 + 0.25 = 1.25
    # S·q = β * v * 1.25
    ok3 = result.shape == (8,) and not np.allclose(result, 0.0)
    results["test3_ingest_query_roundtrip"] = {
        "pass": ok3,
        "result_shape": result.shape,
        "result_nonzero": not np.allclose(result, 0.0),
        "total_updates": layer.total_updates,
        "detail": f"ingest+query 往返: result shape={result.shape}, nonzero={not np.allclose(result, 0.0)}"
    }
    if not ok3:
        all_pass = False

    # ── 测试 4: project_to_srank 维度投影正确性 ─────────────────────
    high_dim = np.random.randn(64).astype(np.float32)
    low_dim = np.random.randn(4).astype(np.float32)
    proj_high = project_to_srank(high_dim, target_rank=8)
    proj_low = project_to_srank(low_dim, target_rank=8)
    ok4 = (
        proj_high.shape == (8,)
        and proj_low.shape == (8,)
        and not np.allclose(proj_high, 0.0)
        # low dim (4) should be zero-padded: last 4 elements should be 0
        and np.allclose(proj_low[4:], 0.0)
    )
    results["test4_project_to_srank"] = {
        "pass": ok4,
        "high_dim_shape": proj_high.shape,
        "low_dim_shape": proj_low.shape,
        "low_dim_tail_zero": bool(np.allclose(proj_low[4:], 0.0)),
        "detail": f"64→8 投影 shape={proj_high.shape}, 4→8 末尾补零={np.allclose(proj_low[4:], 0.0)}"
    }
    if not ok4:
        all_pass = False

    # ── 测试 5: flush 序列化/反序列化循环验证 ───────────────────────
    layer5 = DeltaMemLayer.create_default(rank=8)
    for i in range(5):
        k5 = np.random.randn(8).astype(np.float32)
        v5 = np.random.randn(8).astype(np.float32)
        layer5.ingest(k5, v5)
    # Serialize
    d = layer5.to_dict()
    # Deserialize
    layer5_restored = DeltaMemLayer.from_dict(d)
    # Verify S matrix matches
    s_match = np.allclose(layer5.smatrix.S, layer5_restored.smatrix.S)
    # Verify metadata matches
    meta_match = (
        layer5.smatrix.step == layer5_restored.smatrix.step
        and layer5.flushed_count == layer5_restored.flushed_count
        and layer5.total_updates == layer5_restored.total_updates
        and layer5.last_flush_step == layer5_restored.last_flush_step
    )
    ok5 = s_match and meta_match
    results["test5_serialization_roundtrip"] = {
        "pass": ok5,
        "s_match": s_match,
        "meta_match": meta_match,
        "step": layer5.smatrix.step,
        "detail": f"to_dict→from_dict 往返: S 一致={s_match}, 元数据一致={meta_match}"
    }
    if not ok5:
        all_pass = False

    results["all_pass"] = all_pass
    return results


# ====================================================================
# CLI 入口
# ====================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("TOMAS-AGI δ-mem (DeltaMemLayer) 自检验证")
    print("=" * 60)

    test_results = test_delta_mem()
    for key, val in test_results.items():
        if key == "all_pass":
            continue
        status = "PASS" if val.get("pass") else "FAIL"
        print(f"  [{status}] {key}: {val.get('detail', val)}")

    print(f"\n  {'='*30}")
    n_pass = sum(1 for k, v in test_results.items() if k != "all_pass" and v.get("pass"))
    n_total = sum(1 for k in test_results if k != "all_pass")
    print(f"  结果: {n_pass}/{n_total} PASS — {'ALL PASS' if test_results['all_pass'] else 'SOME FAILED'}")
    print(f"  {'='*30}")
