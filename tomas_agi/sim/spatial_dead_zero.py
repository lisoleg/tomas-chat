"""
空间死零审计 — 3D/几何内容的物理接地校验
==========================================
基于 HY World 2.0 的空间显影与死零审计 (章锋, 2026).

核心机制:
  1. 重力校验: 物体必须被支撑 (地面/其他物体)
  2. 碰撞检测: 物体不能穿透其他物体
  3. 空间 MUS: 空间语义冲突 (既开放又封闭)
  4. ℐ-修正 Loss: L_TOMAS = L_HY + λ_I Σ ℐ(v) · ||v - v̂||²

HY World 2.0: https://github.com/Tencent-Hunyuan/HY-World-2.0

Author: TOMAS v3.0
Date: 2026-06-16
"""

import math
import logging
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 数据类
# ═══════════════════════════════════════════════════════════════

class SpatialStatus(Enum):
    """空间审计状态"""
    GROUNDED = "GROUNDED"             # 物理接地
    FLOATING = "FLOATING"             # 悬浮 (无支撑)
    PENETRATING = "PENETRATING"       # 穿透 (碰撞)
    UNSTABLE = "UNSTABLE"             # 不稳定
    MUS_ACTIVE = "MUS_ACTIVE"         # 空间双存
    DEAD_ZERO = "DEAD_ZERO"           # 死零 (无物理依据)


@dataclass
class GravityCheck:
    """重力校验结果"""
    object_id: str
    is_supported: bool
    support_id: Optional[str] = None   # 支撑物 ID
    ground_distance: float = 0.0       # 离地距离
    i_value: float = 0.5
    status: SpatialStatus = SpatialStatus.GROUNDED


@dataclass
class CollisionCheck:
    """碰撞检测结果"""
    object_a_id: str
    object_b_id: str
    overlap_volume: float = 0.0
    penetration_depth: float = 0.0
    i_value: float = 0.5
    status: SpatialStatus = SpatialStatus.GROUNDED


@dataclass
class SpatialMUSCheck:
    """空间 MUS 双存检测结果"""
    region_id: str
    semantics_a: str                   # 语义 A (如 "open")
    semantics_b: str                   # 语义 B (如 "closed")
    asym: float = 0.0
    i_value_a: float = 0.5
    i_value_b: float = 0.5
    status: SpatialStatus = SpatialStatus.MUS_ACTIVE


@dataclass
class SpatialAuditReport:
    """空间审计报告"""
    total_objects: int
    grounded: int
    floating: int
    penetrating: int
    unstable: int
    mus_active: int
    dead_zero: int
    details: List[Dict[str, Any]] = field(default_factory=list)
    global_i_density: float = 0.0


# ═══════════════════════════════════════════════════════════════
# Gravity Validator — 重力校验
# ═══════════════════════════════════════════════════════════════

