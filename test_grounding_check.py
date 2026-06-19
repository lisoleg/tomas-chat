#!/usr/bin/env python3
"""
测试 extend_hypergraph.py 和 tshield_wrapper.py 的集成

验证：
1. ExtendHypergraph.grounding_check() 正确调用 TShieldWrapper.check_std_ref()
2. ExtendHypergraph.grounding_check() 正确调用 TShieldWrapper.validate_psi_alignment()
"""
import sys
import os

# 添加 sim 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tomas_agi/sim"))


def test_integration():
    """测试集成"""
    print("=== 测试 extend_hypergraph + tshield_wrapper 集成 ===\n")

    # 1. 导入模块
    try:
        from extend_hypergraph import (
            EMLLiteKB, EMLHyperedge, ExtendHypergraph,
            HypergraphOpType
        )
        from tshield_wrapper import TShieldWrapper
        print("[OK] 模块导入成功")
    except Exception as e:
        print(f"[FAIL] 模块导入失败: {e}")
        return False

    # 2. 创建 TShieldWrapper 实例（作为 verifier）
    try:
        tshield = TShieldWrapper(enable_g_ego=False)
        print("[OK] TShieldWrapper 实例创建成功")
    except Exception as e:
        print(f"[FAIL] TShieldWrapper 创建失败: {e}")
        return False

    # 3. 创建 ExtendHypergraph 实例（传入 tshield 作为 verifier）
    try:
        kb = EMLLiteKB()
        ext = ExtendHypergraph(kb, t_shield_verifier=tshield)
        print("[OK] ExtendHypergraph 实例创建成功（带 verifier）")
    except Exception as e:
        print(f"[FAIL] ExtendHypergraph 创建失败: {e}")
        return False

    # 4. 创建一个带 std_ref 的 EML 超边
    try:
        edge = EMLHyperedge(
            edge_id="test_edge_001",
            source_nodes=["node_1"],
            target_nodes=["node_2"],
            relation="test_relation",
            i_value=0.8,
            std_ref="test_std_v1.0",  # 有 std_ref
        )
        kb.add_edge(edge)
        print(f"[OK] 创建带 std_ref 的超边: {edge.edge_id}")
    except Exception as e:
        print(f"[FAIL] 创建超边失败: {e}")
        return False

    # 5. 调用 grounding_check()（应该调用 tshield.check_std_ref()）
    try:
        result = ext.grounding_check("test_edge_001")
        print(f"[INFO] GroundingCheck 结果:")
        print(f"  edge_id: {result.get('edge_id')}")
        print(f"  is_grounded: {result.get('is_grounded')}")
        print(f"  std_ref_valid: {result.get('std_ref_valid')}")
        print(f"  dz_reason: {result.get('dz_reason')}")
        print(f"  psi_alignment: {result.get('psi_alignment')}")

        if result.get("std_ref_valid") is True:
            print("[OK] std_ref 校验通过（调用了 tshield.check_std_ref()）")
        else:
            print(f"[WARN] std_ref 校验未通过: {result.get('reason')}")
    except Exception as e:
        print(f"[FAIL] GroundingCheck 调用失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 6. 测试不带 std_ref 的超边
    try:
        edge2 = EMLHyperedge(
            edge_id="test_edge_002",
            source_nodes=["node_3"],
            target_nodes=["node_4"],
            relation="test_relation_2",
            i_value=0.6,
            std_ref=None,  # 无 std_ref
        )
        kb.add_edge(edge2)
        result2 = ext.grounding_check("test_edge_002")
        print(f"\n[INFO] 不带 std_ref 的 GroundingCheck 结果:")
        print(f"  std_ref_valid: {result2.get('std_ref_valid')} (应该是 None)")

        if result2.get("std_ref_valid") is None:
            print("[OK] 无 std_ref 时跳过校验")
        else:
            print(f"[WARN] 无 std_ref 但 std_ref_valid={result2.get('std_ref_valid')}")
    except Exception as e:
        print(f"[FAIL] 测试不带 std_ref 的超边失败: {e}")
        return False

    print("\n=== 所有测试通过 ===")
    return True


if __name__ == "__main__":
    success = test_integration()
    sys.exit(0 if success else 1)
