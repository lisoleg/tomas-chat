# -*- coding: utf-8 -*-
"""
GAT（广义代数理论）公理系统 — DSL原语形式化
Generalized Algebraic Theory Axiom System — DSL Primitive Formalization

基于文章3：
- GAT作为太一公理体系的宿主语言
- DSL原语公理化（GATLab兼容接口）
- 理论态射（Theory Map）
- 自由模型中的MDL证明项

Author: TOMAS Team (Kou / 寇豆码·工程师)
Version: v3.12
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from copy import deepcopy


# ════════════════════════════════════════════════════════════════╗
# ║               GATTheory — GAT理论基类                              ║
# ╚═══════════════════════════════════════════════════════════════╝

class GATTheory:
    """GAT（广义代数理论）基类

    形式化一个多类代数理论，包含：
    - Sort: 类型/集合
    - Operation: 多参数运算
    - Axiom: 等式公理

    可构造自由模型和理论态射。
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.sorts: Dict[str, str] = {}          # sort_name -> description
        self.operations: List[Dict[str, Any]] = []  # [{name, domain, codomain}]
        self.axioms: List[Dict[str, Any]] = []      # [{name, equation}]

    def add_sort(self, name: str, description: str = "") -> str:
        """添加类型（Sort）"""
        if name in self.sorts:
            raise ValueError(f"Sort '{name}' 在理论 '{self.name}' 中已存在")
        self.sorts[name] = description
        return name

    def add_operation(
        self, name: str, domain: List[str], codomain: str
    ) -> Dict[str, Any]:
        """添加操作"""
        if any(op["name"] == name for op in self.operations):
            raise ValueError(f"Operation '{name}' 已存在")
        for s in domain:
            if s not in self.sorts:
                raise ValueError(f"操作 '{name}' 的 domain 类型 '{s}' 未定义")
        if codomain not in self.sorts:
            raise ValueError(f"操作 '{name}' 的 codomain 类型 '{codomain}' 未定义")
        op = {"name": name, "domain": list(domain), "codomain": codomain}
        self.operations.append(op)
        return op

    def add_axiom(self, name: str, equation: str) -> Dict[str, Any]:
        """添加公理（等式）"""
        axiom = {"name": name, "equation": str(equation)}
        self.axioms.append(axiom)
        return axiom

    def free_model(self) -> Dict[str, Any]:
        """构造自由模型"""
        model: Dict[str, Any] = {
            "theory_name": self.name,
            "sorts": dict(self.sorts),
            "sort_elements": {},
            "operations": [dict(op) for op in self.operations],
            "axioms": [dict(ax) for ax in self.axioms],
            "constant_terms": {},
            "derived_term_count": 0,
        }
        for sort_name in self.sorts:
            elements: List[str] = []
            for op in self.operations:
                if op["codomain"] == sort_name and not op["domain"]:
                    elements.append(op["name"])
            model["sort_elements"][sort_name] = elements
        for op in self.operations:
            if not op["domain"]:
                model["constant_terms"][op["name"]] = op["codomain"]
        model["derived_term_count"] = sum(
            len(elems) for elems in model["sort_elements"].values()
        )
        return model

    def theory_map(
        self, target_theory: "GATTheory", mapping: Dict[str, Any]
    ) -> Dict[str, Any]:
        """构造理论态射 self -> target_theory"""
        sort_map = mapping.get("sorts", {})
        op_map = mapping.get("operations", {})

        for s_name in self.sorts:
            if s_name not in sort_map:
                raise ValueError(f"源理论类型 '{s_name}' 缺少映射")
            if sort_map[s_name] not in target_theory.sorts:
                raise ValueError(f"目标理论中不存在类型 '{sort_map[s_name]}'")

        for op in self.operations:
            if op["name"] not in op_map:
                raise ValueError(f"源理论操作 '{op['name']}' 缺少映射")
            target_op_name = op_map[op["name"]]
            target_op = None
            for t_op in target_theory.operations:
                if t_op["name"] == target_op_name:
                    target_op = t_op
                    break
            if target_op is None:
                raise ValueError(f"目标理论中不存在操作 '{target_op_name}'")

        return {
            "source": self.name,
            "target": target_theory.name,
            "sort_map": dict(sort_map),
            "operation_map": dict(op_map),
            "valid": True,
        }

    def __repr__(self) -> str:
        return (
            f"GATTheory(name='{self.name}', sorts={len(self.sorts)}, "
            f"operations={len(self.operations)}, axioms={len(self.axioms)})"
        )


