"""
HY World 2.0 ↔ TOMAS EML Bridge
================================
将腾讯混元 HY World 2.0 的四阶段 3D 世界模型管线映射到 TOMAS EML 超图。

基于文章: 太一互搏范式下 HY World 的空间显影与死零审计 (章锋, 2026)

管线映射:
  HY-Pano 2.0    → EML 超图节点 v_i 构建 (全景语义解析)
  WorldNav        → κ-Snap 轨迹选择 (Max-ℐ 漫游)
  WorldStereo 2.0 → EML 超边几何嵌入 (空间关系建模)
  WorldMirror 2.0 → ℐ-加权 3DGS 重建 (ℐ 守恒几何先验)

HY World 2.0 GitHub: https://github.com/Tencent-Hunyuan/HY-World-2.0

Author: TOMAS v3.0
Date: 2026-06-16
"""

import json
import math
import logging
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 数据类
# ═══════════════════════════════════════════════════════════════

class EvidenceFlag(Enum):
    """证据来源标志 — 对应文章中的 src_flag 分类"""
    EMPIRICAL = "EMPIRICAL"       # 有直接经验证据
    INHERITED = "INHERITED"       # 由先验知识继承而来
    INFERRED = "INFERRED"         # ℐ-可推演但未直接观测
    UNGROUNDED = "UNGROUNDED"     # 无物理/语义支撑


class SceneObjectType(Enum):
    """场景物体类型 — 对应 HY World 输出分类"""
    FOREGROUND = "foreground"     # 前景物体
    MIDGROUND = "midground"       # 中景物体
    BACKGROUND = "background"     # 远景物体
    NAVMESH = "navmesh"           # 导航网格
    OCCLUDER = "occluder"         # 遮挡物


@dataclass
class SpatialVertex:
    """EML 超图空间节点 — 对应 HY World 3D 单资产"""
    id: str
    obj_type: SceneObjectType
    position: Tuple[float, float, float]  # (x, y, z) 世界坐标
    scale: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    i_value: float = 0.5       # ℐ 信息存在度
    evidence: EvidenceFlag = EvidenceFlag.EMPIRICAL
    semantic_tags: List[str] = field(default_factory=list)
    geometry_hash: str = ""    # 几何签名 (用于去重)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SpatialHyperedge:
    """EML 空间超边 — 对应 HY World 场景空间关系"""
    id: str
    source_id: str              # 源节点 ID
    target_id: str              # 目标节点 ID
    relation_type: str          # 关系类型: supports, contains, adjacent, occludes
    i_value: float = 0.5        # ℐ 信息存在度
    asym: float = 0.0           # 非结合残联值 Asym
    spatial_distance: float = 0.0  # 欧氏距离
    evidence: EvidenceFlag = EvidenceFlag.EMPIRICAL
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class KappaSnapshot:
    """κ-Snap 空间显影快照 — 对应 WorldNav 轨迹点"""
    id: str
    position: Tuple[float, float, float]
    lookat: Tuple[float, float, float]
    i_value: float = 0.5        # 当前位置 ℐ 密度
    visible_vertices: List[str] = field(default_factory=list)
    visible_edges: List[str] = field(default_factory=list)
    timestamp: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HYScene:
    """HY World 2.0 生成的完整场景"""
    id: str
    vertices: List[SpatialVertex] = field(default_factory=list)
    edges: List[SpatialHyperedge] = field(default_factory=list)
    kappa_snaps: List[KappaSnapshot] = field(default_factory=list)
    panorama_hash: str = ""
    global_i_density: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════
# Stage A: HY-Pano 2.0 → EML 顶点构建
# ═══════════════════════════════════════════════════════════════

