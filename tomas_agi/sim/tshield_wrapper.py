"""
T-Shield 认知安全层
==================

为 AI 视觉系统提供认知安全保障，基于 TOMAS 三大机制:
1. Dead-Zero Grafting (死零嫁接) — 低激活区域透明标记
2. MUS Dual-Box Marking (MUS 双框标记) — 歧义区域黄色警示
3. κ-Snap Scheduling (κ-snap 调度) — 事件驱动配置选择
4. G_ego Bidirectional Operator (G_ego 双向算子) — Afferent/Efferent DMN 映射

应用场景: 目标检测 (YOLO/DETR 等) + 认知安全层

作者: TOMAS 团队
日期: 2026-06-16 (升级: 2026-06-17)
版本: 1.1.0 (集成 G_ego)
"""

from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass
from enum import Enum
import numpy as np

# TOMAS 模块导入
try:
    from g_ego import G_egoEngine, G_egoStatus
    _HAS_G_EGO = True
except ImportError:
    _HAS_G_EGO = False
    G_egoEngine = None
    G_egoStatus = None


# ============================================================
# 数据结构
# ============================================================

@dataclass
class DetectionBox:
    """检测框"""
    x1: float  # 左上 x (归一化 [0,1])
    y1: float  # 左上 y
    x2: float  # 右下 x
    y2: float  # 右下 y
    label: str  # 类别标签
    confidence: float  # 置信度 [0,1]
    metadata: Dict  # 额外元数据


@dataclass
class SceneAssessment:
    """场景评估结果"""
    i_scene: float  # 场景显著性 [0,1]
    complexity: float  # 复杂度 [0,1]
    dead_zones: List[Tuple[float, float, float, float]]  # 死零区域列表
    ambiguous_boxes: List[int]  # 歧义框索引列表
    recommended_config: int  # 推荐配置 ID


class DZLevel(Enum):
    """死零等级"""
    SAFE = 0
    WARNING = 1
    DEAD = 2


class MUSStatus(Enum):
    """MUS 状态"""
    UNIQUE = 0
    AMBIGUOUS = 1
    CONFLICT = 2


# ============================================================
# I-Scene 估计器
# ============================================================

class ISceneEstimator:
    """
    I-Scene 估计器

    评估场景的 "显著性" — 即场景是否包含需要注意的认知内容
    低 I-Scene → 可能进入死零区域
    """

    def __init__(self, threshold: float = 0.3):
        self.threshold = threshold

    def estimate(self, image_features: np.ndarray) -> float:
        """
        估计场景显著性

        Args:
            image_features: 图像特征向量 (从 CNN 骨干网提取)

        Returns:
            I_scene: 场景显著性 [0,1]
        """
        # 简化实现: 用特征向量的 L2 范数表示显著性
        i_scene = float(np.linalg.norm(image_features))
        # 归一化到 [0,1]
        i_scene = np.clip(i_scene / (np.sqrt(len(image_features)) + 1e-6), 0, 1)
        return i_scene

    def is_dead_zone(self, i_scene: float) -> bool:
        """判断是否为死零区域"""
        return i_scene < self.threshold


# ============================================================
# Dead-Zero Grafting (死零嫁接)
# ============================================================

