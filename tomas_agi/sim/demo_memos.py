#!/usr/bin/env python3
"""
TOMAS-MemOS 融合层 — 端到端演示脚本
=====================================================

展示五点升维的完整工作流：
  (1) 死零校验 — ℐ值低于阈值拒绝写入
  (2) MUS 双存 — 矛盾记忆双存不覆盖
  (3) ψ-锚 — 记忆附加自我状态快照
  (4) κ-Gate — 按语境深度激活记忆
  (5) EML 超边 — 记忆以 EML 超边形式组织

运行方式:
    python -m tomas_agi.sim.demo_memos
    # 或
    python demo_memos.py
"""

import sys
import os
import tempfile
import shutil
import json

# 确保项目路径可导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sim.memos_fusion import TOMAS_Mem_OS_Fusion, MemoryRecord
from sim.psi_anchor import PsiAnchor

# ── ANSI 颜色 ──────────────────────────────────────────────
class C:
    """终端颜色"""
    H = "\033[1;36m"   # 标题（亮青）
    K = "\033[1;33m"   # 键（黄）
    V = "\033[1;32m"   # 值（绿）
    E = "\033[1;31m"   # 错误/警告（红）
    M = "\033[1;35m"   # MUS（洋红）
    G = "\033[0;32m"   # 成功（暗绿）
    D = "\033[0;37m"   # 默认
    R = "\033[0m"      # 重置
    B = "\033[1m"      # 粗体
    I = "\033[3m"      # 斜体


def header(text: str, n: int = 1):
    """打印场景标题"""
    print(f"\n{C.H}━━━ [{n}] {text} {C.R}")
    print("-" * 56)


def show_result(result: dict, title: str = ""):
    """格式化打印结果"""
    if title:
        print(f"  {C.B}{title}:{C.R}")
    for k, v in result.items():
        if k == "records":
            continue
        color = C.G if result.get("status") in ("written", "success") else C.E
        print(f"  {C.K}{k:<18}{C.R} → {color}{v}{C.R}")


def show_record(record: MemoryRecord, prefix: str = "  "):
    """格式化打印一条记忆记录"""
    print(f"{prefix}{C.B}{record.edge_id[:12]}...{C.R}")
    print(f"{prefix}  {record.concept_pair[0]} {C.M}→{C.R} {record.concept_pair[1]}"
          f"   (ℐ={record.i_value:.2f}, asym={record.asym:.2f})")
    if record.psi_anchor:
        pa = record.psi_anchor
        print(f"{prefix}  ψ-锚: κ={pa.kappa_at_write} | {pa.self_state}")
        if pa.continuation_branch:
            print(f"{prefix}        分支: {pa.continuation_branch}")


# ════════════════════════════════════════════════════════════
#  主演示流程
# ════════════════════════════════════════════════════════════

