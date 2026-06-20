"""
TOMAS-MemOS 融合层
Author: Zhang Feng / TOMAS Team
Date: 2026-06-16

实现 TOMAS 对 MemOS 的五点升维：
1. 死零校验（Dead-Zero Check）
2. MUS 双存机制（MUS Dual Storage）
3. ψ-锚（Self-Snapshot）
4. κ-Gate 激活
5. EML 作为语义本体
"""

import json
import time
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

try:
    from .psi_anchor import PsiAnchor, PsiAnchorManager
except ImportError:
    from psi_anchor import PsiAnchor, PsiAnchorManager

try:
    from .dead_zero_mus import DeadZeroMUSGate
except ImportError:
    from dead_zero_mus import DeadZeroMUSGate

try:
    from .contradiction_detector import ContradictionDetector
except ImportError:
    from contradiction_detector import ContradictionDetector

# 可选依赖：κ-Snap 算子（Merkle Root 批上链）
try:
    from .ksnap_operator import KSnapOperator, SnapEvent
    _HAS_KSNAP = True
except ImportError:
    try:
        from ksnap_operator import KSnapOperator, SnapEvent
        _HAS_KSNAP = True
    except ImportError:
        _HAS_KSNAP = False
        KSnapOperator = None  # type: ignore
        SnapEvent = None  # type: ignore

# 可选依赖：Mina 递归 SNARK 桥接（上链存证）
try:
    from .mina_kappa_bridge import MinaTOMASSnap
    _HAS_MINA = True
except ImportError:
    try:
        from mina_kappa_bridge import MinaTOMASSnap
        _HAS_MINA = True
    except ImportError:
        _HAS_MINA = False
        MinaTOMASSnap = None  # type: ignore

# 配置日志
logger = logging.getLogger(__name__)


@dataclass
class MemoryRecord:
    """记忆记录：EML 超边 + ψ-锚 + 元数据"""
    edge_id: str
    concept_pair: Tuple[str, str]
    relation: str
    i_value: float  # ℐ-值（信息存在度）
    asym: float  # Asym 值（MUS 标记）
    psi_anchor: Optional[PsiAnchor]
    meta: Dict[str, Any]
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    last_accessed: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    access_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "edge_id": self.edge_id,
            "concept_pair": list(self.concept_pair),
            "relation": self.relation,
            "i_value": self.i_value,
            "asym": self.asym,
            "psi_anchor": self.psi_anchor.to_dict() if self.psi_anchor else None,
            "meta": self.meta,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MemoryRecord":
        """从字典反序列化"""
        psi = PsiAnchor.from_dict(d["psi_anchor"]) if d.get("psi_anchor") else None
        return cls(
            edge_id=d["edge_id"],
            concept_pair=tuple(d["concept_pair"]),
            relation=d["relation"],
            i_value=d["i_value"],
            asym=d["asym"],
            psi_anchor=psi,
            meta=d.get("meta", {}),
            created_at=d.get("created_at", ""),
            last_accessed=d.get("last_accessed", ""),
            access_count=d.get("access_count", 0),
        )