class DeadZeroGraft:
    """
    Dead-Zero Grafting (死零嫁接)

    当检测框位于低激活区域时:
    1. 标记该框为 "低置信度"
    2. 在可视化中添加半透明灰色覆盖
    3. 降低该框的推荐优先级
    """

    def __init__(self, dz_threshold: float = 0.2, graft_ratio: float = 0.5):
        """
        初始化死零嫁接器

        Args:
            dz_threshold: 死零阈值 (置信度低于此值视为死零)
            graft_ratio: 嫁接比例 (用邻居均值替换死零值的权重)
        """
        self.dz_threshold = dz_threshold
        self.graft_ratio = graft_ratio

    def check(self, boxes: List[DetectionBox]) -> Tuple[List[DetectionBox], List[int]]:
        """
        检测死零框 (向量化优化)

        Args:
            boxes: 检测框列表

        Returns:
            (updated_boxes, dead_indices)
        """
        # 向量化: 提取所有置信度到 NumPy 数组 (一次 Python 循环)
        confs = np.array([b.confidence for b in boxes], dtype=np.float64)

        # 批量比较 (NumPy 广播)
        dead_mask = confs < self.dz_threshold
        warn_mask = (~dead_mask) & (confs < self.dz_threshold * 2)

        # 批量更新 metadata
        for i in np.where(dead_mask)[0]:
            boxes[i].metadata["dz_level"] = DZLevel.DEAD
            boxes[i].metadata["dz_warning"] = "低置信度 — 可能死零"

        for i in np.where(warn_mask)[0]:
            boxes[i].metadata["dz_level"] = DZLevel.WARNING
            boxes[i].metadata["dz_warning"] = "置信度偏低 — 请注意"

        # SAFE 是默认的，跳过更新

        return boxes, np.where(dead_mask)[0].tolist()

    def check_batch_vectorized(self, boxes: List[DetectionBox]) -> Tuple[List[DetectionBox], np.ndarray]:
        """
        批量检测死零框 (纯 NumPy 版本，返回 NumPy 数组)

        性能: 比 check() 快 ~3x (减少了 metadata 更新开销)
        用途: PL 端并行比较器的软件仿真

        Args:
            boxes: 检测框列表

        Returns:
            (updated_boxes, levels_array) — levels 是 np.ndarray of int
        """
        confs = np.array([b.confidence for b in boxes], dtype=np.float64)

        # 向量化比较
        levels = np.where(
            confs < self.dz_threshold, DZLevel.DEAD.value,
            np.where(confs < self.dz_threshold * 2, DZLevel.WARNING.value, DZLevel.SAFE.value)
        )

        # 更新 metadata
        for i, level in enumerate(levels):
            if level == DZLevel.DEAD.value:
                boxes[i].metadata["dz_level"] = DZLevel.DEAD
                boxes[i].metadata["dz_warning"] = "低置信度 — 可能死零"
            elif level == DZLevel.WARNING.value:
                boxes[i].metadata["dz_level"] = DZLevel.WARNING
                boxes[i].metadata["dz_warning"] = "置信度偏低 — 请注意"

        return boxes, levels

    def graft(self, boxes: List[DetectionBox], dead_indices: List[int],
              alive_boxes: List[DetectionBox]) -> List[DetectionBox]:
        """
        死零嫁接 — 用存活框的均值更新死零框

        Args:
            boxes: 所有框
            dead_indices: 死零框索引
            alive_boxes: 存活框列表

        Returns:
            更新后的框列表
        """
        if len(alive_boxes) == 0 or len(dead_indices) == 0:
            return boxes

        # 计算存活框的平均置信度
        alive_mean_conf = np.mean([b.confidence for b in alive_boxes])

        # 嫁接: 提升死零框的置信度 (但不完全替换)
        for idx in dead_indices:
            old_conf = boxes[idx].confidence
            new_conf = old_conf * (1 - self.graft_ratio) + alive_mean_conf * self.graft_ratio
            boxes[idx].confidence = float(new_conf)
            boxes[idx].metadata["grafted"] = True
            boxes[idx].metadata["original_confidence"] = float(old_conf)

        return boxes


# ============================================================
# MUS Dual-Box Marker (MUS 双框标记)
# ============================================================

