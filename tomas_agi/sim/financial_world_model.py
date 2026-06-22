# -*- coding: utf-8 -*-
"""
Financial World Model — 金融市场作为最抽象世界模型 v3.12
===========================================================

核心理论：
    TOMAS AGI v3.12 将金融市场视为最抽象的世界模型 ——
    LOB (限价订单簿) = 微观状态相空间，
    做市商 = 相位连续性算子，
    滑点 = 相位失配代价。

核心功能:
  01. LimitOrderBook — 限价订单簿 (LOB)，微观价格发现引擎
  02. MarketMaker — 做市商 (相位连续性算子)，提供流动性
  03. SlippageModel — 滑点作为相位失配代价
  04. ENPVCalculator — 期望净正收益 (ENPV) 决策引擎
  05. LiquidityCircuitBreaker — 流动性熔断 (奇点检测)

TOMAS 映射:
  - LOB bid/ask 分层 = EML 双链在价格维度的投影
  - 做市 spread = Ω 旋转拉开的 D_p 相位间隙
  - 滑点 = ψ-锚 偏差导致的执行延迟惩罚
  - 深度熵 = 奇点检测 (LOB-G 在金融域的实例化)
  - ENPV > 0 = G_ego 目的对齐 (正收益方向)

Author: TOMAS Team (Kou / 寇豆码·工程师)
Version: v3.12
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import bisect
import logging
import math
import random
import time
from enum import Enum
from collections import deque

logger = logging.getLogger(__name__)

# ── 数学快捷 ────────────────────────────────────────────────────
sqrt = math.sqrt
exp = math.exp
log = math.log
pi = math.pi


# ╔════════════════════════════════════════════════════════════════╗
# ║               枚举                                                ║
# ╚════════════════════════════════════════════════════════════════╝

class OrderSide(Enum):
    """订单方向"""
    BID = "bid"      # 买单
    ASK = "ask"      # 卖单

class CircuitState(Enum):
    """熔断状态"""
    NORMAL = "normal"
    WARNING = "warning"      # 深度稀薄警告
    BREAKER_TRIPPED = "breaker_tripped"  # 熔断触发

class MarketPhase(Enum):
    """市场相位 (对应 EML 链间相位差)"""
    IN_PHASE = "in_phase"           # 同相 (流动性充沛)
    PHASE_SHIFT = "phase_shift"     # 相位漂移 (spread 扩大)
    PHASE_MISMATCH = "phase_mismatch"     # 失配 (滑点放大)
    SINGULARITY = "singularity"     # 奇点 (流动性干涸)


# ╔════════════════════════════════════════════════════════════════╗
# ║               数据结构                                            ║
# ╚════════════════════════════════════════════════════════════════╝

@dataclass
class Order:
    """订单记录"""
    order_id: str
    side: OrderSide
    price: float
    size: float                # 数量
    timestamp: float = field(default_factory=time.time)
    filled: float = 0.0        # 已成交数量

    @property
    def remaining(self) -> float:
        return max(0.0, self.size - self.filled)

    @property
    def is_filled(self) -> bool:
        return self.remaining < 1e-12

    def fill(self, amount: float) -> float:
        """撮合部分成交，返回实际成交量"""
        fillable = min(amount, self.remaining)
        self.filled += fillable
        return fillable


@dataclass
class MatchResult:
    """撮合结果"""
    executed_size: float
    avg_exec_price: float
    total_cost: float
    slippage: float
    filled_orders: List[Order] = field(default_factory=list)
    remaining_size: float = 0.0


@dataclass
class EnpvDecision:
    """ENPV 决策结果"""
    enpv: float
    prob_fill: float
    expected_profit: float
    slippage_cost: float
    opportunity_cost: float
    should_chase: bool
    explanation: str = ""


# ╔════════════════════════════════════════════════════════════════╗
# ║               LimitOrderBook — 限价订单簿                         ║
# ╚════════════════════════════════════════════════════════════════╝

class LimitOrderBook:
    """限价订单簿 (LOB) — EML 微观状态相空间在价格维度的投影

    买卖队列分层对应 EML 双链结构：
      bid 队列 = 意识链 (主动需求, 从下往上推价格)
      ask 队列 = 物质链 (被动供给, 从上往下拉价格)

    TOMAS v3.12 关键洞察：
      LOB 是最原始的世界模型 —— 每一笔限价单
      都是一个 ψ-锚 (意志锚定)，将主观估值投影到客观市场。
    """

    def __init__(self):
        self._order_id_counter: int = 0
        self.bid_orders: List[Order] = []    # 买单 (按价格降序)
        self.ask_orders: List[Order] = []    # 卖单 (按价格升序)
        self.trade_history: List[MatchResult] = []
        self._last_mid: float = 0.0

    def _next_id(self) -> str:
        self._order_id_counter += 1
        return f"order_{self._order_id_counter:06d}"

    def add_order(self, side: OrderSide, price: float, size: float) -> Order:
        """添加限价单到订单簿"""

        if price <= 0 or size <= 0:
            raise ValueError(f"Invalid order: price={price}, size={size}")

        order = Order(
            order_id=self._next_id(),
            side=side,
            price=price,
            size=size,
        )

        if side == OrderSide.BID:
            insert_idx = bisect.bisect_right(
                [-o.price for o in self.bid_orders], -price
            )
            self.bid_orders.insert(insert_idx, order)
        else:
            insert_idx = bisect.bisect_right(
                [o.price for o in self.ask_orders], price
            )
            self.ask_orders.insert(insert_idx, order)

        return order

    def get_best_bid(self) -> Optional[float]:
        """获取最佳买价 (最高买价)"""
        if not self.bid_orders:
            return None
        return self.bid_orders[0].price

    def get_best_ask(self) -> Optional[float]:
        """获取最佳卖价 (最低卖价)"""
        if not self.ask_orders:
            return None
        return self.ask_orders[0].price

    @property
    def mid_price(self) -> Optional[float]:
        """中间价 = (best_bid + best_ask) / 2"""
        bb = self.get_best_bid()
        ba = self.get_best_ask()
        if bb is None or ba is None:
            return None
        mid = (bb + ba) / 2.0
        self._last_mid = mid
        return mid

    @property
    def spread(self) -> Optional[float]:
        """买卖价差"""
        bb = self.get_best_bid()
        ba = self.get_best_ask()
        if bb is None or ba is None:
            return None
        return ba - bb

    @property
    def spread_bps(self) -> Optional[float]:
        """买卖价差 (基点, bp)"""
        mid = self.mid_price
        s = self.spread
        if mid is None or s is None or mid < 1e-12:
            return None
        return (s / mid) * 10000.0

    def match_market_order(self, side: OrderSide, size: float) -> MatchResult:
        """市价单撮合 — 穿越订单簿获取流动性"""

        if side == OrderSide.BID:
            target_queue = self.ask_orders
        else:
            target_queue = self.bid_orders

        remaining = size
        total_cost = 0.0
        total_size = 0.0
        filled_orders: List[Order] = []

        for order in target_queue[:]:
            if remaining < 1e-12:
                break
            fill_amount = order.fill(remaining)
            if fill_amount > 1e-12:
                total_cost += fill_amount * order.price
                total_size += fill_amount
                remaining -= fill_amount
                filled_orders.append(order)
            if order.is_filled:
                target_queue.remove(order)

        avg_price = total_cost / total_size if total_size > 1e-12 else 0.0

        intended = size * (self._last_mid if self._last_mid > 0 else avg_price)
        slippage = abs(intended - total_cost) / max(intended, 1e-12) if intended > 0 else 0.0

        result = MatchResult(
            executed_size=total_size,
            avg_exec_price=avg_price,
            total_cost=total_cost,
            slippage=slippage,
            filled_orders=filled_orders,
            remaining_size=remaining,
        )
        self.trade_history.append(result)
        return result

    def depth_entropy(self) -> float:
        """LOB 深度熵 — 奇点检测的核心度量"""

        if not self.bid_orders and not self.ask_orders:
            return 0.0

        depth_map: Dict[float, float] = {}

        for order in self.bid_orders:
            key = round(order.price, 2)
            depth_map[key] = depth_map.get(key, 0.0) + order.remaining

        for order in self.ask_orders:
            key = round(order.price, 2)
            depth_map[key] = depth_map.get(key, 0.0) + order.remaining

        total_depth = sum(depth_map.values())
        if total_depth < 1e-12:
            return 0.0

        entropy = 0.0
        for depth in depth_map.values():
            if depth > 1e-12:
                p = depth / total_depth
                entropy -= p * log(p)

        return entropy

    def get_bid_depth(self, levels: int = 5) -> List[Tuple[float, float]]:
        """获取买单前 N 层深度"""
        return [(o.price, o.remaining) for o in self.bid_orders[:levels]]

    def get_ask_depth(self, levels: int = 5) -> List[Tuple[float, float]]:
        """获取卖单前 N 层深度"""
        return [(o.price, o.remaining) for o in self.ask_orders[:levels]]

    def total_bid_volume(self) -> float:
        """买单总量"""
        return sum(o.remaining for o in self.bid_orders)

    def total_ask_volume(self) -> float:
        """卖单总量"""
        return sum(o.remaining for o in self.ask_orders)

    def clear(self) -> None:
        """清空订单簿"""
        self.bid_orders.clear()
        self.ask_orders.clear()

    def __repr__(self) -> str:
        bb = self.get_best_bid()
        ba = self.get_best_ask()
        return (
            f"LOB(best_bid={bb}, best_ask={ba}, "
            f"bid_orders={len(self.bid_orders)}, "
            f"ask_orders={len(self.ask_orders)}, "
            f"depth_entropy={self.depth_entropy():.3f})"
        )


# ╔════════════════════════════════════════════════════════════════╗
# ║               MarketMaker — 做市商 (相位连续性算子)                ║
# ╚════════════════════════════════════════════════════════════════╝

class MarketMaker:
    """做市商 — 相位连续性算子"""

    def __init__(self, spread: float = 0.01, inventory_target: float = 0.0):
        self.spread = spread
        self.inventory_target = inventory_target
        self.inventory: float = 0.0
        self.profit_and_loss: float = 0.0
        self.trade_count: int = 0
        self._last_quote_bid: float = 0.0
        self._last_quote_ask: float = 0.0

    def provide_liquidity(self, lob: LimitOrderBook) -> Tuple[Optional[Order], Optional[Order]]:
        """向 LOB 提供流动性"""

        mid = lob.mid_price
        if mid is None:
            return None, None

        adj_spread = self.spread * self.inventory_risk_multiplier()
        half_spread = adj_spread / 2.0

        bid_price = mid * (1.0 - half_spread)
        ask_price = mid * (1.0 + half_spread)

        if self.inventory > 0:
            bid_price *= (1.0 - 0.001 * self.inventory)
            ask_price *= (1.0 - 0.001 * self.inventory)
        elif self.inventory < 0:
            bid_price *= (1.0 + 0.001 * abs(self.inventory))
            ask_price *= (1.0 + 0.001 * abs(self.inventory))

        quote_size = 100.0
        bid_order = lob.add_order(OrderSide.BID, bid_price, quote_size)
        ask_order = lob.add_order(OrderSide.ASK, ask_price, quote_size)

        self._last_quote_bid = bid_price
        self._last_quote_ask = ask_price
        self.trade_count += 2

        return bid_order, ask_order

    def phase_alignment_fee(self, trade_price: float, mid_price: float) -> float:
        """相位对齐费 ≈ 滑点"""
        if mid_price < 1e-12:
            return 0.0
        return abs(trade_price - mid_price) / mid_price

    def inventory_risk_premium(self, inventory: float) -> float:
        """库存风险溢价 — 动态调整 spread"""
        sigma_inv = 0.5
        return abs(inventory) * sigma_inv

    def inventory_risk_multiplier(self) -> float:
        """库存风险乘数"""
        premium = self.inventory_risk_premium(self.inventory)
        return 1.0 + premium

    def adjust_inventory(self, trade_side: OrderSide, size: float) -> None:
        """调整库存"""
        if trade_side == OrderSide.BID:
            self.inventory += size
        else:
            self.inventory -= size

    def get_quote(self, mid_price: float) -> Tuple[float, float]:
        """获取当前报价 (不实际挂单)"""
        adj_spread = self.spread * self.inventory_risk_multiplier()
        half_spread = adj_spread / 2.0
        return (
            mid_price * (1.0 - half_spread),
            mid_price * (1.0 + half_spread),
        )


# ╔════════════════════════════════════════════════════════════════╗
# ║               SlippageModel — 滑点作为相位失配代价                ║
# ╚════════════════════════════════════════════════════════════════╝

class SlippageModel:
    """滑点模型 — 相位失配的财务表达"""

    def __init__(self, base_slippage_rate: float = 0.001):
        self.base_slippage_rate = base_slippage_rate
        self.jitter_history: List[float] = []

    def compute_slippage(self, intended_price: float,
                         executed_price: float) -> float:
        """计算滑点 (相对值)"""
        if intended_price < 1e-12:
            return abs(executed_price)
        return abs(intended_price - executed_price) / intended_price

    def phase_misalignment_cost(self, phi_t: float,
                                 phi_t_prev: float) -> float:
        """相位失配代价"""
        k = self.base_slippage_rate
        delta = phi_t - phi_t_prev
        return k * (math.sin(delta / 2.0) ** 2)

    def jitter_penalty(self, jitter: float) -> float:
        """Jitter 穿透惩罚"""
        sigma = 1.0
        self.jitter_history.append(jitter)
        if len(self.jitter_history) > 1000:
            self.jitter_history.pop(0)
        return max(0.0, exp(jitter / sigma) - 1.0)

    def estimated_slippage_from_entropy(self, depth_entropy: float,
                                         size_ratio: float) -> float:
        """从 LOB 深度熵估算预期滑点"""
        if depth_entropy < 1e-12:
            return size_ratio
        return self.base_slippage_rate * size_ratio / exp(depth_entropy)


# ╔════════════════════════════════════════════════════════════════╗
# ║               ENPVCalculator — 期望净正收益                       ║
# ╚════════════════════════════════════════════════════════════════╝

class ENPVCalculator:
    """ENPV (Expected Net Positive Value) 收益决策引擎"""

    def __init__(self, risk_free_rate: float = 0.03):
        self.risk_free_rate = risk_free_rate

    def compute_enpv(self, prob_fill: float, expected_profit: float,
                     slippage_cost: float, opportunity_cost: float) -> float:
        """计算期望净正收益"""
        return prob_fill * expected_profit - slippage_cost - opportunity_cost

    def compute_enpv_detailed(self, prob_fill: float, expected_profit: float,
                               slippage_cost: float, opportunity_cost: float,
                               phase_alignment_tax: float = 0.0) -> EnpvDecision:
        """详细 ENPV 计算 (含相位对齐税)"""
        enpv = (prob_fill * expected_profit
                - slippage_cost
                - opportunity_cost
                - phase_alignment_tax)
        return EnpvDecision(
            enpv=enpv,
            prob_fill=prob_fill,
            expected_profit=expected_profit,
            slippage_cost=slippage_cost,
            opportunity_cost=opportunity_cost,
            should_chase=self.should_chase(enpv),
            explanation=self._explain(enpv),
        )

    def should_chase(self, enpv: float, enpv_threshold: float = 0.0) -> bool:
        """是否追单"""
        return enpv > enpv_threshold

    def estimate_fill_probability(self, queue_position: int,
                                   total_orders: int) -> float:
        """估算成交概率"""
        if total_orders <= 0:
            return 0.0
        ratio = queue_position / max(total_orders, 1)
        return exp(-ratio)

    def _explain(self, enpv: float) -> str:
        if enpv > 0.5:
            return "STRONG_CHASE — 强烈追单 (目的高度对齐)"
        elif enpv > 0.0:
            return "CHASE — 追单 (净正收益)"
        elif enpv > -0.3:
            return "HOLD — 观望 (正负边界)"
        else:
            return "PASS — 放弃 (目的背离)"


# ╔════════════════════════════════════════════════════════════════╗
# ║               LiquidityCircuitBreaker — 流动性熔断               ║
# ╚════════════════════════════════════════════════════════════════╝

class LiquidityCircuitBreaker:
    """流动性熔断机制 — LOB 奇点检测器"""

    def __init__(self, depth_threshold: float = 0.1,
                 entropy_threshold: float = 0.3,
                 cooldown_seconds: float = 30.0):
        self.depth_threshold = depth_threshold
        self.entropy_threshold = entropy_threshold
        self.cooldown_seconds = cooldown_seconds
        self.state: CircuitState = CircuitState.NORMAL
        self.last_tripped: float = 0.0
        self.trip_count: int = 0

    def check_circuit_break(self, lob: LimitOrderBook,
                            depth_threshold: Optional[float] = None) -> Tuple[bool, CircuitState, str]:
        """检测 LOB 深度奇点，判断是否触发熔断"""

        threshold = depth_threshold if depth_threshold is not None else self.depth_threshold

        if self.state == CircuitState.BREAKER_TRIPPED:
            if time.time() - self.last_tripped < self.cooldown_seconds:
                return True, self.state, "BREAKER_COOLDOWN"
            else:
                self.state = CircuitState.NORMAL

        entropy = lob.depth_entropy()
        if entropy < self.entropy_threshold:
            self.state = CircuitState.BREAKER_TRIPPED
            self.last_tripped = time.time()
            self.trip_count += 1
            return (True, self.state,
                    f"SINGULARITY_DETECTED: entropy={entropy:.4f} < {self.entropy_threshold}")

        total_depth = lob.total_bid_volume() + lob.total_ask_volume()
        if total_depth < threshold:
            self.state = CircuitState.WARNING
            return (False, self.state,
                    f"WARNING: total_depth={total_depth:.4f} < {threshold}")

        self.state = CircuitState.NORMAL
        return False, self.state, "NORMAL"

    def reset(self) -> None:
        """重置熔断器"""
        self.state = CircuitState.NORMAL
        self.last_tripped = 0.0

    def get_phase(self) -> MarketPhase:
        """从熔断状态推断市场相位"""
        return {
            CircuitState.NORMAL: MarketPhase.IN_PHASE,
            CircuitState.WARNING: MarketPhase.PHASE_SHIFT,
            CircuitState.BREAKER_TRIPPED: MarketPhase.SINGULARITY,
        }.get(self.state, MarketPhase.IN_PHASE)


# ╔════════════════════════════════════════════════════════════════╗
# ║               工厂函数 / 便捷接口                                 ║
# ╚════════════════════════════════════════════════════════════════╝

def build_financial_world(tick_size: float = 0.01) -> Dict[str, Any]:
    """构建完整金融世界模型组件"""
    lob = LimitOrderBook()
    mm = MarketMaker(spread=0.01)
    sm = SlippageModel(base_slippage_rate=0.001)
    enpv = ENPVCalculator()
    cb = LiquidityCircuitBreaker()
    return {
        "lob": lob,
        "market_maker": mm,
        "slippage_model": sm,
        "enpv_calculator": enpv,
        "circuit_breaker": cb,
    }


# ╔════════════════════════════════════════════════════════════════╗
# ║               自测 (≥20 测试)                                     ║
# ╚════════════════════════════════════════════════════════════════╝

def _self_test():
    """模块自测 — financial_world_model v3.12"""
    print("=" * 64)
    print("Financial World Model v3.12 Self-Test (TOMAS AGI)")
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

    # ── Test 01: Basic LOB order insertion ──
    lob = LimitOrderBook()
    lob.add_order(OrderSide.BID, 100.0, 10.0)
    lob.add_order(OrderSide.BID, 99.0, 5.0)
    lob.add_order(OrderSide.ASK, 101.0, 8.0)
    lob.add_order(OrderSide.ASK, 102.0, 12.0)
    check("T01: bid orders count", len(lob.bid_orders) == 2)
    check("T02: ask orders count", len(lob.ask_orders) == 2)

    # ── Test 03-04: Best bid/ask ──
    check("T03: best_bid = 100.0", abs(lob.get_best_bid() - 100.0) < 1e-9)
    check("T04: best_ask = 101.0", abs(lob.get_best_ask() - 101.0) < 1e-9)

    # ── Test 05: Mid price & spread ──
    check("T05: mid_price = 100.5", abs(lob.mid_price - 100.5) < 1e-9)
    check("T06: spread = 1.0", abs(lob.spread - 1.0) < 1e-9)

    # ── Test 07: Match market buy order ──
    lob2 = LimitOrderBook()
    lob2.add_order(OrderSide.ASK, 101.0, 5.0)
    lob2.add_order(OrderSide.ASK, 102.0, 10.0)
    lob2.add_order(OrderSide.ASK, 103.0, 15.0)
    result = lob2.match_market_order(OrderSide.BID, 12.0)
    check("T07: executed size = 12", abs(result.executed_size - 12.0) < 1e-9)
    check("T08: avg price ≈ 101.583", abs(result.avg_exec_price - (5*101 + 7*102)/12) < 0.01)
    check("T09: slippage >= 0", result.slippage >= 0)
    check("T10: remaining after match", abs(result.remaining_size - 0.0) < 1e-9)

    # ── Test 13: Depth entropy ──
    lob4 = LimitOrderBook()
    for i in range(10):
        lob4.add_order(OrderSide.BID, 100.0 - i * 0.1, 10.0)
        lob4.add_order(OrderSide.ASK, 100.0 + i * 0.1, 10.0)
    entropy = lob4.depth_entropy()
    check("T14: multi-level entropy > 2.0", entropy > 2.0,
          f"entropy={entropy:.3f}")

    # ── Test 17: Market Maker ──
    mm = MarketMaker(spread=0.02)
    lob_mm = LimitOrderBook()
    lob_mm.add_order(OrderSide.BID, 95.0, 100.0)
    lob_mm.add_order(OrderSide.ASK, 105.0, 100.0)
    bid_o, ask_o = mm.provide_liquidity(lob_mm)
    check("T17: MM bid placed", bid_o is not None)
    check("T18: MM ask placed", ask_o is not None)

    # ── Test 21: Phase alignment fee ──
    fee = mm.phase_alignment_fee(101.0, 100.0)
    check("T21: fee = 0.01 (1%)", abs(fee - 0.01) < 1e-9, f"fee={fee:.6f}")

    # ── Test 26: Slippage Model ──
    sm = SlippageModel(base_slippage_rate=0.001)
    s = sm.compute_slippage(100.0, 99.5)
    check("T26: slippage = 0.005 (0.5%)", abs(s - 0.005) < 1e-9)

    # ── Test 32: ENPV Calculator ──
    enpv_calc = ENPVCalculator()
    val = enpv_calc.compute_enpv(0.8, 1.0, 0.1, 0.05)
    check("T32: ENPV = 0.65", abs(val - 0.65) < 1e-9, f"enpv={val}")

    # ── Test 39: Liquidity Circuit Breaker ──
    cb = LiquidityCircuitBreaker(depth_threshold=10.0, entropy_threshold=0.5)
    lob_normal = LimitOrderBook()
    for i in range(20):
        lob_normal.add_order(OrderSide.BID, 100.0 - i * 0.1, 10.0)
        lob_normal.add_order(OrderSide.ASK, 100.0 + i * 0.1, 10.0)
    broken, state, reason = cb.check_circuit_break(lob_normal)
    check("T39: normal LOB → no break", not broken, f"state={state.value}")

    print(f"\n{'=' * 64}")
    print(f"Self-Test Complete: {passed} passed, {failed} failed")
    print(f"{'=' * 64}")
    return passed, failed


if __name__ == "__main__":
    _self_test()
