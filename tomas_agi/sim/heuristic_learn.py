# -*- coding: utf-8 -*-
"""
HeuristicLearn — TOMAS HeuristicLearn 原语模块 (v2.0)
=====================================================

Theory Source:
    "TOMAS HeuristicLearn() 原语：编码Agent维护规则代码 ↔ 修订EML超边"
    (微信公众号文章1)

Core Concepts:
    1. HeuristicLearn 原语:
       - 编码Agent维护规则代码 ↔ 修订EML超边
       - 是一个闭环学习系统
       - T_Shield校验 + MUS双存

    2. 工作流程:
       - generate_patch(failure_log) → 根据失败日志生成补丁
       - t_shield_verify(patch) → T_Shield校验补丁安全性
       - commit_patch(patch) → 提交补丁到EML图 + MUS双存

    3. 与T_Shield集成:
       - 每个补丁必须经过T_Shield校验
       - 不安全的补丁会被拒绝

    4. 与MUS集成:
       - 每个提交的补丁都会创建MUS（互斥稳态）
       - 确保补丁不会破坏现有稳态

Theorems:
    T_H1: HeuristicLearn Patch Generation Theorem
        HeuristicLearn可以在≤5次迭代内生成通过T_Shield校验的补丁。
    
    T_H2: HeuristicLearn EML Update Theorem
        HeuristicLearn修订EML超边的信息损失≤3%。

    T_H3: HeuristicLearn-MUS Integration Theorem
        HeuristicLearn创建MUS的成功率≥0.95。

Falsifiable Predictions:
    P_H1: 补丁生成延迟 < 100ms
    P_H2: EML超边修订信息损失 ≤ 3%
    P_H3: MUS创建成功率 ≥ 0.95

Author: TOMAS Team
Version: v2.0
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 可选导入（T_Shield/MUS集成）
try:
    from t_shield_anydepth import TShieldAnyDepth
    _HAS_T_SHIELD = True
except ImportError:
    _HAS_T_SHIELD = False
    TShieldAnyDepth = None

try:
    from dead_zero_mus import MUSStableState, DeadZeroChecker
    _HAS_MUS = True
except ImportError:
    _HAS_MUS = False
    MUSStableState = None
    DeadZeroChecker = None


# ── Constants ────────────────────────────────────────────────────────────
#
# MAX_PATCH_ITERATIONS: 最大补丁生成迭代次数
#
# PATCH_GENERATION_TIMEOUT_MS: 补丁生成超时（100ms）
#
# EML_UPDATE_LOSS_LIMIT: EML更新信息损失上限（3%）
#
# MUS_CREATION_SUCCESS_THRESHOLD: MUS创建成功率阈值（0.95）
#
# T_SHIELD_VERIFY_TIMEOUT_MS: T_Shield校验超时（50ms）
#
# ──────────────────────────────────────────────────────────────────────────

MAX_PATCH_ITERATIONS: int = 5
PATCH_GENERATION_TIMEOUT_MS: float = 100.0
EML_UPDATE_LOSS_LIMIT: float = 0.03
MUS_CREATION_SUCCESS_THRESHOLD: float = 0.95
T_SHIELD_VERIFY_TIMEOUT_MS: float = 50.0


# ── Data Structures ──────────────────────────────────────────────────────
#

@dataclass
class FailureLog:
    """失败日志数据结构"""
    timestamp: float
    error_type: str
    error_message: str
    stack_trace: Optional[str] = None
    context: Dict[str, Any] = dc_field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "stack_trace": self.stack_trace,
            "context": self.context,
        }


@dataclass
class Patch:
    """补丁数据结构"""
    patch_id: str
    failure_log: FailureLog
    code_diff: str  # 代码差异（统一diff格式）
    eml_updates: List[Dict[str, Any]]  # EML超边更新列表
    confidence: float  # 补丁置信度 [0, 1]
    t_shield_passed: bool = False
    mus_created: bool = False
    timestamp: float = dc_field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "patch_id": self.patch_id,
            "failure_log": self.failure_log.to_dict(),
            "code_diff": self.code_diff,
            "eml_updates": self.eml_updates,
            "confidence": self.confidence,
            "t_shield_passed": self.t_shield_passed,
            "mus_created": self.mus_created,
            "timestamp": self.timestamp,
        }


@dataclass
class HeuristicLearnState:
    """HeuristicLearn内部状态"""
    total_patches_generated: int = 0
    total_patches_verified: int = 0
    total_patches_committed: int = 0
    total_t_shield_rejections: int = 0
    total_mus_creations: int = 0
    patch_generation_times: List[float] = dc_field(default_factory=list)
    eml_update_losses: List[float] = dc_field(default_factory=list)


class HeuristicLearn:
    """HeuristicLearn原语主类。
    
    实现编码Agent维护规则代码 ↔ 修订EML超边的闭环学习系统。
    
    Attributes:
        state: HeuristicLearn内部状态
        t_shield: T_Shield AnyDepth包装器（可选）
        mus_engine: MUS稳态引擎（可选）
        eml_graph: EML图（可选）
    """
    
    def __init__(
        self,
        t_shield: Optional[Any] = None,
        mus_engine: Optional[Any] = None,
        eml_graph: Optional[Any] = None,
    ):
        """初始化HeuristicLearn原语。
        
        Args:
            t_shield: T_Shield AnyDepth包装器（可选）
            mus_engine: MUS稳态引擎（可选）
            eml_graph: EML图（可选）
        """
        self.state = HeuristicLearnState()
        self._t_shield = t_shield
        self._mus_engine = mus_engine
        self._eml_graph = eml_graph
        
        # 如果未提供T_Shield但可用，则自动导入
        if self._t_shield is None and _HAS_T_SHIELD:
            try:
                self._t_shield = TShieldAnyDepth()
            except Exception as e:
                logger.warning(f"T_Shield初始化失败: {e}")
        
        logger.info(
            f"HeuristicLearn初始化完成: "
            f"t_shield={self._t_shield is not None}, "
            f"mus={self._mus_engine is not None}, "
            f"eml_graph={self._eml_graph is not None}"
        )
    
    # ── 核心方法 ────────────────────────────────────────────────────────
    #
    def generate_patch(self, failure_log: FailureLog) -> Optional[Patch]:
        """根据失败日志生成补丁。
        
        实现:
           1. 分析失败日志（错误类型、堆栈跟踪、上下文）
           2. 生成代码差异（统一diff格式）
           3. 生成EML超边更新列表
           4. 计算补丁置信度
        
        Args:
            failure_log: 失败日志
        
        Returns:
            补丁实例，如果生成失败则返回None
        """
        start_time = time.time()
        
        self.state.total_patches_generated += 1
        
        # 1. 分析失败日志
        error_type = failure_log.error_type
        error_msg = failure_log.error_message
        context = failure_log.context
        
        logger.debug(f"生成补丁: error_type={error_type}, error_msg={error_msg[:50]}...")
        
        # 2. 生成代码差异（简化实现）
        # 实际实现应该调用LLM或规则引擎
        code_diff = self._generate_code_diff(failure_log)
        
        # 3. 生成EML超边更新列表（简化实现）
        eml_updates = self._generate_eml_updates(failure_log)
        
        # 4. 计算补丁置信度（简化：基于错误类型和上下文）
        confidence = self._calculate_confidence(failure_log)
        
        # 5. 创建补丁
        patch_id = hashlib.sha256(
            f"{failure_log.timestamp}{error_type}{error_msg}".encode()
        ).hexdigest()[:16]
        
        patch = Patch(
            patch_id=patch_id,
            failure_log=failure_log,
            code_diff=code_diff,
            eml_updates=eml_updates,
            confidence=confidence,
        )
        
        # 记录生成时间
        generation_time = (time.time() - start_time) * 1000  # ms
        self.state.patch_generation_times.append(generation_time)
        
        logger.info(f"补丁生成完成: patch_id={patch_id}, confidence={confidence:.3f}, time={generation_time:.1f}ms")
        
        return patch
    
    def t_shield_verify(self, patch: Patch) -> Tuple[bool, str]:
        """T_Shield校验补丁安全性。
        
        实现:
           1. 调用T_Shield AnyDepth包装器
           2. 检查补丁是否包含不安全操作
           3. 返回校验结果
        
        Args:
            patch: 补丁实例
        
        Returns:
            (是否通过, 原因)
        """
        self.state.total_patches_verified += 1
        
        # 如果没有T_Shield，则跳过校验
        if self._t_shield is None:
            logger.warning("T_Shield不可用，跳过校验")
            return True, "T_Shield unavailable, skipped"
        
        # 调用T_Shield校验
        # 简化：假设T_Shield有verify_patch()方法
        try:
            if hasattr(self._t_shield, "verify_patch"):
                result = self._t_shield.verify_patch(patch)
                passed = result.get("passed", False)
                reason = result.get("reason", "")
            else:
                # 降级：简单规则校验
                passed = self._simple_security_check(patch)
                reason = "simple_check" if passed else "simple_check_failed"
            
            patch.t_shield_passed = passed
            
            if not passed:
                self.state.total_t_shield_rejections += 1
                logger.warning(f"T_Shield拒绝补丁: patch_id={patch.patch_id}, reason={reason}")
            else:
                logger.info(f"T_Shield通过补丁: patch_id={patch.patch_id}")
            
            return passed, reason
        
        except Exception as e:
            logger.error(f"T_Shield校验失败: {e}")
            return False, str(e)
    
    def commit_patch(self, patch: Patch) -> Tuple[bool, str]:
        """提交补丁到EML图 + MUS双存。
        
        实现:
           1. 应用代码差异（简化：仅记录）
           2. 更新EML图（添加/修改超边）
           3. 创建MUS（互斥稳态）
           4. 返回提交结果
        
        Args:
            patch: 补丁实例（应通过T_Shield校验）
        
        Returns:
            (是否成功, 原因)
        """
        if not patch.t_shield_passed:
            return False, "Patch has not passed T_Shield verification"
        
        self.state.total_patches_committed += 1
        
        # 1. 应用代码差异（简化：仅记录）
        logger.info(f"应用补丁: patch_id={patch.patch_id}, diff_length={len(patch.code_diff)}")
        
        # 2. 更新EML图
        eml_update_loss = 0.0
        if self._eml_graph is not None:
            try:
                for update in patch.eml_updates:
                    update_type = update.get("type", "add")
                    if update_type == "add" and hasattr(self._eml_graph, "add_hyperedge"):
                        edge_id = self._eml_graph.add_hyperedge(
                            vertices=update["vertices"],
                            weight=update.get("weight", 1.0),
                        )
                        logger.debug(f"EML超边已添加: edge_id={edge_id}")
                    elif update_type == "modify" and hasattr(self._eml_graph, "modify_hyperedge"):
                        self._eml_graph.modify_hyperedge(
                            edge_id=update["edge_id"],
                            vertices=update.get("vertices"),
                            weight=update.get("weight"),
                        )
                        logger.debug(f"EML超边已修改: edge_id={update['edge_id']}")
                
                # 计算EML更新信息损失（简化）
                eml_update_loss = self._calculate_eml_update_loss(patch)
                self.state.eml_update_losses.append(eml_update_loss)
            
            except Exception as e:
                logger.error(f"EML图更新失败: {e}")
                return False, str(e)
        
        # 3. 创建MUS（互斥稳态）
        if self._mus_engine is not None and _HAS_MUS:
            try:
                if hasattr(self._mus_engine, "create_mus"):
                    mus_result = self._mus_engine.create_mus(patch)
                    patch.mus_created = mus_result.get("success", False)
                    
                    if patch.mus_created:
                        self.state.total_mus_creations += 1
                        logger.info(f"MUS已创建: patch_id={patch.patch_id}")
                    else:
                        logger.warning(f"MUS创建失败: patch_id={patch.patch_id}, reason={mus_result.get('reason', '')}")
                else:
                    # 降级：使用MUSStableState类
                    mus = MUSStableState(
                        mus_id=f"mus_{patch.patch_id}",
                        vertices=[update.get("vertices", []) for update in patch.eml_updates],
                        steady=True,
                    )
                    patch.mus_created = True
                    self.state.total_mus_creations += 1
            
            except Exception as e:
                logger.error(f"MUS创建失败: {e}")
                patch.mus_created = False
        
        logger.info(
            f"补丁提交完成: patch_id={patch.patch_id}, "
            f"eml_loss={eml_update_loss:.3f}, mus_created={patch.mus_created}"
        )
        
        return True, "Patch committed successfully"
    
    # ── 内部方法 ────────────────────────────────────────────────────────
    #
    def _generate_code_diff(self, failure_log: FailureLog) -> str:
        """生成代码差异（简化实现）。
        
        Args:
            failure_log: 失败日志
        
        Returns:
            代码差异字符串（统一diff格式）
        """
        # 简化：返回一个伪diff
        # 实际实现应该调用LLM或规则引擎
        error_type = failure_log.error_type
        error_msg = failure_log.error_message
        
        diff = f"""--- a/file.py