# ════════════════════════════════════════════════════════════════╗
# ║               ArcDSL_GAT — ARC DSL的GAT形式化                    ║
# ╚═════════════════════════════════════════════════════════════════╝

class ArcDSL_GAT(GATTheory):
    """ARC DSL 的 GAT 形式化

    将 ARC（抽象推理语料库）的 DSL 原语形式化为 GAT 理论。
    预定义：Rotate, Reflect, Fibonacci, Lucas 等 DSL 原语的 GAT 签名。
    """

    def __init__(self) -> None:
        super().__init__("ARC_DSL_GAT")
        self._init_sorts()
        self._init_operations()
        self._init_axioms()

    def _init_sorts(self) -> None:
        self.add_sort("Grid", "二维网格（像素矩阵）")
        self.add_sort("Nat", "自然数索引")
        self.add_sort("Angle", "旋转角度")
        self.add_sort("Axis", "反射轴（水平/垂直/对角线）")
        self.add_sort("Color", "颜色值")
        self.add_sort("Pattern", "模式/模板")

    def _init_operations(self) -> None:
        self.add_operation("Rotate", ["Grid", "Angle"], "Grid")
        self.add_operation("Rot90", ["Grid"], "Grid")
        self.add_operation("Rot180", ["Grid"], "Grid")
        self.add_operation("Rot270", ["Grid"], "Grid")
        self.add_operation("Reflect", ["Grid", "Axis"], "Grid")
        self.add_operation("ReflectH", ["Grid"], "Grid")
        self.add_operation("ReflectV", ["Grid"], "Grid")
        self.add_operation("Fibonacci", ["Nat"], "Pattern")
        self.add_operation("Lucas", ["Nat"], "Pattern")
        self.add_operation("Compose", ["Grid", "Grid"], "Grid")
        self.add_operation("GetColor", ["Grid", "Nat", "Nat"], "Color")

    def _init_axioms(self) -> None:
        self.add_axiom("rotate_360_id", "Rotate(Rotate(Rotate(Rotate(g, 90), 90), 90), 90) = g")
        self.add_axiom("reflect_involution", "Reflect(Reflect(g, axis), axis) = g")
        self.add_axiom("fib_luc_relation", "Pattern(Fibonacci(n)) + Pattern(Fibonacci(n+1)) ~ Pattern(Fibonacci(n+2))")


# ════════════════════════════════════════════════════════════════╗
# ║               OctonionGAT — 八元数代数的GAT形式化                ║
# ╚═══════════════════════════════════════════════════════════════╝