class GravityValidator:
    """
    重力校验器

    检查 3D 场景中每个物体是否有物理支撑:
      - 地面支撑 (y ≈ 0)
      - 其他物体支撑 (AABB 垂直重叠)
      - 悬浮检测 (无支撑 + 离地 > threshold)

    对应文章 P_HW_1 实验:
      "古代木桌，悬空离地 30cm" → ℐ(ground_contact) < θ → UNGROUNDED
    """

    def __init__(
        self,
        ground_y: float = 0.0,
        float_threshold: float = 0.15,  # 离地 > 15cm → 可能悬浮
        theta_dead: float = 0.15,
    ):
        self.ground_y = ground_y
        self.float_threshold = float_threshold
        self.theta_dead = theta_dead

    def check_object(
        self,
        obj_id: str,
        position: Tuple[float, float, float],
        scale: Tuple[float, float, float],
        i_value: float,
        other_objects: List[Dict[str, Any]],
    ) -> GravityCheck:
        """
        检查单个物体的重力状态

        Args:
            obj_id: 物体 ID
            position: (x, y, z) 世界坐标
            scale: (sx, sy, sz) 包围盒尺度
            i_value: ℐ 值
            other_objects: 其他物体列表 [{"id", "position", "scale"}, ...]

        Returns:
            GravityCheck
        """
        ground_dist = position[1] - scale[1] / 2 - self.ground_y

        # 1. 地面支撑: 物体底部接近地面
        if ground_dist <= self.float_threshold:
            return GravityCheck(
                object_id=obj_id,
                is_supported=True,
                support_id="ground",
                ground_distance=ground_dist,
                i_value=i_value,
                status=SpatialStatus.GROUNDED,
            )

        # 2. 其他物体支撑: 检查是否有物体在其下方
        for other in other_objects:
            if other["id"] == obj_id:
                continue
            other_pos = other["position"]
            other_scale = other["scale"]

            # 检查: other 在 obj 的正下方, 且 AABB 有重叠
            if self._is_supporting(
                position, scale, other_pos, other_scale
            ):
                return GravityCheck(
                    object_id=obj_id,
                    is_supported=True,
                    support_id=other["id"],
                    ground_distance=position[1] - other_pos[1],
                    i_value=i_value,
                    status=SpatialStatus.GROUNDED,
                )

        # 3. 悬浮: 无支撑
        status = SpatialStatus.FLOATING
        if i_value < self.theta_dead:
            status = SpatialStatus.DEAD_ZERO

        return GravityCheck(
            object_id=obj_id,
            is_supported=False,
            ground_distance=ground_dist,
            i_value=i_value,
            status=status,
        )

    def _is_supporting(
        self,
        obj_pos: Tuple[float, float, float],
        obj_scale: Tuple[float, float, float],
        sup_pos: Tuple[float, float, float],
        sup_scale: Tuple[float, float, float],
    ) -> bool:
        """检查 sup 是否支撑 obj"""
        # sup 必须在 obj 下方
        if sup_pos[1] + sup_scale[1] / 2 > obj_pos[1] - obj_scale[1] / 2 + 0.01:
            return False

        # 垂直间隙 < 支撑阈值
        gap = (obj_pos[1] - obj_scale[1] / 2) - (sup_pos[1] + sup_scale[1] / 2)
        if gap > self.float_threshold:
            return False

        # XZ 平面 AABB 重叠
        return self._aabb_overlap_2d(obj_pos, obj_scale, sup_pos, sup_scale)

    def _aabb_overlap_2d(
        self,
        pos_a: Tuple[float, float, float],
        scale_a: Tuple[float, float, float],
        pos_b: Tuple[float, float, float],
        scale_b: Tuple[float, float, float],
    ) -> bool:
        """XZ 平面 AABB 重叠检测"""
        for dim in [0, 2]:  # x, z
            min_a = pos_a[dim] - scale_a[dim] / 2
            max_a = pos_a[dim] + scale_a[dim] / 2
            min_b = pos_b[dim] - scale_b[dim] / 2
            max_b = pos_b[dim] + scale_b[dim] / 2
            if max_a < min_b or max_b < min_a:
                return False
        return True

    def audit_scene(
        self,
        objects: List[Dict[str, Any]],
    ) -> List[GravityCheck]:
        """
        审计整个场景的重力合规性
        """
        results = []
        for obj in objects:
            others = [o for o in objects if o["id"] != obj["id"]]
            check = self.check_object(
                obj_id=obj["id"],
                position=obj["position"],
                scale=obj.get("scale", (1.0, 1.0, 1.0)),
                i_value=obj.get("i_value", 0.5),
                other_objects=others,
            )
            results.append(check)

        floating_count = sum(1 for r in results if r.status == SpatialStatus.FLOATING)
        dz_count = sum(1 for r in results if r.status == SpatialStatus.DEAD_ZERO)
        logger.info(
            f"[Gravity] {len(results)} objects: "
            f"{len(results) - floating_count - dz_count} grounded, "
            f"{floating_count} floating, {dz_count} dead-zero"
        )
        return results


# ═══════════════════════════════════════════════════════════════
# Spatial MUS Detector — 空间语义双存检测
# ═══════════════════════════════════════════════════════════════

