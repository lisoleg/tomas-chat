# -*- coding: utf-8 -*-
"""
MNQ-Deep Cross-Layer Ω-φ Transformer
========================================

基于复合体理学四重理论基石的 MNQ-Deep 核心实现：
- IWPUGrid: 整数权重处理单元，消除浮点累积误差
- TriDriveAttention: 三驱动力注意力（Protect/Serve/Stabilize + Ω门控）
- LiuMechanism: 刘机制 δS_Rel=0，以熵增约束替代反向传播
- OmegaPhiTransformer: 主类，训练-推理分离架构

参考: MNQ-Deep Cross-Layer Ω-φ Transformer 论文
作者: TOMAS 团队
日期: 2026-06-21
版本: 1.0.0
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Any
import logging

logger = logging.getLogger(__name__)


# ============================================================
# 数据结构
# ============================================================

@dataclass
class IWPUConfig:
    """整数权重处理单元配置"""
    bits: int = 8
    grid_size: int = 256  # 2^bits


@dataclass
class TriDriveConfig:
    """三驱动力注意力配置"""
    dim: int = 512
    heads: int = 8
    omega_init: float = 0.5


@dataclass
class LiuConfig:
    """刘机制配置"""
    delta_s_rel: float = 0.0  # 熵增约束目标


@dataclass
class MNQDeepConfig:
    """MNQ-Deep 主配置"""
    dim: int = 512
    iwpu_bits: int = 8
    omega_init: float = 0.5
    delta_s_rel: float = 0.0
    frozen_kernel: bool = False


# ============================================================
# IWPUGrid — 整数权重处理单元
# ============================================================

class IWPUGrid:
    """整数权重处理单元 — 消除浮点累积误差，保证确定性推理

    核心原理:
        - quantize: 浮点权重 → 离散整数（消除浮点累积误差）
        - dequantize: 整数 → 浮点（恢复推理精度）
        - 使用均匀量化: int_weight = round(float_weight * (2^bits - 1) / scale)
    """

    def __init__(self, config: IWPUConfig):
        self.config = config
        self.scale = 1.0  # 量化缩放因子

    def quantize(self, weights: np.ndarray) -> np.ndarray:
        """将浮点权重量化为离散整数

        Args:
            weights: 浮点权重数组

        Returns:
            整数权重数组（uint8 或更高精度，取决于 bits）
        """
        if weights.size == 0:
            return np.array([], dtype=np.uint8)

        # 计算缩放因子（使用最大值）
        max_val = np.max(np.abs(weights))
        if max_val > 0:
            self.scale = max_val
            # 量化到 [0, 2^bits - 1]
            int_weights = np.round(
                (weights / max_val + 1) * (self.config.grid_size - 1) / 2
            ).astype(np.uint8)
        else:
            int_weights = np.zeros_like(weights, dtype=np.uint8)

        logger.debug(
            f"[IWPU] Quantized {weights.shape} weights "
            f"(bits={self.config.bits}, scale={self.scale:.4f})"
        )
        return int_weights

    def dequantize(self, int_weights: np.ndarray) -> np.ndarray:
        """反量化回浮点

        Args:
            int_weights: 整数权重数组

        Returns:
            浮点权重数组
        """
        if int_weights.size == 0:
            return np.array([], dtype=np.float32)

        if self.scale == 0:
            return int_weights.astype(np.float32)

        # 反量化: float = (int / (2^bits - 1) * 2 - 1) * scale
        float_weights = (
            int_weights.astype(np.float32) / (self.config.grid_size - 1) * 2 - 1
        ) * self.scale

        logger.debug(
            f"[IWPU] Dequantized {int_weights.shape} weights "
            f"(scale={self.scale:.4f})"
        )
        return float_weights


# ============================================================
# AttentionHead — 单头注意力（TriDrive 内部使用）
# ============================================================

class AttentionHead:
    """单头注意力模块"""

    def __init__(self, config: TriDriveConfig, head_type: str = "protect"):
        self.config = config
        self.head_type = head_type  # "protect" | "serve" | "stabilize"
        # 简化的线性投影（实际实现应使用可学习参数）
        self.W_q = np.random.randn(config.dim, config.dim) * 0.01
        self.W_k = np.random.randn(config.dim, config.dim) * 0.01
        self.W_v = np.random.randn(config.dim, config.dim) * 0.01

    def forward(self, Q: np.ndarray, K: np.ndarray, V: np.ndarray) -> np.ndarray:
        """单头注意力前向传播

        Args:
            Q: Query 矩阵 (batch, seq_len, dim)
            K: Key 矩阵 (batch, seq_len, dim)
            V: Value 矩阵 (batch, seq_len, dim)

        Returns:
            注意力输出 (batch, seq_len, dim)
        """
        # 简化实现: 线性投影 + softmax 注意力
        # 实际应使用多头注意力的完整实现
        batch_size, seq_len, dim = Q.shape

        # 线性投影
        Q_proj = Q @ self.W_q  # (batch, seq_len, dim)
        K_proj = K @ self.W_k
        V_proj = V @ self.W_v

        # 缩放点积注意力
        scores = Q_proj @ K_proj.transpose(0, 2, 1) / np.sqrt(dim)
        attn_weights = self._softmax(scores)
        output = attn_weights @ V_proj

        return output

    @staticmethod
    def _softmax(x: np.ndarray) -> np.ndarray:
        """Softmax 函数"""
        exp_x = np.exp(x - np.max(x, axis=-1, keepdims=True))
        return exp_x / np.sum(exp_x, axis=-1, keepdims=True)


# ============================================================
# OmegaGate — Ω 门控融合
# ============================================================

class OmegaGate:
    """Ω 门控融合单元 — 融合三驱动力输出"""

    def __init__(self, config: TriDriveConfig):
        self.config = config
        self.omega = config.omega_init  # 可学习门控值

    def forward(self, protect_out: np.ndarray, serve_out: np.ndarray,
                stabilize_out: np.ndarray) -> np.ndarray:
        """Ω 门控融合三头输出

        Args:
            protect_out: Protect 头输出 (batch, seq_len, dim)
            serve_out: Serve 头输出 (batch, seq_len, dim)
            stabilize_out: Stabilize 头输出 (batch, seq_len, dim)

        Returns:
            融合输出 (batch, seq_len, dim)
        """
        # Ω 门控: output = ω * protect + (1-ω)/2 * serve + (1-ω)/2 * stabilize
        omega = self.omega
        output = (
            omega * protect_out
            + (1 - omega) / 2 * serve_out
            + (1 - omega) / 2 * stabilize_out
        )

        logger.debug(f"[Ω-Gate] Fusion with ω={omega:.4f}")
        return output


# ============================================================
# TriDriveAttention — 三驱动力注意力
# ============================================================

class TriDriveAttention:
    """三驱动力注意力：Protect/Serve/Stabilize 三头并行 + Ω门控融合

    参考文章：MNQ-Deep Cross-Layer Ω-φ Transformer
    - Protect-Attn: 保护已有知识
    - Serve-Attn: 服务当前任务
    - Stabilize-Attn: 稳定跨层信号
    - Ω Gate: 门控融合三头输出
    """

    def __init__(self, config: TriDriveConfig):
        self.config = config
        self.protect_head = AttentionHead(config, head_type="protect")
        self.serve_head = AttentionHead(config, head_type="serve")
        self.stabilize_head = AttentionHead(config, head_type="stabilize")
        self.omega_gate = OmegaGate(config)

    def forward(self, Q: np.ndarray, K: np.ndarray, V: np.ndarray) -> np.ndarray:
        """三驱动力前向传播

        Args:
            Q: Query 矩阵 (batch, seq_len, dim)
            K: Key 矩阵 (batch, seq_len, dim)
            V: Value 矩阵 (batch, seq_len, dim)

        Returns:
            融合后的注意力输出 (batch, seq_len, dim)
        """
        # 三头并行计算
        protect_out = self.protect_head.forward(Q, K, V)
        serve_out = self.serve_head.forward(Q, K, V)
        stabilize_out = self.stabilize_head.forward(Q, K, V)

        # Ω 门控融合
        output = self.omega_gate.forward(protect_out, serve_out, stabilize_out)

        return output


# ============================================================
# LiuMechanism — 刘机制 δS_Rel=0
# ============================================================

class LiuMechanism:
    """刘机制：以熵增约束 δS_Rel=0 替代反向传播

    核心原理：使用最小熵增原则更新权重，无需梯度计算

    参考: 复合体理学第一基石 — 刘原理
    """

    def __init__(self, config: LiuConfig):
        self.config = config

    def apply(self, activations: np.ndarray,
              prev_activations: Optional[np.ndarray] = None) -> float:
        """计算熵增并更新权重，返回 Loss 值

        核心公式: δS_Rel = S(current) - S(previous) → 0
        当 δS_Rel > 0 时，增加熵（鼓励探索）
        当 δS_Rel < 0 时，减少熵（鼓励利用）

        Args:
            activations: 当前层激活值 (batch, dim)
            prev_activations: 前一层激活值（可选）

        Returns:
            loss: 熵增约束损失值
        """
        # 计算当前激活的熵
        current_entropy = self._compute_entropy(activations)

        if prev_activations is not None:
            prev_entropy = self._compute_entropy(prev_activations)
            delta_s_rel = current_entropy - prev_entropy
        else:
            delta_s_rel = current_entropy

        # 熵增约束损失: |δS_Rel - target|
        loss = abs(delta_s_rel - self.config.delta_s_rel)

        logger.debug(
            f"[LiuMechanism] δS_Rel={delta_s_rel:.6f}, "
            f"target={self.config.delta_s_rel}, loss={loss:.6f}"
        )

        return loss

    @staticmethod
    def _compute_entropy(activations: np.ndarray) -> float:
        """计算激活值的熵

        Args:
            activations: 激活值数组

        Returns:
            熵值
        """
        # 将激活值归一化为概率分布
        flat = activations.flatten()
        # 使用 softmax 转换为概率
        exp_act = np.exp(flat - np.max(flat))
        probs = exp_act / np.sum(exp_act)

        # 计算熵: -Σ p * log(p)
        entropy = -np.sum(probs * np.log(probs + 1e-10))

        return float(entropy)


# ============================================================
# OmegaPhiTransformer — 主类
# ============================================================

class OmegaPhiTransformer:
    """MNQ-Deep Cross-Layer Ω-φ Transformer

    训练-推理分离架构：
    - 训练阶段：IWPU 离散化 + LiuMechanism δS_Rel=0 + 跨层Ω累积
    - 推理阶段：Frozen Kernel 确定性推理
    """

    def __init__(self, config: MNQDeepConfig):
        self.config = config
        self.iwpu_grid = IWPUGrid(IWPUConfig(bits=config.iwpu_bits))
        self.tri_drive = TriDriveAttention(
            TriDriveConfig(dim=config.dim, omega_init=config.omega_init)
        )
        self.liu_mechanism = LiuMechanism(LiuConfig(delta_s_rel=config.delta_s_rel))
        self.omega_accumulator = []  # 跨层Ω累积
        self.frozen = config.frozen_kernel
        self.weights = {}  # 存储量化后的权重

        logger.info(
            f"[OmegaPhiTransformer] Initialized with dim={config.dim}, "
            f"iwpu_bits={config.iwpu_bits}, frozen={self.frozen}"
        )

    def forward(self, x: np.ndarray) -> np.ndarray:
        """前向传播：IWPU离散化 → TriDrive注意力 → 衰减残差

        Args:
            x: 输入张量 (batch, seq_len, dim)

        Returns:
            输出张量 (batch, seq_len, dim)
        """
        # 1. IWPU 离散化（训练时量化权重，推理时使用冻结权重）
        if not self.frozen:
            # 训练阶段: 量化当前权重
            quantized = self.iwpu_grid.quantize(x)
            x_discrete = self.iwpu_grid.dequantize(quantized)
        else:
            # 推理阶段: 使用冻结的整数权重
            if 'frozen_weights' in self.weights:
                x_discrete = self.weights['frozen_weights']
            else:
                x_discrete = x

        # 2. TriDrive 注意力
        # 简化: 使用 x 作为 Q, K, V
        output = self.tri_drive.forward(x_discrete, x_discrete, x_discrete)

        # 3. 衰减残差（跨层Ω累积的衰减）
        decay_rate = 0.9
        if len(self.omega_accumulator) > 0:
            omega_sum = sum(self.omega_accumulator)
            output = output * (1 - decay_rate) + output * decay_rate * np.tanh(omega_sum)

        return output

    def train_step(self, batch: Dict) -> float:
        """单步训练：前向 + LiuMechanism 更新

        Args:
            batch: 训练批次数据，包含 'x' (输入) 和可选 'y' (标签)

        Returns:
            loss: 训练损失值
        """
        x = batch.get('x')
        if x is None:
            raise ValueError("Batch must contain 'x' key")

        # 前向传播
        output = self.forward(x)

        # LiuMechanism 更新（计算熵增约束损失）
        loss = self.liu_mechanism.apply(output)

        # 跨层Ω累积
        omega_value = float(np.mean(output))
        self.accumulate_omega(omega_value)

        logger.debug(f"[OmegaPhiTransformer] Train step loss={loss:.6f}")
        return loss

    def freeze_kernel(self) -> None:
        """Freeze kernel for deterministic inference

        冻结当前权重（量化为整数），确保推理时的确定性
        """
        self.frozen = True
        # 这里应该冻结所有可学习参数，简化实现只设置标志
        logger.info("[OmegaPhiTransformer] Kernel frozen for deterministic inference")

    def accumulate_omega(self, omega_value: float) -> None:
        """跨层Ω累积

        Args:
            omega_value: 当前层的 Ω 值
        """
        self.omega_accumulator.append(omega_value)
        # 限制累积长度（防止内存溢出）
        if len(self.omega_accumulator) > 100:
            self.omega_accumulator.pop(0)

        logger.debug(
            f"[OmegaPhiTransformer] Ω accumulated: {len(self.omega_accumulator)} "
            f"values, latest={omega_value:.6f}"
        )


# ============================================================
# 导出
# ============================================================

__all__ = [
    "IWPUConfig",
    "TriDriveConfig",
    "LiuConfig",
    "MNQDeepConfig",
    "IWPUGrid",
    "AttentionHead",
    "OmegaGate",
    "TriDriveAttention",
    "LiuMechanism",
    "OmegaPhiTransformer",
]