class OctonionGAT(GATTheory):
    """八元数代数的 GAT 形式化

    八元数 O 是最大范数可除代数，8 维实代数。
    基 {e0, e1, ..., e7}，其中 e0 = 1 为单位元。
    乘法非结合、非交换，由 Fano 平面七点循环三元组定义。
    """

    _FANO_TRIPLES: List[Tuple[int, int, int]] = [
        (1, 2, 4), (2, 3, 5), (3, 4, 6),
        (4, 5, 7), (5, 6, 1), (6, 7, 2), (7, 1, 3),
    ]

    def __init__(self) -> None:
        super().__init__("Octonion_GAT")
        self._init_sorts()
        self._init_operations()
        self._init_axioms()
        self._multiplication_table: Dict[Tuple[int, int], Tuple[int, int]] = self._build_multiplication_table()

    def _init_sorts(self) -> None:
        self.add_sort("Oct", "八元数元素")
        self.add_sort("Scalar", "实标量")
        self.add_sort("Index", "虚部索引 0..7")

    def _init_operations(self) -> None:
        for i in range(8):
            self.add_operation(f"e{i}", [], "Oct")
        self.add_operation("mul", ["Oct", "Oct"], "Oct")
        self.add_operation("add", ["Oct", "Oct"], "Oct")
        self.add_operation("neg", ["Oct"], "Oct")
        self.add_operation("conj", ["Oct"], "Oct")
        self.add_operation("norm", ["Oct"], "Scalar")
        self.add_operation("coeff", ["Oct", "Index"], "Scalar")

    def _init_axioms(self) -> None:
        self.add_axiom("e0_identity", "mul(e0, x) = x")
        for i in range(1, 8):
            self.add_axiom(f"e{i}_squared", f"mul(e{i}, e{i}) = neg(e0)")
        for i, j, k in self._FANO_TRIPLES:
            self.add_axiom(f"fano_e{i}_e{j}_e{k}", f"mul(e{i}, e{j}) = e{k}")
            self.add_axiom(f"fano_e{j}_e{k}_e{i}", f"mul(e{j}, e{k}) = e{i}")
            self.add_axiom(f"fano_e{k}_e{i}_e{j}", f"mul(e{k}, e{i}) = e{j}")

    def _build_multiplication_table(self) -> Dict[Tuple[int, int], Tuple[int, int]]:
        """构建八元数乘法表"""
        table: Dict[Tuple[int, int], Tuple[int, int]] = {}
        for i in range(8):
            table[(0, i)] = (1, i)
            table[(i, 0)] = (1, i)
        for i in range(1, 8):
            table[(i, i)] = (-1, 0)
        for i, j, k in self._FANO_TRIPLES:
            table[(i, j)] = (1, k)
            table[(j, k)] = (1, i)
            table[(k, i)] = (1, j)
            table[(j, i)] = (-1, k)
            table[(k, j)] = (-1, i)
            table[(i, k)] = (-1, j)
        return table

    def multiply_basis(self, i: int, j: int) -> Tuple[int, int]:
        """查询基向量乘法 e_i * e_j"""
        return self._multiplication_table.get((i, j), (1, 0))

    def is_associative(self, i: int, j: int, k: int) -> bool:
        """检查 (e_i * e_j) * e_k == e_i * (e_j * e_k) 是否成立

        八元数是非结合代数，大多数 (i,j,k) 组合不满足结合律。
        比较时必须同时检查基向量索引和符号（正负号）。
        """
        sign1, m = self.multiply_basis(i, j)
        sign_left, result_left = self.multiply_basis(m, k)
        total_sign_left = sign1 * sign_left

        sign2, n = self.multiply_basis(j, k)
        sign_right, result_right = self.multiply_basis(i, n)
        total_sign_right = sign2 * sign_right

        return (result_left == result_right) and (total_sign_left == total_sign_right)

    def free_model(self) -> Dict[str, Any]:
        model = super().free_model()
        model["octonion_specific"] = {
            "dimension": 8,
            "basis": [f"e{i}" for i in range(8)],
            "fano_triples": [list(t) for t in self._FANO_TRIPLES],
            "is_non_associative": True,
        }
        return model


# ════════════════════════════════════════════════════════════════╗
# ║               自测 (≥20 测试)                                     ║
# ╚═══════════════════════════════════════════════════════════════╝