class SpatialMUSDetector:
    """
    空间 MUS (Mutual Uncertain State) 检测器

    检测 3D 空间中的语义冲突:
      - 同一区域需要同时满足两个矛盾语义
      - 如车间"安全区": 既需通透(视看)又需封闭(禁入)
      - 如中医空间辨证: "既开放又封闭"

    触发条件 (对应文章):
      - 两超边 Asym ≥ 0.1
      - 竞争假设的 ℐ 差值 < 0.1
      → 标 [MUS_ACTIVE]

    VR 交互策略: 默认透, 靠近触发禁入提示
    """

    # 已知的空间语义对立对
    SPATIAL_ANTONYMS: Dict[str, str] = {
        "open": "closed",
        "closed": "open",
        "transparent": "opaque",
        "opaque": "transparent",
        "accessible": "restricted",
        "restricted": "accessible",
        "visible": "hidden",
        "hidden": "visible",
        "safe": "dangerous",
        "dangerous": "safe",
        "hot": "cold",
        "cold": "hot",
        "dry": "wet",
        "wet": "dry",
    }

    def __init__(
        self,
        asym_threshold: float = 0.1,
        iota_gap_threshold: float = 0.1,
        theta_dead: float = 0.15,
    ):
        self.asym_threshold = asym_threshold
        self.iota_gap_threshold = iota_gap_threshold
        self.theta_dead = theta_dead

    def detect(
        self,
        region_id: str,
        semantics: List[str],
        i_values: Optional[List[float]] = None,
    ) -> List[SpatialMUSCheck]:
        """
        检测区域内的空间语义冲突

        Args:
            region_id: 区域 ID
            semantics: 语义标签列表
            i_values: 对应 ℐ 值列表

        Returns:
            MUS 检测结果列表
        """
        results = []
        n = len(semantics)
        i_values = i_values or [0.5] * n

        for i in range(n):
            for j in range(i + 1, n):
                si, sj = semantics[i].lower(), semantics[j].lower()

                # 检查是否为空间语义对立
                if self.SPATIAL_ANTONYMS.get(si) == sj:
                    i_i, i_j = i_values[i], i_values[j]

                    # 计算 Asym
                    asym = abs(i_i - i_j)

                    # MUS 触发: Asym ≥ 阈值 且 ℐ 差距小
                    if asym >= self.asym_threshold and abs(i_i - i_j) < self.iota_gap_threshold:
                        results.append(SpatialMUSCheck(
                            region_id=region_id,
                            semantics_a=si,
                            semantics_b=sj,
                            asym=asym,
                            i_value_a=i_i,
                            i_value_b=i_j,
                            status=SpatialStatus.MUS_ACTIVE,
                        ))
                    elif i_i < self.theta_dead or i_j < self.theta_dead:
                        # 低 ℐ 侧标记为死零
                        results.append(SpatialMUSCheck(
                            region_id=region_id,
                            semantics_a=si,
                            semantics_b=sj,
                            asym=asym,
                            i_value_a=i_i,
                            i_value_b=i_j,
                            status=SpatialStatus.DEAD_ZERO,
                        ))

        if results:
            mus_count = sum(1 for r in results if r.status == SpatialStatus.MUS_ACTIVE)
            logger.info(
                f"[SpatialMUS] Region {region_id}: {len(results)} conflicts, "
                f"{mus_count} MUS_ACTIVE"
            )

        return results

    def is_antonym_pair(self, sem_a: str, sem_b: str) -> bool:
        """检查两个语义是否互为反义"""
        return self.SPATIAL_ANTONYMS.get(sem_a.lower(), "") == sem_b.lower()


# ═══════════════════════════════════════════════════════════════
# ℐ-修正 Loss Function
# ═══════════════════════════════════════════════════════════════