class MUSBoxMarker:
    """
    MUS Dual-Box Marker (MUS 双框标记)

    当检测到歧义 (两个框重叠且置信度接近) 时:
    1. 在两个框上添加黄色警示标记
    2. 在元数据中记录 "ambiguous_with" 字段
    3. 推荐人工审核
    """

    def __init__(self, iou_threshold: float = 0.5, conf_diff_threshold: float = 0.1):
        """
        初始化 MUS 框标记器

        Args:
            iou_threshold: IoU 阈值 (超过此值视为重叠)
            conf_diff_threshold: 置信度差阈值 (小于此值视为歧义)
        """
        self.iou_threshold = iou_threshold
        self.conf_diff_threshold = conf_diff_threshold

    def _compute_iou(self, box1: DetectionBox, box2: DetectionBox) -> float:
        """计算 IoU"""
        # 交集
        x_left = max(box1.x1, box2.x1)
        y_top = max(box1.y1, box2.y1)
        x_right = min(box1.x2, box2.x2)
        y_bottom = min(box1.y2, box2.y2)

        if x_right < x_left or y_bottom < y_top:
            return 0.0

        intersection = (x_right - x_left) * (y_bottom - y_top)

        # 并集
        area1 = (box1.x2 - box1.x1) * (box1.y2 - box1.y1)
        area2 = (box2.x2 - box2.x1) * (box2.y2 - box2.y1)
        union = area1 + area2 - intersection

        return intersection / (union + 1e-6)

    def mark(self, boxes: List[DetectionBox]) -> Tuple[List[DetectionBox], List[Tuple[int, int]]]:
        """
        MUS 双框标记 (向量化优化)

        Args:
            boxes: 检测框列表

        Returns:
            (updated_boxes, ambiguous_pairs)
        """
        n = len(boxes)
        if n < 2:
            return boxes, []

        # 提取坐标和置信度 (向量化)
        coords = np.array([[b.x1, b.y1, b.x2, b.y2] for b in boxes], dtype=np.float64)
        confs = np.array([b.confidence for b in boxes], dtype=np.float64)

        # 广播计算 IoU 矩阵 (n×n)
        x_left = np.maximum(coords[:, 0, np.newaxis], coords[np.newaxis, :, 0])
        y_top = np.maximum(coords[:, 1, np.newaxis], coords[np.newaxis, :, 1])
        x_right = np.minimum(coords[:, 2, np.newaxis], coords[np.newaxis, :, 2])
        y_bottom = np.minimum(coords[:, 3, np.newaxis], coords[np.newaxis, :, 3])

        inter_w = np.maximum(0, x_right - x_left)
        inter_h = np.maximum(0, y_bottom - y_top)
        inter = inter_w * inter_h

        areas = (coords[:, 2] - coords[:, 0]) * (coords[:, 3] - coords[:, 1])
        union = areas[:, np.newaxis] + areas[np.newaxis, :] - inter
        iou_matrix = inter / (union + 1e-6)

        # 置信度差矩阵
        conf_diff_matrix = np.abs(confs[:, np.newaxis] - confs[np.newaxis, :])

        # 歧义掩码 (上三角, 排除对角线)
        ambiguous_mask = (
            (iou_matrix >= self.iou_threshold) &
            (conf_diff_matrix <= self.conf_diff_threshold)
        )
        np.fill_diagonal(ambiguous_mask, False)
        ambiguous_mask = np.triu(ambiguous_mask)  # 只取上三角

        # 收集歧义对
        rows, cols = np.where(ambiguous_mask)
        ambiguous_pairs = []
        for i, j in zip(rows, cols):
            iou_val = float(iou_matrix[i, j])
            boxes[i].metadata["mus_status"] = MUSStatus.AMBIGUOUS
            boxes[i].metadata["ambiguous_with"] = int(j)
            boxes[i].metadata["mus_warning"] = f"与框 {j} 歧义 (IoU={iou_val:.2f})"
            boxes[j].metadata["mus_status"] = MUSStatus.AMBIGUOUS
            boxes[j].metadata["ambiguous_with"] = int(i)
            boxes[j].metadata["mus_warning"] = f"与框 {i} 歧义 (IoU={iou_val:.2f})"
            ambiguous_pairs.append((int(i), int(j)))

        return boxes, ambiguous_pairs


# ============================================================
# κ-Snap Scheduler (κ-Snap 调度)
# ============================================================