class HYPanoVertexBuilder:
    """
    HY-Pano 2.0 全景图 → EML 超图节点构建

    将 360° 全景图中的语义区域映射为 EML 空间节点:
      - 前景物体 → foreground SpatialVertex (ℐ 最高)
      - 中景物体 → midground SpatialVertex
      - 远景物体 → background SpatialVertex (ℐ 最低)
    """

    # DIKWP 层 ↔ ℐ 范围映射 (对应文章 Table)
    DIKWP_I_RANGES = {
        "D": (0.0, 0.15),    # Data — 裸像素/原始信号
        "I": (0.15, 0.35),   # Info — 结构化信息
        "K": (0.35, 0.65),   # Knowledge — 语义理解
        "W": (0.65, 0.85),   # Wisdom — 空间推理
        "P": (0.85, 1.0),    # Purpose — 目的/意图
    }

    def __init__(self, theta_dead: float = 0.15):
        self.theta_dead = theta_dead
        self.vertices: List[SpatialVertex] = []

    def parse_panorama_semantics(
        self,
        panorama_data: Dict[str, Any],
        evidence_flag: EvidenceFlag = EvidenceFlag.EMPIRICAL,
    ) -> List[SpatialVertex]:
        """
        从全景图语义分割结果构建 EML 节点列表

        Args:
            panorama_data: {
                "objects": [{"label": str, "bbox": [...], "depth": float, "confidence": float}],
                "scene_type": str,
                ...
            }

        Returns:
            SpatialVertex 列表 (已滤除死零节点)
        """
        self.vertices = []
        objects = panorama_data.get("objects", [])

        for i, obj in enumerate(objects):
            label = obj.get("label", f"obj_{i}")
            depth = obj.get("depth", 1.0)
            confidence = obj.get("confidence", 0.5)

            # 按深度确定对象类型和 ℐ 值
            obj_type, i_val = self._classify_by_depth(depth, confidence)

            # 死零过滤: ℐ < θ_dead → 跳过 (不对应 EML 节点)
            if i_val < self.theta_dead:
                logger.debug(f"[HY-Pano→EML] DEAD_ZERO: {label} ℐ={i_val:.3f}")
                continue

            vertex = SpatialVertex(
                id=f"v_pano_{i}_{label}",
                obj_type=obj_type,
                position=self._estimate_3d_position(obj, depth),
                scale=self._estimate_scale(obj),
                i_value=i_val,
                evidence=evidence_flag,
                semantic_tags=obj.get("tags", [label]),
                geometry_hash=self._hash_geometry(obj),
                metadata={"depth": depth, "confidence": confidence},
            )
            self.vertices.append(vertex)

        logger.info(
            f"[HY-Pano→EML] Parsed {len(objects)} objects → "
            f"{len(self.vertices)} vertices (dead-zero filtered: "
            f"{len(objects) - len(self.vertices)})"
        )
        return self.vertices

    def _classify_by_depth(
        self, depth: float, confidence: float
    ) -> Tuple[SceneObjectType, float]:
        """按深度分类对象类型并计算 ℐ 值"""
        # ℐ = confidence × depth_weight
        # 前景(近处) ℐ 更高, 远景 ℐ 更低
        if depth < 5.0:
            obj_type = SceneObjectType.FOREGROUND
            i_weight = 0.9
        elif depth < 20.0:
            obj_type = SceneObjectType.MIDGROUND
            i_weight = 0.6
        else:
            obj_type = SceneObjectType.BACKGROUND
            i_weight = 0.3

        i_val = confidence * i_weight
        return obj_type, min(1.0, max(0.0, i_val))

    def _estimate_3d_position(
        self, obj: Dict[str, Any], depth: float
    ) -> Tuple[float, float, float]:
        """从全景图 bbox + depth 估算 3D 位置"""
        bbox = obj.get("bbox", [0, 0, 1, 1])
        # 简化: 假设全景图为球形投影, bbox 中心 → 方向角
        cx = (bbox[0] + bbox[2]) / 2 if len(bbox) >= 4 else 0.5
        cy = (bbox[1] + bbox[3]) / 2 if len(bbox) >= 4 else 0.5
        # 球面坐标 → 直角坐标
        theta = cx * 2 * math.pi  # 方位角
        phi = cy * math.pi         # 仰角
        x = depth * math.sin(phi) * math.cos(theta)
        y = depth * math.cos(phi)
        z = depth * math.sin(phi) * math.sin(theta)
        return (round(x, 3), round(y, 3), round(z, 3))

    def _estimate_scale(self, obj: Dict[str, Any]) -> Tuple[float, float, float]:
        """估算物体尺度"""
        bbox = obj.get("bbox", [0, 0, 1, 1])
        w = max(0.1, (bbox[2] - bbox[0]) if len(bbox) >= 4 else 1.0)
        h = max(0.1, (bbox[3] - bbox[1]) if len(bbox) >= 4 else 1.0)
        return (w, h, w)  # 假设正方体

    def _hash_geometry(self, obj: Dict[str, Any]) -> str:
        """几何签名 (简化hash)"""
        bbox = obj.get("bbox", [])
        label = obj.get("label", "")
        depth = obj.get("depth", 0)
        return f"{label}_{depth:.1f}_{'_'.join(str(b) for b in bbox)}"

    def get_dikwp_distribution(self) -> Dict[str, int]:
        """获取当前顶点的 DIKWP 层分布"""
        dist = {"D": 0, "I": 0, "K": 0, "W": 0, "P": 0}
        for v in self.vertices:
            for layer, (lo, hi) in self.DIKWP_I_RANGES.items():
                if lo <= v.i_value < hi:
                    dist[layer] += 1
                    break
        return dist