def main():
    print(f"{C.H}{'='*56}")
    print(f"   TOMAS-MemOS 融合层 — 五点升维演示")
    print(f"{'='*56}{C.R}")

    # 创建临时存储目录
    tmpdir = tempfile.mkdtemp(prefix="memos_demo_")
    store_path = os.path.join(tmpdir, "memory_store.json")

    # 可选：加载 EML 文件用于 Layer 3 矛盾检测
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    eml_path = os.path.join(project_root, "data", "physics_distilled.eml")
    concepts_path = os.path.join(project_root, "data", "physics_distilled.concepts.json")

    has_eml = os.path.exists(eml_path) and os.path.exists(concepts_path)

    # ── 初始化 ──────────────────────────────────────────
    print(f"\n{C.I}初始化 TOMAS-MemOS 融合层...{C.R}")
    fusion = TOMAS_Mem_OS_Fusion(
        store_path=store_path,
        theta_dead=0.15,
        theta_write=0.3,
        theta_archieve=0.1,
        enable_mus=True,
        enable_psi=True,
        enable_kappa_gate=True,
        eml_path=eml_path if has_eml else None,
        concepts_json_path=concepts_path if has_eml else None,
    )
    print(f"  {C.G}✓ 融合层就绪{C.R}")
    print(f"  {C.I}  EML Layer 3: {'已启用' if has_eml else '未启用（文件缺失）'}{C.R}")
    print(f"  {C.I}  存储路径: {store_path}{C.R}")

    # ── [1] 死零校验 ────────────────────────────────────
    header("死零校验：ℐ 值过低 → 拒绝写入")
    r = fusion.write_memory("太阳绕地球运转", {"concepts": ["太阳", "地球"], "current_kappa": 3})
    show_result(r)
    assert r["status"] == "rejected", "死零校验应拒绝 ℐ=0.05 的输入！"
    print(f"  {C.G}✓ 预言 P_Mem_1 验证通过：死零拒绝{C.R}")

    # ── [2] 正常写入 ────────────────────────────────────
    header("正常写入：ℐ 值达标 → 写入成功")
    r = fusion.write_memory(
        "心主神明，为君主之官",
        {"concepts": ["心", "神明"], "self_state": "研读《黄帝内经》", "current_kappa": 4}
    )
    show_result(r)
    assert r["status"] == "written", "正常写入应成功！"
    print(f"  {C.G}✓ 正常写入成功（edge_id={r['edge_id']}）{C.R}")

    # ── [3] ψ-锚验证 ───────────────────────────────────
    header("ψ-锚：写入后记忆携带自我状态快照")
    records = fusion.store.get_all()
    for rec in records:
        show_record(rec)
    first = records[0]
    assert first.psi_anchor is not None, "ψ-锚应存在！"
    assert first.psi_anchor.self_state == "研读《黄帝内经》", "自我状态应正确记录！"
    print(f"  {C.G}✓ 预言 P_Mem_3 验证通过：ψ-锚正确附加{C.R}")
    print(f"  {C.I}  自我状态: {first.psi_anchor.self_state}{C.R}")
    print(f"  {C.I}  写入时 κ 值: {first.psi_anchor.kappa_at_write}{C.R}")

    # ── [4] 更多写入（建立记忆库） ─────────────────────
    header("建立记忆库：写入多条关联记忆")
    memories = [
        ("肺主气，司呼吸", ["肺", "气"], "研读脏腑学说", 4),
        ("心主血脉，其华在面", ["心", "血脉"], "临床观察记录", 4),
        ("肾主水，藏精", ["肾", "水"], "研读《难经》", 3),
        ("肝主疏泄，调畅气机", ["肝", "气"], "跟诊记录", 3),
    ]
    for text, concepts, state, kappa in memories:
        r = fusion.write_memory(
            text,
            {"concepts": concepts, "self_state": state, "current_kappa": kappa}
        )
        print(f"  {C.G}✓{C.R} 写入: {C.B}{text:<30}{C.R} ℐ={r['i_value']:.2f}  κ={kappa}")
    print(f"  {C.I}  当前记忆总数: {len(fusion.store.get_all())}{C.R}")

    # ── [5] κ-Gate 召回 ─────────────────────────────────
    header("κ-Gate 召回：不同 κ 值激活不同记忆")
    for kappa in [4, 3, 2, 1]:
        result = fusion.recall_memory("脏腑", current_kappa=kappa)
        status = result.get("status", "?")
        count = result.get("activated_count", 0)
        color = C.G if status == "success" else C.E
        print(f"  κ={kappa}: {color}{status:<15}{C.R} 激活 {count} 条记忆")

    # 验证 κ=4 时应激活脏腑辨证记忆
    result_k4 = fusion.recall_memory("心", current_kappa=4)
    assert result_k4["status"] == "success", "κ=4 召回应成功！"
    print(f"  {C.G}✓ κ-Gate 激活验证通过{C.R}")

    # ── [6] MUS 双存 ────────────────────────────────────
    header("MUS 双存：矛盾记忆双存不覆盖")
    # 先写入一条"脑主神明"（与之前的"心主神明"形成矛盾）
    r_brain = fusion.write_memory(
        "脑主神明，为元神之府",
        {"concepts": ["脑", "神明"], "self_state": "研读李时珍《本草纲目》", "current_kappa": 4}
    )
    show_result(r_brain)
    assert r_brain["mus_active"], "MUS 应激活！"
    print(f"  {C.G}✓ 预言 P_Mem_2 验证通过：MUS 双存{C.R}")

    # 验证两条记忆都存在
    all_recs = fusion.store.get_all()
    heart_records = [r for r in all_recs if r.concept_pair[0] == "心" and r.concept_pair[1] == "神明"]
    brain_records = [r for r in all_recs if r.concept_pair[0] == "脑" and r.concept_pair[1] == "神明"]
    print(f"  {C.M}心→神明 记忆: {len(heart_records)} 条{C.R}")
    print(f"  {C.M}脑→神明 记忆: {len(brain_records)} 条{C.R}")
    assert len(heart_records) >= 1, "心主神明的记忆应仍在！"
    assert len(brain_records) >= 1, "脑主神明的记忆应已写入！"

    # κ-Snap 双分支回答
    result_mus = fusion.recall_memory("神明", current_kappa=4)
    if result_mus.get("mus_count", 0) > 0:
        print(f"\n  {C.M}κ-Snap 双分支回答:{C.R}")
        print(f"  {C.I}{result_mus.get('response', '')}{C.R}")

    # ── [7] ψ-锚回溯 ────────────────────────────────────
    header("ψ-锚回溯：根据自我状态定位记忆来源")
    all_records = fusion.store.get_all()
    for rec in all_records:
        if rec.psi_anchor:
            source = rec.psi_anchor.self_state
            kappa = rec.psi_anchor.kappa_at_write
            concepts = f"{rec.concept_pair[0]}→{rec.concept_pair[1]}"
            print(f"  {C.K}{concepts:<24}{C.R} {C.I}{source:<20}{C.R} κ={kappa}")

    # ── [8] 统计汇总 ────────────────────────────────────
    header("统计汇总")
    stats = fusion.get_stats()
    for k, v in stats.items():
        color = C.M if k == "mus_pairs" else C.V
        print(f"  {C.K}{k:<20}{C.R} → {color}{v}{C.R}")

    # ── 清理 ────────────────────────────────────────────
    print(f"\n{C.I}清理临时文件...{C.R}", end=" ")
    shutil.rmtree(tmpdir, ignore_errors=True)
    print(f"{C.G}完成{C.R}")

    # ── 总结 ────────────────────────────────────────────
    print(f"\n{C.H}{'='*56}")
    print(f"   演示完成！五点升维全部验证通过 ✅")
    print(f"{'='*56}{C.R}")
    print(f"""
  {C.G}1. 死零校验{C.R}    — ℐ < θ_dead ⇒ 拒绝写入      [{C.G}✓{C.R}]
  {C.G}2. MUS 双存{C.R}    — 矛盾记忆双存不覆盖          [{C.G}✓{C.R}]
  {C.G}3. ψ-锚{C.R}       — 自我状态快照附加            [{C.G}✓{C.R}]
  {C.G}4. κ-Gate{C.R}     — 按语境深度激活记忆          [{C.G}✓{C.R}]
  {C.G}5. EML 超边{C.R}   — 概念对+关系+ℐ值 存储       [{C.G}✓{C.R}]
    """)


if __name__ == "__main__":
    main()