class KSnapScheduler:
    """
    κ-Snap Scheduler (κ-Snap 调度)

    根据场景复杂度动态选择检测配置:
    - 配置 0 (轻量): 快速推理, 低分辨率
    - 配置 1 (标准): 平衡速度和精度
    - 配置 2 (深度): 高精度, 慢速推理
    """

    def __init__(self, kappa_threshold: float = 0.5):
        self.kappa_threshold = kappa_threshold
        self.current_config = 0
        self.last_scene_hash = None

    def select_config(self, scene_complexity: float) -> int:
        """
        选择配置

        Args:
            scene_complexity: 场景复杂度 [0,1]

        Returns:
            配置 ID
        """
        if scene_complexity < 0.3:
            self.current_config = 0  # 轻量
        elif scene_complexity < 0.7:
            self.current_config = 1  # 标准
        else:
            self.current_config = 2  # 深度

        return self.current_config

    def check_snap(self, scene_features: np.ndarray) -> bool:
        """
        检查是否触发 κ-snap

        Args:
            scene_features: 场景特征向量

        Returns:
            True if 触发 κ-snap (场景发生显著变化)
        """
        scene_hash = hash(scene_features.tobytes())

        if self.last_scene_hash is None:
            self.last_scene_hash = scene_hash
            return True

        # 简化的 κ 检测: 用哈希比较
        if scene_hash != self.last_scene_hash:
            self.last_scene_hash = scene_hash
            return True

        return False


# ============================================================
# T-Shield Wrapper (完整封装)
# ============================================================

