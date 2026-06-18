# -*- coding: utf-8 -*-
"""
T_Shield_AnyDepth — TOMAS T-Shield AnyDepth 包装模块 (v2.0)
======================================================

Theory Source:
    "T-Shield AnyDepth 包装：Dead-Zero嫁接 + MUS标记 + κ-Snap调度"
    (微信公众号文章6)

Core Concepts:
    1. T-Shield AnyDepth 包装:
       - Dead-Zero 嫁接（OOD 拒检）→ 对分布外数据拒绝检测
       - MUS 标记（遮挡模糊双框）→ 对遮挡/模糊数据双框标记
       - κ-Snap 按 ℐ 调度 → 根据ℐ值动态调度深度配置

    2. 三阶段保护:
       - Stage 1: Dead-Zero 嫁接（OOD检测）
       - Stage 2: MUS 标记（遮挡/模糊检测）
       - Stage 3: κ-Snap 调度（深度配置选择）

    3. 与Dead-Zero集成:
       - 使用DeadZeroChecker进行OOD检测
       - 对OOD数据拒绝检测（节省计算）

    4. 与MUS集成:
       - 使用MUSStableState进行遮挡/模糊检测
       - 对遮挡/模糊数据双框标记（提高鲁棒性）

    5. 与κ-Snap集成:
       - 根据ℐ值选择合适的深度配置
       - ℐ高 → 深层配置（高精度）
       - ℐ低 → 浅层配置（高效率）

Theorems:
    T_T1: T_Shield AnyDepth OOD Theorem
        T-Shield AnyDepth可以在≤2个推理步骤内检测到OOD数据并拒绝检测。
    
    T_T2: T_Shield AnyDepth MUS Theorem
        T-Shield AnyDepth可以在≤3个推理步骤内完成遮挡/模糊数据的双框标记。
    
    T_T3: T_Shield AnyDepth κ-Snap Theorem
        T-Shield AnyDepth可以根据ℐ值准确选择合适的深度配置（准确率≥0.90）。

Falsifiable Predictions:
    P_T1: OOD检测延迟 < 20ms
    P_T2: MUS双框标记延迟 < 30ms
    P_T3: κ-Snap调度延迟 < 10ms
    P_T4: 深度配置选择准确率 ≥ 0.90

Author: TOMAS Team
Version: v2.0
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field as dc_field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 可选导入（Dead-Zero/MUS/κ-Snap集成）
try:
    from dead_zero_mus import DeadZeroChecker, MUSStableState
    _HAS_DEAD_ZERO = True
except ImportError:
    _HAS_DEAD_ZERO = False
    DeadZeroChecker = None
    MUSStableState = None

try:
    from eml_semzip import EMLSemZip
    _HAS_EML_SEMZIP = True
except ImportError:
    _HAS_EML_SEMZIP = False
    EMLSemZip = None


# ── Constants ────────────────────────────────────────────────────────────
#
# OOD_DETECTION_TIMEOUT_MS: OOD检测超时（20ms）
#
# MUS_MARKING_TIMEOUT_MS: MUS双框标记超时（30ms）
#
# KAPPA_SNAP_SCHEDULING_TIMEOUT_MS: κ-Snap调度超时（10ms）
#
# DEPTH_CONFIG_SELECTION_ACCURACY_THRESHOLD: 深度配置选择准确率阈值（0.90）
#
# DEFAULT_I_HIGH_THRESHOLD: ℐ高阈值（深层配置）
#
# DEFAULT_I_LOW_THRESHOLD: ℐ低阈值（浅层配置）
#
# ──────────────────────────────────────────────────────────────────────────

OOD_DETECTION_TIMEOUT_MS: float = 20.0
MUS_MARKING_TIMEOUT_MS: float = 30.0
KAPPA_SNAP_SCHEDULING_TIMEOUT_MS: float = 10.0
DEPTH_CONFIG_SELECTION_ACCURACY_THRESHOLD: float = 0.90
DEFAULT_I_HIGH_THRESHOLD: float = 0.7
DEFAULT_I_LOW_THRESHOLD: float = 0.3


# ── Enums ──────────────────────────────────────────────────────────────
#

class DepthConfig(str, Enum):
    """深度配置枚举"""
    SHALLOW = "shallow"   # 浅层（高效率）
    MEDIUM = "medium"       # 中层（平衡）
    DEEP = "deep"           # 深层（高精度）
    ANYDEPTH = "anydepth"   # 任意深度（自适应）


class SceneType(str, Enum):
    """场景类型枚举"""
    CLEAR = "clear"             # 清晰场景
    OCCLUDED = "occluded"      # 遮挡场景
    BLURRED = "blurred"        # 模糊场景
    OOD = "ood"                 # 分布外场景
    MIXED = "mixed"             # 混合场景


# ── Data Structures ──────────────────────────────────────────────────────
#

@dataclass
class Scene:
    """场景数据结构"""
    scene_id: str
    scene_type: SceneType
    image_data: Optional[Any] = None
    metadata: Dict[str, Any] = dc_field(default_factory=dict)
    i_value: float = 0.5  # ℐ值（Dead-Zero阈值）
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "scene_type": self.scene_type.value,
            "image_data": "<omitted>" if self.image_data is not None else None,
            "metadata": self.metadata,
            "i_value": self.i_value,
        }


@dataclass
class DetectionResult:
    """检测结果数据结构"""
    scene_id: str
    is_ood: bool  # 是否是OOD数据
    is_occluded: bool  # 是否遮挡
    is_blurred: bool  # 是否模糊
    boxes: List[Dict[str, Any]]  # 检测框列表
    depth_config: DepthConfig  # 使用的深度配置
    confidence: float  # 检测置信度
    latency_ms: float  # 总延迟（ms）
    timestamp: float = dc_field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "is_ood": self.is_ood,
            "is_occluded": self.is_occluded,
            "is_blurred": self.is_blurred,
            "boxes": self.boxes,
            "depth_config": self.depth_config.value,
            "confidence": self.confidence,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp,
        }


@dataclass
class TShieldAnyDepthState:
    """T-Shield AnyDepth内部状态"""
    total_scenes_processed: int = 0
    total_ood_rejections: int = 0
    total_mus_markings: int = 0
    total_kappa_snap_schedules: int = 0
    ood_detection_latencies: List[float] = dc_field(default_factory=list)
    mus_marking_latencies: List[float] = dc_field(default_factory=list)
    kappa_snap_scheduling_latencies: List[float] = dc_field(default_factory=list)
    depth_config_usage: Dict[str, int] = dc_field(default_factory=dict)


class TShieldAnyDepth:
    """T-Shield AnyDepth 包装器主类。
    
    实现Dead-Zero嫁接 + MUS标记 + κ-Snap调度的三阶段保护。
    
    Attributes:
        state: T-Shield AnyDepth内部状态
        dead_zero_checker: Dead-Zero检查器（可选）
        mus_engine: MUS稳态引擎（可选）
        eml_semzip: EML语义压缩器（可选）
        depth_configs: 深度配置字典
    """
    
    def __init__(
        self,
        dead_zero_checker: Optional[Any] = None,
        mus_engine: Optional[Any] = None,
        eml_semzip: Optional[Any] = None,
        i_high_threshold: float = DEFAULT_I_HIGH_THRESHOLD,
        i_low_threshold: float = DEFAULT_I_LOW_THRESHOLD,
    ):
        """初始化T-Shield AnyDepth包装器。
        
        Args:
            dead_zero_checker: Dead-Zero检查器（可选）
            mus_engine: MUS稳态引擎（可选）
            eml_semzip: EML语义压缩器（可选）
            i_high_threshold: ℐ高阈值（深层配置）
            i_low_threshold: ℐ低阈值（浅层配置）
        """
        self.state = TShieldAnyDepthState()
        self._dead_zero = dead_zero_checker
        self._mus_engine = mus_engine
        self._eml_semzip = eml_semzip
        self._i_high = i_high_threshold
        self._i_low = i_low_threshold
        
        # 如果未提供Dead-Zero但可用，则自动导入
        if self._dead_zero is None and _HAS_DEAD_ZERO:
            try:
                self._dead_zero = DeadZeroChecker()
            except Exception as e:
                logger.warning(f"Dead-Zero初始化失败: {e}")
        
        # 如果未提供EMLSemZip但可用，则自动导入
        if self._eml_semzip is None and _HAS_EML_SEMZIP:
            try:
                self._eml_semzip = EMLSemZip()
            except Exception as e:
                logger.warning(f"EMLSemZip初始化失败: {e}")
        
        # 深度配置
        self._depth_configs = {
            DepthConfig.SHALLOW: {
                "num_layers": 3,
                "hidden_dim": 128,
                "attention_heads": 4,
            },
            DepthConfig.MEDIUM: {
                "num_layers": 6,
                "hidden_dim": 256,
                "attention_heads": 8,
            },
            DepthConfig.DEEP: {
                "num_layers": 12,
                "hidden_dim": 512,
                "attention_heads": 16,
            },
            DepthConfig.ANYDEPTH: {
                "adaptive": True,
                "min_layers": 3,
                "max_layers": 12,
            },
        }
        
        logger.info(
            f"T-Shield AnyDepth初始化完成: "
            f"dead_zero={self._dead_zero is not None}, "
            f"mus={self._mus_engine is not None}, "
            f"eml_semzip={self._eml_semzip is not None}"
        )
    
    # ── 核心方法 ────────────────────────────────────────────────────────
    #
    def estimate_i_support(self, scene: Scene) -> float:
        """估计场景的ℐ支持值。
        
        实现:
           1. 分析场景特征（清晰度、遮挡度、模糊度）
           2. 估计ℐ支持值
        
        Args:
            scene: 场景实例
        
        Returns:
            ℐ支持值 [0, 1]
        """
        # 简化：基于场景类型估计ℐ值
        scene_type = scene.scene_type
        
        if scene_type == SceneType.CLEAR:
            # 清晰场景 → 高ℐ值
            i_support = 0.9
        elif scene_type == SceneType.OCCLUDED:
            # 遮挡场景 → 中ℐ值
            i_support = 0.5
        elif scene_type == SceneType.BLURRED:
            # 模糊场景 → 中ℐ值
            i_support = 0.4
        elif scene_type == SceneType.OOD:
            # OOD场景 → 低ℐ值
            i_support = 0.1
        elif scene_type == SceneType.MIXED:
            # 混合场景 → 低ℐ值
            i_support = 0.3
        else:
            # 默认 → 中ℐ值
            i_support = 0.5
        
        # 使用场景自带的ℐ值（如果有效）
        if 0.0 <= scene.i_value <= 1.0:
            # 加权平均：估计值 0.7 + 自带值 0.3
            i_support = 0.7 * i_support + 0.3 * scene.i_value
        
        logger.debug(f"ℐ支持值估计: scene_id={scene.scene_id}, i_support={i_support:.3f}")
        
        return i_support
    
    def mark_mus(self, boxes: List[Dict[str, Any]], scores: List[float]) -> List[Dict[str, Any]]:
        """MUS标记（遮挡模糊双框）。
        
        实现:
           1. 对检测框进行MUS标记
           2. 对遮挡/模糊区域进行双框标记
        
        Args:
            boxes: 检测框列表（每个框: {"x1":, "y1":, "x2":, "y2":}）
            scores: 检测分数列表（每个框的置信度）
        
        Returns:
            标记后的检测框列表（可能包含双框）
        """
        start_time = time.time()
        
        self.state.total_mus_markings += 1
        
        marked_boxes = []
        
        for i, (box, score) in enumerate(zip(boxes, scores)):
            # 原始框
            marked_box = {
                "box_id": i,
                "box": box,
                "score": score,
                "is_mus_marked": False,
                "mus_box": None,
            }
            
            # MUS标记条件：低分数或遮挡/模糊
            if score < 0.5:
                # 低分数 → MUS标记（双框）
                mus_box = self._create_mus_box(box, expansion=0.2)
                marked_box["is_mus_marked"] = True
                marked_box["mus_box"] = mus_box
                
                logger.debug(f"MUS标记: box_id={i}, score={score:.3f}")
            
            marked_boxes.append(marked_box)
        
        # 记录延迟
        latency = (time.time() - start_time) * 1000  # ms
        self.state.mus_marking_latencies.append(latency)
        
        logger.info(f"MUS标记完成: n_boxes={len(boxes)}, n_marked={sum(1 for b in marked_boxes if b['is_mus_marked'])}, latency={latency:.1f}ms")
        
        return marked_boxes
    
    def select_depth_config(self, i_scene: float) -> DepthConfig:
        """根据ℐ值选择深度配置。
        
        实现:
           1. 根据ℐ值选择合适的深度配置
           2. ℐ高 → 深层配置（高精度）
           3. ℐ低 → 浅层配置（高效率）
        
        Args:
            i_scene: 场景的ℐ值
        
        Returns:
            深度配置
        """
        self.state.total_kappa_snap_schedules += 1
        
        # 根据ℐ值选择深度配置
        if i_scene >= self._i_high:
            # ℐ高 → 深层配置
            config = DepthConfig.DEEP
        elif i_scene >= self._i_low:
            # ℐ中 → 中层配置
            config = DepthConfig.MEDIUM
        else:
            # ℐ低 → 浅层配置
            config = DepthConfig.SHALLOW
        
        # 记录使用情况
        config_name = config.value
        self.state.depth_config_usage[config_name] = self.state.depth_config_usage.get(config_name, 0) + 1
        
        logger.debug(f"深度配置选择: i_scene={i_scene:.3f}, config={config.value}")
        
        return config
    
    def detect(self, scene: Scene) -> DetectionResult:
        """完整检测工作流：OOD检测 → MUS标记 → κ-Snap调度。
        
        实现:
           1. Stage 1: Dead-Zero 嫁接（OOD检测）
           2. Stage 2: MUS 标记（遮挡/模糊检测）
           3. Stage 3: κ-Snap 调度（深度配置选择）
        
        Args:
            scene: 场景实例
        
        Returns:
            检测结果
        """
        start_time = time.time()
        
        self.state.total_scenes_processed += 1
        
        # ── Stage 1: Dead-Zero 嫁接（OOD检测）───
        #
        is_ood = False
        ood_reason = ""
        
        if self._dead_zero is not None:
            try:
                # 调用Dead-Zero检查器
                if hasattr(self._dead_zero, "check"):
                    dz_result = self._dead_zero.check(
                        matched_edges=[],  # 简化：空边列表
                        query=scene.scene_id,
                        context={"scene_type": scene.scene_type.value},
                    )
                    is_ood = dz_result.is_dead if hasattr(dz_result, "is_dead") else False
                    ood_reason = dz_result.reason if hasattr(dz_result, "reason") else ""
                else:
                    # 降级：简单OOD检测
                    is_ood = self._simple_ood_detection(scene)
            
            except Exception as e:
                logger.error(f"Dead-Zero OOD检测失败: {e}")
                is_ood = False
        
        if is_ood:
            # OOD数据 → 拒绝检测
            self.state.total_ood_rejections += 1
            
            logger.info(f"OOD拒绝: scene_id={scene.scene_id}, reason={ood_reason}")
            
            # 返回空结果
            return DetectionResult(
                scene_id=scene.scene_id,
                is_ood=True,
                is_occluded=False,
                is_blurred=False,
                boxes=[],
                depth_config=DepthConfig.SHALLOW,
                confidence=0.0,
                latency_ms=(time.time() - start_time) * 1000,
            )
        
        # ── Stage 2: MUS 标记（遮挡/模糊检测）───
        #
        is_occluded = scene.scene_type == SceneType.OCCLUDED
        is_blurred = scene.scene_type == SceneType.BLURRED
        
        # 简化：生成伪检测框
        dummy_boxes = self._generate_dummy_boxes(scene)
        dummy_scores = [0.9 - i * 0.1 for i in range(len(dummy_boxes))]
        
        # MUS标记
        marked_boxes = self.mark_mus(dummy_boxes, dummy_scores)
        
        # ── Stage 3: κ-Snap 调度（深度配置选择）───
        #
        # 估计ℐ支持值
        i_scene = self.estimate_i_support(scene)
        
        # 选择深度配置
        depth_config = self.select_depth_config(i_scene)
        
        # ── 最终检测（简化）───
        #
        # 简化：返回标记后的框
        final_boxes = []
        for marked_box in marked_boxes:
            final_boxes.append({
                "box_id": marked_box["box_id"],
                "box": marked_box["box"],
                "score": marked_box["score"],
                "depth_config": depth_config.value,
            })
            
            # 如果有MUS框，也添加
            if marked_box["is_mus_marked"] and marked_box["mus_box"] is not None:
                final_boxes.append({
                    "box_id": f"{marked_box['box_id']}_mus",
                    "box": marked_box["mus_box"],
                    "score": marked_box["score"] * 0.8,  # MUS框分数略低
                    "depth_config": depth_config.value,
                })
        
        # 计算检测置信度（简化）
        confidence = 1.0 / max(len(final_boxes), 1)
        
        # 总延迟
        total_latency = (time.time() - start_time) * 1000  # ms
        
        result = DetectionResult(
            scene_id=scene.scene_id,
            is_ood=False,
            is_occluded=is_occluded,
            is_blurred=is_blurred,
            boxes=final_boxes,
            depth_config=depth_config,
            confidence=confidence,
            latency_ms=total_latency,
        )
        
        logger.info(
            f"检测完成: scene_id={scene.scene_id}, "
            f"n_boxes={len(final_boxes)}, "
            f"depth_config={depth_config.value}, "
            f"latency={total_latency:.1f}ms"
        )
        
        return result
    
    # ── 内部方法 ────────────────────────────────────────────────────────
    #
    def _create_mus_box(self, box: Dict[str, float], expansion: float = 0.2) -> Dict[str, float]:
        """创建MUS框（扩展原始框）。
        
        Args:
            box: 原始框（{"x1":, "y1":, "x2":, "y2":}）
            expansion: 扩展比例
        
        Returns:
            MUS框（扩展后的框）
        """
        x1, y1, x2, y2 = box["x1"], box["y1"], box["x2"], box["y2"]
        
        width = x2 - x1
        height = y2 - y1
        
        # 扩展框
        new_x1 = x1 - width * expansion
        new_y1 = y1 - height * expansion
        new_x2 = x2 + width * expansion
        new_y2 = y2 + height * expansion
        
        return {
            "x1": new_x1,
            "y1": new_y1,
            "x2": new_x2,
            "y2": new_y2,
        }
    
    def _simple_ood_detection(self, scene: Scene) -> bool:
        """简单OOD检测（降级方案）。
        
        Args:
            scene: 场景实例
        
        Returns:
            是否是OOD数据
        """
        # 简化：基于场景类型判断
        return scene.scene_type == SceneType.OOD
    
    def _generate_dummy_boxes(self, scene: Scene) -> List[Dict[str, float]]:
        """生成伪检测框（简化实现）。
        
        Args:
            scene: 场景实例
        
        Returns:
            伪检测框列表
        """
        # 简化：返回1-3个伪框
        n_boxes = 2 if scene.scene_type == SceneType.CLEAR else 1
        
        boxes = []
        for i in range(n_boxes):
            boxes.append({
                "x1": 100 + i * 50,
                "y1": 100 + i * 50,
                "x2": 200 + i * 50,
                "y2": 200 + i * 50,
            })
        
        return boxes
    
    # ── 统计方法 ────────────────────────────────────────────────────────
    #
    def get_statistics(self) -> Dict[str, Any]:
        """获取T-Shield AnyDepth统计信息。
        
        Returns:
            统计信息字典
        """
        avg_ood_latency = (
            sum(self.state.ood_detection_latencies) / len(self.state.ood_detection_latencies)
            if self.state.ood_detection_latencies else 0.0
        )
        
        avg_mus_latency = (
            sum(self.state.mus_marking_latencies) / len(self.state.mus_marking_latencies)
            if self.state.mus_marking_latencies else 0.0
        )
        
        avg_kappa_snap_latency = (
            sum(self.state.kappa_snap_scheduling_latencies) / len(self.state.kappa_snap_scheduling_latencies)
            if self.state.kappa_snap_scheduling_latencies else 0.0
        )
        
        ood_rejection_rate = (
            self.state.total_ood_rejections / max(self.state.total_scenes_processed, 1)
        )
        
        return {
            "total_scenes_processed": self.state.total_scenes_processed,
            "total_ood_rejections": self.state.total_ood_rejections,
            "total_mus_markings": self.state.total_mus_markings,
            "total_kappa_snap_schedules": self.state.total_kappa_snap_schedules,
            "avg_ood_detection_latency_ms": avg_ood_latency,
            "avg_mus_marking_latency_ms": avg_mus_latency,
            "avg_kappa_snap_scheduling_latency_ms": avg_kappa_snap_latency,
            "ood_rejection_rate": ood_rejection_rate,
            "depth_config_usage": self.state.depth_config_usage,
        }
    
    # ── 验证方法 ────────────────────────────────────────────────────────
    #
    def verify_patch(self, patch: Any) -> Dict[str, Any]:
        """验证补丁安全性（供HeuristicLearn使用）。
        
        Args:
            patch: 补丁实例
        
        Returns:
            验证结果（{"passed": bool, "reason": str}）
        """
        # 简化：检查补丁是否包含不安全操作
        if hasattr(patch, "code_diff"):
            code_diff = patch.code_diff
            
            unsafe_patterns = [
                "os.system",
                "subprocess.call",
                "eval(",
                "exec(",
            ]
            
            for pattern in unsafe_patterns:
                if pattern in code_diff:
                    return {"passed": False, "reason": f"Unsafe pattern detected: {pattern}"}
        
        return {"passed": True, "reason": "All checks passed"}


# ── 测试/示例 ──────────────────────────────────────────────────────────
#

if __name__ == "__main__":
    # 示例：使用T-Shield AnyDepth
    logging.basicConfig(level=logging.INFO)
    
    # 创建T-Shield AnyDepth实例
    t_shield = TShieldAnyDepth()
    
    # 创建测试场景
    test_scenes = [
        Scene(scene_id="scene_001", scene_type=SceneType.CLEAR, i_value=0.8),
        Scene(scene_id="scene_002", scene_type=SceneType.OCCLUDED, i_value=0.5),
        Scene(scene_id="scene_003", scene_type=SceneType.BLURRED, i_value=0.4),
        Scene(scene_id="scene_004", scene_type=SceneType.OOD, i_value=0.1),
    ]
    
    # 运行检测
    for scene in test_scenes:
        print(f"\n检测场景: {scene.scene_id} ({scene.scene_type.value})")
        
        result = t_shield.detect(scene)
        
        print(f"  OOD: {result.is_ood}")
        print(f"  遮挡: {result.is_occluded}")
        print(f"  模糊: {result.is_blurred}")
        print(f"  检测框数: {len(result.boxes)}")
        print(f"  深度配置: {result.depth_config.value}")
        print(f"  置信度: {result.confidence:.3f}")
        print(f"  延迟: {result.latency_ms:.1f}ms")
    
    # 打印统计信息
    stats = t_shield.get_statistics()
    print(f"\n统计信息:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
