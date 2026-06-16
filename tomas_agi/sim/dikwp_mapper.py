"""
DIKWP 五层模型 → EML 超图层分类器
===================================
基于 章锋(2026) "从DIKWP五层模型到EML超图:基于ℐ-守恒的语义度类划分"

核心映射:
  D (Data)      ↔ EML 原始节点 (ℐ ≈ 0)
  I (Information) ↔ EML 激活超边 (ℐ ~ 0.1-0.3)
  K (Knowledge) ↔ EML 稳定子图 (ℐ ~ 0.3-0.7)
  W (Wisdom)    ↔ EML 跨域超图协调 (ℐ ~ 0.7-0.9)
  P (Purpose)   ↔ EML ψ-锚点 (ℐ ~ 1.0)

应用:
  >>> mapper = DIKWPMapper()
  >>> layer = mapper.classify(i_value=0.55)
  >>> print(layer)  # DIKWPLayer.KNOWLEDGE
  >>> feedback = mapper.backpropagate(source_layer=DIKWPLayer.WISDOM,
  ...                                 target_layer=DIKWPLayer.KNOWLEDGE,
  ...                                 i_gradient=-0.2)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
import logging
import math

logger = logging.getLogger(__name__)


class DIKWPLayer(Enum):
    """DIKWP 五层认知层次"""
    DATA = "D"           # 原始数据, ℐ ≈ 0
    INFORMATION = "I"    # 激活信息, ℐ ~ 0.1-0.3
    KNOWLEDGE = "K"      # 稳定知识, ℐ ~ 0.3-0.7
    WISDOM = "W"         # 决策智慧, ℐ ~ 0.7-0.9
    PURPOSE = "P"        # 意图锚点, ℐ ~ 1.0

    @property
    def order(self) -> int:
        """认知层次序号 (0-4)"""
        return list(DIKWPLayer).index(self)

    @property
    def label_cn(self) -> str:
        """中文标签"""
        return {
            DIKWPLayer.DATA: "数据层",
            DIKWPLayer.INFORMATION: "信息层",
            DIKWPLayer.KNOWLEDGE: "知识层",
            DIKWPLayer.WISDOM: "智慧层",
            DIKWPLayer.PURPOSE: "意图层",
        }[self]

    @property
    def i_range(self) -> Tuple[float, float]:
        """ℐ-密度默认区间"""
        return {
            DIKWPLayer.DATA: (0.0, 0.1),
            DIKWPLayer.INFORMATION: (0.1, 0.35),
            DIKWPLayer.KNOWLEDGE: (0.35, 0.7),
            DIKWPLayer.WISDOM: (0.7, 0.9),
            DIKWPLayer.PURPOSE: (0.9, 1.0),
        }[self]


@dataclass
class IDensityBin:
    """ℐ-密度分类仓"""
    layer: DIKWPLayer
    i_min: float        # 下界(含)
    i_max: float        # 上界(不含, P层为1.0含)
    node_count: int = 0
    edge_count: int = 0
    avg_i_value: float = 0.0

    def contains(self, i_value: float) -> bool:
        """检查 ℐ 值是否落入此 bin"""
        if self.layer == DIKWPLayer.PURPOSE:
            return self.i_min <= i_value <= self.i_max
        return self.i_min <= i_value < self.i_max

    def record(self, i_value: float, is_edge: bool = False) -> None:
        """记录一个数据点"""
        total = self.node_count + self.edge_count
        self.avg_i_value = (self.avg_i_value * total + i_value) / (total + 1)
        if is_edge:
            self.edge_count += 1
        else:
            self.node_count += 1


@dataclass
class IFlowRecord:
    """ℐ-流记录 — 双向反馈的载体"""
    source_layer: DIKWPLayer
    target_layer: DIKWPLayer
    i_gradient: float        # 正=增强, 负=抑制
    edge_id: Optional[str] = None
    timestamp: Optional[float] = None
    meta: Dict = field(default_factory=dict)


class DIKWPMapper:
    """
    DIKWP 五层分类器
    
    将 EML 超图中的节点/超边按 ℐ-密度映射到 DIKWP 五层。
    核心机制：
      1. ℐ-bin 度类划分 — 按 ℐ 值区间分类到 D/I/K/W/P 层
      2. 双向反馈 — W→K 抑制错误权重, P→全层 ψ-锚定
      3. ℐ-守恒验证 — 输出 ℐ ≤ 输入 ℐ 总和
    """

    def __init__(
        self,
        custom_thresholds: Optional[Dict[DIKWPLayer, Tuple[float, float]]] = None,
        enable_conservation_check: bool = True,
        enable_backpropagation: bool = True,
    ):
        """
        Args:
            custom_thresholds: 自定义 ℐ-区间阈值
            enable_conservation_check: 是否启用 ℐ-守恒检查
            enable_backpropagation: 是否启用双向反馈
        """
        self.bins: Dict[DIKWPLayer, IDensityBin] = {}
        self.flow_log: List[IFlowRecord] = []
        self.conservation_violations: List[Dict] = []
        self.enable_conservation = enable_conservation_check
        self.enable_backprop = enable_backpropagation
        
        for layer in DIKWPLayer:
            i_range = custom_thresholds.get(layer, layer.i_range) if custom_thresholds else layer.i_range
            self.bins[layer] = IDensityBin(layer=layer, i_min=i_range[0], i_max=i_range[1])
        
        logger.info(f"[DIKWPMapper] 初始化完成, {len(self.bins)} 个 ℐ-bin")

    def classify(self, i_value: float) -> DIKWPLayer:
        """
        将 ℐ 值分类到 DIKWP 层
        
        Args:
            i_value: 信息存在度值 [0,1]
        
        Returns:
            对应的 DIKWP 层
        
        Raises:
            ValueError: i_value 超出 [0,1]
        """
        if not 0.0 <= i_value <= 1.0:
            raise ValueError(f"ℐ 值超出 [0,1] 范围: {i_value}")
        
        for layer in [DIKWPLayer.PURPOSE, DIKWPLayer.WISDOM, DIKWPLayer.KNOWLEDGE,
                       DIKWPLayer.INFORMATION, DIKWPLayer.DATA]:
            if self.bins[layer].contains(i_value):
                return layer
        
        # Fallback (不应到达)
        return DIKWPLayer.DATA

    def classify_batch(
        self, items: List[Tuple[str, float, bool]]
    ) -> Dict[DIKWPLayer, List[Tuple[str, float]]]:
        """
        批量分类并更新统计
        
        Args:
            items: [(标识符, ℐ值, 是否为超边), ...]
        
        Returns:
            {DIKWPLayer: [(id, i_val), ...]}
        """
        result: Dict[DIKWPLayer, List[Tuple[str, float]]] = {
            layer: [] for layer in DIKWPLayer
        }
        
        for item_id, i_val, is_edge in items:
            layer = self.classify(i_val)
            self.bins[layer].record(i_val, is_edge=is_edge)
            result[layer].append((item_id, i_val))
        
        return result

    def get_layer_density(self, layer: DIKWPLayer) -> float:
        """获取指定层的 ℐ-密度（平均 ℐ 值）"""
        return self.bins[layer].avg_i_value

    def get_layer_population(self, layer: DIKWPLayer) -> int:
        """获取指定层的数据点总数"""
        bin_ = self.bins[layer]
        return bin_.node_count + bin_.edge_count

    def backpropagate(
        self,
        source_layer: DIKWPLayer,
        target_layer: DIKWPLayer,
        i_gradient: float,
        edge_id: Optional[str] = None,
    ) -> IFlowRecord:
        """
        双向反馈 — ℐ-流反向传播
        
        当上层发现下层有误时(W→K 抑制错误权重)或 Purpose 锚定全体时,
        通过反向 ℐ-梯度调节下层超边权重。
        
        Args:
            source_layer: 反馈来源层 (通常 W 或 P)
            target_layer: 反馈目标层 (通常 K 或 I)
            i_gradient: ℐ-梯度, 正=增强, 负=抑制
            edge_id: 目标超边 ID
        
        Returns:
            IFlowRecord — 反馈流记录
        """
        if not self.enable_backprop:
            logger.debug("[DIKWPMapper] 双向反馈已禁用")
            return IFlowRecord(
                source_layer=source_layer,
                target_layer=target_layer,
                i_gradient=0.0,
                edge_id=edge_id,
            )
        
        # 验证反馈方向: 只能上层→下层
        if source_layer.order <= target_layer.order:
            logger.warning(
                f"[DIKWPMapper] 无效反馈方向: {source_layer.name}→{target_layer.name}, "
                f"反馈只能上层→下层"
            )
        
        import time
        record = IFlowRecord(
            source_layer=source_layer,
            target_layer=target_layer,
            i_gradient=i_gradient,
            edge_id=edge_id,
            timestamp=time.time(),
            meta={
                "direction": f"{source_layer.label_cn}→{target_layer.label_cn}",
                "effect": "增强" if i_gradient >= 0 else "抑制",
            },
        )
        self.flow_log.append(record)
        
        logger.info(
            f"[DIKWPMapper] 反馈 {source_layer.label_cn}→{target_layer.label_cn}: "
            f"∇ℐ={i_gradient:+.3f} ({record.meta['effect']})"
        )
        return record

    def check_i_conservation(self, input_total: float, output_total: float) -> bool:
        """
        ℐ-守恒验证 (Axiom A1)
        
        任何输出知识的 ℐ-值不得超过输入信息的 ℐ-总和。
        违反时记录违规并返回 False。
        
        Args:
            input_total: 输入 ℐ 总和
            output_total: 输出 ℐ 总和
        
        Returns:
            True=守恒, False=违规
        """
        if not self.enable_conservation:
            return True
        
        if output_total > input_total + 1e-9:  # 浮点容差
            violation = {
                "input_total": input_total,
                "output_total": output_total,
                "excess": output_total - input_total,
                "message": f"ℐ-守恒违规: 输出 ℐ={output_total:.4f} > 输入 ℐ={input_total:.4f}",
            }
            self.conservation_violations.append(violation)
            logger.warning(f"[DIKWPMapper] {violation['message']}")
            return False
        
        return True

    def get_profile(self) -> Dict:
        """获取当前 DIKWP 分层快照"""
        profile = {}
        for layer in DIKWPLayer:
            bin_ = self.bins[layer]
            profile[layer.value] = {
                "label": layer.label_cn,
                "i_range": [bin_.i_min, bin_.i_max],
                "node_count": bin_.node_count,
                "edge_count": bin_.edge_count,
                "total": bin_.node_count + bin_.edge_count,
                "avg_i": round(bin_.avg_i_value, 4),
                "density": round(
                    (bin_.node_count + bin_.edge_count) / max(
                        sum(b.node_count + b.edge_count for b in self.bins.values()), 1
                    ), 4
                ),
            }
        return profile

    def get_feedback_summary(self) -> Dict:
        """获取双向反馈摘要"""
        by_direction = {}
        for record in self.flow_log:
            key = f"{record.source_layer.value}→{record.target_layer.value}"
            if key not in by_direction:
                by_direction[key] = {"count": 0, "total_gradient": 0.0, "enhance": 0, "suppress": 0}
            by_direction[key]["count"] += 1
            by_direction[key]["total_gradient"] += record.i_gradient
            if record.i_gradient >= 0:
                by_direction[key]["enhance"] += 1
            else:
                by_direction[key]["suppress"] += 1
        return {
            "total_flows": len(self.flow_log),
            "by_direction": by_direction,
            "violations": len(self.conservation_violations),
        }


# 便捷函数
def dikwp_layer_of(i_value: float) -> DIKWPLayer:
    """快速分类: ℐ值 → DIKWP层"""
    mapper = DIKWPMapper()
    return mapper.classify(i_value)