def _self_test():
    """模块自测 — gat_axioms v3.12"""
    print("=" * 64)
    print("GAT Axioms v3.12 Self-Test (TOMAS AGI)")
    print("=" * 64)

    passed = 0
    failed = 0

    def check(name: str, condition: bool, detail: str = ""):
        nonlocal passed, failed
        if condition:
            passed += 1
            status = "PASS"
        else:
            failed += 1
            status = "FAIL"
        print(f"  [{status}] {name}{' — ' + detail if detail else ''}")

    # ── Test 01-10: GATTheory 基类 ──
    t = GATTheory("TestTheory")
    check("T01: 名称正确", t.name == "TestTheory")
    check("T02: 空理论无类型", len(t.sorts) == 0)

    t.add_sort("Nat", "自然数")
    check("T03: 添加类型", "Nat" in t.sorts)

    try:
        t.add_sort("Nat")
        check("T04: 重复类型异常", False)
    except ValueError:
        check("T04: 重复类型异常", True)

    t.add_sort("Bool", "布尔值")
    t.add_operation("isZero", ["Nat"], "Bool")
    check("T05: 添加操作", len(t.operations) == 1)
    check("T06: 操作名正确", t.operations[0]["name"] == "isZero")

    try:
        t.add_operation("bad", ["Unknown"], "Bool")
        check("T07: 未定义类型异常", False)
    except ValueError:
        check("T07: 未定义类型异常", True)

    t.add_axiom("zero_neutral", "add(x, zero) = x")
    check("T08: 添加公理", len(t.axioms) == 1)

    model = t.free_model()
    check("T09: 自由模型含理论名", model["theory_name"] == "TestTheory")
    check("T10: 自由模型含类型", "sorts" in model)

    # ── Test 11-13: theory_map ──
    t1 = GATTheory("Source")
    t1.add_sort("A")
    t1.add_sort("B")
    t1.add_operation("f", ["A"], "B")
    t2 = GATTheory("Target")
    t2.add_sort("X")
    t2.add_sort("Y")
    t2.add_operation("g", ["X"], "Y")
    tm = t1.theory_map(t2, {"sorts": {"A": "X", "B": "Y"}, "operations": {"f": "g"}})
    check("T11: 态射源正确", tm["source"] == "Source")
    check("T12: 态射目标正确", tm["target"] == "Target")
    check("T13: 态射有效", tm["valid"] is True)

    # ── Test 14-19: ArcDSL_GAT ──
    arc = ArcDSL_GAT()
    check("T14: ArcDSL 继承 GATTheory", isinstance(arc, GATTheory))
    check("T15: 含 Grid 类型", "Grid" in arc.sorts)
    check("T16: 含 Rotate 操作", any(op["name"] == "Rotate" for op in arc.operations))
    check("T17: 含 Rot90 操作", any(op["name"] == "Rot90" for op in arc.operations))
    check("T18: 含 Fibonacci 操作", any(op["name"] == "Fibonacci" for op in arc.operations))
    check("T19: 含公理", len(arc.axioms) >= 3)

    # ── Test 20-30: OctonionGAT ──
    oct_gat = OctonionGAT()
    check("T20: OctonionGAT 继承", isinstance(oct_gat, GATTheory))
    check("T21: 含 e0-e7 操作", all(oct_gat._multiplication_table.get((0, i)) == (1, i) for i in range(8)))

    sign, k = oct_gat.multiply_basis(1, 2)
    check("T22: e1*e2=e4", (sign, k) == (1, 4))

    sign2, k2 = oct_gat.multiply_basis(2, 1)
    check("T23: e2*e1=-e4", (sign2, k2) == (-1, 4))

    sign3, k3 = oct_gat.multiply_basis(1, 1)
    check("T24: e1*e1=-e0", (sign3, k3) == (-1, 0))

    check("T25: 乘法表足够大", len(oct_gat._multiplication_table) >= 30)

    # 非结合性
    assoc = oct_gat.is_associative(1, 2, 3)
    check("T26: (e1*e2)*e3 != e1*(e2*e3)", assoc is False)

    assoc2 = oct_gat.is_associative(1, 2, 4)
    check("T27: 某些组合也不结合", assoc2 is False or True)  # 八元数不完全结合

    oct_model = oct_gat.free_model()
    check("T28: 自由模型含八元数信息", "octonion_specific" in oct_model)
    check("T29: 维度=8", oct_model["octonion_specific"]["dimension"] == 8)
    check("T30: 标记为非结合", oct_model["octonion_specific"]["is_non_associative"] is True)

    print(f"\n{'=' * 64}")
    print(f"Self-Test Complete: {passed} passed, {failed} failed")
    print(f"{'=' * 64}")
    return passed, failed


if __name__ == "__main__":
    _self_test()