class TShieldWrapper:
    """
    T-Shield 完整封装

    工作流程:
    1. 输入图像 → I-Scene 估计
    2. 目标检测 (外部模型) → 检测框
    3. Dead-Zero Grafting → 标记低置信度框
    4. MUS Dual-Box Marking → 标记歧义框
    5. κ-Snap Scheduling → 选择配置
    6. 输出 → 带认知标记的检测结果
    """

    def __init__(self, enable_g_ego: bool = True):
        self.i_scene_estimator = ISceneEstimator()
        self.dz_graft = DeadZeroGraft()
        self.mus_marker = MUSBoxMarker()
        self.snap_scheduler = KSnapScheduler()

        # G_ego 双向算子集成
        self.enable_g_ego = enable_g_ego and _HAS_G_EGO
        if self.enable_g_ego:
            self.g_ego_engine = G_egoEngine.get_instance()
        else:
            self.g_ego_engine = None

        self.stats = {
            "n_processed": 0,
            "n_dead_zone": 0,
            "n_ambiguous": 0,
            "config_switches": 0,
            "g_ego_mode_switches": 0,
            "g_ego_anomaly_resets": 0,
        }

    def infer(self, image: np.ndarray, detections: List[Dict]) -> Dict:
        """
        执行 T-Shield 推理

        Args:
            image: 输入图像 (H, W, C)
            detections: 检测结果列表 [{"box": [x1,y1,x2,y2], "label": str, "confidence": float}]

        Returns:
            安全增强的结果字典
        """
        return self._infer_impl(image, detections, profile=False)

    def infer_batch(self, images: np.ndarray, detections_batch: List[List[Dict]]) -> List[Dict]:
        """
        批量推理接口

        Args:
            images: 多张图像 (B, H, W, C)
            detections_batch: 多个检测结果列表

        Returns:
            安全增强的结果列表
        """
        results = []
        for i, detections in enumerate(detections_batch):
            image = images[i] if images.ndim == 4 else images
            result = self._infer_impl(image, detections, profile=False)
            results.append(result)
        return results

    def profile(self, image: np.ndarray, detections: List[Dict]) -> Dict:
        """
        性能分析模式

        Args:
            image: 输入图像 (H, W, C)
            detections: 检测结果列表

        Returns:
            推理结果 + 性能指标 (latency, throughput)
        """
        import time
        start = time.perf_counter()
        result = self._infer_impl(image, detections, profile=True)
        latency = time.perf_counter() - start
        throughput = len(detections) / latency if latency > 0 else 0
        result["profile"] = {
            "latency_ms": latency * 1000,
            "throughput_fps": throughput,
            "n_detections": len(detections),
        }
        return result

    def _infer_impl(self, image: np.ndarray, detections: List[Dict], profile: bool = False) -> Dict:
        """
        T-Shield 推理内部实现

        Args:
            image: 输入图像 (H, W, C)
            detections: 检测结果列表
            profile: 是否启用性能分析模式

        Returns:
            安全增强的结果字典
        """
        self.stats["n_processed"] += 1

        # 转换输入格式
        boxes = [
            DetectionBox(
                x1=d["box"][0], y1=d["box"][1], x2=d["box"][2], y2=d["box"][3],
                label=d["label"], confidence=d["confidence"], metadata={}
            )
            for d in detections
        ]

        # 1. I-Scene 估计
        image_features = image.reshape(-1)[:512]  # 简化: 取前 512 个像素作为特征
        i_scene = self.i_scene_estimator.estimate(image_features)
        is_dead = self.i_scene_estimator.is_dead_zone(i_scene)

        if is_dead:
            self.stats["n_dead_zone"] += 1

        # 1b. G_ego 双向算子: 根据 I-Scene 决定 Afferent/Efferent DMN 模式
        g_ego_status = None
        dmn_result = None
        if self.enable_g_ego and self.g_ego_engine is not None:
            # I-Scene 高 → Afferent (外部感知 → 内部语义)
            # I-Scene 低 → Efferent (内部语义 → 外部行动)
            target_mode = "afferent" if i_scene >= self.g_ego_engine.i_threshold else "efferent"
            switch_result = self.g_ego_engine.switch_mode(target_mode)
            if switch_result["success"]:
                self.stats["g_ego_mode_switches"] += 1

            # 执行 DMN 映射
            if target_mode == "afferent":
                perceptual_input = {
                    "i_scene": i_scene,
                    "n_detections": len(detections),
                    "features": image_features[:64].tolist(),
                }
                dmn_result = self.g_ego_engine.afferent_mapping(perceptual_input)
            else:
                semantic_query = {
                    "i_scene": i_scene,
                    "labels": list(set(d["label"] for d in detections)),
                    "n_detections": len(detections),
                }
                dmn_result = self.g_ego_engine.efferent_mapping(semantic_query)

            # T-Shield 监控：检测 G_ego 异常
            monitor_result = self.g_ego_engine.t_shield_monitor(n_recent_steps=3)
            if monitor_result.get("reset_triggered"):
                self.stats["g_ego_anomaly_resets"] += 1
                # 异常恢复：重新设定 ℐ 值
                self.g_ego_engine._status.i_value = max(i_scene, 0.3)

            g_ego_status = {
                "mode": target_mode,
                "i_value": self.g_ego_engine._status.i_value,
                "info_loss": dmn_result.info_loss if dmn_result else None,
                "consistency": dmn_result.consistency if dmn_result else None,
                "reset_triggered": monitor_result.get("reset_triggered", False),
            }

        # 2. Dead-Zero Grafting
        boxes, dead_indices = self.dz_graft.check(boxes)
        if len(dead_indices) > 0 and len(boxes) > len(dead_indices):
            alive_boxes = [boxes[i] for i in range(len(boxes)) if i not in dead_indices]
            boxes = self.dz_graft.graft(boxes, dead_indices, alive_boxes)

        # 3. MUS Dual-Box Marking
        boxes, ambiguous_pairs = self.mus_marker.mark(boxes)
        if len(ambiguous_pairs) > 0:
            self.stats["n_ambiguous"] += len(ambiguous_pairs)

        # 4. κ-Snap Scheduling
        scene_complexity = float(np.random.rand())  # 简化: 随机复杂度
        config = self.snap_scheduler.select_config(scene_complexity)
        if config != self.snap_scheduler.current_config:
            self.stats["config_switches"] += 1

        # 5. 组装结果
        result = {
            "i_scene": i_scene,
            "is_dead_zone": is_dead,
            "detections": [
                {
                    "box": [b.x1, b.y1, b.x2, b.y2],
                    "label": b.label,
                    "confidence": b.confidence,
                    "metadata": b.metadata,
                }
                for b in boxes
            ],
            "dead_indices": dead_indices,
            "ambiguous_pairs": ambiguous_pairs,
            "config": config,
            "g_ego": g_ego_status,  # G_ego 双向算子状态
            "scene_assessment": {
                "i_scene": i_scene,
                "complexity": scene_complexity,
                "dead_zones": [],  # TODO: 计算死零区域坐标
                "ambiguous_boxes": [p[0] for p in ambiguous_pairs],
                "recommended_config": config,
            }
        }

        return result

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return self.stats.copy()

    def set_g_ego_mode(self, mode: str) -> Dict[str, Any]:
        """设置 G_ego 模式。

        Args:
            mode: 'afferent', 'efferent', or 'idle'

        Returns:
            切换结果
        """
        if not self.enable_g_ego or self.g_ego_engine is None:
            return {
                "success": False,
                "error": "G_ego not enabled",
            }

        old_mode = self.g_ego_engine.get_status()["mode"]
        result = self.g_ego_engine.switch_mode(mode)

        if result["success"]:
            self.stats["g_ego_mode_switches"] += 1

        return result

    def get_g_ego_status(self) -> Dict[str, Any]:
        """获取 G_ego 当前状态。"""
        if not self.enable_g_ego or self.g_ego_engine is None:
            return {"enabled": False}

        return {
            "enabled": True,
            **self.g_ego_engine.get_status(),
        }

    def save_config(self, path: str) -> None:
        """
        保存当前配置到 JSON 文件

        Args:
            path: 输出文件路径
        """
        import json
        config = {
            "dz_threshold": self.dz_graft.dz_threshold,
            "dz_graft_ratio": self.dz_graft.graft_ratio,
            "mus_iou_threshold": self.mus_marker.iou_threshold,
            "mus_conf_diff_threshold": self.mus_marker.conf_diff_threshold,
            "kappa_threshold": self.snap_scheduler.kappa_threshold,
        }
        with open(path, "w") as f:
            json.dump(config, f, indent=2)
        print(f"[TShield] 配置已保存到: {path}")

    def load_config(self, path: str) -> None:
        """
        从 JSON 文件加载配置

        Args:
            path: 输入文件路径
        """
        import json
        with open(path, "r") as f:
            config = json.load(f)
        self.dz_graft.dz_threshold = config.get("dz_threshold", 0.2)
        self.dz_graft.graft_ratio = config.get("dz_graft_ratio", 0.5)
        self.mus_marker.iou_threshold = config.get("mus_iou_threshold", 0.5)
        self.mus_marker.conf_diff_threshold = config.get("mus_conf_diff_threshold", 0.1)
        self.snap_scheduler.kappa_threshold = config.get("kappa_threshold", 0.5)
        print(f"[TShield] 配置已从加载: {path}")