# ═══════════════════════════════════════════════════════════════
# Stage B: WorldNav → κ-Snap 轨迹选择
# ═══════════════════════════════════════════════════════════════

class WorldNavKappaSnapper:
    """
    WorldNav 轨迹规划 → κ-Snap 空间显影

    沿 EML 超图做 Max-ℐ 漫游轨迹:
      - 计算每个候选视点的 ℐ 密度
      - 选 Max-ℐ 路径作为 κ-Snap 序列
      - 标记 ℐ-inferred 区域 (未直接观测但可推演)
    """

    def __init__(self, theta_dead: float = 0.15):
        self.theta_dead = theta_dead
        self.kappa_snaps: List[KappaSnapshot] = []

    def plan_trajectory(
        self,
        vertices: List[SpatialVertex],
        edges: List[SpatialHyperedge],
        start_pos: Optional[Tuple[float, float, float]] = None,
        num_snaps: int = 10,
    ) -> List[KappaSnapshot]:
        """
        基于 EML 超图规划 κ-Snap 轨迹

        策略: 贪心选 Max-ℐ 密度视点 → 构建 κ-Snap 序列

        Args:
            vertices: EML 空间节点列表
            edges: EML 空间超边列表
            start_pos: 起始位置 (默认原点)
            num_snaps: κ-Snap 数量

        Returns:
            κ-Snap 序列
        """
        self.kappa_snaps = []
        if not vertices:
            return self.kappa_snaps

        # 构建空间索引: 按位置分区
        current_pos = start_pos or (0.0, 0.0, 0.0)

        for snap_idx in range(num_snaps):
            # 找到当前视点 ℐ 密度最高的方向
            best_i_density = -1.0
            best_vertex = None
            best_visible_v = []
            best_visible_e = []

            for v in vertices:
                # 计算从 current_pos 看向 v 的 ℐ 密度
                dist = self._euclidean(current_pos, v.position)
                if dist < 0.01:  # 跳过自身
                    continue
                # ℐ 密度 = Σ(可见顶点 ℐ) / distance
                visible_v, visible_e = self._get_visible_set(
                    current_pos, v.position, vertices, edges
                )
                i_density = sum(vv.i_value for vv in visible_v) / max(dist, 1.0)

                if i_density > best_i_density:
                    best_i_density = i_density
                    best_vertex = v
                    best_visible_v = [vv.id for vv in visible_v]
                    best_visible_e = [ee.id for ee in visible_e]

            if best_vertex is None:
                break

            snap = KappaSnapshot(
                id=f"kappa_{snap_idx}",
                position=best_vertex.position,
                lookat=current_pos,
                i_value=best_i_density,
                visible_vertices=best_visible_v,
                visible_edges=best_visible_e,
                timestamp=float(snap_idx),
                metadata={"snap_index": snap_idx},
            )
            self.kappa_snaps.append(snap)
            current_pos = best_vertex.position

        logger.info(
            f"[WorldNav→κ-Snap] Planned {len(self.kappa_snaps)} κ-snaps, "
            f"avg ℐ-density={sum(s.i_value for s in self.kappa_snaps) / max(len(self.kappa_snaps), 1):.3f}"
        )
        return self.kappa_snaps

    def _get_visible_set(
        self,
        origin: Tuple[float, float, float],
        direction: Tuple[float, float, float],
        vertices: List[SpatialVertex],
        edges: List[SpatialHyperedge],
    ) -> Tuple[List[SpatialVertex], List[SpatialHyperedge]]:
        """获取从 origin 看向 direction 的可见顶点和超边集合"""
        visible_v = []
        visible_ids = set()

        # 简化: 圆锥视场 — 夹角 < 60° 视为可见
        dir_vec = (
            direction[0] - origin[0],
            direction[1] - origin[1],
            direction[2] - origin[2],
        )
        dir_len = math.sqrt(sum(d * d for d in dir_vec))
        if dir_len < 0.001:
            return visible_v, []

        for v in vertices:
            to_v = (
                v.position[0] - origin[0],
                v.position[1] - origin[1],
                v.position[2] - origin[2],
            )
            to_v_len = math.sqrt(sum(t * t for t in to_v))
            if to_v_len < 0.001:
                continue

            dot = (dir_vec[0] * to_v[0] + dir_vec[1] * to_v[1] + dir_vec[2] * to_v[2])
            cos_angle = dot / (dir_len * to_v_len)
            if cos_angle > 0.5:  # < 60°
                visible_v.append(v)
                visible_ids.add(v.id)

        # 找出两端都在可见集合中的超边
        visible_e = [
            e for e in edges
            if e.source_id in visible_ids and e.target_id in visible_ids
        ]

        return visible_v, visible_e

    def _euclidean(
        self, a: Tuple[float, float, float], b: Tuple[float, float, float]
    ) -> float:
        return math.sqrt(sum((ai - bi) ** 2 for ai, bi in zip(a, b)))

    def mark_inferred_regions(self) -> int:
        """标记 ℐ-可推演但未直接观测的区域"""
        inferred_count = 0
        for snap in self.kappa_snaps:
            # 相邻 κ-Snap 之间的盲区标记为 INFERRED
            if snap.i_value < 0.3:
                snap.metadata["region_type"] = "INFERRED"
                inferred_count += 1
        return inferred_count


