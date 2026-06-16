"""
T-Processor v1.0 硬件仿真器
================================

基于 RRAM Crossbar 的模拟存算一体架构，实现 Dead-Zero/MUS/κ-Snap 三大机制的
硬件加速仿真。

核心组件:
- RRAMCrossbar: 存算一体阵列 (I_out = V_in · G)
- DeadZeroComparator: 死零比较器 (硬件熔丝)
- MUSArbiter: MUS 仲裁器 (歧义锁存)
- KSnapScheduler: κ-Snap 调度器 (事件驱动)
- TProcessorV1: 完整 T-Processor 封装
- SiliconPhotonicsInterface: 硅光子接口 (未来扩展)

作者: TOMAS 团队
日期: 2026-06-16
版本: 1.0.0
"""

from typing import List, Dict, Tuple, Optional, Any
import numpy as np
from dataclasses import dataclass
from enum import Enum
import hashlib
import time


# ============================================================
# 数据结构
# ============================================================

class DZLevel(Enum):
    """死零等级"""
    SAFE = 0       # 安全 (| activation | ≥ ε)
    WARNING = 1    # 预警 (ε > | activation | ≥ ε/10)
    DEAD = 2       # 死零 (| activation | < ε/10)


class MUSStatus(Enum):
    """MUS 状态"""
    UNIQUE = 0     # 唯一解
    AMBIGUOUS = 1  # 歧义 (需仲裁)
    CONFLICT = 2   # 冲突 (多解共存)


@dataclass
class CrossbarCell:
    """RRAM 交叉点单元"""
    conductance: float  # 电导值 G (S)
    stuck: bool = False  # 是否卡死 (老化)

    def program(self, target_g: float, v_pulse: float = 2.0) -> bool:
        """编程电导值"""
        self.conductance = np.clip(target_g, 0.0, 1.0)
        return True


@dataclass
class HyperEdgeState:
    """超边在 T-Processor 中的状态"""
    edge_id: str
    activation: float  # 激活值
    dz_level: DZLevel
    mus_status: MUSStatus
    snap_count: int  # κ-snap 触发次数


# ============================================================
# RRAM Crossbar (存算一体阵列)
# ============================================================

class RRAMCrossbar:
    """
    RRAM 存算一体阵列

    物理原理: I_out = V_in · G (欧姆定律 + 基尔霍夫定律)
    每个交叉点存储一个 EML 超边的权重 (电导值)
    输入电压向量 V_in 同时与整个阵列相乘 → 输出电流向量 I_out
    """

    def __init__(self, n_rows: int, n_cols: int, g_min: float = 0.0, g_max: float = 1.0):
        """
        初始化 RRAM 阵列

        Args:
            n_rows: 输入维度 (超边数)
            n_cols: 输出维度 (概念数)
            g_min: 最小电导 (擦除状态)
            g_max: 最大电导 (编程状态)
        """
        self.n_rows = n_rows
        self.n_cols = n_cols
        self.g_min = g_min
        self.g_max = g_max

        # 电导矩阵 G[i,j] = 从超边 i 到概念 j 的权重
        self.G = np.random.uniform(g_min, g_max * 0.1, (n_rows, n_cols))

        # 统计
        self.write_energy = 0.0  # 编程能耗 (J)
        self.read_energy = 0.0   # 读取能耗 (J)

    def load_eml(self, weights: np.ndarray) -> None:
        """
        从 EML 图加载权重到交叉点

        Args:
            weights: 权重矩阵 (n_rows, n_cols)
        """
        assert weights.shape == (self.n_rows, self.n_cols), "权重矩阵维度不匹配"
        self.G = np.clip(weights, self.g_min, self.g_max)

    def forward(self, v_in: np.ndarray) -> np.ndarray:
        """
        前向传播 (存算一体)

        物理过程:
        1. V_in 施加到字线 (word lines)
        2. 每个交叉点产生电流 I_ij = V_i · G_ij
        3. 位线 (bit lines) 汇总电流 I_out_j = Σ_i I_ij

        Args:
            v_in: 输入电压向量 (n_rows,)

        Returns:
            I_out: 输出电流向量 (n_cols,) → 对应激活值
        """
        v_in = np.asarray(v_in, dtype=np.float64)

        # 存算一体: I_out = V_in · G
        i_out = np.dot(v_in, self.G)

        # 能耗模型 (简化)
        self.read_energy += np.sum(np.abs(v_in)) * 0.1

        return i_out

    def program_cell(self, i: int, j: int, g_target: float) -> bool:
        """编程单个交叉点"""
        if i < 0 or i >= self.n_rows or j < 0 or j >= self.n_cols:
            return False
        self.G[i, j] = np.clip(g_target, self.g_min, self.g_max)
        self.write_energy += 0.01  # 脉冲能耗
        return True

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "n_rows": self.n_rows,
            "n_cols": self.n_cols,
            "g_mean": float(np.mean(self.G)),
            "g_std": float(np.std(self.G)),
            "stuck_ratio": float(np.sum(self.G == self.g_min) / self.G.size),
            "write_energy": self.write_energy,
            "read_energy": self.read_energy,
        }


