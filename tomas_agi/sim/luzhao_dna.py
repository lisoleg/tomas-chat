# -*- coding: utf-8 -*-
"""
鲁兆DNA基因库 - 斐波那契数列、鲁加斯数、八卦数拓扑不变量
Lu Zhao DNA Gene Library — Fibonacci, Lucas, Bagua Topological Invariants

基于文章3和文章4：
- 鲁兆现象：流动性充足+相位连续条件下的拓扑不变量自然涌现
- 斐波那契数列、鲁加斯数、八卦数构成TOMAS拓扑不变量候选集
- 第一浪幅度/时间 = 鲁兆DNA基因，作为MDL搜索种子

Author: TOMAS Team (Kou / 寇豆码·工程师)
Version: v3.12
"""

from __future__ import annotations
import math
from typing import Any, Dict, List, Optional, Tuple

# 黄金比例 φ
_PHI = (1.0 + math.sqrt(5.0)) / 2.0


def fibonacci_numbers(n_terms: int = 20) -> List[int]:
    """斐波那契数列 F[0]=0, F[1]=1, F[n]=F[n-1]+F[n-2]"""
    if n_terms <= 0:
        return []
    if n_terms == 1:
        return [0]
    F = [0, 1]
    while len(F) < n_terms:
        F.append(F[-1] + F[-2])
    return F[:n_terms]


def lucas_numbers(n_terms: int = 20) -> List[int]:
    """鲁加斯数 L[0]=2, L[1]=1, L[n]=L[n-1]+L[n-2]

    恒等关系：L[n] = F[n-1] + F[n+1]
    """
    if n_terms <= 0:
        return []
    if n_terms == 1:
        return [2]
    L = [2, 1]
    while len(L) < n_terms:
        L.append(L[-1] + L[-2])
    return L[:n_terms]


def bagua_constants() -> List[int]:
    """鲁兆常用卦位数"""
    return [1, 3, 5, 8, 13, 21, 23, 29, 34, 55, 89, 144]


def get_chinese_market_invariants() -> List[int]:
    """合并斐波那契+鲁加斯+八卦的唯一有序集合"""
    fib = set(fibonacci_numbers(25))
    luc = set(lucas_numbers(25))
    bag = set(bagua_constants())
    return sorted(fib | luc | bag)