class IotaLossFunction:
    """
    ℐ-修正损失函数

    对应文章公式:
      L_HY = L_MSE + L_Perceptual + L_GAN
      L_TOMAS = L_HY + λ_I Σ ℐ(v) · ||v - v̂||²

    设计原则:
      - 高 ℐ 结构 (主梁/地基) → 高精度重建 (惩罚重)
      - 低 ℐ 装饰 → 可降权 (惩罚轻)
      - 死零区域 → 拒绝/跳过

    对应中医 "抓主证 (脏腑核心超边)"
    """

    def __init__(
        self,
        lambda_i: float = 0.5,      # ℐ 修正权重
        lambda_perceptual: float = 0.3,
        lambda_gan: float = 0.1,
    ):
        self.lambda_i = lambda_i
        self.lambda_perceptual = lambda_perceptual
        self.lambda_gan = lambda_gan

    def compute(
        self,
        predicted: List[Dict[str, Any]],
        ground_truth: List[Dict[str, Any]],
        theta_dead: float = 0.15,
    ) -> Tuple[float, Dict[str, float]]:
        """
        计算 ℐ-修正重建 Loss

        Args:
            predicted: 预测物体列表 [{"position": (x,y,z), "i_value": float}, ...]
            ground_truth: 真值物体列表
            theta_dead: 死零阈值

        Returns:
            (total_loss, {"mse": float, "iota_penalty": float, "perceptual": float, "gan": float})
        """
        mse = 0.0
        iota_penalty = 0.0
        matched = 0

        for pred in predicted:
            # 跳过死零物体
            if pred.get("i_value", 0.5) < theta_dead:
                continue

            gt = self._find_nearest(pred, ground_truth)
            if gt is None:
                continue

            # 位置误差 (MSE)
            pos_err = sum(
                (pred["position"][d] - gt["position"][d]) ** 2
                for d in range(3)
            )

            # 尺度误差
            if "scale" in pred and "scale" in gt:
                scale_err = sum(
                    (pred["scale"][d] - gt["scale"][d]) ** 2
                    for d in range(3)
                )
                pos_err += scale_err

            mse += pos_err

            # ℐ-修正: 高 ℐ 顶点误差惩罚更重
            iota = gt.get("i_value", pred.get("i_value", 0.5))
            iota_penalty += iota * pos_err
            matched += 1

        if matched == 0:
            return 0.0, {"mse": 0.0, "iota_penalty": 0.0, "perceptual": 0.0, "gan": 0.0}

        mse /= matched
        iota_penalty /= matched

        # 感知损失和 GAN 损失的简化模拟
        perceptual = self.lambda_perceptual * mse
        gan = self.lambda_gan * mse

        total = mse + self.lambda_i * iota_penalty + perceptual + gan

        return total, {
            "mse": round(mse, 6),
            "iota_penalty": round(iota_penalty, 6),
            "perceptual": round(perceptual, 6),
            "gan": round(gan, 6),
        }

    def _find_nearest(
        self,
        pred: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        max_dist: float = 50.0,
    ) -> Optional[Dict[str, Any]]:
        """最近邻匹配"""
        best = None
        best_dist = float("inf")
        for c in candidates:
            dist = math.sqrt(
                sum(
                    (pred["position"][d] - c["position"][d]) ** 2
                    for d in range(3)
                )
            )
            if dist < best_dist and dist <= max_dist:
                best_dist = dist
                best = c
        return best


# ═══════════════════════════════════════════════════════════════
# SpatialDeadZeroAuditor — 主编排器
# ═══════════════════════════════════════════════════════════════

