"""
八元数（Octonion）Python 实现
基于 Fano 平面乘法表，用于 TOMAS-AGI 仿真器
"""

import numpy as np
from typing import List, Tuple


# Fano 平面直线（1-indexed）：{1,2,4}, {2,3,5}, {3,4,6}, {4,5,7}, {5,6,1}, {6,7,2}, {7,1,3}
# 对应乘法规则：e_i * e_j = e_k（符号由顺序决定）
FANO_LINES = [
    (1, 2, 4),
    (2, 3, 5),
    (3, 4, 6),
    (4, 5, 7),
    (5, 6, 1),
    (6, 7, 2),
    (7, 1, 3),
]

# 预计算八元数乘法表：mult_table[i][j] = (sign, k)
# 表示 e_i * e_j = sign * e_k（i,j,k 范围 0-7，0 是实部 e0）
_mult_table = [[(0, 0) for _ in range(8)] for _ in range(8)]


def _build_mult_table():
    """构建 Fano 平面乘法查找表"""
    table = [[(0, 0) for _ in range(8)] for _ in range(8)]
    
    # e0 是单位元：e0 * e_j = e_j, e_i * e0 = e_i
    for i in range(8):
        table[0][i] = (1, i)
        table[i][0] = (1, i)
    
    # 设置 e_i * e_i = -e0（虚基的平方是 -1）
    for i in range(1, 8):
        table[i][i] = (-1, 0)
    
    # 根据 Fano 直线填充乘法表
    for (a, b, c) in FANO_LINES:
        # e_a * e_b = e_c
        table[a][b] = (1, c)
        # e_b * e_a = -e_c
        table[b][a] = (-1, c)
        # e_b * e_c = e_a
        table[b][c] = (1, a)
        # e_c * e_b = -e_a
        table[c][b] = (-1, a)
        # e_c * e_a = e_b
        table[c][a] = (1, b)
        # e_a * e_c = -e_b
        table[a][c] = (-1, b)
    
    return table


_mult_table = _build_mult_table()


def fan_multiply(i: int, j: int) -> Tuple[int, int]:
    """
    计算 Fano 平面乘法：e_i * e_j = sign * e_k
    返回 (sign, k)，其中 sign = +1 或 -1，k 是结果基的索引（0-7）
    """
    if i < 0 or i > 7 or j < 0 or j > 7:
        raise ValueError(f"索引超出范围 [0,7]: i={i}, j={j}")
    return _mult_table[i][j]


class Octonion:
    """
    八元数（Octonion）—— 8维非结合代数
    基：e0（实部）, e1, e2, e3, e4, e5, e6, e7（虚部）
    满足 Fano 平面乘法规则
    """
    
    def __init__(self, e0: float = 0.0, e1: float = 0.0, e2: float = 0.0,
                 e3: float = 0.0, e4: float = 0.0, e5: float = 0.0,
                 e6: float = 0.0, e7: float = 0.0):
        self.e = np.array([e0, e1, e2, e3, e4, e5, e6, e7], dtype=np.float64)
    
    @property
    def real(self) -> float:
        """实部（e0 分量）"""
        return self.e[0]
    
    @property
    def imag(self) -> np.ndarray:
        """虚部（e1-e7 分量）"""
        return self.e[1:]
    
    def __mul__(self, other: 'Octonion') -> 'Octonion':
        """
        八元数乘法（非结合）
        使用 Fano 平面乘法表计算
        """
        if not isinstance(other, Octonion):
            # 标量乘法
            return Octonion(*(self.e * other))
        
        c = np.zeros(8, dtype=np.float64)
        
        for i in range(8):
            if abs(self.e[i]) < 1e-15:
                continue
            for j in range(8):
                if abs(other.e[j]) < 1e-15:
                    continue
                
                sign, k = _mult_table[i][j]
                c[k] += sign * self.e[i] * other.e[j]
        
        return Octonion(*c)
    
    def __add__(self, other: 'Octonion') -> 'Octonion':
        """八元数加法"""
        return Octonion(*(self.e + other.e))
    
    def __sub__(self, other: 'Octonion') -> 'Octonion':
        """八元数减法"""
        return Octonion(*(self.e - other.e))
    
    def __neg__(self) -> 'Octonion':
        """取负"""
        return Octonion(*(-self.e))
    
    def __eq__(self, other: object) -> bool:
        """相等比较（考虑浮点误差）"""
        if not isinstance(other, Octonion):
            return False
        return np.allclose(self.e, other.e, atol=1e-10)
    
    def conjugate(self) -> 'Octonion':
        """共轭：a* = a0 - a1*e1 - ... - a7*e7"""
        return Octonion(
            self.e[0],
            -self.e[1], -self.e[2], -self.e[3],
            -self.e[4], -self.e[5], -self.e[6], -self.e[7]
        )
    
    def norm(self) -> float:
        """范数：||a||^2 = a * a_conjugate（实部）"""
        conj = self.conjugate()
        product = self * conj
        return product.real
    
    def abs(self) -> float:
        """绝对值（范数的平方根）"""
        return np.sqrt(self.norm())
    
    def is_unit(self, tol: float = 1e-10) -> bool:
        """是否是单位八元数（范数 ≈ 1）"""
        return abs(self.norm() - 1.0) < tol
    
    def normalize(self) -> 'Octonion':
        """归一化为单位八元数"""
        n = self.abs()
        if n < 1e-15:
            raise ValueError("零八元数无法归一化")
        return Octonion(*(self.e / n))
    
    def __str__(self) -> str:
        parts = [f"{self.e[0]:+.6f}"]
        for i in range(1, 8):
            parts.append(f"{self.e[i]:+.6f}e{i}")
        return " ".join(parts)
    
    def __repr__(self) -> str:
        return f"Octonion({', '.join(f'{x:.6f}' for x in self.e)})"
    
    @classmethod
    def zero(cls) -> 'Octonion':
        """零八元数"""
        return cls()
    
    @classmethod
    def one(cls) -> 'Octonion':
        """单位元 e0"""
        return cls(e0=1.0)
    
    @classmethod
    def basis(cls, i: int) -> 'Octonion':
        """
        第 i 个基元素（i=0 是 e0，i=1-7 是 e1-e7）
        """
        if i < 0 or i > 7:
            raise ValueError(f"基索引必须在 [0,7] 范围内，得到 {i}")
        e = np.zeros(8, dtype=np.float64)
        e[i] = 1.0
        return cls(*e)
    
    @classmethod
    def random(cls, seed: int = None) -> 'Octonion':
        """生成随机八元数"""
        if seed is not None:
            np.random.seed(seed)
        return cls(*np.random.randn(8))