# ═══════════════════════════════════════════════════════════════
# Stage C: WorldStereo 2.0 → EML 超边几何嵌入
# ═══════════════════════════════════════════════════════════════

class WorldStereoSpatialEmbedder:
    """
    WorldStereo 2.0 世界扩展 → EML 超边几何嵌入

    将空间关系编码为 EML 超边:
      - supports: A 支撑 B (物理依赖)
      - contains: A 包含 B (空间包含)
      - adjacent: A 与 B 相邻
      - occludes: A 遮挡 B

    每条超边带 ℐ 值和 Asym 残联:
      ℐ = f(distance, co-visibility, semantic_similarity)
      Asym = |ℐ(A→B) - ℐ(B→A)| (非对称性)
    """

    RELATION_TYPES = ["supports", "contains", "adjacent", "occludes"]

    def __init__(self, theta_dead: float = 0.15):
        self.theta_dead = theta_dead
        self.hyperedges: List[SpatialHyperedge] = []

    def embed_spatial_relations(
        self,
        vertices: List[SpatialVertex],
        relation_threshold: float = 30.0,
    ) -> List[SpatialHyperedge]:
        """
        从顶点集合构建空间关系超边

        规则:
          - 距离 < 2m 且垂直重叠 → supports
          - 距离 < 5m → contains (包围盒检查)
          - 距离 < relation_threshold → adjacent
          - 视线方向重叠 → occludes

        Args:
            vertices: 空间顶点列表
            relation_threshold: 关系判定距离阈值

        Returns:
            空间超边列表
        """
        self.hyperedges = []
        n = len(vertices)

        for i in range(n):
            for j in range(i + 1, n):
                vi, vj = vertices[i], vertices[j]
                dist = self._euclidean(vi.position, vj.position)

                if dist > relation_threshold:
                    continue

                rel_type = self._classify_relation(vi, vj, dist)
                i_val = self._compute_edge_i(vi, vj, dist, rel_type)
                asym = self._compute_asym(vi, vj, rel_type)

                # 死零过滤
                if i_val < self.theta_dead:
                    continue

                evidence = (
                    EvidenceFlag.EMPIRICAL if dist < 10.0
                    else EvidenceFlag.INFERRED
                )

                edge = SpatialHyperedge(
                    id=f"e_{vi.id}_{vj.id}_{rel_type}",
                    source_id=vi.id,
                    target_id=vj.id,
                    relation_type=rel_type,
                    i_value=i_val,
                    asym=asym,
                    spatial_distance=dist,
                    evidence=evidence,
                    metadata={"source_label": vi.semantic_tags, "target_label": vj.semantic_tags},
                )
                self.hyperedges.append(edge)

        logger.info(
            f"[WorldStereo→EML] Embedded {len(self.hyperedges)} spatial hyperedges "
            f"from {n} vertices"
        )
        return self.hyperedges

    def _classify_relation(
        self, vi: SpatialVertex, vj: SpatialVertex, dist: float
    ) -> str:
        """分类两个顶点间的空间关系"""
        # 垂直关系: y 轴差值
        dy = abs(vi.position[1] - vj.position[1])

        # 遮挡判断: 在同一条视线方向
        same_look_dir = self._same_look_direction(vi.position, vj.position)

        if dist < 2.0 and dy > 0.3:
            # 一上一下 → 支撑关系
            return "supports"
        elif dist < 5.0 and self._aabb_contains(vi, vj):
            return "contains"
        elif same_look_dir and dist > 1.0:
            return "occludes"
        else:
            return "adjacent"

    def _compute_edge_i(
        self, vi: SpatialVertex, vj: SpatialVertex,
        dist: float, rel_type: str,
    ) -> float:
        """计算超边 ℐ 值"""
        # 基础 ℐ = (vi ℐ + vj ℐ) / 2
        base_i = (vi.i_value + vj.i_value) / 2

        # 距离衰减
        dist_decay = 1.0 / (1.0 + dist / 10.0)

        # 关系类型加权
        rel_weights = {
            "supports": 0.9,   # 物理支撑最可靠
            "contains": 0.7,
            "adjacent": 0.5,
            "occludes": 0.3,   # 仅视线关系, 可靠性最低
        }
        rel_w = rel_weights.get(rel_type, 0.5)

        return base_i * dist_decay * rel_w

    def _compute_asym(
        self, vi: SpatialVertex, vj: SpatialVertex, rel_type: str
    ) -> float:
        """计算非结合残联 Asym = |ℐ(A→B) - ℐ(B→A)|"""
        # 基于对象类型和尺度的非对称性
        type_weights = {
            SceneObjectType.FOREGROUND: 0.9,
            SceneObjectType.MIDGROUND: 0.6,
            SceneObjectType.BACKGROUND: 0.3,
            SceneObjectType.NAVMESH: 0.5,
            SceneObjectType.OCCLUDER: 0.4,
        }
        w_i = type_weights.get(vi.obj_type, 0.5)
        w_j = type_weights.get(vj.obj_type, 0.5)

        # 尺度差异
        scale_i = sum(vi.scale) / 3
        scale_j = sum(vj.scale) / 3
        scale_asym = abs(scale_i - scale_j) / max(scale_i + scale_j, 0.01)

        return abs(w_i - w_j) * 0.5 + scale_asym * 0.5

    def _euclidean(
        self, a: Tuple[float, float, float], b: Tuple[float, float, float]
    ) -> float:
        return math.sqrt(sum((ai - bi) ** 2 for ai, bi in zip(a, b)))

    def _same_look_direction(
        self, pos_a: Tuple[float, float, float], pos_b: Tuple[float, float, float]
    ) -> bool:
        """判断两点是否在相似视线方向 (用于遮挡判定)"""
        # 简化: 投影到 xz 平面, 角度差 < 30°
        dx_a, dz_a = pos_a[0], pos_a[2]
        dx_b, dz_b = pos_b[0], pos_b[2]
        angle_a = math.atan2(dz_a, dx_a)
        angle_b = math.atan2(dz_b, dx_b)
        diff = abs(angle_a - angle_b) % math.pi
        return diff < math.pi / 6  # 30°

    def _aabb_contains(self, vi: SpatialVertex, vj: SpatialVertex) -> bool:
        """检查 vi 的包围盒是否包含 vj"""
        half_si = tuple(s / 2 for s in vi.scale)
        half_sj = tuple(s / 2 for s in vj.scale)
        for dim in range(3):
            if (
                abs(vi.position[dim] - vj.position[dim])
                > half_si[dim] + half_sj[dim]
            ):
                return False
        return True