class LuZhaoDNA:
    """鲁兆DNA基因 — 市场波浪基因编码与检测

    封装第一浪的持续时间和振幅作为"基因种子"，
    后续波浪应满足基于斐波那契/鲁加斯/八卦数的倍数生成规则。
    """

    def __init__(self, first_wave_duration: int,
                 first_wave_amplitude: float,
                 tolerance: float = 0.15):
        if first_wave_duration <= 0:
            raise ValueError(f"first_wave_duration 必须 > 0，实际: {first_wave_duration}")
        if first_wave_amplitude == 0:
            raise ValueError("first_wave_amplitude 不能为零")
        self.first_wave_duration = first_wave_duration
        self.first_wave_amplitude = abs(first_wave_amplitude)
        self.tolerance = tolerance
        self.invariants = get_chinese_market_invariants()
        self._fib_cache = fibonacci_numbers(50)
        self._luc_cache = lucas_numbers(50)

    def dna_replication_check(self, frames: List[int]) -> Dict[int, Dict[str, Any]]:
        """检测后续浪是否满足"倍数生成/隔代自相似"

        Args:
            frames: 各浪的持续时间列表（不含第一浪）

        Returns:
            {frame_index: {matched, ratio, nearest_invariant, generation_type}}
        """
        result: Dict[int, Dict[str, Any]] = {}
        D0 = self.first_wave_duration
        for idx, frame_len in enumerate(frames):
            ratio = frame_len / D0 if D0 > 0 else float("inf")
            best_inv = None
            best_diff = float("inf")
            for inv in self.invariants:
                diff = abs(ratio - inv)
                if diff < best_diff:
                    best_diff = diff
                    best_inv = inv
            matched = best_diff <= self.tolerance

            gen_type = "exact_multiple" if matched else "non_matching"
            for i, f1 in enumerate(self._fib_cache[3:], 3):
                if i + 2 < len(self._fib_cache):
                    f3 = self._fib_cache[i + 2]
                    if f3 > 0 and abs(ratio - f3 / f1) <= self.tolerance * 0.5:
                        gen_type = "generational_similarity"
                        break

            result[idx] = {
                "matched": matched,
                "ratio": round(ratio, 4),
                "nearest_invariant": best_inv,
                "deviation": round(best_diff, 4),
                "generation_type": gen_type,
                "frame_duration": frame_len,
            }
        return result

    def fibonacci_time_window(self, wave_n: int) -> Tuple[int, int, List[int]]:
        """返回第 n 浪的斐波那契时间窗"""
        if wave_n < 1:
            wave_n = 1
        idx_needed = wave_n + 2
        while len(self._fib_cache) <= idx_needed:
            self._fib_cache = fibonacci_numbers(len(self._fib_cache) + 10)
        fib_n = self._fib_cache[wave_n]
        fib_n1 = self._fib_cache[wave_n + 1]
        if fib_n == 0:
            fib_n = 1
        start_bar = fib_n * self.first_wave_duration
        end_bar = fib_n1 * self.first_wave_duration
        candidates = [
            self._fib_cache[i] * self.first_wave_duration
            for i in range(wave_n, wave_n + 3)
            if i < len(self._fib_cache) and self._fib_cache[i] <= fib_n1
        ]
        return (start_bar, end_bar, candidates)

    def bagua_trigger(self, price_series: List[float]) -> List[Dict[str, Any]]:
        """检测八卦数触发点（局部极值点）"""
        triggers: List[Dict[str, Any]] = []
        bag_set = set(bagua_constants())
        n = len(price_series)
        for i in range(2, n - 2):
            idx_1based = i + 1
            if idx_1based not in bag_set:
                continue
            price = price_series[i]
            prev2 = price_series[i - 2]
            prev1 = price_series[i - 1]
            next1 = price_series[i + 1]
            next2 = price_series[i + 2]
            if price > prev1 and price > prev2 and price > next1 and price > next2:
                triggers.append({
                    "index_zero_based": i,
                    "index_one_based": idx_1based,
                    "price": price,
                    "bagua_number": idx_1based,
                    "extremum_type": "local_high",
                })
            elif price < prev1 and price < prev2 and price < next1 and price < next2:
                triggers.append({
                    "index_zero_based": i,
                    "index_one_based": idx_1based,
                    "price": price,
                    "bagua_number": idx_1based,
                    "extremum_type": "local_low",
                })
        return triggers

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "first_wave_duration": self.first_wave_duration,
            "first_wave_amplitude": self.first_wave_amplitude,
            "tolerance": self.tolerance,
            "invariants": self.invariants,
            "phi_ratio": round(_PHI, 6),
            "lucas_10": self._luc_cache[:10],
            "fibonacci_10": self._fib_cache[:10],
        }

    def __repr__(self) -> str:
        return (f"LuZhaoDNA(duration={self.first_wave_duration}, "
                f"amplitude={self.first_wave_amplitude:.4f}, "
                f"tolerance={self.tolerance})")