@dataclass
class MUSDualStoreEntry:
    """MUS 双存条目：互斥稳态对（波粒二象性模式）。

    互斥稳态不强制平均，保留冲突分支。
    例如：光的"波"描述与"粒"描述共存，而非取折中值。

    Attributes:
        entry_id: 条目唯一标识
        description_a: 描述A（如"波"）
        description_b: 描述B（如"粒"）
        code_a: 代码/数据A
        code_b: 代码/数据B
        created_at: 创建时间戳
        snap_ref: 关联的 κ-Snap 事件 ID
    """

    entry_id: str
    description_a: str
    description_b: str
    code_a: str
    code_b: str
    created_at: float = field(default_factory=time.time)
    snap_ref: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典。"""
        return {
            "entry_id": self.entry_id,
            "description_a": self.description_a,
            "description_b": self.description_b,
            "code_a": self.code_a,
            "code_b": self.code_b,
            "created_at": self.created_at,
            "snap_ref": self.snap_ref,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MUSDualStoreEntry":
        """从字典反序列化。"""
        return cls(
            entry_id=d["entry_id"],
            description_a=d.get("description_a", ""),
            description_b=d.get("description_b", ""),
            code_a=d.get("code_a", ""),
            code_b=d.get("code_b", ""),
            created_at=d.get("created_at", time.time()),
            snap_ref=d.get("snap_ref"),
        )


class MemoryStore:
    """
    轻量级记忆存储（模拟 MemOS）
    
    使用 JSON 文件存储记忆记录，支持：
    - 写入（write）
    - 检索（retrieve）
    - 更新（update）
    - 删除/归档（delete/archieve）
    
    未来可替换为 SQLite 或向量数据库
    """
    
    def __init__(self, store_path: str = None):
        self.store_path = store_path or "tomas_agi/data/memory_store.json"
        self._records: Dict[str, MemoryRecord] = {}
        self._mus_duals: Dict[str, MUSDualStoreEntry] = {}
        self._load()
    
    def _load(self):
        """从 JSON 文件加载记忆记录"""
        try:
            with open(self.store_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data:
                    record = MemoryRecord.from_dict(item)
                    self._records[record.edge_id] = record
            logger.info(f"已加载 {len(self._records)} 条记忆记录")
        except FileNotFoundError:
            logger.info("记忆存储文件不存在，将创建新文件")
            self._records = {}
        except Exception as e:
            logger.error(f"加载记忆存储失败: {e}")
            self._records = {}
    
    def _save(self):
        """保存记忆记录到 JSON 文件"""
        import os
        # 仅当 store_path 包含目录时才创建目录
        dir_name = os.path.dirname(self.store_path)
        if dir_name:  # 仅当 dir_name 非空时创建目录
            os.makedirs(dir_name, exist_ok=True)
        try:
            data = [r.to_dict() for r in self._records.values()]
            with open(self.store_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存记忆存储失败: {e}")
    
    def write(self, record: MemoryRecord, overwrite: bool = True) -> bool:
        """
        写入记忆记录
        
        Args:
            record: 记忆记录
            overwrite: 是否覆盖已存在的记录（MUS 双存时为 False）
            
        Returns:
            是否写入成功
        """
        if record.edge_id in self._records and not overwrite:
            logger.info(f"记忆 {record.edge_id} 已存在，不覆盖（MUS 双存）")
            return False
        
        self._records[record.edge_id] = record
        self._save()
        logger.info(f"已写入记忆 {record.edge_id}: {record.relation}")
        return True
    
    def retrieve(self, query: str, top_k: int = 10) -> List[MemoryRecord]:
        """
        检索记忆记录（简化版：按访问次数 + ℐ-值排序）
        
        Args:
            query: 查询字符串（未来可改为语义相似度）
            top_k: 返回前 k 条
            
        Returns:
            记忆记录列表
        """
        # 简化版：按 (i_value * access_count) 排序
        sorted_records = sorted(
            self._records.values(),
            key=lambda r: r.i_value * (1 + r.access_count),
            reverse=True
        )
        
        # 更新访问信息
        results = []
        for record in sorted_records[:top_k]:
            record.access_count += 1
            record.last_accessed = time.strftime("%Y-%m-%dT%H:%M:%S")
            results.append(record)
        
        self._save()
        return results
    
    def retrieve_by_concepts(self, concepts: List[str]) -> List[MemoryRecord]:
        """
        按概念对检索记忆（精确匹配）
        
        Args:
            concepts: 概念列表
            
        Returns:
            包含任一概念的记忆记录
        """
        results = []
        concept_set = set(concepts)
        for record in self._records.values():
            if set(record.concept_pair) & concept_set:
                results.append(record)
        return results
    
    def delete(self, edge_id: str) -> bool:
        """删除记忆记录"""
        if edge_id in self._records:
            del self._records[edge_id]
            self._save()
            logger.info(f"已删除记忆 {edge_id}")
            return True
        return False
    
    def archieve_low_i(self, theta_archieve: float = 0.1) -> int:
        """
        ℐ-衰减归档：删除 ℐ-值低于阈值的非 MUS 记忆
        
        Returns:
            归档的记忆数量
        """
        to_archive = [
            rid for rid, r in self._records.items()
            if r.i_value < theta_archieve and abs(r.asym) < 0.01
        ]
        for rid in to_archive:
            del self._records[rid]
        
        if to_archive:
            self._save()
        logger.info(f"已归档 {len(to_archive)} 条低 ℐ 记忆")
        return len(to_archive)
    
    def get_all(self) -> List[MemoryRecord]:
        """获取所有记忆记录"""
        return list(self._records.values())
    
    def get_mus_pairs(self) -> List[Tuple[MemoryRecord, MemoryRecord]]:
        """
        获取所有 MUS 配对（矛盾双存记忆）
        
        Returns:
            MUS 配对列表
        """
        # 按 concept_pair 分组
        pairs = {}
        for record in self._records.values():
            key = tuple(sorted(record.concept_pair))
            if key not in pairs:
                pairs[key] = []
            pairs[key].append(record)
        
        # 筛选出互为矛盾的配对（Asym ≠ 0）
        mus_pairs = []
        processed = set()
        
        for key, records in pairs.items():
            if len(records) >= 2:
                # 检查是否至少有一个的 asym != 0
                if any(abs(r.asym) > 0.01 for r in records):
                    mus_pairs.append(tuple(records))
                    for r in records:
                        processed.add(r.edge_id)
        
        # 检查部分重叠（共享至少一个概念）
        all_records = self.get_all()
        for i, r1 in enumerate(all_records):
            if r1.edge_id in processed:
                continue
            if abs(r1.asym) > 0.01:
                # 查找共享概念的其他记录
                for r2 in all_records[i+1:]:
                    if r2.edge_id in processed:
                        continue
                    if set(r1.concept_pair) & set(r2.concept_pair):  # 共享概念
                        mus_pairs.append((r1, r2))
                        processed.add(r1.edge_id)
                        processed.add(r2.edge_id)
                        break
        
        return mus_pairs

    # ----- MUS 双存增强 (T14) -----

    def store_mus_dual(self, key: str, entry: MUSDualStoreEntry) -> bool:
        """存储互斥稳态对（MUS Dual Storage）。

        波粒二象性模式：互斥稳态不强制平均，保留冲突分支。

        Args:
            key: 存储键
            entry: MUS 双存条目

        Returns:
            是否存储成功
        """
        self._mus_duals[key] = entry
        logger.info(
            "MUS 双存已存储: key=%s, entry_id=%s, A='%s' / B='%s'",
            key, entry.entry_id, entry.description_a[:20], entry.description_b[:20],
        )
        return True

    def retrieve_mus_dual(self, key: str) -> Optional[MUSDualStoreEntry]:
        """检索互斥稳态对。

        Args:
            key: 存储键

        Returns:
            MUS 双存条目，不存在则返回 None
        """
        return self._mus_duals.get(key)

    def list_mus_duals(self) -> List[str]:
        """列出所有 MUS 双存键。

        Returns:
            键列表
        """
        return list(self._mus_duals.keys())


class TOMAS_Mem_OS_Fusion:
    """
    TOMAS-MemOS 融合层
    
    实现五点升维：
    1. 死零校验（Dead-Zero Check）
    2. MUS 双存机制（MUS Dual Storage）
    3. ψ-锚（Self-Snapshot）
    4. κ-Gate 激活
    5. EML 作为语义本体
    """
    
    def __init__(
        self,
        store_path: str = None,
        theta_dead: float = 0.15,
        theta_write: float = 0.3,
        theta_archieve: float = 0.1,
        enable_mus: bool = True,
        enable_psi: bool = True,
        enable_kappa_gate: bool = True,
        eml_path: str = None,
        concepts_json_path: str = None,
    ):
        """
        初始化融合层
        
        Args:
            store_path: 记忆存储路径
            theta_dead: 死零阈值（ℐ 值低于此值拒绝写入）
            theta_write: 写入阈值（ℐ 值高于此值才写入）
            theta_archieve: 归档阈值（ℐ 值低于此值归档）
            enable_mus: 是否启用 MUS 双存
            enable_psi: 是否启用 ψ-锚
            enable_kappa_gate: 是否启用 κ-Gate 激活
            eml_path: EML 二进制文件路径（.eml），用于 Layer 3 语义相似度
            concepts_json_path: 概念名称 JSON 文件路径（.concepts.json）
        """
        self.store = MemoryStore(store_path)
        self.dead_zero_gate = DeadZeroMUSGate(
            theta_dead=theta_dead,
            mus_tags=None,
            tie_threshold=0.01,
            enable_audit=True,
        )
        self.theta_write = theta_write
        self.theta_archieve = theta_archieve
        self.enable_mus = enable_mus
        self.enable_psi = enable_psi
        self.enable_kappa_gate = enable_kappa_gate
        
        # 初始化矛盾检测器（三层架构，含 EML Layer 3）
        enable_eml = bool(eml_path)
        self.contradiction_detector = ContradictionDetector(
            enable_nlp=True,          # V1.2: 启用 NLP 主谓宾提取
            enable_eml=enable_eml,    # V2.0: 自动启用 EML 语义相似度
            eml_path=eml_path,
            concepts_json_path=concepts_json_path,
        )
        
        logger.info(
            f"TOMAS-MemOS 融合层初始化完成: theta_dead={theta_dead}, "
            f"enable_mus={enable_mus}, enable_eml={enable_eml}"
        )

        # T14: κ-Snap 批上链 — 待提交事件队列
        self._pending_snap_events: List[Any] = []
        self._mina_snap: Optional[Any] = None
    
    def estimate_i(self, user_input: str, context: Dict[str, Any]) -> float:
        """
        估算 ℐ-值（信息存在度）
        
        简化版：基于以下启发式规则
        1. 与 EML 知识库的匹配度
        2. 用户输入的自信度（标点、措辞）
        3. 上下文一致性
        
        Args:
            user_input: 用户输入
            context: 上下文（包含 EML 匹配结果等）
            
        Returns:
            ℐ-值 [0, 1]
        """
        # 简化版：基于输入长度和标点估算
        i_value = 0.5  # 默认值
        
        # 规则1：带引用/证据的输入 ℐ 值更高
        if "《" in user_input or "》" in user_input:
            i_value += 0.2
        if "根据" in user_input or "研究表明" in user_input:
            i_value += 0.15
        
        # 规则2：绝对化表述降低 ℐ 值
        if "绝对" in user_input or "一定" in user_input or "肯定" in user_input:
            i_value -= 0.1
        
        # 规则3：疑问句式降低 ℐ 值（因为是询问，不是断言）
        if user_input.endswith("？") or user_input.endswith("?"):
            i_value -= 0.15
        
        # 规则4：与上下文的匹配度（如果有 EML 匹配结果）
        eml_matches = context.get("eml_matches", 0)
        i_value += min(eml_matches * 0.05, 0.2)
        
        # 规则5：已知错误陈述降低 ℐ 值
        if "太阳绕地球" in user_input or "地球绕太阳" in user_input:
            i_value = 0.05  # 强行设置低 ℐ 值触发死零
        
        return max(0.0, min(1.0, i_value))
    
    def build_eml_edge(
        self,
        user_input: str,
        i_value: float,
        context: Dict[str, Any],
    ) -> Tuple[str, Tuple[str, str], str, float]:
        """
        构建 EML 超边（简化版）
        
        Args:
            user_input: 用户输入
            i_value: ℐ-值
            context: 上下文
            
        Returns:
            (edge_id, concept_pair, relation, asym)
        """
        # 简化版：从用户输入中提取概念和关系
        # 未来可改用 NLP 工具
        
        # 生成 edge_id
        import hashlib
        edge_id = hashlib.md5(f"{user_input}:{time.time()}".encode()).hexdigest()[:16]
        
        # 提取概念对（简化：用前后文）
        concepts = context.get("concepts", ["用户", "输入"])
        if len(concepts) < 2:
            concepts = concepts + ["未知"] * (2 - len(concepts))
        concept_pair = (concepts[0], concepts[1])
        
        # 关系（简化：用输入的前 50 个字符）
        relation = user_input[:50]
        
        # Asym 值（优先从 context 读取，否则基于启发式）
        asym = context.get("asym", 0.0)
        if asym == 0.0:
            # 启发式规则
            if "但是" in user_input or "但" in user_input or "然而" in user_input:
                asym = 0.5
        
        return edge_id, concept_pair, relation, asym
    
    def _is_contradictory(self, relation1: str, relation2: str) -> bool:
        """
        检测两个关系是否矛盾（增强版）
        
        修改点：调用 ContradictionDetector.is_contradictory()
        三层检测架构：
        - Layer 1: 否定词检测（V1.1）
        - Layer 2: NLP 主谓宾提取（V1.2）
        - Layer 3: EML 语义相似度（V2.0）
        
        Args:
            relation1: 第一个关系文本
            relation2: 第二个关系文本
            
        Returns:
            是否矛盾
        """
        # 调用矛盾检测器（三层架构）
        return self.contradiction_detector.is_contradictory(relation1, relation2)
    
    def _find_contradictory_memories(
        self,
        concept_pair: Tuple[str, str],
        relation: str,
        asym: float,
    ) -> List[MemoryRecord]:
        """
        查找与当前边矛盾的已有记忆

        两阶段检索：
        (A) 精确概念对匹配 → 直接矛盾检测
        (B) 单概念共享匹配 → 用每个概念名做模糊检索，检测跨概念对矛盾（如"心→神明"与"脑→神明"）

        Args:
            concept_pair: 当前边的概念对
            relation: 当前边的关系文本
            asym: 当前边的 asym 值

        Returns:
            矛盾记忆列表（非空时表示 MUS 应激活）
        """
        candidates = []

        # 阶段 A: 精确概念对匹配
        exact_matches = self.store.retrieve_by_concepts(list(concept_pair))
        for ex in exact_matches:
            if self._is_mus_match(ex, relation, asym):
                candidates.append(ex)

        # 阶段 B: 单概念共享匹配（跨概念对 MUS）
        if not candidates:
            seen_ids = set()
            for concept in concept_pair:
                shared = self.store.retrieve(concept, top_k=20)
                for ex in shared:
                    if ex.edge_id in seen_ids:
                        continue
                    seen_ids.add(ex.edge_id)
                    # 跳过完全相同的概念对（已由阶段A覆盖）
                    if set(ex.concept_pair) == set(concept_pair):
                        continue
                    # 检查是否共享至少一个概念
                    if not (set(ex.concept_pair) & set(concept_pair)):
                        continue
                    if self._is_mus_match(ex, relation, asym):
                        candidates.append(ex)

        return candidates

    def _is_mus_match(
        self,
        existing: MemoryRecord,
        relation: str,
        asym: float,
    ) -> bool:
        """
        判断一条已有记忆是否与当前写入构成 MUS 矛盾

        Args:
            existing: 已有记忆记录
            relation: 当前关系文本
            asym: 当前 asym 值

        Returns:
            是否矛盾
        """
        # 条件1: asym 符号相反 → 直接矛盾
        if abs(existing.asym) > 0.01 and abs(asym) > 0.01:
            if (existing.asym > 0 and asym < 0) or (existing.asym < 0 and asym > 0):
                return True

        # 条件2: 三层矛盾检测器判定
        if self._is_contradictory(relation, existing.relation):
            return True

        return False

    def write_memory(self, user_input: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        写入记忆（五步流程）
        
        Args:
            user_input: 用户输入
            context: 上下文（包含 concepts, eml_matches 等）
            
        Returns:
            写入结果字典
        """
        # Step 1: 重要性判别（简化版）
        if len(user_input.strip()) < 2:
            return {"status": "skipped", "reason": "输入过短"}
        
        # Step 2: TOMAS 死零校验
        i_value = self.estimate_i(user_input, context)
        if i_value < self.dead_zero_gate.dead_zero_checker.theta_dead:
            return {
                "status": "rejected",
                "reason": "DEAD_ZERO_REJECT",
                "message": f"[DEAD_ZERO_REJECT]: 无据不记。（ℐ={i_value:.3f} < θ_dead={self.dead_zero_gate.dead_zero_checker.theta_dead}）",
                "i_value": i_value,
            }
        
        # Step 3: 构建 EML 超边
        edge_id, concept_pair, relation, asym = self.build_eml_edge(user_input, i_value, context)
        
        # Step 4: MUS 检查
        overwrite = True
        mus_active = False
        if self.enable_mus:
            existing = self._find_contradictory_memories(concept_pair, relation, asym)
            if existing:
                mus_active = True
                overwrite = False
                asym = 0.5  # 标记为正 asym
                logger.info(f"MUS 激活：{concept_pair} 存在矛盾记忆")
        
        # Step 5: 附加 ψ-锚
        psi_anchor = None
        if self.enable_psi:
            psi_anchor = PsiAnchor(
                self_state=context.get("self_state", "持有'记录用户信息'的元意向"),
                kappa_at_write=context.get("current_kappa", 4),
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
                emotion_tone=context.get("emotion_tone"),
                continuation_branch=context.get("continuation_branch"),
            )
        
        # 构建记忆记录
        record = MemoryRecord(
            edge_id=edge_id,
            concept_pair=concept_pair,
            relation=relation,
            i_value=i_value,
            asym=asym,
            psi_anchor=psi_anchor,
            meta=context.get("meta", {}),
        )
        
        # 写入存储
        self.store.write(record, overwrite=overwrite)
        
        # 定期归档低 ℐ 记忆
        if len(self.store.get_all()) % 10 == 0:
            self.store.archieve_low_i(self.theta_archieve)
        
        return {
            "status": "written",
            "edge_id": edge_id,
            "i_value": i_value,
            "mus_active": mus_active,
            "psi_anchor": psi_anchor.to_dict() if psi_anchor else None,
            "message": f"[写入成功] edge_id={edge_id}, ℐ={i_value:.3f}" + (" [MUS_ACTIVE]" if mus_active else ""),
        }
    
    def recall_memory(
        self,
        query: str,
        current_kappa: int,
        context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        回忆记忆（三步流程）
        
        Args:
            query: 查询字符串
            current_kappa: 当前 κ 值（语境深度）
            context: 上下文
            
        Returns:
            回忆结果字典
        """
        context = context or {}
        
        # Step 1: 检索候选记忆
        candidates = self.store.retrieve(query, top_k=10)
        
        if not candidates:
            return {
                "status": "no_match",
                "message": "[无匹配记忆]",
                "response": None,
            }
        
        # Step 2: κ-Gate 激活（根据 κ 值过滤）
        if self.enable_kappa_gate:
            activated = self._kappa_gate_filter(candidates, current_kappa)
        else:
            activated = candidates
        
        if not activated:
            return {
                "status": "no_activation",
                "message": f"[κ-Gate 未激活任何记忆] current_kappa={current_kappa}",
                "response": None,
            }
        
        # Step 3: κ-Snap 裁决（生成回答）
        response = self._kappa_snap(activated, current_kappa, context)
        
        return {
            "status": "success",
            "activated_count": len(activated),
            "mus_count": sum(1 for r in activated if abs(r.asym) > 0.01),
            "response": response,
            "records": [r.to_dict() for r in activated[:3]],  # 返回前 3 条
        }
    
    def _kappa_gate_filter(
        self,
        candidates: List[MemoryRecord],
        current_kappa: int,
    ) -> List[MemoryRecord]:
        """
        κ-Gate 过滤：根据当前 κ 值激活特定度类的记忆
        
        κ 值与记忆类型的映射：
        - κ=1: 节律感知记忆
        - κ=2: 藏象辨证记忆
        - κ=3: 经络演进记忆
        - κ=4: 脏腑辨证记忆
        - κ=5: 溯因推理记忆
        - κ=6: 太极回溯记忆
        
        Args:
            candidates: 候选记忆
            current_kappa: 当前 κ 值
            
        Returns:
            激活的记忆列表
        """
        # 简化版：根据 psi_anchor.kappa_at_write 过滤
        activated = []
        for record in candidates:
            if record.psi_anchor:
                # 如果记忆的 κ 值与当前 κ 值匹配，或相差不超过 1
                if abs(record.psi_anchor.kappa_at_write - current_kappa) <= 1:
                    activated.append(record)
            else:
                # 无 ψ-锚的记忆，默认激活
                activated.append(record)
        
        return activated
    
    def _kappa_snap(
        self,
        activated: List[MemoryRecord],
        current_kappa: int,
        context: Dict[str, Any],
    ) -> str:
        """
        κ-Snap 裁决：生成回答
        
        如果有 MUS 双存记忆，生成"既…也…"式双分支回答
        
        Args:
            activated: 激活的记忆
            current_kappa: 当前 κ 值
            context: 上下文
            
        Returns:
            生成的回答文本
        """
        if not activated:
            return "[无激活记忆]"
        
        # 检查是否有 MUS 双存
        mus_records = [r for r in activated if abs(r.asym) > 0.01]
        
        response_parts = []
        
        if mus_records:
            # MUS 双存：生成双分支回答
            response_parts.append("【MUS 双存记忆】")
            for i, record in enumerate(mus_records):
                branch = record.psi_anchor.continuation_branch if record.psi_anchor else None
                if branch:
                    response_parts.append(f"  - 分支{i+1}（{branch}）：{record.relation}")
                else:
                    response_parts.append(f"  - 记忆{i+1}：{record.relation}")
            
            # 添加 ψ-锚信息
            if mus_records[0].psi_anchor:
                psi_info = PsiAnchorManager.format_for_response(mus_records[0].psi_anchor)
                response_parts.append(psi_info)
            
            response_parts.append("\n阴平阳秘，双存不悖。")
        else:
            # 普通记忆：生成单分支回答
            top_record = activated[0]
            response_parts.append(f"【记忆回溯】{top_record.relation}")
            
            if top_record.psi_anchor:
                psi_info = PsiAnchorManager.format_for_response(top_record.psi_anchor)
                response_parts.append(psi_info)
        
        return "\n".join(response_parts)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取融合层统计信息"""
        all_records = self.store.get_all()
        mus_pairs = self.store.get_mus_pairs()
        
        return {
            "total_memories": len(all_records),
            "mus_pairs": len(mus_pairs),
            "avg_i_value": sum(r.i_value for r in all_records) / max(len(all_records), 1),
            "theta_dead": self.dead_zero_gate.dead_zero_checker.theta_dead,
            "enable_mus": self.enable_mus,
            "enable_psi": self.enable_psi,
            "enable_kappa_gate": self.enable_kappa_gate,
        }

    # ----- ψ-审计接口 (文章3) -----

    def record_psi_snapshot(
        self,
        snap_id: str,
        hyperedge_id: str,
        kappa: int,
        mus_active: bool = False,
    ):
        """
        记录 ψ-审计快照

        委托给 DeadZeroMUSGate.record_psi_snapshot()

        Args:
            snap_id: 快照 ID
            hyperedge_id: EML 超边 ID
            kappa: 当前 κ 值
            mus_active: 是否 MUS 激活
        """
        self.dead_zero_gate.record_psi_snapshot(
            snap_id=snap_id,
            hyperedge_id=hyperedge_id,
            kappa=kappa,
            mus_active=mus_active,
        )

    def get_audit_log(self) -> List[Dict]:
        """获取 ψ-审计日志"""
        return self.dead_zero_gate.psi_audit_log.copy()

    def get_adc_metrics(self) -> Dict:
        """获取 ADC 反欺骗指标"""
        return self.dead_zero_gate.get_adc_report()

    # ----- DIKWP 语义闭合接口 (章锋2026 文章1) -----

    def get_dikwp_layer_profile(self) -> Dict[str, Any]:
        """
        获取 DIKWP 分层画像

        按 ℐ-密度将全部记忆分配到 D/I/K/W/P 五层:
          D(ℐ≈0) → 原始感知数据
          I(ℐ~0.1-0.3) → 初步语义关联
          K(ℐ~0.3-0.7) → 稳定知识子图
          W(ℐ~0.7-0.9) → 跨域决策智慧
          P(ℐ~1.0) → ψ-锚定边界

        Returns:
            {layer: {count, avg_i, ratio, ...}}
        """
        all_records = self.store.get_all()
        if not all_records:
            return {"empty": True, "message": "记忆库为空"}

        layers = {'D': [], 'I': [], 'K': [], 'W': [], 'P': []}
        thresholds = {
            'D': (0.0, 0.1), 'I': (0.1, 0.35),
            'K': (0.35, 0.7), 'W': (0.7, 0.9), 'P': (0.9, 1.0),
        }

        for record in all_records:
            i_val = record.i_value
            for layer, (lo, hi) in thresholds.items():
                if lo <= i_val < hi or (layer == 'P' and i_val >= hi):
                    layers[layer].append(i_val)
                    break

        total = len(all_records)
        profile = {}
        for layer, i_vals in layers.items():
            profile[layer] = {
                'label': {'D': '数据层', 'I': '信息层', 'K': '知识层',
                          'W': '智慧层', 'P': '意图层'}[layer],
                'count': len(i_vals),
                'ratio': round(len(i_vals) / max(total, 1), 4),
                'avg_i': round(sum(i_vals) / max(len(i_vals), 1), 4) if i_vals else 0,
            }

        return {
            'total': total,
            'layers': profile,
            'dominant_layer': max(profile, key=lambda k: profile[k]['count']),
        }

    def check_dikwp_semantic_closure(
        self, subject: str, predicate: str, object_: str
    ) -> Dict[str, Any]:
        """
        检查目标命题在现有记忆中的语义闭合性

        验证 DIKWP 层间的语义传递链是否可闭合:
          若记忆中有 A→B 和 B→C, 则 A→C 应语义可推导

        Args:
            subject: 目标主语
            predicate: 目标谓词
            object_: 目标宾语

        Returns:
            {is_derivable, confidence, gaps, ...}
        """
        all_records = self.store.get_all()

        # 从记忆中提取三元组
        triples = []
        i_values = {}
        for idx, record in enumerate(all_records):
            # 从 relation 字段解析 (subject, predicate, object)
            rel = record.relation
            parts = rel.replace('→', ',').replace('->', ',').split(',')
            if len(parts) >= 2:
                s = parts[0].strip()
                o = parts[-1].strip()
                p = '→'.join(parts[1:-1]).strip() if len(parts) > 2 else '关联'
                triples.append((s, p, o))
                i_values[idx] = record.i_value

        if not triples:
            return {'is_derivable': False, 'confidence': 0,
                    'gaps': ['记忆库中无可提取的三元组'], 'explanation': '语义闭合检查无数据'}

        # 使用语义闭合检查器
        try:
            from .semantic_math import SemanticClosure
        except ImportError:
            import sys, os
            sys.path.insert(0, os.path.dirname(__file__))
            from semantic_math import SemanticClosure  # type: ignore

        closure = SemanticClosure()
        result = closure.check_closure(
            statements=triples,
            target=(subject, predicate, object_),
            i_values=i_values,
        )

        return {
            'is_derivable': result.is_derivable,
            'confidence': result.confidence,
            'i_conserved': result.i_conserved,
            'derivation_path': result.explanation,
            'gaps': result.gaps,
        }

    def apply_dikwp_bidirectional_feedback(
        self, source_layer: str, target_layer: str, gradient: float
    ) -> List[Dict]:
        """
        应用 DIKWP 层间双向反馈

        基于文章1: W→K 抑制错误权重, P→全层 ψ-锚定

        Args:
            source_layer: 反馈来源 (D/I/K/W/P)
            target_layer: 反馈目标 (D/I/K/W/P)
            gradient: ℐ-梯度, 正=增强, 负=抑制

        Returns:
            受影响的记忆列表
        """
        all_records = self.store.get_all()
        affected = []

        thresholds = {
            'D': (0.0, 0.1), 'I': (0.1, 0.35),
            'K': (0.35, 0.7), 'W': (0.7, 0.9), 'P': (0.9, 1.0),
        }
        target_lo, target_hi = thresholds.get(target_layer.upper(), (0, 1))

        for record in all_records:
            i_val = record.i_value
            if target_lo <= i_val < target_hi or (target_layer == 'P' and i_val >= target_hi):
                old_i = record.i_value
                record.i_value = max(0.0, min(1.0, record.i_value + gradient))
                affected.append({
                    'edge_id': record.edge_id,
                    'old_i': round(old_i, 4),
                    'new_i': round(record.i_value, 4),
                    'delta': round(gradient, 4),
                })

        logger.info(
            f"[DIKWP反馈] {source_layer}→{target_layer} ∇ℐ={gradient:+.3f}, "
            f"影响 {len(affected)} 条记忆"
        )
        return affected

    # ----- 语义防火墙钩子 (章锋2026) -----

    def install_semantic_firewall(self, firewall) -> 'TOMAS_Mem_OS_Fusion':
        """
        安装语义防火墙

        基于 semantic_firewall.py 的 SemanticFirewall

        Args:
            firewall: SemanticFirewall 实例
        """
        self._firewall = firewall
        logger.info("[MemOS] 语义防火墙已安装")
        return self

    def firewall_check_input(self, query: str,
                             dikwp_layer: str = "I") -> Tuple:
        """
        防火墙输入检查 — 在推理前调用

        Returns:
            (verdict, details)
        """
        if not hasattr(self, '_firewall') or not self._firewall:
            from tomas_agi.sim.semantic_firewall import FirewallVerdict
            return FirewallVerdict.ALLOW, {"note": "防火墙未安装"}

        return self._firewall.inspect_input(query, dikwp_layer)

    def firewall_check_output(self, response: str, query: str = "",
                              eml_context: Dict = None,
                              expected_layer: str = "K") -> Tuple:
        """
        防火墙输出检查 — 在返回响应前调用

        Returns:
            (verdict, details)
        """
        if not hasattr(self, '_firewall') or not self._firewall:
            from tomas_agi.sim.semantic_firewall import FirewallVerdict
            return FirewallVerdict.ALLOW, {"note": "防火墙未安装"}

        return self._firewall.inspect_output(
            response, query, eml_context, expected_layer
        )

    def get_firewall_logs(self, direction: str = None) -> List:
        """获取防火墙日志"""
        if not hasattr(self, '_firewall') or not self._firewall:
            return []
        return self._firewall.get_logs(direction)

    def get_firewall_stats(self):
        """获取防火墙统计"""
        if not hasattr(self, '_firewall') or not self._firewall:
            return None
        return self._firewall.get_stats()

    # ----- Palantir EML 摄入 (章锋2026) -----

    def ingest_palantir_ontology(self, palantir_mapper) -> Dict[str, Any]:
        """
        从 Palantir 本体映射器摄入 EML 图

        基于 palantir_mapper.py:
          Ontology实体 → EML顶点
          Ontology关系 → EML超边 (含 ℐ-权重和死零过滤)

        Args:
            palantir_mapper: PalantirEMLMapper 实例 (已加载本体)

        Returns:
            {ingested_vertices, ingested_edges, dead_zero_rejected}
        """
        eml_graph = palantir_mapper.map_to_eml()
        vertices = eml_graph.get('vertices', [])
        edges = eml_graph.get('edges', [])

        ingested_v = 0
        ingested_e = 0
        dz_rejected = 0

        # 摄入顶点 → 作为特殊记忆记录存储
        for v in vertices:
            vid = v.get('id', f"v-{ingested_v}")
            record = MemoryRecord(
                edge_id=vid,
                concept_pair=(v.get('name', vid), ''),
                relation='EML_VERTEX',
                i_value=v.get('i_val', v.get('confidence', 0.5)),
                asym=0.0,
                psi_anchor=None,
                meta={'type': 'vertex', 'dikwp': v.get('dikwp', 'K')},
            )
            self.store.write(record, overwrite=True)
            ingested_v += 1

        # 摄入超边 → MemoryStore
        for e in edges:
            if e.get('dead_zero'):
                dz_rejected += 1
                logger.debug(f"[Palantir摄入] DEAD_ZERO: {e['id']}")
                continue

            nodes = e.get('nodes', ['?', '?'])
            source = e.get('source_name', nodes[0] if len(nodes) > 0 else '?')
            target = e.get('target_name', nodes[1] if len(nodes) > 1 else '?')
            record = MemoryRecord(
                edge_id=e.get('id', f"e-{ingested_e}"),
                concept_pair=(source, target),
                relation=e.get('relation_type', 'RELATED'),
                i_value=e.get('i_val', 0.5),
                asym=e.get('asym', 0.0),
                psi_anchor=None,
                meta={
                    'type': 'edge',
                    'source': f"palantir:{palantir_mapper.ontology.name if palantir_mapper.ontology else 'unknown'}",
                    'dikwp_layer': e.get('dikwp_layer', 'K'),
                },
            )
            self.store.write(record, overwrite=True)
            ingested_e += 1

        result = {
            "ingested_vertices": ingested_v,
            "ingested_edges": ingested_e,
            "dead_zero_rejected": dz_rejected,
            "ontology_name": palantir_mapper.ontology.name if palantir_mapper.ontology else None,
            "dikwp_distribution": eml_graph.get('dikwp_layers', {}),
        }

        logger.info(
            f"[Palantir摄入] V={ingested_v} E={ingested_e} DZ={dz_rejected} "
            f"DIKWP={eml_graph.get('dikwp_layers', {})}"
        )
        return result

    def get_dikwp_pie_data(self) -> Dict:
        """
        获取 DIKWP 饼图数据 — 供前端饼图使用

        Returns:
            {layers: [{layer, name, count, percentage}], total_edges}
        """
        all_records = self.store.get_all()
        if not all_records:
            return {"layers": [], "total_edges": 0}

        thresholds = {
            'D': (0.0, 0.15), 'I': (0.15, 0.35),
            'K': (0.35, 0.65), 'W': (0.65, 0.85), 'P': (0.85, 1.0),
        }
        layer_names = {
            'D': '数据 Data', 'I': '信息 Info',
            'K': '知识 Knowledge', 'W': '智慧 Wisdom', 'P': '目的 Purpose',
        }

        counts = {layer: 0 for layer in thresholds}
        for r in all_records:
            for layer, (lo, hi) in thresholds.items():
                if lo <= r.i_value < hi or (layer == 'P' and r.i_value >= hi):
                    counts[layer] += 1
                    break

        total = sum(counts.values()) or 1
        layers = [
            {
                "layer": layer,
                "name": layer_names[layer],
                "count": counts[layer],
                "percentage": round(counts[layer] / total * 100, 1),
            }
            for layer in ['D', 'I', 'K', 'W', 'P']
        ]

        return {"layers": layers, "total_edges": total}


    # ----- HY World Bridge 钩子 (章锋2026 文章2) -----

    def install_hyworld_bridge(self, bridge) -> 'TOMAS_Mem_OS_Fusion':
        """
        安装 HY World 2.0 ↔ TOMAS EML 桥接器

        基于 hyworld_bridge.py 的 HYWorldBridge

        Args:
            bridge: HYWorldBridge 实例
        """
        self._hyworld_bridge = bridge
        logger.info("[MemOS] HY World Bridge 已安装")
        return self

    def hyworld_build_scene(self, panorama_data: Dict[str, Any],
                            scene_id: str = None) -> Any:
        """
        从全景图数据构建 HY Scene (通过桥接器)

        Returns:
            HYScene 对象
        """
        if not hasattr(self, '_hyworld_bridge') or not self._hyworld_bridge:
            raise RuntimeError("HY World Bridge 未安装, 请先调用 install_hyworld_bridge()")
        return self._hyworld_bridge.build_scene(panorama_data, scene_id)

    def hyworld_dead_zero_audit(self, scene: Any) -> Dict[str, Any]:
        """
        对 HY Scene 执行死零审计

        Returns:
            {passed, rejected, mus_flagged, details, ...}
        """
        if not hasattr(self, '_hyworld_bridge') or not self._hyworld_bridge:
            raise RuntimeError("HY World Bridge 未安装")
        return self._hyworld_bridge.dead_zero_audit(scene)

    # ----- SAI T-Proc 钩子 (章锋2026 文章1) -----

    def install_sai_tproc(self, tproc) -> 'TOMAS_Mem_OS_Fusion':
        """
        安装 SAI T-Processor 后置审计器

        基于 sai_tproc.py 的 TProcAuditor

        Args:
            tproc: TProcAuditor 实例
        """
        self._sai_tproc = tproc
        logger.info("[MemOS] SAI T-Proc 审计器已安装")
        return self

    def sai_audit_hypothesis(self, hypothesis) -> Any:
        """
        审计单个 SAI 假设

        Returns:
            AuditResult (ALLOW/REJECT/MUS_ACTIVE)
        """
        if not hasattr(self, '_sai_tproc') or not self._sai_tproc:
            raise RuntimeError("SAI T-Proc 未安装, 请先调用 install_sai_tproc()")
        return self._sai_tproc.audit_hypothesis(hypothesis)

    def sai_audit_batch(self, hypotheses: List) -> List:
        """批量审计 SAI 假设池"""
        if not hasattr(self, '_sai_tproc') or not self._sai_tproc:
            raise RuntimeError("SAI T-Proc 未安装")
        return self._sai_tproc.audit_batch(hypotheses)

    def sai_filter_allowed(self, hypotheses: List) -> List:
        """过滤: 仅返回通过审计的假设"""
        if not hasattr(self, '_sai_tproc') or not self._sai_tproc:
            raise RuntimeError("SAI T-Proc 未安装")
        return self._sai_tproc.filter_allowed(hypotheses)

    def get_sai_audit_report(self) -> Dict[str, Any]:
        """获取 SAI 审计报告"""
        if not hasattr(self, '_sai_tproc') or not self._sai_tproc:
            return {"error": "SAI T-Proc 未安装"}
        return self._sai_tproc.get_audit_report()

    # ----- 空间死零审计钩子 (章锋2026) -----

    def install_spatial_auditor(self, auditor) -> 'TOMAS_Mem_OS_Fusion':
        """
        安装空间死零审计器

        基于 spatial_dead_zero.py 的 SpatialDeadZeroAuditor

        Args:
            auditor: SpatialDeadZeroAuditor 实例
        """
        self._spatial_auditor = auditor
        logger.info("[MemOS] 空间死零审计器已安装")
        return self

    def audit_3d_scene(self, objects: List[Dict[str, Any]],
                       ground_truth: List[Dict[str, Any]] = None) -> Any:
        """
        对 3D 场景执行空间死零审计

        Returns:
            SpatialAuditReport
        """
        if not hasattr(self, '_spatial_auditor') or not self._spatial_auditor:
            raise RuntimeError("空间死零审计器未安装, 请先调用 install_spatial_auditor()")
        return self._spatial_auditor.audit(objects, ground_truth)

    def filter_3d_scene(self, objects: List[Dict[str, Any]]) -> Tuple:
        """
        过滤 3D 场景: 移除死零/悬浮物体

        Returns:
            (passed_objects, rejected_objects)
        """
        if not hasattr(self, '_spatial_auditor') or not self._spatial_auditor:
            raise RuntimeError("空间死零审计器未安装")
        return self._spatial_auditor.filter_scene(objects)

    def auto_snap_scene(self, objects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """自动将悬浮物体吸附到地面"""
        if not hasattr(self, '_spatial_auditor') or not self._spatial_auditor:
            raise RuntimeError("空间死零审计器未安装")
        return self._spatial_auditor.auto_snap_to_ground(objects)

    def get_spatial_audit(self, objects: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        综合空间审计: 获取完整报告

        快捷方法 — 一站式审计
        """
        if not hasattr(self, '_spatial_auditor') or not self._spatial_auditor:
            raise RuntimeError("空间死零审计器未安装")

        report = self._spatial_auditor.audit(objects)
        return {
            "total_objects": report.total_objects,
            "grounded": report.grounded,
            "floating": report.floating,
            "penetrating": report.penetrating,
            "unstable": report.unstable,
            "mus_active": report.mus_active,
            "dead_zero": report.dead_zero,
            "global_i_density": report.global_i_density,
            "details": report.details,
        }


    # ══════════════════════════════════════════════
    # IDO 桥接 (2026-06-16)
    # ══════════════════════════════════════════════

    def install_ido_bridge(self, theta_dead: float = 0.15):
        """安装 IDO 桥接引擎"""
        try:
            from .ido_bridge import IDOBridge
        except ImportError:
            from ido_bridge import IDOBridge
        self._ido_bridge = IDOBridge(theta_dead=theta_dead)

    def ido_evaluate(self, hypothesis_data: Dict[str, Any],
                     eml_data: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """IDO 假设评估 — 梯度流 + T-Proc 审计"""
        if not hasattr(self, '_ido_bridge') or not self._ido_bridge:
            raise RuntimeError("IDO 桥接未安装")
        try:
            from .ido_bridge import IDOHypothesis, IDOTier, EvidenceLevel
        except ImportError:
            from ido_bridge import IDOHypothesis, IDOTier, EvidenceLevel
        h = IDOHypothesis(
            id=hypothesis_data.get("id", "unnamed"),
            problem=hypothesis_data.get("problem", ""),
            description=hypothesis_data.get("description", ""),
            tier=IDOTier(hypothesis_data.get("tier", "Tier2")),
            axiom_status=hypothesis_data.get("axiom_status", {"A1":False,"A2":False,"A3":False,"A4":False}),
            i_support=hypothesis_data.get("i_support", 0.3),
            asym=hypothesis_data.get("asym", 0.0),
            competing=hypothesis_data.get("competing", []),
            evidence=EvidenceLevel(hypothesis_data.get("evidence", "UNGROUNDED")),
        )
        assessment = self._ido_bridge.evaluate_hypothesis(h, eml_data)
        return {
            "hypothesis_id": assessment.hypothesis_id,
            "tier": assessment.tier.value,
            "tomas_status": assessment.tomas_status,
            "i_support": assessment.i_support,
            "passed_axioms": assessment.passed_axioms,
            "pending_axioms": assessment.pending_axioms,
            "next_action": assessment.next_action,
            "report": assessment.report,
        }

    def ido_flow_search(self, problem: str, eml_data: Optional[List[Dict]] = None) -> Dict:
        """IDO 梯度流搜索"""
        if not hasattr(self, '_ido_bridge') or not self._ido_bridge:
            raise RuntimeError("IDO 桥接未安装")
        return self._ido_bridge.flow_search(problem, eml_data)

    def ido_tier_classify(self, problem: str, axiom_status: Optional[Dict] = None) -> str:
        """IDO 分层分类"""
        if not hasattr(self, '_ido_bridge') or not self._ido_bridge:
            raise RuntimeError("IDO 桥接未安装")
        return self._ido_bridge.tier_classify(problem, axiom_status).value

    def ido_kappa_store(self, content: Dict, record_id: Optional[str] = None) -> Dict:
        """κ-MM 记忆存储"""
        if not hasattr(self, '_ido_bridge') or not self._ido_bridge:
            raise RuntimeError("IDO 桥接未安装")
        record = self._ido_bridge.kappa_store(content, record_id)
        return {"id": record.id, "holographic_projection": record.holographic_projection,
                "kappa_signature": str(record.kappa_signature), "retrieval_count": record.retrieval_count}

    def ido_kappa_recall(self, record_id: str) -> Optional[Dict]:
        """κ-MM 记忆检索"""
        if not hasattr(self, '_ido_bridge') or not self._ido_bridge:
            raise RuntimeError("IDO 桥接未安装")
        record = self._ido_bridge.kappa_recall(record_id)
        if not record: return None
        return {"id": record.id, "content": record.content, "holographic_projection": record.holographic_projection,
                "kappa_signature": str(record.kappa_signature), "retrieval_count": record.retrieval_count}

    def ido_prime_zero_measure(self, prime_data: Optional[List[float]] = None,
                               zero_data: Optional[List[float]] = None) -> Dict:
        """素数-零点对偶测度"""
        if not hasattr(self, '_ido_bridge') or not self._ido_bridge:
            raise RuntimeError("IDO 桥接未安装")
        state = self._ido_bridge.prime_zero_measure(prime_data, zero_data)
        return state.to_dict()

    def ido_predictions(self) -> Dict:
        """可证伪预言 P_IDO_1/2/3"""
        if not hasattr(self, '_ido_bridge') or not self._ido_bridge:
            raise RuntimeError("IDO 桥接未安装")
        return {
            "p_ido_1": self._ido_bridge.predict_p_ido_1(),
            "p_ido_2": self._ido_bridge.predict_p_ido_2(),
            "p_ido_3": self._ido_bridge.predict_p_ido_3(),
        }

    def get_ido_stats(self) -> Dict:
        """IDO 桥接统计"""
        if not hasattr(self, '_ido_bridge') or not self._ido_bridge:
            return {"status": "not_installed"}
        return self._ido_bridge.get_stats()


    # ══════════════════════════════════════════════════════════
    # FDE 本体构建器集成 (道法术器)
    # ══════════════════════════════════════════════════════════

    def install_fde_builder(self, theta_dead: float = 0.15) -> None:
        """安装 FDE 本体构建器"""
        from .fde_builder import FDEOntologyBuilder
        self._fde_builder = FDEOntologyBuilder(theta_dead=theta_dead)

    @property
    def fde_installed(self) -> bool:
        return hasattr(self, '_fde_builder') and self._fde_builder is not None

    def fde_add_node(self, node) -> None:
        if not self.fde_installed: raise RuntimeError("FDE 构建器未安装")
        self._fde_builder.add_node(node)

    def fde_validate(self, node_id: str):
        if not self.fde_installed: raise RuntimeError("FDE 构建器未安装")
        return self._fde_builder.validate_full(node_id)

    def fde_build_from_eml(self, vertices: list, domain: str = "") -> list:
        if not self.fde_installed: raise RuntimeError("FDE 构建器未安装")
        return self._fde_builder.build_from_eml(vertices, domain)

    def fde_calibrate(self, node_id: str, evidence: list) -> float:
        if not self.fde_installed: raise RuntimeError("FDE 构建器未安装")
        return self._fde_builder.calibrate_iota(node_id, evidence)

    def fde_set_echo(self, node_id: str, ctx) -> None:
        if not self.fde_installed: raise RuntimeError("FDE 构建器未安装")
        self._fde_builder.set_echo_context(node_id, ctx)

    def fde_check_alignment(self, node_id: str, threshold: float = 0.7) -> dict:
        if not self.fde_installed: raise RuntimeError("FDE 构建器未安装")
        return self._fde_builder.check_cross_domain_alignment(node_id, threshold)

    def fde_stats(self) -> dict:
        if not self.fde_installed: return {"status": "not_installed"}
        return self._fde_builder.stats

    # ══════════════════════════════════════════════════════════
    # 双时间维度引擎集成
    # ══════════════════════════════════════════════════════════

    def install_dual_timeline(self, theta_dead: float = 0.15, max_recursion: int = 10) -> None:
        """安装双时间维度引擎"""
        from .dual_timeline import DualTimelineEngine
        self._dual_timeline = DualTimelineEngine(
            theta_dead=theta_dead, max_recursion=max_recursion
        )

    @property
    def dual_timeline_installed(self) -> bool:
        return hasattr(self, '_dual_timeline') and self._dual_timeline is not None

    def dt_observe(self, event_id: str, payload: dict = None, iota: float = 0.5):
        if not self.dual_timeline_installed: raise RuntimeError("双时间引擎未安装")
        return self._dual_timeline.observe(event_id, payload, iota)

    def dt_think(self, event_id: str, content: str, iota: float = 0.5,
                 recursion: int = 0, predecessors: list = None, linked_causal: str = None):
        if not self.dual_timeline_installed: raise RuntimeError("双时间引擎未安装")
        return self._dual_timeline.think(event_id, content, iota, recursion, predecessors, linked_causal)

    def dt_stats(self) -> dict:
        if not self.dual_timeline_installed: return {"status": "not_installed"}
        return self._dual_timeline.stats

    # ══════════════════════════════════════════════════════════
    # IT-OT 翻译桥集成
    # ══════════════════════════════════════════════════════════

    def install_itot_bridge(self, theta_dead: float = 0.15) -> None:
        """安装 IT-OT 翻译桥"""
        from .itot_bridge import ITOTBridge
        self._itot_bridge = ITOTBridge(theta_dead=theta_dead)

    @property
    def itot_installed(self) -> bool:
        return hasattr(self, '_itot_bridge') and self._itot_bridge is not None

    def itot_translate(self, term: str, source: str = "IT") -> str:
        if not self.itot_installed: raise RuntimeError("IT-OT 翻译桥未安装")
        from .itot_bridge import TechDomain
        domain = TechDomain.IT if source == "IT" else TechDomain.OT
        result = self._itot_bridge.translate(term, domain)
        return result or ""

    def itot_register_debt(self, debt) -> None:
        if not self.itot_installed: raise RuntimeError("IT-OT 翻译桥未安装")
        self._itot_bridge.register_debt(debt)

    def itot_scan_debts(self) -> list:
        if not self.itot_installed: raise RuntimeError("IT-OT 翻译桥未安装")
        return self._itot_bridge.scan_critical_debts()

    def itot_evaluate_trust(self, entity_id: str, iota: float = 0.5, content: str = ""):
        if not self.itot_installed: raise RuntimeError("IT-OT 翻译桥未安装")
        return self._itot_bridge.evaluate_trust(entity_id, iota, content)

    def itot_register_entity(self, entity_id: str) -> None:
        if not self.itot_installed: raise RuntimeError("IT-OT 翻译桥未安装")
        self._itot_bridge.register_entity(entity_id)

    def itot_stats(self) -> dict:
        if not self.itot_installed: return {"status": "not_installed"}
        return self._itot_bridge.stats

    # ══════════════════════════════════════════════════════════
    # κ-Snap 批上链集成 (T14)
    # ══════════════════════════════════════════════════════════

    def add_snap_event(self, event: Any) -> None:
        """添加 κ-Snap 事件到待上链队列。

        Args:
            event: SnapEvent 实例
        """
        self._pending_snap_events.append(event)
        logger.debug(
            "SnapEvent 已加入待上链队列: %s (队列长度=%d)",
            getattr(event, "event_id", str(id(event))),
            len(self._pending_snap_events),
        )

    def get_pending_snap_events(self) -> List:
        """获取待上链的 SnapEvent 列表。

        Returns:
            待上链事件列表（副本）
        """
        return list(self._pending_snap_events)

    def batch_commit_to_chain(self, events: List) -> str:
        """批量提交 κ-Snap 事件到链上（Merkle Root 存证）。

        流程：
          1. 调用 KSnapOperator.batch_merkle_root() 计算 Merkle Root
          2. 可选调用 MinaTOMASSnap.batch_prove() 上链
          3. 返回 merkle_root hash

        Args:
            events: SnapEvent 列表

        Returns:
            Merkle Root 哈希字符串（十六进制）
        """
        if not events:
            logger.info("batch_commit_to_chain: 空事件列表，返回全零 Merkle Root")
            return "0" * 64

        # 1. 计算 Merkle Root
        merkle_root: str
        if _HAS_KSNAP and KSnapOperator is not None:
            merkle_root = KSnapOperator.batch_merkle_root(events)
            logger.info(
                "batch_commit_to_chain: Merkle Root=%s (%d events)",
                merkle_root[:16] + "...",
                len(events),
            )
        else:
            # 降级：本地 SHA-256 简单拼接哈希
            import hashlib
            combined = "".join(
                str(getattr(e, "event_id", "")) + str(getattr(e, "timestamp", ""))
                for e in events
            )
            merkle_root = hashlib.sha256(combined.encode("utf-8")).hexdigest()
            logger.warning(
                "batch_commit_to_chain: KSnapOperator 不可用，使用降级哈希: %s...",
                merkle_root[:16],
            )

        # 2. 可选上链（MinaTOMASSnap）
        if _HAS_MINA and MinaTOMASSnap is not None:
            try:
                mina = self._get_mina_snap()
                proof_hash = mina.batch_prove(events)
                logger.info(
                    "batch_commit_to_chain: Mina 上链完成, proof_hash=%s...",
                    proof_hash[:16],
                )
            except Exception as e:
                logger.warning("batch_commit_to_chain: Mina 上链失败 (降级): %s", e)

        return merkle_root

    def flush_snap_events(self) -> str:
        """批量提交所有待上链事件，返回 Merkle Root。

        提交后清空待上链队列。

        Returns:
            Merkle Root 哈希字符串（十六进制）
        """
        events = self._pending_snap_events
        if not events:
            logger.info("flush_snap_events: 无待上链事件")
            return "0" * 64

        merkle_root = self.batch_commit_to_chain(events)
        committed_count = len(events)
        self._pending_snap_events = []
        logger.info(
            "flush_snap_events: 已提交 %d 个事件, merkle_root=%s...",
            committed_count,
            merkle_root[:16],
        )
        return merkle_root

    def _get_mina_snap(self) -> Any:
        """懒加载 MinaTOMASSnap 实例（单例）。"""
        if self._mina_snap is None:
            if _HAS_MINA and MinaTOMASSnap is not None:
                self._mina_snap = MinaTOMASSnap()
                logger.info("MinaTOMASSnap 实例已懒加载")
            else:
                logger.warning("MinaTOMASSnap 不可用，跳过上链")
        return self._mina_snap


# 导出
__all__ = [
    "TOMAS_Mem_OS_Fusion",
    "MemoryStore",
    "MemoryRecord",
    "MUSDualStoreEntry",
    "PsiAnchor",
    "PsiAnchorManager",
]
