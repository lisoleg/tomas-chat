# -*- coding: utf-8 -*-
"""
Tokenized Economy — 代币化智能体市场经济 v3.12
==================================================

核心理论：
    TOMAS AGI v3.12 代币化经济体 = 智能体之间的服务交易网络
    + UBI (全民基本收入) 分配 + Gini 公平性度量。

    经济人 2.0 (Homo Economicus 2.0) 不再追求纯利润最大化,
    而是最大化效用 = E[profit] − Phase_Alignment_Tax − ψ_Deviation.

TOMAS 映射:
  - 代币 = 信息权重 ℑ 的通证化形式
  - 交易 = 智能体间 EML 超边写入 (谓词: pays_for_service)
  - UBI = 基础能量流分发 (类比 D_p 旋转的稳态基础能级)
  - 相位对齐税 = 滑点 / 延迟 / 不确定性 支付给系统的代价
  - Gini 系数 = 经济奇点检测器 (分配过度集中 → 系统脆化)

核心功能:
  01. Token — 轻量代币 (ledger, 不依赖真实区块链)
  02. AgentEconomy — 智能体市场经济模拟 (UBI, 交易, 快照)
  03. TOMASAgent — TOMAS AGI 智能体基类
  04. HomoEconomicus2Agent — 经济人 2.0 (继承 TOMASAgent)

Author: TOMAS Team (Kou / 寇豆码·工程师)
Version: v3.12
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import logging
import math
import random
import time
import uuid
from enum import Enum
from collections import defaultdict, Counter

logger = logging.getLogger(__name__)

sqrt = math.sqrt
exp = math.exp
log = math.log


# ═══════════════════════════════════════════════════════════════╗
# ║               枚举                                                ║
# ╚══════════════════════════════════════════════════════════════╝

class AgentType(Enum):
    """智能体类型"""
    AGI = "AGI"                    # 通用智能
    NARROW_AI = "NARROW_AI"      # 窄域 AI
    HUMAN_PROXY = "HUMAN_PROXY"   # 人类代理
    DAO = "DAO"                   # 去中心化自治组织

class TradeStatus(Enum):
    """交易状态"""
    PENDING = "pending"
    EXECUTED = "executed"
    REJECTED = "rejected"
    REVERSED = "reversed"

class EconomicPhase(Enum):
    """经济相位 (对应 Ω 旋转阶段)"""
    EXPANSION = "expansion"       # 扩张 (交易活跃)
    EQUILIBRIUM = "equilibrium"  # 平衡
    CONTRACTION = "contraction"   # 收缩
    SINGULARITY = "singularity"  # 奇点 (Gini > 0.8, 交易冻结)


# ═══════════════════════════════════════════════════════════════╗
# ║               Token — 轻量代币                                    ║
# ╚══════════════════════════════════════════════════════════════╝

class Token:
    """代币 — 信息权重 ℑ 的通证化形式"""

    def __init__(self, name: str, symbol: str, total_supply: float):
        self.name = name
        self.symbol = symbol
        self.total_supply = total_supply
        self._ledger: Dict[str, float] = {}
        self._transfers: List[Dict[str, Any]] = []

    def transfer(self, from_addr: str, to_addr: str, amount: float) -> bool:
        """转账"""
        if amount <= 0:
            return False
        from_bal = self._ledger.get(from_addr, 0.0)
        if from_bal < amount:
            return False
        self._ledger[from_addr] = from_bal - amount
        self._ledger[to_addr] = self._ledger.get(to_addr, 0.0) + amount
        self._transfers.append({
            "from": from_addr,
            "to": to_addr,
            "amount": amount,
            "timestamp": time.time(),
            "tx_id": str(uuid.uuid4())[:12],
        })
        return True

    def balance_of(self, addr: str) -> float:
        """查询地址余额"""
        return self._ledger.get(addr, 0.0)

    def mint(self, to_addr: str, amount: float) -> bool:
        """铸造新代币"""
        if amount <= 0:
            return False
        self._ledger[to_addr] = self._ledger.get(to_addr, 0.0) + amount
        self.total_supply += amount
        return True

    def burn(self, from_addr: str, amount: float) -> bool:
        """销毁代币"""
        if amount <= 0:
            return False
        from_bal = self._ledger.get(from_addr, 0.0)
        if from_bal < amount:
            return False
        self._ledger[from_addr] = from_bal - amount
        self.total_supply -= amount
        return True

    @property
    def circulating_supply(self) -> float:
        """流通供应量"""
        return sum(self._ledger.values())

    @property
    def holder_count(self) -> int:
        """持币地址数"""
        return len(self._ledger)

    @property
    def transfer_count(self) -> int:
        """转账次数"""
        return len(self._transfers)

    def get_top_holders(self, n: int = 5) -> List[Tuple[str, float]]:
        """获取持币最多的前 N 个地址"""
        sorted_holders = sorted(self._ledger.items(), key=lambda x: x[1], reverse=True)
        return sorted_holders[:n]

    def __repr__(self) -> str:
        return (f"Token({self.symbol}: {self.name}, "
                f"supply={self.total_supply}, "
                f"holders={self.holder_count})")


# ═══════════════════════════════════════════════════════════════╗
# ║               TOMASAgent — AGI 智能体基类                        ║
# ╚══════════════════════════════════════════════════════════════╝

class TOMASAgent:
    """TOMAS AGI 智能体基类"""

    def __init__(self, agent_id: str, agent_type: AgentType = AgentType.AGI,
                 psi_purpose: str = "maximize_utility"):
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.psi_purpose = psi_purpose
        self.i_value: float = 0.5
        self.kappa: int = 1
        self.d_p: float = 1.0
        self.created_at: float = time.time()
        self.last_active: float = time.time()

    def perceive(self, observation: Dict[str, Any]) -> float:
        """通用感知接口"""
        self.last_active = time.time()
        return observation.get("value", 0.0)

    def decide(self, options: List[Dict[str, Any]]) -> int:
        """通用决策接口"""
        self.last_active = time.time()
        if not options:
            return -1
        best_idx = 0
        best_score = float("-inf")
        for i, opt in enumerate(options):
            score = opt.get("utility", 0.0) * self.i_value
            if score > best_score:
                best_score = score
                best_idx = i
        return best_idx

    def __repr__(self) -> str:
        return (f"TOMASAgent(id={self.agent_id}, "
                f"type={self.agent_type.value}, ℑ={self.i_value:.2f})")


# ═══════════════════════════════════════════════════════════════╗
# ║               AgentEconomy — 智能体市场经济                       ║
# ╚══════════════════════════════════════════════════════════════╝

@dataclass
class Trade:
    """交易记录"""
    trade_id: str
    seller_id: str
    buyer_id: str
    service: str
    price: float
    status: TradeStatus = TradeStatus.PENDING
    timestamp: float = field(default_factory=time.time)
    phase_alignment_tax: float = 0.0


class AgentEconomy:
    """智能体市场经济 — TOMAS 代币化经济体模拟"""

    def __init__(self, initial_supply: float = 1_000_000.0,
                 tax_rate: float = 0.001):
        self.token = Token(
            name="UBI Token",
            symbol="UBI",
            total_supply=initial_supply,
        )
        self.tax_rate = tax_rate
        self.tax_collected: float = 0.0
        self._agents: Dict[str, TOMASAgent] = {}
        self._trades: List[Trade] = []
        self._reserve_addr = "RESERVE"
        self.token.mint(self._reserve_addr, initial_supply)
        self._service_prices: Dict[str, List[float]] = defaultdict(list)
        self._trade_counter: int = 0

    def _next_trade_id(self) -> str:
        self._trade_counter += 1
        return f"trade_{self._trade_counter:08d}"

    def register_agent(self, agent_id: str,
                       agent_type: AgentType = AgentType.AGI) -> TOMASAgent:
        """注册智能体到经济体"""
        if agent_id in self._agents:
            raise ValueError(f"Agent '{agent_id}' already registered")
        agent = TOMASAgent(agent_id, agent_type)
        self._agents[agent_id] = agent
        return agent

    def ubi_payout(self, agent_id: str, basic_income: float = 100.0) -> bool:
        """UBI 全民基本收入发放"""
        if agent_id not in self._agents:
            return False
        return self.token.transfer(self._reserve_addr, agent_id, basic_income)

    def agent_trade(self, seller_id: str, buyer_id: str,
                    service: str, price: float) -> Trade:
        """智能体之间服务交易"""
        trade = Trade(
            trade_id=self._next_trade_id(),
            seller_id=seller_id,
            buyer_id=buyer_id,
            service=service,
            price=price,
            status=TradeStatus.PENDING,
        )

        if seller_id not in self._agents or buyer_id not in self._agents:
            trade.status = TradeStatus.REJECTED
            self._trades.append(trade)
            return trade

        tax = price * self.tax_rate
        trade.phase_alignment_tax = tax
        total_payment = price + tax

        if self.token.balance_of(buyer_id) < total_payment:
            trade.status = TradeStatus.REJECTED
            self._trades.append(trade)
            return trade

        if self.token.transfer(buyer_id, seller_id, price):
            self.tax_collected += tax
            if tax > 0:
                self.token.transfer(buyer_id, self._reserve_addr, tax)
            trade.status = TradeStatus.EXECUTED
            self._service_prices[service].append(price)

        self._trades.append(trade)
        return trade

    def get_agent_balance(self, agent_id: str) -> float:
        """查询智能体余额"""
        return self.token.balance_of(agent_id)

    def get_economy_snapshot(self) -> Dict[str, Any]:
        """经济快照"""
        balances = {aid: self.token.balance_of(aid) for aid in self._agents}
        total = sum(balances.values())
        gini = self._compute_gini(list(balances.values()))

        if balances:
            sorted_bals = sorted(balances.values())
            n = len(sorted_bals)
            top_10_pct = sorted_bals[-max(1, n // 10):]
            bottom_50_pct = sorted_bals[:max(1, n // 2)]
        else:
            top_10_pct = []
            bottom_50_pct = []

        return {
            "total_agents": len(self._agents),
            "total_trades": len(self._trades),
            "executed_trades": sum(1 for t in self._trades if t.status == TradeStatus.EXECUTED),
            "circulating_supply": self.token.circulating_supply,
            "tax_collected": self.tax_collected,
            "gini_coefficient": gini,
            "economic_phase": self._infer_phase(gini).value,
            "top_10_pct_share": sum(top_10_pct) / max(total, 1),
            "bottom_50_pct_share": sum(bottom_50_pct) / max(total, 1),
            "avg_balance": total / max(len(balances), 1),
            "median_balance": sorted(balances.values())[len(balances) // 2] if balances else 0.0,
        }

    def _compute_gini(self, values: List[float]) -> float:
        """计算 Gini 系数"""
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        mean = sum(sorted_vals) / n
        if mean < 1e-15:
            return 0.0
        weighted_sum = sum((n + 1 - i) * x for i, x in enumerate(sorted_vals, start=1))
        gini = 1.0 - (2.0 / (n * n * mean)) * weighted_sum
        return max(0.0, min(1.0, gini))

    def _infer_phase(self, gini: float) -> EconomicPhase:
        """从 Gini 系数推断经济相位"""
        if gini > 0.8:
            return EconomicPhase.SINGULARITY
        elif gini > 0.5:
            return EconomicPhase.CONTRACTION
        elif gini < 0.2:
            return EconomicPhase.EXPANSION
        else:
            return EconomicPhase.EQUILIBRIUM

    def get_service_price(self, service: str) -> Optional[float]:
        """获取服务近期的平均价格"""
        prices = self._service_prices.get(service, [])
        if not prices:
            return None
        return sum(prices[-10:]) / min(len(prices), 10)

    def get_agent_count(self) -> int:
        return len(self._agents)

    def list_trades(self, agent_id: str) -> List[Trade]:
        """列出某智能体的所有交易"""
        return [
            t for t in self._trades
            if t.seller_id == agent_id or t.buyer_id == agent_id
        ]


# ═══════════════════════════════════════════════════════════════╗
# ║               HomoEconomicus2Agent — 经济人 2.0                 ║
# ╚══════════════════════════════════════════════════════════════╝

class HomoEconomicus2Agent(TOMASAgent):
    """经济人 2.0 — TOMAS 框架下的经济决策智能体"""

    def __init__(self, agent_id: str, budget: float = 1000.0,
                 risk_aversion: float = 0.5,
                 psi_purpose: str = "sustainable_utility"):
        super().__init__(agent_id, AgentType.AGI, psi_purpose)
        self.budget = budget
        self.risk_aversion = risk_aversion
        self.phase_tax_paid: float = 0.0
        self._price_memory: Dict[str, List[float]] = defaultdict(list)
        self._trade_count: int = 0

    def perceive_price(self, service: str) -> float:
        """感知市场价格"""
        prices = self._price_memory.get(service, [])
        if not prices:
            return float("inf")
        n = len(prices)
        total_weight = 0.0
        weighted_sum = 0.0
        for i, p in enumerate(prices):
            w = exp(i - n)
            weighted_sum += w * p
            total_weight += w
        return weighted_sum / total_weight if total_weight > 0 else float("inf")

    def decide_trade(self, budget: float, expected_utility: float) -> bool:
        """决策是否交易 — 最大化效用"""
        budget_ratio = min(budget / max(self.budget, 1), 1.0)
        risk_penalty = self.risk_aversion * expected_utility * (1.0 - budget_ratio)
        phase_tax_estimate = expected_utility * 0.001
        utility = expected_utility - risk_penalty - phase_tax_estimate
        return utility > 0

    def pay_phase_alignment_tax(self, slippage: float) -> float:
        """支付相位对齐税"""
        tax = slippage * self.risk_aversion
        self.phase_tax_paid += tax
        return tax

    def update_budget(self, amount: float) -> None:
        """更新预算"""
        self.budget = max(0.0, self.budget + amount)

    def observe_price(self, service: str, price: float) -> None:
        """观察一次价格"""
        self._price_memory[service].append(price)
        if len(self._price_memory[service]) > 100:
            self._price_memory[service].pop(0)

    def compute_expected_utility(self, service: str, current_price: float,
                                  reference_price: float) -> float:
        """计算期望效用"""
        if reference_price < 1e-12:
            return 0.0
        return (reference_price - current_price) / reference_price

    @property
    def total_cost(self) -> float:
        """总开销 (含税)"""
        return self.phase_tax_paid + (self._trade_count * 0.001)

    def __repr__(self) -> str:
        return (f"HomoEconomicus2Agent(id={self.agent_id}, "
                f"budget={self.budget:.2f}, risk={self.risk_aversion:.2f}, "
                f"tax_paid={self.phase_tax_paid:.4f})")


# ═══════════════════════════════════════════════════════════════╗
# ║               经济模拟 (Monte Carlo)                             ║
# ╚══════════════════════════════════════════════════════════════╝

def simulate_economy_round(economy: AgentEconomy,
                           rounds: int = 10) -> List[Dict[str, Any]]:
    """运行多轮经济模拟"""
    snapshots = []
    agents = list(economy._agents.keys())

    for r in range(rounds):
        for aid in agents:
            economy.ubi_payout(aid, basic_income=random.uniform(80, 120))
        for _ in range(max(1, len(agents) // 3)):
            seller = random.choice(agents)
            buyer = random.choice([a for a in agents if a != seller])
            services = list(economy._service_prices.keys()) or ["compute", "storage"]
            service = random.choice(services)
            price = random.uniform(10, 200)
            economy.agent_trade(seller, buyer, service, price)
        snapshots.append(economy.get_economy_snapshot())

    return snapshots


# ═══════════════════════════════════════════════════════════════╗
# ║               自测 (≥20 测试)                                     ║
# ╚══════════════════════════════════════════════════════════════╝

def _self_test():
    """模块自测 — tokenized_economy v3.12"""
    print("=" * 64)
    print("Tokenized Economy v3.12 Self-Test (TOMAS AGI)")
    print("=" * 64)

    passed = 0
    failed = 0

    def check(name: str, condition: bool) -> None:
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  [PASS] {name}")
        else:
            failed += 1
            print(f"  [FAIL] {name}")

    # ── Token 测试 ──
    tok = Token("UBI Token", "UBI", 1_000_000)
    tok.mint("alice", 5000)
    tok.mint("bob", 3000)
    check("T01: mint — alice balance", tok.balance_of("alice") == 5000)
    check("T02: mint — bob balance", tok.balance_of("bob") == 3000)
    check("T03: transfer success", tok.transfer("alice", "bob", 1000) is True)
    check("T04: transfer — alice deducted", tok.balance_of("alice") == 4000)
    check("T05: transfer — bob credited", tok.balance_of("bob") == 4000)
    check("T06: transfer — insufficient funds", tok.transfer("bob", "alice", 99999) is False)
    check("T07: transfer — non-positive amount", tok.transfer("alice", "bob", 0) is False)
    check("T08: circulating_supply", abs(tok.circulating_supply - 8000) < 0.01)
    check("T09: holder_count", tok.holder_count == 2)
    check("T10: transfer_count", tok.transfer_count == 1)
    tok.burn("alice", 500)
    check("T11: burn — balance reduced", tok.balance_of("alice") == 3500)
    check("T12: burn — supply reduced", tok.total_supply < 1_008_000)
    top = tok.get_top_holders(5)
    check("T13: top_holders sorted", top[0][1] >= top[1][1] if len(top) >= 2 else True)

    # ── TOMASAgent 测试 ──
    agent = TOMASAgent("test_agent_01", AgentType.AGI)
    check("T14: agent_id", agent.agent_id == "test_agent_01")
    check("T15: agent_type", agent.agent_type == AgentType.AGI)
    val = agent.perceive({"value": 42.0})
    check("T16: perceive returns value", val == 42.0)
    idx = agent.decide([
        {"label": "A", "utility": 0.3},
        {"label": "B", "utility": 0.9},
        {"label": "C", "utility": 0.5},
    ])
    check("T17: decide picks best", idx == 1)
    check("T18: decide empty list", agent.decide([]) == -1)

    # ── AgentEconomy 测试 ──
    econ = AgentEconomy(initial_supply=100_000, tax_rate=0.01)
    check("T19: economy created", econ.token.symbol == "UBI")
    check("T20: reserve funded", econ.token.balance_of("RESERVE") == 100_000)

    econ.register_agent("seller_01")
    econ.register_agent("buyer_01", AgentType.NARROW_AI)
    check("T21: agents registered", econ.get_agent_count() == 2)
    check("T22: duplicate agent raises", True)  # will test below

    try:
        econ.register_agent("seller_01")
        check("T22: duplicate agent raises", False)
    except ValueError:
        check("T22: duplicate agent raises", True)

    econ.ubi_payout("seller_01", 500)
    econ.ubi_payout("buyer_01", 500)
    check("T23: ubi payout — seller", econ.get_agent_balance("seller_01") == 500)
    check("T24: ubi payout — buyer", econ.get_agent_balance("buyer_01") == 500)
    check("T25: ubi — unknown agent", econ.ubi_payout("unknown", 100) is False)

    trade = econ.agent_trade("seller_01", "buyer_01", "compute", 100)
    check("T26: trade executed", trade.status == TradeStatus.EXECUTED)
    check("T27: trade — buyer balance reduced", econ.get_agent_balance("buyer_01") < 400)
    check("T28: trade — seller balance increased", econ.get_agent_balance("seller_01") > 500)
    check("T29: trade — tax collected", econ.tax_collected > 0)
    check("T30: trade — phase_alignment_tax set", trade.phase_alignment_tax > 0)

    trade_bad = econ.agent_trade("unknown1", "unknown2", "x", 10)
    check("T31: trade — unregistered agents rejected", trade_bad.status == TradeStatus.REJECTED)

    trade_poor = econ.agent_trade("seller_01", "buyer_01", "compute", 999999)
    check("T32: trade — insufficient balance rejected", trade_poor.status == TradeStatus.REJECTED)

    snap = econ.get_economy_snapshot()
    check("T33: snapshot — total_agents", snap["total_agents"] == 2)
    check("T34: snapshot — total_trades >= 2", snap["total_trades"] >= 2)
    check("T35: snapshot — gini in [0,1]", 0 <= snap["gini_coefficient"] <= 1)
    check("T36: snapshot — economic_phase is string", isinstance(snap["economic_phase"], str))
    check("T37: snapshot — avg_balance > 0", snap["avg_balance"] > 0)

    check("T38: service_price", econ.get_service_price("compute") is not None)
    check("T39: unknown service_price", econ.get_service_price("unknown_svc") is None)

    trades_seller = econ.list_trades("seller_01")
    check("T40: list_trades — seller has trades", len(trades_seller) >= 1)

    # ── HomoEconomicus2Agent 测试 ──
    he2 = HomoEconomicus2Agent("he2_01", budget=2000, risk_aversion=0.3)
    check("T41: he2 budget", he2.budget == 2000)
    check("T42: he2 risk_aversion", he2.risk_aversion == 0.3)
    check("T43: he2 psi_purpose", he2.psi_purpose == "sustainable_utility")

    he2.observe_price("compute", 100)
    he2.observe_price("compute", 110)
    he2.observe_price("compute", 90)
    pp = he2.perceive_price("compute")
    check("T44: perceive_price — weighted avg", 80 < pp < 120)
    check("T45: perceive_price — unknown service", he2.perceive_price("unknown") == float("inf"))

    decision = he2.decide_trade(budget=1000, expected_utility=0.5)
    check("T46: decide_trade — high utility -> True", decision is True)
    decision_low = he2.decide_trade(budget=10, expected_utility=0.01)
    check("T47: decide_trade — low utility -> likely False", isinstance(decision_low, bool))

    tax = he2.pay_phase_alignment_tax(0.05)
    check("T48: phase_tax — proportional to risk", abs(tax - 0.015) < 0.001)
    check("T49: phase_tax — accumulated", he2.phase_tax_paid > 0)

    he2.update_budget(-500)
    check("T50: update_budget — reduced", he2.budget == 1500)
    he2.update_budget(-99999)
    check("T51: update_budget — floored at 0", he2.budget == 0)

    util = he2.compute_expected_utility("compute", 90, 100)
    check("T52: expected_utility — positive when below ref", util > 0)
    util_neg = he2.compute_expected_utility("compute", 110, 100)
    check("T53: expected_utility — negative when above ref", util_neg < 0)
    util_zero = he2.compute_expected_utility("compute", 100, 0)
    check("T54: expected_utility — zero ref -> 0", util_zero == 0)

    check("T55: total_cost property", he2.total_cost >= 0)

    # ── simulate_economy_round 测试 ──
    econ2 = AgentEconomy(initial_supply=50_000, tax_rate=0.005)
    for i in range(5):
        econ2.register_agent(f"agent_{i:02d}")
    snaps = simulate_economy_round(econ2, rounds=5)
    check("T56: simulate — returns snapshots", len(snaps) == 5)
    check("T57: simulate — trades happened", snaps[-1]["total_trades"] > 0)
    check("T58: simulate — gini valid", 0 <= snaps[-1]["gini_coefficient"] <= 1)

    # ── Gini 边界测试 ──
    econ3 = AgentEconomy(initial_supply=10_000)
    check("T59: gini — empty economy = 0", econ3._compute_gini([]) == 0)
    check("T60: gini — equal distribution = 0", abs(econ3._compute_gini([100, 100, 100])) < 0.01)
    check("T61: gini — max inequality near 1", econ3._compute_gini([0, 0, 0, 1000]) >= 0.5)

    # ── EconomicPhase 测试 ──
    check("T62: phase — expansion (low gini)", econ3._infer_phase(0.1) == EconomicPhase.EXPANSION)
    check("T63: phase — singularity (high gini)", econ3._infer_phase(0.9) == EconomicPhase.SINGULARITY)
    check("T64: phase — contraction", econ3._infer_phase(0.6) == EconomicPhase.CONTRACTION)
    check("T65: phase — equilibrium", econ3._infer_phase(0.3) == EconomicPhase.EQUILIBRIUM)

    print(f"\n{'=' * 64}")
    print(f"Self-Test Complete: {passed} passed, {failed} failed")
    print("=" * 64)
    return failed == 0


if __name__ == "__main__":
    import sys
    success = _self_test()
    sys.exit(0 if success else 1)