# ============================================================
# Dead-Zero Comparator (死零比较器)
# ============================================================

class DeadZeroComparator:
    """
    死零比较器 (硬件熔丝)

    物理实现: 比较器 + 阈值检测电路
    当激活值接近零时触发 "死零" 信号 → 熔断对应电路路径
    """

    def __init__(self, epsilon: float = 1e-3, warning_ratio: float = 0.1):
        """
        初始化死零比较器

        Args:
            epsilon: 死零阈值
            warning_ratio: 预警比例 (epsilon * warning_ratio = 预警阈值)
        """
        self.epsilon = epsilon
        self.warning_threshold = epsilon * warning_ratio
        self.trigger_count = 0
        self.fuse_blown = False

    def check(self, activation: float) -> DZLevel:
        """
        检测死零

        Args:
            activation: 激活值 (绝对值)

        Returns:
            DZLevel: 死零等级
        """
        abs_act = abs(float(activation))

        if abs_act < self.warning_threshold:
            self.trigger_count += 1
            return DZLevel.DEAD
        elif abs_act < self.epsilon:
            return DZLevel.WARNING
        else:
            return DZLevel.SAFE

    def batch_check(self, activations: np.ndarray) -> List[DZLevel]:
        """批量检测"""
        return [self.check(a) for a in activations]

    def graft(self, i_out: np.ndarray, dead_mask: np.ndarray) -> np.ndarray:
        """
        Dead-Zero Grafting (死零嫁接)

        将死零位置的输出嫁接到安全值:
        I_out'[i] = I_out[i] if not dead else mean(I_out[alive])

        Args:
            i_out: 原始输出
            dead_mask: 死零掩码

        Returns:
            嫁接后的输出
        """
        i_out = np.asarray(i_out, dtype=np.float64)
        alive_mask = ~dead_mask

        if np.sum(alive_mask) == 0:
            # 全部死零 → 返回零
            return np.zeros_like(i_out)

        alive_mean = np.mean(i_out[alive_mask])
        i_out_grafted = i_out.copy()
        i_out_grafted[dead_mask] = alive_mean

        return i_out_grafted


# ============================================================
# MUS Arbiter (MUS 仲裁器)
# ============================================================

class MUSArbiter:
    """
    MUS 仲裁器 (歧义锁存)

    物理实现: 比较器链 + 锁存电路
    当多个输出同时激活 (MUS 歧义) 时，选择最优解并锁存
    """

    def __init__(self, score_threshold: float = 0.1, max_ambiguity: int = 3):
        """
        初始化 MUS 仲裁器

        Args:
            score_threshold: 分数差阈值 (小于此值视为歧义)
            max_ambiguity: 最大歧义数 (超过则标记为 CONFLICT)
        """
        self.score_threshold = score_threshold
        self.max_ambiguity = max_ambiguity
        self.latch_state = None  # 锁存状态

    def arbitrate(self, outputs: np.ndarray, metadata: List[Dict] = None) -> Tuple[np.ndarray, List[Dict]]:
        """
        MUS 仲裁

        算法:
        1. 找出 top-k 输出 (k ≤ max_ambiguity)
        2. 如果 top-1 和 top-2 分数差 < threshold → 歧义
        3. 返回仲裁后的输出 + 元数据

        Args:
            outputs: 输出向量
            metadata: 每个输出的元数据

        Returns:
            (arbitrated_outputs, updated_metadata)
        """
        outputs = np.asarray(outputs, dtype=np.float64)
        n = len(outputs)

        if metadata is None:
            metadata = [{} for _ in range(n)]

        # 找出 top-k
        top_indices = np.argsort(outputs)[::-1][:self.max_ambiguity]
        top_values = outputs[top_indices]

        # 判断歧义
        if len(top_values) >= 2:
            score_diff = abs(float(top_values[0]) - float(top_values[1]))
            if score_diff < self.score_threshold:
                # 歧义 → 标记
                for idx in top_indices[:2]:
                    metadata[idx]["mus_status"] = MUSStatus.AMBIGUOUS
                self.latch_state = "ambiguous"
            else:
                # 唯一解
                metadata[top_indices[0]]["mus_status"] = MUSStatus.UNIQUE
                self.latch_state = "unique"
        else:
            metadata[top_indices[0]]["mus_status"] = MUSStatus.UNIQUE
            self.latch_state = "unique"

        # 仲裁: 保留 top-1, 其他置零
        arbitrated = np.zeros_like(outputs)
        arbitrated[top_indices[0]] = outputs[top_indices[0]]

        return arbitrated, metadata

    def mark_dual_box(self, box1: Dict, box2: Dict, scene: np.ndarray) -> Dict:
        """
        MUS 双框标记 (用于 T-Shield)

        当检测到歧义时，在两个候选框上都标记 MUS 警示

        Args:
            box1: 候选框 1
            box2: 候选框 2
            scene: 场景特征

        Returns:
            更新后的场景评估
        """
        return {
            "box1_marked": True,
            "box2_marked": True,
            "ambiguity_score": float(np.random.rand()),
            "recommendation": "human_review"
        }