# ═══════════════════════════════════════════════════════════════
# Stage D: WorldMirror 2.0 → ℐ-加权 3DGS 重建
# ═══════════════════════════════════════════════════════════════

class WorldMirrorIotaMapper:
    """
    WorldMirror 2.0 3D 重建 → ℐ-加权 3DGS 映射

    将 WorldMirror 2.0 的深度/法线/点云/3DGS 输出映射为 ℐ-加权几何:
      - 高 ℐ 区域 (主结构) → 高精度重建
      - 低 ℐ 区域 (装饰) → 可降权/简化
      - 死零区域 → 拒绝或标记

    对应文章中的 ℐ-修正 Loss:
      L_TOMAS = L_HY + λ_I Σ ℐ(v) · ||v - v̂||²
    """

    def __init__(
        self,
        theta_dead: float = 0.15,
        lambda_i: float = 0.5,  # ℐ 修正权重
    ):
        self.theta_dead = theta_dead
        self.lambda_i = lambda_i

    def compute_iota_loss(
        self,
        predicted: List[SpatialVertex],
        ground_truth: List[SpatialVertex],
    ) -> Tuple[float, Dict[str, float]]:
        """
        计算 ℐ-修正 Loss

        L_TOMAS = L_MSE + λ_I Σ ℐ(v) · ||v - v̂||²

        Returns:
            (total_loss, {"mse": mse, "iota_penalty": penalty})
        """
        # 匹配预测和真值顶点 (按 ID 或位置最近邻)
        mse = 0.0
        iota_penalty = 0.0
        matched = 0

        for pred in predicted:
            # 找最近的 GT 顶点
            best_gt = self._find_nearest(pred.position, ground_truth)
            if best_gt is None:
                continue

            # MSE
            pos_err = sum(
                (pred.position[d] - best_gt.position[d]) ** 2
                for d in range(3)
            )
            mse += pos_err

            # ℐ-修正: 高 ℐ 顶点重建误差惩罚更重
            iota_penalty += best_gt.i_value * pos_err
            matched += 1

        if matched == 0:
            return 0.0, {"mse": 0.0, "iota_penalty": 0.0}

        mse /= matched
        iota_penalty /= matched
        total = mse + self.lambda_i * iota_penalty

        return total, {"mse": mse, "iota_penalty": iota_penalty}

    def _find_nearest(
        self,
        pos: Tuple[float, float, float],
        candidates: List[SpatialVertex],
        max_dist: float = 50.0,
    ) -> Optional[SpatialVertex]:
        """找最近邻顶点"""
        best = None
        best_dist = float("inf")
        for c in candidates:
            dist = math.sqrt(sum((pos[d] - c.position[d]) ** 2 for d in range(3)))
            if dist < best_dist and dist <= max_dist:
                best_dist = dist
                best = c
        return best

    def filter_dead_zero_geometry(
        self,
        vertices: List[SpatialVertex],
    ) -> Tuple[List[SpatialVertex], int]:
        """
        滤除死零几何体

        返回: (通过过滤的顶点列表, 被拒绝数量)
        """
        rejected = 0
        passed = []
        for v in vertices:
            if v.i_value < self.theta_dead:
                rejected += 1
                v.evidence = EvidenceFlag.UNGROUNDED
                logger.debug(f"[WorldMirror→ℐ] DEAD_ZERO: {v.id} ℐ={v.i_value:.3f}")
            else:
                passed.append(v)

        logger.info(
            f"[WorldMirror→ℐ] Filtered: {len(passed)} passed, "
            f"{rejected} dead-zero rejected"
        )
        return passed, rejected

    def prioritize_iota_geometry(
        self,
        vertices: List[SpatialVertex],
        budget: int,
    ) -> List[SpatialVertex]:
        """
        按 ℐ 值优先保留高 ℐ 几何体 (用于带宽/内存受限场景)

        对应文章: "高 ℐ 结构 (主梁/地基) 优先保留, 低 ℐ 装饰可降权"
        """
        sorted_v = sorted(vertices, key=lambda v: v.i_value, reverse=True)
        kept = sorted_v[:budget]
        dropped = sorted_v[budget:]
        for v in dropped:
            v.evidence = EvidenceFlag.UNGROUNDED
        logger.info(
            f"[WorldMirror→ℐ] Budget={budget}: kept {len(kept)}, "
            f"dropped {len(dropped)}"
        )
        return kept