def test_fano_table():
    """测试 Fano 乘法表的正确性"""
    errors = []
    
    # 测试 e0 是单位元
    for i in range(8):
        ei = Octonion.basis(i)
        e0 = Octonion.one()
        
        prod1 = e0 * ei
        prod2 = ei * e0
        
        if prod1 != ei:
            errors.append(f"e0 * e{i} 失败: 得到 {prod1}，期望 {ei}")
        if prod2 != ei:
            errors.append(f"e{i} * e0 失败: 得到 {prod2}，期望 {ei}")
    
    # 测试 e_i * e_i = -e0
    for i in range(1, 8):
        ei = Octonion.basis(i)
        prod = ei * ei
        expected = Octonion(e0=-1.0)
        if prod != expected:
            errors.append(f"e{i} * e{i} 失败: 得到 {prod}，期望 {expected}")
    
    # 测试 Fano 直线 {1,2,4}：e1*e2=e4, e2*e1=-e4
    e1 = Octonion.basis(1)
    e2 = Octonion.basis(2)
    e4 = Octonion.basis(4)
    
    if e1 * e2 != e4:
        errors.append(f"e1*e2 失败: 得到 {e1 * e2}，期望 {e4}")
    if e2 * e1 != -e4:
        errors.append(f"e2*e1 失败: 得到 {e2 * e1}，期望 {-e4}")
    
    # 测试 {2,3,5}：e2*e3=e5
    e3 = Octonion.basis(3)
    e5 = Octonion.basis(5)
    if e2 * e3 != e5:
        errors.append(f"e2*e3 失败: 得到 {e2 * e3}，期望 {e5}")
    
    # 测试 {7,1,3}：e7*e1=e3
    e7 = Octonion.basis(7)
    e3 = Octonion.basis(3)
    if e7 * e1 != e3:
        errors.append(f"e7*e1 失败: 得到 {e7 * e1}，期望 {e3}")
    
    return errors


def test_non_associativity():
    """
    测试八元数的非结合性：(a*b)*c != a*(b*c)（一般情况）
    """
    np.random.seed(42)
    a = Octonion.random()
    b = Octonion.random()
    c = Octonion.random()
    
    left = (a * b) * c
    right = a * (b * c)
    
    # 一般情况下不相等（非结合）
    is_equal = np.allclose(left.e, right.e, atol=1e-10)
    
    return {
        'a': a,
        'b': b,
        'c': c,
        '(a*b)*c': left,
        'a*(b*c)': right,
        'is_associative_for_this_triple': is_equal,
        'note': '八元数一般是非结合的，但某些三元组满足结合性'
    }


def test_norm_product():
    """
    测试范数乘积：N(a*b) = N(a) * N(b)
    八元数是可除代数，范数满足此性质
    """
    np.random.seed(123)
    a = Octonion.random()
    b = Octonion.random()
    
    # 归一化以便测试
    a = a.normalize()
    b = b.normalize()
    
    prod = a * b
    
    norm_a = a.norm()
    norm_b = b.norm()
    norm_prod = prod.norm()
    
    expected = norm_a * norm_b
    error = abs(norm_prod - expected)
    
    return {
        'N(a)': norm_a,
        'N(b)': norm_b,
        'N(a*b)': norm_prod,
        'N(a)*N(b)': expected,
        'error': error,
        'pass': error < 1e-10
    }


if __name__ == '__main__':
    print("=" * 60)
    print("八元数（Octonion）Python 实现 —— 测试套件")
    print("=" * 60)
    
    # 测试1：Fano 乘法表
    print("\n[测试1] Fano 平面乘法表...")
    errors = test_fano_table()
    if errors:
        print(f"  [FAIL] 失败：{len(errors)} 个错误")
        for err in errors:
            print(f"    - {err}")
    else:
        print("  [PASS] 通过：Fano 乘法表正确")
    
    # 测试2：非结合性
    print("\n[测试2] 非结合性检查...")
    result = test_non_associativity()
    print(f"  (a*b)*c = {result['(a*b)*c']}")
    print(f"  a*(b*c) = {result['a*(b*c)']}")
    print(f"  是否相等：{result['is_associative_for_this_triple']}")
    
    # 测试3：范数乘积
    print("\n[测试3] 范数乘积 N(a*b) = N(a)*N(b)...")
    norm_result = test_norm_product()
    print(f"  N(a) = {norm_result['N(a)']:.10f}")
    print(f"  N(b) = {norm_result['N(b)']:.10f}")
    print(f"  N(a*b) = {norm_result['N(a*b)']:.10f}")
    print(f"  N(a)*N(b) = {norm_result['N(a)*N(b)']:.10f}")
    print(f"  误差 = {norm_result['error']:.2e}")
    if norm_result['pass']:
        print("  [PASS] 通过")
    else:
        print("  [FAIL] 失败")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