# ============================================================
# κ-Snap Scheduler (κ-Snap 调度器)
# ============================================================

class KSnapScheduler:
    """
    κ-Snap 调度器 (事件驱动)

    物理实现: 事件检测电路 + 配置切换
    仅在 κ 事件 (显著变化) 发生时触发计算，其他时间休眠
    """

    def __init__(self, kappa_threshold: float = 0.5, cooldown: int = 3):
        """
        初始化 κ-Snap 调度器

        Args:
            kappa_threshold: κ 事件阈值
            cooldown: 冷却周期 (避免频繁切换)
        """
        self.kappa_threshold = kappa_threshold
        self.cooldown = cooldown
        self.last_snap = -cooldown
        self.snap_count = 0
        self.current_config = 0  # 当前配置 ID

    def step(self, t: int, delta: float) -> bool:
        """
        时间步推进

        Args:
            t: 当前时间步
            delta: 变化量 (| new_state - old_state |)

        Returns:
            True if κ-snap 触发
        """
        if t - self.last_snap < self.cooldown:
            return False

        if delta >= self.kappa_threshold:
            self.last_snap = t
            self.snap_count += 1
            return True
        return False

    def select_config(self, scene_complexity: float) -> int:
        """
        根据场景复杂度选择配置

        Args:
            scene_complexity: 场景复杂度 [0, 1]

        Returns:
            配置 ID (0=轻量, 1=标准, 2=深度)
        """
        if scene_complexity < 0.3:
            self.current_config = 0  # 轻量配置
        elif scene_complexity < 0.7:
            self.current_config = 1  # 标准配置
        else:
            self.current_config = 2  # 深度配置

        return self.current_config

    def get_schedule(self) -> Dict:
        """获取调度计划"""
        return {
            "next_snap": self.last_snap + self.cooldown,
            "snap_count": self.snap_count,
            "current_config": self.current_config,
        }


# ============================================================
# T-Processor v1.0 (完整封装)
# ============================================================