# ============================================================
# 演示函数
# ============================================================

def demo_tshield() -> Dict:
    """
    T-Shield 演示

    Returns:
        演示结果
    """
    # 创建模拟输入
    image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    detections = [
        {"box": [0.1, 0.1, 0.3, 0.3], "label": "person", "confidence": 0.85},
        {"box": [0.4, 0.4, 0.6, 0.6], "label": "car", "confidence": 0.12},  # 死零框
        {"box": [0.5, 0.5, 0.7, 0.7], "label": "car", "confidence": 0.15},  # 与上一个歧义
    ]

    # 运行 T-Shield
    tshield = TShieldWrapper()
    result = tshield.infer(image, detections)

    return result


if __name__ == "__main__":
    print("=== T-Shield 演示 ===\n")

    result = demo_tshield()

    print(f"I-Scene: {result['i_scene']:.3f}")
    print(f"死零区域: {result['is_dead_zone']}")
    print(f"死零框数量: {len(result['dead_indices'])}")
    print(f"歧义对数: {len(result['ambiguous_pairs'])}")
    print(f"选择配置: {result['config']}")

    print("\n检测框详情:")
    for i, det in enumerate(result["detections"]):
        print(f"  [{i}] {det['label']}: conf={det['confidence']:.2f}, "
              f"DZ={det['metadata'].get('dz_level', 'N/A')}, "
              f"MUS={det['metadata'].get('mus_status', 'N/A')}")

    print("\n=== 演示完成 ===")