# ═══════════════════════════════════════════════════════════════
# HY World Bridge — 主编排器
# ═══════════════════════════════════════════════════════════════

class HYWorldBridge:
    """
    HY World 2.0 ↔ TOMAS EML 总桥接器

    将 HY World 2.0 的四阶段流水线完整映射到 TOMAS 理论框架:

      HY-Pano 2.0 (全景) → HYPanoVertexBuilder → EML 顶点
      WorldNav (轨迹)     → WorldNavKappaSnapper → κ-Snap
      WorldStereo 2.0 (扩展) → WorldStereoSpatialEmbedder → 超边
      WorldMirror 2.0 (合成) → WorldMirrorIotaMapper → ℐ-加权几何

    使用示例:
        bridge = HYWorldBridge(theta_dead=0.15)
        scene = bridge.build_scene(panorama_data)
        audit = bridge.dead_zero_audit(scene)
        print(f"ℐ density: {scene.global_i_density:.3f}")
    """

    # HY World 2.0 四阶管线 ↔ TOMAS 层级映射
    PIPELINE_MAP = {
        "hy_pano_2": {
            "stage": "A",
            "component": "HYPanoVertexBuilder",
            "tomas_level": 3.5,
            "dikwp": "I→K",
            "desc": "全景语义 → EML 节点构建",
        },
        "world_nav": {
            "stage": "B",
            "component": "WorldNavKappaSnapper",
            "tomas_level": 4.0,
            "dikwp": "K→W",
            "desc": "轨迹规划 → κ-Snap 空间显影",
        },
        "world_stereo_2": {
            "stage": "C",
            "component": "WorldStereoSpatialEmbedder",
            "tomas_level": 3.5,
            "dikwp": "W",
            "desc": "世界扩展 → EML 超边几何嵌入",
        },
        "world_mirror_2": {
            "stage": "D",
            "component": "WorldMirrorIotaMapper",
            "tomas_level": 4.0,
            "dikwp": "W→P",
            "desc": "3D 合成 → ℐ-加权几何重建",
        },
    }

    def __init__(
        self,
        theta_dead: float = 0.15,
        lambda_i: float = 0.5,
        enable_kappa_snap: bool = True,
    ):
        self.theta_dead = theta_dead
        self.lambda_i = lambda_i

        # 初始化四个阶段组件
        self.pano_builder = HYPanoVertexBuilder(theta_dead=theta_dead)
        self.kappa_snapper = WorldNavKappaSnapper(theta_dead=theta_dead) if enable_kappa_snap else None
        self.stereo_embedder = WorldStereoSpatialEmbedder(theta_dead=theta_dead)
        self.mirror_mapper = WorldMirrorIotaMapper(
            theta_dead=theta_dead, lambda_i=lambda_i
        )

        self.scenes: List[HYScene] = []

    def build_scene(
        self,
        panorama_data: Dict[str, Any],
        scene_id: Optional[str] = None,
    ) -> HYScene:
        """
        从全景图数据构建完整 HY Scene

        完整四阶段流程:
          A: parse → vertices
          B: plan  → κ-snaps
          C: embed → hyperedges
          D: filter → ℐ-weighted geometry

        Args:
            panorama_data: HY-Pano 2.0 输出的全景语义数据
            scene_id: 场景 ID

        Returns:
            HYScene (含 vertices, edges, κ-snaps)
        """
        scene_id = scene_id or f"scene_{len(self.scenes)}"

        # Stage A: 全景语义 → EML 顶点
        vertices = self.pano_builder.parse_panorama_semantics(panorama_data)
        logger.info(f"[HYWorld Bridge] Stage A: {len(vertices)} vertices")

        # Stage B: 轨迹规划 → κ-Snap
        kappa_snaps = []
        if self.kappa_snapper and vertices:
            kappa_snaps = self.kappa_snapper.plan_trajectory(vertices, [])
            self.kappa_snapper.mark_inferred_regions()
        logger.info(f"[HYWorld Bridge] Stage B: {len(kappa_snaps)} κ-snaps")

        # Stage C: 空间关系 → EML 超边
        edges = self.stereo_embedder.embed_spatial_relations(vertices)
        logger.info(f"[HYWorld Bridge] Stage C: {len(edges)} hyperedges")

        # Stage D: ℐ-加权几何过滤
        valid_vertices, dz_rejected = self.mirror_mapper.filter_dead_zero_geometry(
            vertices
        )
        logger.info(
            f"[HYWorld Bridge] Stage D: {len(valid_vertices)} valid, "
            f"{dz_rejected} dead-zero"
        )

        # 计算全局 ℐ 密度
        global_i = (
            sum(v.i_value for v in valid_vertices) / max(len(valid_vertices), 1)
            if valid_vertices
            else 0.0
        )

        scene = HYScene(
            id=scene_id,
            vertices=valid_vertices,
            edges=edges,
            kappa_snaps=kappa_snaps,
            panorama_hash=panorama_data.get("hash", ""),
            global_i_density=global_i,
            metadata={
                "dead_zero_rejected": dz_rejected,
                "total_objects": len(panorama_data.get("objects", [])),
                "dikwp_distribution": self.pano_builder.get_dikwp_distribution(),
                "pipeline_stages": list(self.PIPELINE_MAP.keys()),
            },
        )
        self.scenes.append(scene)
        return scene

    def dead_zero_audit(self, scene: HYScene) -> Dict[str, Any]:
        """
        对 HY Scene 执行死零审计

        检查:
          1. ℐ < θ_dead 顶点 → UNGROUNDED
          2. 物理支撑缺失 → 悬浮物检测
          3. Asym ≥ 阈值 → MUS 标记

        Returns:
            {"passed": int, "rejected": int, "mus_flagged": int, "details": [...]}
        """
        rejected = 0
        mus_flagged = 0
        details = []

        # 死零检查
        for v in scene.vertices:
            if v.i_value < self.theta_dead:
                rejected += 1
                details.append({
                    "vertex_id": v.id,
                    "issue": "DEAD_ZERO",
                    "i_value": v.i_value,
                    "semantic_tags": v.semantic_tags,
                })

        # 悬浮物检测: 检查是否有 supports 关系的超边
        supported_ids: Set[str] = set()
        for e in scene.edges:
            if e.relation_type == "supports":
                supported_ids.add(e.target_id)

        for v in scene.vertices:
            if v.obj_type == SceneObjectType.FOREGROUND and v.id not in supported_ids:
                # 前景物体缺少支撑 → 可能是悬浮物
                if v.position[1] > 0.15:  # 离地 > 15cm
                    details.append({
                        "vertex_id": v.id,
                        "issue": "FLOATING_OBJECT",
                        "position_y": v.position[1],
                        "i_value": v.i_value,
                    })
                    if v.i_value < self.theta_dead * 2:
                        rejected += 1

        # MUS 检测: Asym ≥ 0.1 的超边
        asym_threshold = 0.1
        for e in scene.edges:
            if e.asym >= asym_threshold:
                mus_flagged += 1
                details.append({
                    "edge_id": e.id,
                    "issue": "MUS_ACTIVE",
                    "asym": e.asym,
                    "relation_type": e.relation_type,
                })

        result = {
            "passed": len(scene.vertices) - rejected,
            "rejected": rejected,
            "mus_flagged": mus_flagged,
            "total_vertices": len(scene.vertices),
            "total_edges": len(scene.edges),
            "global_i_density": scene.global_i_density,
            "details": details,
        }

        logger.info(
            f"[HYWorld Audit] Passed={result['passed']} "
            f"Rejected={rejected} MUS={mus_flagged}"
        )
        return result

    def compute_iota_loss(
        self,
        scene: HYScene,
        ground_truth_vertices: List[SpatialVertex],
    ) -> Tuple[float, Dict[str, float]]:
        """
        计算场景级 ℐ-修正 Loss

        L_TOMAS = L_HY + λ_I Σ ℐ(v) · ||v - v̂||²
        """
        return self.mirror_mapper.compute_iota_loss(
            scene.vertices, ground_truth_vertices
        )

    def get_pipeline_report(self) -> Dict[str, Any]:
        """获取管线状态报告"""
        return {
            "stages": self.PIPELINE_MAP,
            "total_scenes": len(self.scenes),
            "theta_dead": self.theta_dead,
            "lambda_i": self.lambda_i,
            "kappa_snap_enabled": self.kappa_snapper is not None,
        }

    def export_scene_json(self, scene: HYScene) -> Dict[str, Any]:
        """导出场景为 JSON (用于与 HY World 2.0 原生输出交互)"""
        return {
            "id": scene.id,
            "global_i_density": scene.global_i_density,
            "vertices": [
                {
                    "id": v.id,
                    "type": v.obj_type.value,
                    "position": list(v.position),
                    "scale": list(v.scale),
                    "i_value": v.i_value,
                    "evidence": v.evidence.value,
                    "semantic_tags": v.semantic_tags,
                }
                for v in scene.vertices
            ],
            "edges": [
                {
                    "id": e.id,
                    "source": e.source_id,
                    "target": e.target_id,
                    "relation": e.relation_type,
                    "i_value": e.i_value,
                    "asym": e.asym,
                    "distance": e.spatial_distance,
                }
                for e in scene.edges
            ],
            "kappa_snaps": [
                {
                    "id": ks.id,
                    "position": list(ks.position),
                    "lookat": list(ks.lookat),
                    "i_value": ks.i_value,
                    "visible_count": len(ks.visible_vertices),
                }
                for ks in scene.kappa_snaps
            ],
            "metadata": scene.metadata,
        }