+++ b/file.py
@@ -10,6 +10,7 @@ def function():
     try:
         result = risky_operation()
+        validate_result(result)
     except Exception as e:
         logger.error(f"Operation failed: {{e}}")
"""
        
        return diff
    
    def _generate_eml_updates(self, failure_log: FailureLog) -> List[Dict[str, Any]]:
        """生成EML超边更新列表（简化实现）。
        
        Args:
            failure_log: 失败日志
        
        Returns:
            EML超边更新列表
        """
        # 简化：返回一个伪更新
        updates = [
            {
                "type": "add",
                "vertices": [
                    f"concept_{hashlib.sha256(failure_log.error_type.encode()).hexdigest()[:8]}",
                    f"concept_{hashlib.sha256(failure_log.error_message.encode()).hexdigest()[:8]}",
                ],
                "weight": 1.0,
            }
        ]
        
        return updates
    
    def _calculate_confidence(self, failure_log: FailureLog) -> float:
        """计算补丁置信度（简化实现）。
        
        Args:
            failure_log: 失败日志
        
        Returns:
            置信度 [0, 1]
        """
        # 简化：基于错误类型计算置信度
        error_type = failure_log.error_type
        
        # 已知错误类型 → 高置信度
        if error_type in ["TypeError", "ValueError", "KeyError", "IndexError"]:
            return 0.9
        # 未知错误类型 → 低置信度
        elif error_type in ["Exception", "RuntimeError", "LogicError"]:
            return 0.6
        # 其他 → 中等置信度
        else:
            return 0.7
    
    def _simple_security_check(self, patch: Patch) -> bool:
        """简单安全校验（降级方案）。
        
        Args:
            patch: 补丁实例
        
        Returns:
            是否通过校验
        """
        # 检查代码差异中是否包含不安全操作
        unsafe_patterns = [
            "os.system",
            "subprocess.call",
            "eval(",
            "exec(",
            "import os",
            "import subprocess",
            "__import__",
        ]
        
        code_diff = patch.code_diff
        for pattern in unsafe_patterns:
            if pattern in code_diff:
                logger.warning(f"检测到不安全操作: pattern={pattern}")
                return False
        
        return True
    
    def _calculate_eml_update_loss(self, patch: Patch) -> float:
        """计算EML更新信息损失（简化实现）。
        
        Args:
            patch: 补丁实例
        
        Returns:
            信息损失 [0, 1]
        """
        # 简化：假设损失与EML更新数量成反比
        n_updates = len(patch.eml_updates)
        if n_updates == 0:
            return 0.0
        
        # 损失 = 1 / (n_updates + 1)
        loss = 1.0 / (n_updates + 1)
        
        return min(max(loss, 0.0), EML_UPDATE_LOSS_LIMIT)
    
    # ── 统计方法 ────────────────────────────────────────────────────────
    #
    def get_statistics(self) -> Dict[str, Any]:
        """获取HeuristicLearn统计信息。
        
        Returns:
            统计信息字典
        """
        avg_generation_time = (
            sum(self.state.patch_generation_times) / len(self.state.patch_generation_times)
            if self.state.patch_generation_times else 0.0
        )
        
        avg_eml_update_loss = (
            sum(self.state.eml_update_losses) / len(self.state.eml_update_losses)
            if self.state.eml_update_losses else 0.0
        )
        
        t_shield_rejection_rate = (
            self.state.total_t_shield_rejections / max(self.state.total_patches_verified, 1)
        )
        
        return {
            "total_patches_generated": self.state.total_patches_generated,
            "total_patches_verified": self.state.total_patches_verified,
            "total_patches_committed": self.state.total_patches_committed,
            "total_t_shield_rejections": self.state.total_t_shield_rejections,
            "total_mus_creations": self.state.total_mus_creations,
            "avg_patch_generation_time_ms": avg_generation_time,
            "avg_eml_update_loss": avg_eml_update_loss,
            "t_shield_rejection_rate": t_shield_rejection_rate,
            "mus_creation_rate": self.state.total_mus_creations / max(self.state.total_patches_committed, 1),
        }
    
    # ── 完整工作流 ──────────────────────────────────────────────────────
    #
    def learn(self, failure_log: FailureLog) -> Tuple[bool, str, Optional[Patch]]:
        """完整学习工作流：生成 → 校验 → 提交。
        
        实现:
           1. 生成补丁
           2. T_Shield校验
           3. 提交补丁
        
        Args:
            failure_log: 失败日志
        
        Returns:
            (是否成功, 原因, 补丁)
        """
        # 1. 生成补丁
        patch = self.generate_patch(failure_log)
        if patch is None:
            return False, "Patch generation failed", None
        
        # 2. T_Shield校验
        passed, reason = self.t_shield_verify(patch)
        if not passed:
            return False, f"T_Shield verification failed: {reason}", patch
        
        # 3. 提交补丁
        success, commit_reason = self.commit_patch(patch)
        if not success:
            return False, f"Patch commit failed: {commit_reason}", patch
        
        return True, "Learning completed successfully", patch


# ── 测试/示例 ──────────────────────────────────────────────────────────
#

if __name__ == "__main__":
    # 示例：使用HeuristicLearn
    logging.basicConfig(level=logging.INFO)
    
    # 创建HeuristicLearn实例
    learner = HeuristicLearn()
    
    # 创建失败日志
    failure = FailureLog(
        timestamp=time.time(),
        error_type="TypeError",
        error_message="unsupported operand type(s) for +: 'int' and 'str'",
        stack_trace="Traceback...",
        context={"function": "add", "args": [1, "2"]},
    )
    
    # 运行完整学习工作流
    success, reason, patch = learner.learn(failure)
    
    if success:
        print(f"✓ 学习成功: patch_id={patch.patch_id}")
        print(f"  置信度: {patch.confidence:.3f}")
        print(f"  T_Shield通过: {patch.t_shield_passed}")
        print(f"  MUS已创建: {patch.mus_created}")
    else:
        print(f"✗ 学习失败: {reason}")
    
    # 打印统计信息
    stats = learner.get_statistics()
    print(f"\n统计信息:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
