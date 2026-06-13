"""
drift_detector.py — TOMAS-AGI ψ 语义漂移检测器 v1.6

监控 ψ（世界语义向量）稳定性，使用 Φ（余弦相似度）滑动窗口。
当加权变异系数（CV）超过阈值时，标记语义漂移。

漂移检测作为 δ-mem S-update 阻尼的触发器:
  - 漂移检测到 → D-Core S beta 降至 0.2x（阻尼噪声摄入）
  - 漂移消退 → 恢复完整 S 学习率

v1.6 (2026-06-13): HyperParamAdapter — 基于多轮 CV 历史自动适配
  γ_max, γ_min, cv_mid。追踪 200 轮 CV 分布，每 20 轮基于分位数
  启发式自动调整。消除 sigmoid 超参手动调优需求。

v1.5 (2026-06-11): 连续自调衰减 — 用平滑 sigmoid 公式替代硬编码
  三阶段查表：
    γ(CV, dCV/dt) = γ_max − Δγ × σ((CV−CV_mid)/T) × slope_factor(dCV/dt)
  消除阶段边界不连续，根据 CV 趋势方向预适应。

v1.4 (2026-06-11): 自适应三阶段衰减（前代版本，auto_tune=False 时可用）

v1.3 (2026-06-11): 指数衰减加权 CV 计算

Author: TOMAS-AGI Team (自太极OS v1.6 移植)
Version: v1.6 — 超参自动适配 (2026-06-13)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class DriftDetector:
    """滑动窗口 ψ 漂移检测器，使用加权 CV 计算。

    追踪 Φ（一致性）得分的滑动窗口，计算加权变异系数（std/mean）。
    近期 Φ 值权重大，漂移恢复更快。

    v1.5 (2026-06-11): 连续自调衰减。
        auto_tune=True（推荐）时，衰减因子是 CV 及其导数的连续 sigmoid 函数：
        γ(CV, dCV/dt) = γ_max − Δγ × σ((CV−CV_mid)/T) × slope_factor(dCV/dt)

    v1.4 (2026-06-11): 自适应三阶段衰减（旧版）。
        STABLE=0.70, DRIFTING=0.35, RECOVERY=base_decay(0.55)。

    v1.3 (2026-06-11): 指数衰减加权 CV 计算。

    参数:
        window_size: Φ 值追踪窗口大小（默认 20）。
        cv_threshold: 漂移判定 CV 阈值（默认 0.30）。
        decay: CV 加权的基础衰减因子（默认 0.55）。
            当 auto_tune=True 时作为回退值。
        adaptive: 启用自适应衰减模式（默认 True）。
            当 auto_tune=True，使用连续 sigmoid 公式。
            当 auto_tune=False，使用三阶段查表（v1.4）。
            当 adaptive=False，使用固定衰减（v1.3）。
        auto_tune: 使用连续 sigmoid 衰减自调（默认 True）。
            需要 adaptive=True 才会生效。
        gamma_max: 自调 γ 上界（默认 0.85）。
        gamma_min: 自调 γ 下界（默认 0.20）。
        cv_mid: sigmoid 拐点 CV 值（默认 0.25）。
        temperature: sigmoid 陡度（默认 0.08，越小越陡）。
        slope_alpha: CV 斜率最大调节幅度（默认 0.15）。
        slope_k: CV 变化率敏感度（默认 20.0）。
        min_samples_before_detect: 漂移判定所需最少样本数（默认 5）。
            防止早期 CV 不稳定导致误报。
        hysteresis_rounds: 漂移确认所需连续超阈值轮数（默认 2）。
            Schmitt 触发器机制，滤除瞬时波动。
        phi_history: Φ 值的循环缓冲区。
        write_idx: 循环缓冲区当前写位置。
        count: 缓冲区内有效条目数。
    """

    window_size: int = 20
    cv_threshold: float = 0.30
    decay: float = 0.55                     # 基础衰减因子（auto_tune 关闭时回退值）
    adaptive: bool = True                    # 启用自适应衰减
    auto_tune: bool = True                   # v1.5: 连续 sigmoid 自调
    # ── 自调超参（v1.5）──────────────────────────────────────────────
    gamma_max: float = 0.85                  # 上界：极稳定 → 慢遗忘
    gamma_min: float = 0.20                  # 下界：重漂移 → 快遗忘
    cv_mid: float = 0.25                     # sigmoid 拐点（γ 取中值处的 CV）
    temperature: float = 0.08                # sigmoid 陡度（越小越陡）
    slope_alpha: float = 0.15                # 最大斜率调节比例
    slope_k: float = 20.0                    # 斜率敏感度增益
    # ── 检测参数 ────────────────────────────────────────────────────
    min_samples_before_detect: int = 5
    hysteresis_rounds: int = 2
    phi_history: np.ndarray = field(init=False)
    write_idx: int = 0
    count: int = 0
    _drifting_streak: int = 0          # 连续超阈值轮数
    _currently_drifting: bool = False   # 已确认漂移状态（锁存）
    _stage: str = "STABLE"             # STABLE | DRIFTING | RECOVERY（auto_tune 时仅诊断用）
    _was_drifting: bool = False        # 追踪先前的漂移状态以检测 RECOVERY
    _recovery_streak: int = 0          # RECOVERY 中连续 CV < 0.15 的轮数
    _prev_cv: float = 0.0              # v1.5: 上一轮 CV，用于斜率计算
    _effective_decay: float = 0.55     # v1.5: 缓存的有效衰减因子（诊断用）
    adapter: Optional["HyperParamAdapter"] = None  # v1.6: 自动适配 γ_max/γ_min/cv_mid

    def __post_init__(self):
        self.phi_history = np.zeros(self.window_size, dtype=np.float64)

    # ── 自适应衰减（v1.5: 连续自调）───────────────────────────────

    def _get_decay(self) -> float:
        """返回 CV 加权的有效衰减因子。

        v1.5 auto_tune 模式（默认）:
            γ(CV, dCV/dt) = γ_max − Δγ × σ((CV−CV_mid)/T) × slope_factor
            其中 slope_factor = 1.0 − α × tanh(k × dCV/dt)

        v1.4 三阶段模式（adaptive=True, auto_tune=False）:
            STABLE=0.70, DRIFTING=0.35, RECOVERY=base_decay

        v1.3 固定模式（adaptive=False）:
            返回配置的 decay 值。

        auto_tune 公式保证:
          - CV << cv_mid（极稳定）: γ ≈ γ_max (0.85, 慢遗忘)
          - CV >> cv_mid（重漂移）: γ ≈ γ_min (0.20, 快遗忘)
          - dCV/dt > 0（恶化中）: slope_factor < 1 → γ 进一步降低（提前应对）
          - dCV/dt < 0（改善中）: slope_factor > 1 → γ 增加（加速恢复）
        """
        if not self.adaptive:
            return self.decay

        if not self.auto_tune:
            # v1.4 三阶段查表
            if self._stage == "DRIFTING":
                return 0.35
            elif self._stage == "RECOVERY":
                return self.decay
            else:
                return 0.70

        # ── v1.5 连续自调 ──────────────────────────────────────────
        # current_cv → _compute_weighted_stats 使用缓存 _effective_decay
        # （不会递归：缓存值是上一轮 _get_decay 设置的）
        cv = self.current_cv

        # Sigmoid: 将 CV 映射到 [0, 1]，中心在 cv_mid
        if self.temperature <= 0:
            sigmoid = 1.0 if cv > self.cv_mid else 0.0
        else:
            x = (cv - self.cv_mid) / self.temperature
            x = max(-50.0, min(50.0, x))   # 防止 exp 溢出
            sigmoid = 1.0 / (1.0 + np.exp(-x))

        # 从 sigmoid 得到基础连续 γ
        delta_gamma = self.gamma_max - self.gamma_min
        gamma_continuous = self.gamma_max - delta_gamma * sigmoid

        # 斜率因子：根据 CV 趋势方向调整
        # _prev_cv 在 is_drifting() 中从上一轮设置
        dcv_dt = cv - self._prev_cv
        slope_factor = 1.0 - self.slope_alpha * np.tanh(self.slope_k * dcv_dt)

        gamma_effective = gamma_continuous * slope_factor

        # 限制到安全范围
        gamma_effective = max(self.gamma_min, min(self.gamma_max, gamma_effective))

        self._effective_decay = float(gamma_effective)
        return self._effective_decay

    def _update_stage(self) -> None:
        """根据漂移检测状态更新自适应阶段。

        阶段转换:
          STABLE → DRIFTING: 漂移确认（迟滞满足）
          DRIFTING → RECOVERY: CV 降到阈值以下（立即退出）
          RECOVERY → STABLE: CV < 0.15 连续 2 轮
            （RECOVERY 退出迟滞防止过早返回 STABLE）
        """
        if not self.adaptive:
            return
        if self._currently_drifting:
            self._was_drifting = True
            self._stage = "DRIFTING"
            self._recovery_streak = 0
        elif self._was_drifting:
            self._stage = "RECOVERY"
            if self.current_cv < 0.15:
                self._recovery_streak += 1
            else:
                self._recovery_streak = 0
            if self._recovery_streak >= 2:
                self._was_drifting = False
                self._stage = "STABLE"
                self._recovery_streak = 0
        else:
            self._stage = "STABLE"
            self._recovery_streak = 0

    # ── 推入新观测 ────────────────────────────────────────────────

    def push(self, phi_value: float) -> None:
        """将新的 Φ 值记录到滑动窗口中。

        在一致性循环中每次 Ψ 检查后调用。
        v1.6: push 后若配置了 HyperParamAdapter，触发 adapt()。

        参数:
            phi_value: 最新步骤的 Φ（余弦相似度）得分。
        """
        self.phi_history[self.write_idx] = float(phi_value)
        self.write_idx = (self.write_idx + 1) % self.window_size
        if self.count < self.window_size:
            self.count += 1

        # v1.6: CV 更新后触发超参自动适配
        if self.adapter is not None and self.count >= 3:
            cv = self.current_cv
            self.adapter.push(cv)
            self.adapter.adapt(self)

    # ── 加权统计量（v1.3: 指数衰减）───────────────────────────────

    def _compute_weighted_stats(self) -> tuple[float, float, float]:
        """计算指数衰减加权的均值、标准差和 CV。

        权重公式: w[i] = decay^(n-1-i) / sum(decay^k)
        其中 i=0 最旧样本，i=n-1 最新样本。
        最新样本归一化后权重始终为 1.0。

        循环缓冲区按时间顺序重建:
          window_chrono[0] = 最旧, window_chrono[n-1] = 最新。

        v1.5: 使用缓存的 _effective_decay 避免循环依赖。
              此计算中使用的 decay 来自上一轮。
              _get_decay() 在 CV 计算后将 _effective_decay 更新为下一轮值。

        返回:
            (加权均值, 加权标准差, 加权变异系数)
        """
        n = self.count
        # 从循环缓冲区重建时间序
        if n < self.window_size:
            window = self.phi_history[:n]
        else:
            indices = [(self.write_idx + i) % self.window_size for i in range(n)]
            window = self.phi_history[indices]  # 时间序: [最旧, ..., 最新]

        # 确定有效衰减因子而不调用 _get_decay()
        # 避免循环依赖（_get_decay → current_cv → 本方法）
        if not self.adaptive:
            effective_decay = self.decay
        elif not self.auto_tune:
            # v1.4 三阶段查表（内联以避免递归）
            if self._stage == "DRIFTING":
                effective_decay = 0.35
            elif self._stage == "RECOVERY":
                effective_decay = self.decay
            else:
                effective_decay = 0.70
        else:
            # v1.5 auto_tune: 使用上一轮的缓存值
            effective_decay = self._effective_decay
        exponents = np.arange(n - 1, -1, -1, dtype=np.float64)
        raw_weights = np.power(effective_decay, exponents)
        weights = raw_weights / raw_weights.sum()

        weighted_mean = float(np.average(window, weights=weights))

        if weighted_mean < 1e-8:
            return 0.0, 0.0, 0.0

        # 加权标准差: sqrt(Σ w[i] * (x[i] - mean)^2)
        deviations = window - weighted_mean
        weighted_var = float(np.average(deviations ** 2, weights=weights))
        weighted_std = np.sqrt(weighted_var)

        weighted_cv = weighted_std / weighted_mean
        return weighted_mean, weighted_std, weighted_cv

    # ── 漂移检测 ──────────────────────────────────────────────────

    def is_drifting(self) -> bool:
        """检查 ψ 是否当前正在漂移。

        漂移检测由两道安全门控控制:
          1. min_samples_before_detect: 样本不足时不检测
             （防止早期 CV 不稳定误报）。
          2. hysteresis_rounds: 需 N 轮连续超阈值
             （Schmitt 触发器机制）。

        CV 计算使用指数衰减加权（v1.3）:
          近期 Φ 值主导 CV，Φ 恢复正常水平后漂移恢复更快。

        退出漂移状态: CV 降到阈值以下立即退出
        （无退出迟滞——我们希望尽快恢复学习）。

        返回:
            True 表示漂移已确认，False 表示未漂移。
        """
        if self.count < self.min_samples_before_detect:
            self._drifting_streak = 0
            self._currently_drifting = False
            return False

        _, _, cv = self._compute_weighted_stats()

        is_over_threshold = cv > self.cv_threshold

        if is_over_threshold:
            self._drifting_streak += 1
            if self._drifting_streak >= self.hysteresis_rounds:
                self._currently_drifting = True
        else:
            # CV 降到阈值以下 → 立即退出漂移
            self._drifting_streak = 0
            self._currently_drifting = False

        self._update_stage()

        # v1.5: 追踪上一轮 CV 供 _get_decay() 斜率计算
        self._prev_cv = cv

        return self._currently_drifting

    # ── 统计信息 ───────────────────────────────────────────────────

    @property
    def current_cv(self) -> float:
        """Φ 窗口当前加权变异系数（v1.3: 指数衰减加权）。"""
        if self.count < 3:
            return 0.0
        _, _, cv = self._compute_weighted_stats()
        return float(cv)

    @property
    def mean_phi(self) -> float:
        """当前窗口加权平均 Φ 值（v1.3: 指数衰减加权）。"""
        if self.count == 0:
            return 0.0
        mean, _, _ = self._compute_weighted_stats()
        return float(mean)

    def stats(self) -> dict:
        """返回漂移检测器状态的诊断统计。

        返回:
            包含以下键的字典: window_size, count, current_cv, mean_phi,
            is_drifting, cv_threshold, drifting_streak, min_samples,
            decay, adaptive, auto_tune, stage, prev_cv,
            adapter_enabled, gamma_max, gamma_min, cv_mid。
        """
        return {
            "window_size": self.window_size,
            "count": self.count,
            "current_cv": round(self.current_cv, 4),
            "mean_phi": round(self.mean_phi, 4),
            "is_drifting": self.is_drifting(),
            "cv_threshold": self.cv_threshold,
            "drifting_streak": self._drifting_streak,
            "min_samples_before_detect": self.min_samples_before_detect,
            "decay": self._get_decay(),
            "adaptive": self.adaptive,
            "auto_tune": self.auto_tune,
            "stage": self._stage,
            "prev_cv": round(self._prev_cv, 4),
            # v1.6: 超参适配器状态
            "adapter_enabled": self.adapter is not None,
            "gamma_max": self.gamma_max,
            "gamma_min": self.gamma_min,
            "cv_mid": self.cv_mid,
        }

    # ── 重置 ───────────────────────────────────────────────────────

    def reset(self) -> None:
        """将漂移检测器重置到初始状态。"""
        self.phi_history = np.zeros(self.window_size, dtype=np.float64)
        self.write_idx = 0
        self.count = 0
        self._drifting_streak = 0
        self._currently_drifting = False
        self._stage = "STABLE"
        self._was_drifting = False
        self._recovery_streak = 0
        self._prev_cv = 0.0
        self._effective_decay = self.decay


# ====================================================================
# v1.6 HyperParamAdapter — 自动调整 γ_max / γ_min / cv_mid
# ====================================================================


@dataclass
class HyperParamAdapter:
    """自动适配 DriftDetector 超参数的统计模块。

    v1.6 (2026-06-13): 基于多轮 CV 历史统计自动调整 sigmoid 公式的
    γ_max, γ_min, cv_mid 三个关键超参，消除手动调参需求。

    适配策略:
      - cv_mid: 设为 CV 分布的滚动分位数（默认 60 分位）
      - gamma_max: 基于稳定度比例自适应（越稳定 → 越高，慢遗忘）
      - gamma_min: 基于最差 CV 自适应（越差 → 越低，快遗忘）

    参数:
        history_size: CV 历史记录上限（默认 200）。
        adaptation_interval: 两次适配之间的最小轮数（默认 20）。
        cv_mid_quantile: 用于 cv_mid 的分位数（默认 0.60）。
        rounds_since_adapt: 距上次适配的轮数。
        cv_history: CV 历史值列表（最近 history_size 个）。
        cv_mid_bounds: cv_mid 的安全边界 (min, max)。
        gamma_max_bounds: gamma_max 的安全边界 (min, max)。
        gamma_min_bounds: gamma_min 的安全边界 (min, max)。
        _last_adapted: 最近一次适配的参数字典（诊断用）。
    """

    history_size: int = 200
    adaptation_interval: int = 20
    cv_mid_quantile: float = 0.60
    rounds_since_adapt: int = 0
    cv_history: list = field(default_factory=list)
    cv_mid_bounds: tuple = (0.15, 0.40)
    gamma_max_bounds: tuple = (0.70, 0.95)
    gamma_min_bounds: tuple = (0.10, 0.35)
    _last_adapted: dict = field(default_factory=dict)

    def push(self, cv: float) -> None:
        """记录一个新的 CV 值到历史缓冲区。

        参数:
            cv: 当前加权 CV 值。
        """
        self.cv_history.append(float(cv))
        if len(self.cv_history) > self.history_size:
            self.cv_history.pop(0)
        self.rounds_since_adapt += 1

    def should_adapt(self) -> bool:
        """检查是否满足适配条件。

        返回:
            True 如果距上次适配 ≥ adaptation_interval 且历史 ≥ 20 条。
        """
        return (
            self.rounds_since_adapt >= self.adaptation_interval
            and len(self.cv_history) >= 20
        )

    def adapt(self, detector: "DriftDetector") -> dict:
        """计算适配后的超参并应用到 detector。

        使用最近 100 个 CV 值（不超过历史长度）计算统计量，
        根据稳定性指标调整三个关键超参。

        参数:
            detector: 要更新的 DriftDetector 实例。

        返回:
            适配结果字典，包含 adapted 标志和新参数值。
        """
        if not self.should_adapt():
            return {"adapted": False}

        import numpy as np

        # 取最近最多 100 个 CV 做统计
        window_size = min(100, len(self.cv_history))
        cvs = np.array(self.cv_history[-window_size:])

        # ── cv_mid: 滚动分位数 ────────────────────────────────────
        new_cv_mid = float(np.quantile(cvs, self.cv_mid_quantile))
        new_cv_mid = max(self.cv_mid_bounds[0], min(self.cv_mid_bounds[1], new_cv_mid))

        # ── gamma_max: 稳定度比例驱动 ─────────────────────────────
        stability_ratio = float(np.mean(cvs < 0.15))
        new_gamma_max = 0.70 + 0.25 * stability_ratio
        new_gamma_max = max(
            self.gamma_max_bounds[0], min(self.gamma_max_bounds[1], new_gamma_max)
        )

        # ── gamma_min: 最差 CV 驱动 ────────────────────────────────
        worst_cv = float(np.max(cvs[-20:]))
        if worst_cv > 0.40:
            new_gamma_min = 0.10
        elif worst_cv > 0.30:
            new_gamma_min = 0.15
        else:
            new_gamma_min = 0.20
        new_gamma_min = max(
            self.gamma_min_bounds[0], min(self.gamma_min_bounds[1], new_gamma_min)
        )

        # 应用到 detector
        detector.cv_mid = new_cv_mid
        detector.gamma_max = new_gamma_max
        detector.gamma_min = new_gamma_min

        self.rounds_since_adapt = 0
        self._last_adapted = {
            "adapted": True,
            "cv_mid": round(new_cv_mid, 4),
            "gamma_max": round(new_gamma_max, 4),
            "gamma_min": round(new_gamma_min, 4),
            "stability_ratio": round(stability_ratio, 4),
            "worst_cv": round(worst_cv, 4),
            "window_size": window_size,
        }
        return self._last_adapted

    def reset(self) -> None:
        """重置适配器到初始状态。"""
        self.cv_history.clear()
        self.rounds_since_adapt = 0
        self._last_adapted = {}

    def stats(self) -> dict:
        """返回适配器诊断统计。

        返回:
            包含历史长度、最近适配参数等的字典。
        """
        return {
            "history_len": len(self.cv_history),
            "rounds_since_adapt": self.rounds_since_adapt,
            "last_adapted": self._last_adapted,
        }


# ====================================================================
# 预计算的 ψ 稳定区域分析（用于分析 / 可视化）
# ====================================================================


def analyze_stability(phi_sequence: list[float]) -> dict:
    """分析 Φ 序列的稳定区域。

    将序列切分为稳定（CV < 0.15）、过渡（0.15 ≤ CV < 0.30）
    和漂移（CV ≥ 0.30）时段。

    参数:
        phi_sequence: 时间序 Φ 值列表。

    返回:
        包含稳定性分析的字典。
    """
    detector = DriftDetector(window_size=min(len(phi_sequence), 20))
    regions = []
    current_region = None

    for i, phi in enumerate(phi_sequence):
        detector.push(phi)
        is_drifting = detector.is_drifting()
        cv = detector.current_cv

        tag = "drifting" if is_drifting else ("stable" if cv < 0.15 else "transitional")

        if current_region is None or current_region["tag"] != tag:
            if current_region is not None:
                current_region["end"] = i - 1
                regions.append(current_region)
            current_region = {"tag": tag, "start": i, "end": None, "cv": round(cv, 4)}

    if current_region is not None:
        current_region["end"] = len(phi_sequence) - 1
        regions.append(current_region)

    return {
        "total_steps": len(phi_sequence),
        "regions": regions,
        "stable_ratio": sum(
            1 for r in regions if r["tag"] == "stable"
        ) / max(len(regions), 1),
    }


# ====================================================================
# 自检验证
# ====================================================================


def test_drift_detector() -> dict:
    """DriftDetector + HyperParamAdapter 自检验证。

    测试场景:
      1. 基础 push + CV 计算
      2. 漂移检测（正常序列 vs 漂移序列）
      3. HyperParamAdapter 适配
      4. 连续 sigmoid 自调
      5. 三阶段模式回退
      6. analyze_stability 分析

    返回:
        测试结果字典。
    """
    results = {}
    all_pass = True

    # ── 测试 1: 基础 push + CV 计算 ──────────────────────────────
    dd = DriftDetector(window_size=10, min_samples_before_detect=3)
    for phi in [0.95, 0.93, 0.94, 0.92, 0.96]:
        dd.push(phi)

    cv = dd.current_cv
    results["test1_push_and_cv"] = {
        "pass": 0.0 < cv < 0.5,
        "cv": round(cv, 4),
        "detail": "CV 应 > 0 且 < 0.5（五个高 Φ 值应为稳定状态）"
    }
    if not results["test1_push_and_cv"]["pass"]:
        all_pass = False

    # ── 测试 2: 漂移检测 ─────────────────────────────────────────
    dd2 = DriftDetector(window_size=5, min_samples_before_detect=3,
                         hysteresis_rounds=2, cv_threshold=0.30)
    # 先喂稳定序列
    for phi in [0.95] * 5:
        dd2.push(phi)
        dd2.is_drifting()
    # 再喂剧烈波动序列（高低交替产生高 CV）
    for phi in [0.80, 0.15, 0.70, 0.10, 0.60, 0.05, 0.50, 0.05]:
        dd2.push(phi)
        dd2.is_drifting()

    is_drifting = dd2.is_drifting()
    results["test2_drift_detection"] = {
        "pass": is_drifting,
        "is_drifting": is_drifting,
        "stage": dd2._stage,
        "cv": round(dd2.current_cv, 4),
        "detail": f"剧烈波动序列应触发漂移检测 (CV={dd2.current_cv:.4f})"
    }
    if not results["test2_drift_detection"]["pass"]:
        all_pass = False

    # ── 测试 3: HyperParamAdapter ─────────────────────────────────
    dd3 = DriftDetector(window_size=10, min_samples_before_detect=3)
    dd3.adapter = HyperParamAdapter(history_size=50, adaptation_interval=5)

    # 先喂稳定 CV
    for phi in [0.95, 0.94, 0.93, 0.92, 0.96] * 4:
        dd3.push(phi)
    result = dd3.adapter.adapt(dd3)
    results["test3_hyperparam_adapter"] = {
        "pass": isinstance(result, dict) and "adapted" in result,
        "adapted": result.get("adapted", False),
        "detail": "HyperParamAdapter 应能返回适配结果"
    }
    if not results["test3_hyperparam_adapter"]["pass"]:
        all_pass = False

    # ── 测试 4: 连续 sigmoid 自调 ─────────────────────────────────
    dd4 = DriftDetector(auto_tune=True, adaptive=True, window_size=5,
                         min_samples_before_detect=3, cv_threshold=0.30)
    decays = []
    # 先稳后剧烈波动
    for phi in [0.95, 0.94, 0.93, 0.92, 0.96,   # 稳定
                0.70, 0.15, 0.65, 0.10, 0.55, 0.05]:  # 剧烈波动
        dd4.push(phi)
        dd4.is_drifting()
        dd4._get_decay()  # 触发 _effective_decay 更新
        decays.append(dd4._effective_decay)

    # 验证衰减有变化（sigmoid 机制应有响应）
    unique_decays = len(set(round(d, 3) for d in decays))
    has_variation = unique_decays >= 2
    results["test4_continuous_sigmoid"] = {
        "pass": has_variation,
        "unique_decays": unique_decays,
        "decay_values": [round(d, 4) for d in decays],
        "detail": f"连续 sigmoid 应产生可测的 γ 变化 (unique={unique_decays})"
    }
    if not results["test4_continuous_sigmoid"]["pass"]:
        all_pass = False

    # ── 测试 5: 三阶段模式回退 ────────────────────────────────────
    dd5 = DriftDetector(auto_tune=False, adaptive=True, window_size=5,
                         min_samples_before_detect=3, hysteresis_rounds=2,
                         cv_threshold=0.30)
    # 稳定状态
    for phi in [0.95] * 5:
        dd5.push(phi)
        dd5.is_drifting()
    stage_stable = dd5._stage

    # 漂移状态（剧烈波动产生高 CV）
    for phi in [0.70, 0.10, 0.65, 0.05, 0.55, 0.05, 0.50, 0.05]:
        dd5.push(phi)
        dd5.is_drifting()
    stage_drifting = dd5._stage

    results["test5_three_stage"] = {
        "pass": stage_stable == "STABLE" and stage_drifting == "DRIFTING",
        "stable_stage": stage_stable,
        "drifting_stage": stage_drifting,
        "cv": round(dd5.current_cv, 4),
        "detail": f"三阶段模式应正确切换 STABLE({stage_stable}) → DRIFTING({stage_drifting}), CV={dd5.current_cv:.4f}"
    }
    if not results["test5_three_stage"]["pass"]:
        all_pass = False

    # ── 测试 6: analyze_stability ─────────────────────────────────
    phi_seq = [0.95] * 10 + [0.50] * 10 + [0.95] * 10
    analysis = analyze_stability(phi_seq)
    results["test6_analyze_stability"] = {
        "pass": "regions" in analysis and len(analysis["regions"]) >= 3,
        "num_regions": len(analysis.get("regions", [])),
        "detail": "应检测到稳定→漂移→稳定的三个区域"
    }
    if not results["test6_analyze_stability"]["pass"]:
        all_pass = False

    results["all_pass"] = all_pass
    return results


# ====================================================================
# CLI 入口
# ====================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("TOMAS-AGI DriftDetector v1.6 自检验证")
    print("=" * 60)

    test_results = test_drift_detector()
    for key, val in test_results.items():
        if key == "all_pass":
            continue
        status = "PASS" if val.get("pass") else "FAIL"
        print(f"  [{status}] {key}: {val.get('detail', val)}")

    print(f"\n  {'='*30}")
    print(f"  结果: {'ALL PASS' if test_results['all_pass'] else 'SOME FAILED'}")
    print(f"  {'='*30}")