class TProcessorV1:
    """
    T-Processor v1.0 完整封装

    工作流程:
    1. 输入 → RRAM Crossbar (存算一体前向传播)
    2. 输出 → Dead-Zero Comparator (死零检测)
    3. 候选 → MUS Arbiter (歧义仲裁)
    4. 触发 → κ-Snap Scheduler (事件调度)
    5. 输出 → 结构化结果
    """

    def __init__(self, n_inputs: int, n_outputs: int):
        """
        初始化 T-Processor

        Args:
            n_inputs: 输入维度 (超边数)
            n_outputs: 输出维度 (概念数)
        """
        self.crossbar = RRAMCrossbar(n_inputs, n_outputs)
        self.dz_comparator = DeadZeroComparator()
        self.mus_arbiter = MUSArbiter()
        self.snap_scheduler = KSnapScheduler()

        self.t = 0  # 时间步
        self.history = []  # 历史记录

    def tick(self, inputs: np.ndarray, prev_state: Optional[np.ndarray] = None) -> Dict:
        """
        时间步推进 (完整 T-Processor 周期)

        Args:
            inputs: 输入向量
            prev_state: 上一时间步状态 (用于 κ-snap)

        Returns:
            结果字典
        """
        self.t += 1

        # 1. RRAM Crossbar 前向传播
        i_out = self.crossbar.forward(inputs)

        # 2. Dead-Zero 检测
        dz_levels = self.dz_comparator.batch_check(i_out)
        dead_mask = np.array([level == DZLevel.DEAD for level in dz_levels])

        # 3. Dead-Zero Grafting
        if np.any(dead_mask):
            i_out = self.dz_comparator.graft(i_out, dead_mask)

        # 4. MUS 仲裁
        metadata = [{"dz_level": level} for level in dz_levels]
        i_out_arbitrated, metadata = self.mus_arbiter.arbitrate(i_out, metadata)

        # 5. κ-Snap 调度
        if prev_state is not None:
            delta = float(np.max(np.abs(i_out - prev_state)))
            snap_triggered = self.snap_scheduler.step(self.t, delta)
        else:
            snap_triggered = False

        # 6. 记录历史
        result = {
            "t": self.t,
            "raw_output": i_out.tolist(),
            "arbitrated_output": i_out_arbitrated.tolist(),
            "dead_mask": dead_mask.tolist(),
            "snap_triggered": snap_triggered,
            "dz_stats": {
                "n_dead": int(np.sum(dead_mask)),
                "n_warning": int(np.sum([level == DZLevel.WARNING for level in dz_levels])),
            }
        }
        self.history.append(result)

        return result

    def load_eml(self, eml_path: str) -> bool:
        """从 EML 文件加载权重"""
        try:
            # 简化: 随机初始化
            n = self.crossbar.n_rows
            m = self.crossbar.n_cols
            weights = np.random.uniform(0.1, 0.5, (n, m))
            self.crossbar.load_eml(weights)
            return True
        except Exception:
            return False

    def get_stats(self) -> Dict:
        """获取完整统计"""
        return {
            "t": self.t,
            "crossbar": self.crossbar.get_stats(),
            "snap_scheduler": self.snap_scheduler.get_schedule(),
            "history_len": len(self.history),
        }


# ============================================================
# 硅光子接口 (未来扩展)
# ============================================================

class SiliconPhotonicsInterface:
    """
    硅光子接口 (未来扩展)

    物理原理: 光波导 + 微环谐振器
    用光强度表示激活值 → 光速计算 + 低能耗
    """

    def __init__(self, n_channels: int = 128):
        self.n_channels = n_channels
        self.wavelengths = np.linspace(1540, 1560, n_channels)  # C 波段

    def optical_forward(self, inputs: np.ndarray) -> np.ndarray:
        """
        光学前向传播 (未来实现)

        原理: I_out = |W · E_in|^2 (相干叠加)
        """
        # TODO: 实现光学矩阵乘法
        raise NotImplementedError("硅光子计算模块待硬件支持")


# ============================================================
# 可证伪预言 (Certifiable Falsification Prophecies)
# ============================================================

"""
以下预言可在硅后验证 (post-silicon verification):

1. 【RRAM 能耗预言】
   当 n_rows=512, n_cols=512, 单次前向传播能耗 < 1mJ
   → 验证方法: 测量芯片 VDD 电流积分

2. 【死零熔断预言】
   当 |activation| < ε/10 时, 比较器输出 LOW → 熔丝熔断
   → 验证方法: 用示波器观察比较器输出引脚

3. 【MUS 仲裁延迟预言】
   当 top-1 和 top-2 分数差 < 0.1 时, 仲裁器延迟 < 10ns
   → 验证方法: 用高速逻辑分析仪捕获仲裁时序

4. 【κ-Snap 事件驱动预言】
   当场景无变化 (δ < κ_threshold) 时, 功耗接近休眠电流 (< 1mW)
   → 验证方法: 用电源分析仪测量静态功耗

5. 【存算一体精度预言】
   当使用 8-bit 量化电导时, 矩阵乘法误差 < 2%
   → 验证方法: 用已知输入向量和预期输出对比
"""


if __name__ == "__main__":
    # 快速测试
    print("=== T-Processor v1.0 仿真测试 ===\n")

    # 创建处理器
    tp = TProcessorV1(n_inputs=10, n_outputs=5)
    print(f"初始化完成: {tp.get_stats()}")

    # 模拟几步
    for i in range(5):
        inputs = np.random.randn(10)
        result = tp.tick(inputs)
        print(f"\nt={result['t']}: "
              f"dead={result['dz_stats']['n_dead']}, "
              f"snap={result['snap_triggered']}")

    print("\n=== 测试完成 ===")