def _self_test():
    """模块自测 — luzhao_dna v3.12"""
    print("=" * 60)
    print("LuZhao DNA v3.12 Self-Test (TOMAS AGI)")
    print("=" * 60)

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

    # Test 01-06: fibonacci_numbers
    check("T01: fib(0) == []", fibonacci_numbers(0) == [])
    check("T02: fib(1) == [0]", fibonacci_numbers(1) == [0])
    check("T03: fib(2) == [0, 1]", fibonacci_numbers(2) == [0, 1])
    fib10 = fibonacci_numbers(10)
    check("T04: fib(10) 正确", fib10 == [0, 1, 1, 2, 3, 5, 8, 13, 21, 34])
    check("T05: F[7] == 13", fib10[7] == 13)
    check("T06: fib 全非负", all(f >= 0 for f in fibonacci_numbers(20)))

    # Test 07-13: lucas_numbers
    check("T07: luc(0) == []", lucas_numbers(0) == [])
    check("T08: luc(1) == [2]", lucas_numbers(1) == [2])
    check("T09: luc(2) == [2, 1]", lucas_numbers(2) == [2, 1])
    luc10 = lucas_numbers(10)
    check("T10: luc(10) 正确", luc10 == [2, 1, 3, 4, 7, 11, 18, 29, 47, 76])
    check("T11: L[5] == 11", luc10[5] == 11)
    check("T12: L[10] == 123", lucas_numbers(15)[10] == 123)
    ratio = luc10[-1] / luc10[-2] if luc10[-2] != 0 else 0
    check("T13: Lucas 尾部逼近 φ", abs(ratio - _PHI) < 0.1, f"ratio={ratio:.4f}")

    # Test 14-16: bagua_constants
    bag = bagua_constants()
    check("T14: 卦位数12项", len(bag) == 12)
    expected = [1, 3, 5, 8, 13, 21, 23, 29, 34, 55, 89, 144]
    check("T15: 卦位数匹配", bag == expected)
    check("T16: 卦位数全正整数", all(isinstance(x, int) and x > 0 for x in bag))

    # Test 17-20: get_chinese_market_invariants
    inv = get_chinese_market_invariants()
    check("T17: 不变量有序", inv == sorted(inv))
    check("T18: 不变量无重复", len(inv) == len(set(inv)))
    check("T19: 包含1和144", 1 in inv and 144 in inv)
    check("T20: 至少20个不变量", len(inv) >= 20, f"len={len(inv)}")

    # Test 21-30: LuZhaoDNA 类
    dna = LuZhaoDNA(12, 0.15)
    check("T21: duration 存储", dna.first_wave_duration == 12)
    check("T22: amplitude 取绝对值", LuZhaoDNA(10, -0.25).first_wave_amplitude == 0.25)

    try:
        LuZhaoDNA(0, 0.1)
        check("T23: duration=0 应抛异常", False)
    except ValueError:
        check("T23: duration=0 应抛异常", True)

    try:
        LuZhaoDNA(10, 0.0)
        check("T24: amplitude=0 应抛异常", False)
    except ValueError:
        check("T24: amplitude=0 应抛异常", True)

    dna3 = LuZhaoDNA(10, 0.2, tolerance=0.2)
    result = dna3.dna_replication_check([30, 50, 80])
    check("T25: 30=3倍 匹配", result[0]["matched"] is True)
    check("T26: 50=5倍 匹配", result[1]["matched"] is True)
    check("T27: 80=8倍 匹配", result[2]["matched"] is True)

    result2 = dna3.dna_replication_check([7, 22, 9])
    check("T28: 7/10 不匹配", result2[0]["matched"] is False)

    dna4 = LuZhaoDNA(12, 0.1)
    start, end, cands = dna4.fibonacci_time_window(3)
    check("T29: wave3 start=24", start == 24)
    check("T30: wave3 end=36", end == 36)

    # Test 31-35: bagua_trigger
    prices = [10.0, 10.5, 11.0, 10.8, 10.6, 10.3, 10.2,
               12.5, 10.4, 10.3, 10.1, 10.0, 9.8, 9.5]
    triggers = dna4.bagua_trigger(prices)
    check("T31: 检测到八卦触发点", len(triggers) >= 1)

    d = dna4.to_dict()
    check("T32: to_dict 含字段", "first_wave_duration" in d and "invariants" in d)

    check("T33: __repr__ 含类名", "LuZhaoDNA" in repr(dna4))

    dna_loose = LuZhaoDNA(20, 0.1, tolerance=0.5)
    result_loose = dna_loose.dna_replication_check([22])
    check("T34: 大容差匹配", result_loose[0]["matched"] is True)

    result_empty = dna4.dna_replication_check([])
    check("T35: 空帧列表", result_empty == {})

    print(f"\n{'=' * 60}")
    print(f"Self-Test Complete: {passed} passed, {failed} failed")
    print(f"{'=' * 60}")
    return passed, failed


if __name__ == "__main__":
    _self_test()