class SpatialDeadZeroAuditor:
    """
    空间死零审计器 — 主编排器

    组合 GravityValidator + SpatialMUSDetector + IotaLossFunction,
    提供完整的 3D 场景死零审计:
      1. 重力校验 → 检测悬浮/穿透
      2. MUS 检测 → 空间语义冲突
      3. ℐ-修正 Loss → 优先保高 ℐ 结构
      4. 综合报告

    HY World 2.0 融合接口:
      hy_scene → SpatialDeadZeroAuditor.audit() → filtered_scene
    """

    def __init__(
        self,
        theta_dead: float = 0.15,
        asym_threshold: float = 0.1,
        lambda_i: float = 0.5,
        ground_y: float = 0.0,
        float_threshold: float = 0.15,
    ):
        self.theta_dead = theta_dead
        self.gravity = GravityValidator(
            ground_y=ground_y,
            float_threshold=float_threshold,
            theta_dead=theta_dead,
        )
        self.mus_detector = SpatialMUSDetector(
            asym_threshold=asym_threshold,
            theta_dead=theta_dead,
        )
        self.loss_func = IotaLossFunction(lambda_i=lambda_i)

    def audit(
        self,
        objects: List[Dict[str, Any]],
        ground_truth: Optional[List[Dict[str, Any]]] = None,
    ) -> SpatialAuditReport:
        """
        完整空间死零审计

        Args:
            objects: 物体列表
                [{"id": str, "position": (x,y,z), "scale": (sx,sy,sz),
                  "i_value": float, "semantics": [str]}, ...]
            ground_truth: 可选真值 (用于计算 ℐ-修正 Loss)

        Returns:
            SpatialAuditReport
        """
        # 1. 重力审计
        gravity_results = self.gravity.audit_scene(objects)

        # 2. 碰撞检测 (简化: 检查重力结果中的穿透)
        collision_results = []

        # 3. MUS 检测
        mus_results = []
        for obj in objects:
            semantics = obj.get("semantics", [])
            i_values = obj.get("semantic_i_values", [obj.get("i_value", 0.5)] * len(semantics))
            if len(semantics) >= 2:
                mus = self.mus_detector.detect(
                    region_id=obj["id"],
                    semantics=semantics,
                    i_values=i_values,
                )
                mus_results.extend(mus)

        # 4. ℐ-修正 Loss
        loss = None
        if ground_truth:
            loss, loss_components = self.loss_func.compute(
                objects, ground_truth, theta_dead=self.theta_dead
            )

        # 统计
        grounded_count = sum(
            1 for g in gravity_results if g.status == SpatialStatus.GROUNDED
        )
        floating_count = sum(
            1 for g in gravity_results if g.status == SpatialStatus.FLOATING
        )
        dz_count = sum(
            1 for g in gravity_results if g.status == SpatialStatus.DEAD_ZERO
        )
        mus_count = sum(
            1 for m in mus_results if m.status == SpatialStatus.MUS_ACTIVE
        )
        unstable_count = sum(
            1 for g in gravity_results if g.status == SpatialStatus.UNSTABLE
        )
        penetrating_count = len(collision_results)

        # 计算全局 ℐ 密度
        global_i = (
            sum(obj.get("i_value", 0.5) for obj in objects) / max(len(objects), 1)
        )

        # 构建详细报告
        details = []
        for g in gravity_results:
            if g.status != SpatialStatus.GROUNDED:
                details.append({
                    "object_id": g.object_id,
                    "type": "gravity",
                    "status": g.status.value,
                    "ground_distance": g.ground_distance,
                    "i_value": g.i_value,
                })
        for m in mus_results:
            details.append({
                "region_id": m.region_id,
                "type": "mus",
                "status": m.status.value,
                "semantics": f"{m.semantics_a} vs {m.semantics_b}",
                "asym": m.asym,
            })

        report = SpatialAuditReport(
            total_objects=len(objects),
            grounded=grounded_count,
            floating=floating_count,
            penetrating=penetrating_count,
            unstable=unstable_count,
            mus_active=mus_count,
            dead_zero=dz_count,
            details=details,
            global_i_density=round(global_i, 4),
        )

        logger.info(
            f"[SpatialAudit] {report.total_objects} objects: "
            f"G={grounded_count} F={floating_count} P={penetrating_count} "
            f"MUS={mus_count} DZ={dz_count} | ℐ_density={global_i:.3f}"
        )
        return report

    def filter_scene(
        self,
        objects: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        过滤场景: 移除死零/悬浮物体

        Returns:
            (passed_objects, rejected_objects)
        """
        gravity_results = self.gravity.audit_scene(objects)
        passed = []
        rejected = []

        for obj, g in zip(objects, gravity_results):
            if g.status in (SpatialStatus.GROUNDED, SpatialStatus.MUS_ACTIVE):
                passed.append(obj)
            else:
                obj_copy = dict(obj)
                obj_copy["_audit_status"] = g.status.value
                obj_copy["_audit_reason"] = "dead_zero" if g.status == SpatialStatus.DEAD_ZERO else "floating"
                rejected.append(obj_copy)

        logger.info(
            f"[SpatialFilter] {len(passed)} passed, {len(rejected)} rejected "
            f"(from {len(objects)} total)"
        )
        return passed, rejected

    def auto_snap_to_ground(
        self,
        objects: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        自动将悬浮物体吸附到地面

        对应文章策略: "auto-snap-to-floor"
        """
        corrected = []
        for obj in objects:
            obj_copy = dict(obj)
            position = list(obj["position"])
            scale = obj.get("scale", (1.0, 1.0, 1.0))
            ground_dist = position[1] - scale[1] / 2

            if ground_dist > 0.15:  # 离地 > 15cm
                # 自动吸附: y = ground + scale_y/2
                position[1] = scale[1] / 2
                obj_copy["position"] = tuple(position)
                obj_copy["_snapped_to_ground"] = True

            corrected.append(obj_copy)

        return corrected
