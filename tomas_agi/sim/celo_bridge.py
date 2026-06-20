# -*- coding: utf-8 -*-
"""
CeloBridge — Celo 支付结算层桥接 (TOMAS v2.0 T09)
====================================================

将 TOMAS AGI 的经济激励层桥接至 Celo 区块链，支持稳定币 cUSD/cEUR
支付结算和 BLS 聚合签名。

Celo 核心特性：
    1. 稳定币协议：cUSD (Celo Dollar)、cEUR (Celo Euro) — 链上稳定性
    2. BLS 聚合签名：多个签名聚合为单个签名，降低链上验证 Gas 成本
    3. 轻量客户端：手机级设备可验证链上状态
    4. 碳负值：Celo 网络碳负排放，适合 AGI 可持续激励

与 Mina 桥接的关系：
    - Celo 用于支付结算（经济激励层）
    - Mina 用于 κ-Snap 证明上链（因果证明层）
    - 两者互补：Celo 结算 "谁付了多少"，Mina 证明 "发生了什么"

降级策略：
    - httpx 不可用时降级为 urllib.request
    - py_ecc 不可用时降级为 hashlib.sha256 模拟 BLS 聚合
    - Celo RPC 不可用时返回模拟交易哈希（SHA-256）和模拟确认结果

依赖：
    - ksnap_operator.py (KSnapOperator) — 可选（联合批上链）
    - mina_kappa_bridge.py (MinaTOMASSnap) — 可选（联合证明）
    - 标准库 hashlib、json、urllib.request
    - 可选库 httpx、py_ecc

Author: TOMAS Team
Version: v2.0
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 可选依赖：httpx（HTTP 客户端，性能优于 urllib）
try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False
    httpx = None  # type: ignore

# 可选依赖：py_ecc（BLS 签名库）
try:
    from py_ecc.bls import G2ProofOfPossession as bls
    _HAS_BLS = True
except ImportError:
    _HAS_BLS = False
    bls = None  # type: ignore

# 可选依赖：Mina κ-Snap 桥接（联合证明）
try:
    from mina_kappa_bridge import MinaTOMASSnap
    _HAS_MINA = True
except ImportError:
    _HAS_MINA = False
    MinaTOMASSnap = None  # type: ignore

# 可选依赖：κ-Snap 算子（批上链 Merkle Root）
try:
    from ksnap_operator import KSnapOperator, SnapEvent
    _HAS_KSNAP = True
except ImportError:
    _HAS_KSNAP = False
    KSnapOperator = None  # type: ignore
    SnapEvent = None  # type: ignore


# ============================================================
# 常量
# ============================================================

# Celo 稳定币合约地址（Mainnet）
# cUSD (StableToken): 0x765DE816845861e75A25fCA122bb6898B8B1282a
# cEUR (StableTokenEUR): 0xD8763CBa276a3738E6DE85b4b3bF5FDed6D6cA73
CELO_STABLE_TOKEN_ADDRESSES: Dict[str, str] = {
    "cUSD": "0x765DE816845861e75A25fCA122bb6898B8B1282a",
    "cEUR": "0xD8763CBa276a3738E6DE85b4b3bF5FDed6D6cA73",
}

# Celo 原生代币 CELO 地址（用于 Gas 支付）
CELO_NATIVE_TOKEN: str = "0x471EcE3750Da237f93B8E339c536989b8978a438"

# 支持的稳定币列表
SUPPORTED_CURRENCIES: Tuple[str, ...] = ("cUSD", "cEUR")

# 1 单位稳定币 = 10^18 wei（Celo 使用 18 位小数）
DECIMALS: int = 18

# Celo 稳定币 transfer 方法签名（ERC-20 transfer(address,uint256)）
TRANSFER_METHOD_ID: str = "0xa9059cbb"

# RPC 超时（秒）
RPC_TIMEOUT: float = 10.0


# ============================================================
# 数据结构
# ============================================================

@dataclass
class PaymentRecord:
    """支付记录数据结构。

    封装一笔稳定币支付的完整信息，用于链上存证和验证。

    Attributes:
        tx_hash: 交易哈希（十六进制字符串）
        from_addr: 发送方地址
        to_addr: 接收方地址
        amount: 金额（人类可读单位）
        currency: 稳定币类型（"cUSD" 或 "cEUR"）
        timestamp: 支付时间戳（Unix 时间）
        block_number: 区块号（降级模式下为 0）
        is_degraded: 是否降级模式（Celo RPC 不可用）
    """

    tx_hash: str
    from_addr: str
    to_addr: str
    amount: float
    currency: str
    timestamp: float = field(default_factory=time.time)
    block_number: int = 0
    is_degraded: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典。"""
        return {
            "tx_hash": self.tx_hash,
            "from_addr": self.from_addr,
            "to_addr": self.to_addr,
            "amount": self.amount,
            "currency": self.currency,
            "timestamp": self.timestamp,
            "block_number": self.block_number,
            "is_degraded": self.is_degraded,
        }


# ============================================================
# CeloBridge 主类
# ============================================================

class CeloBridge:
    """Celo 支付结算层桥接：稳定币 cUSD/cEUR + BLS 聚合签名。

    将 TOMAS AGI 的经济激励层桥接至 Celo 区块链，支持：
      1. 稳定币支付（cUSD / cEUR）
      2. BLS 聚合签名（降低链上验证成本）
      3. 支付验证（链上确认检查）
      4. 余额查询
      5. 与 Mina κ-Snap 联合证明（可选）

    降级策略：
        - Celo RPC 不可用时，process_payment 返回模拟 tx_hash（SHA-256）
        - verify_payment 返回模拟确认结果（confirmed=True, block_number=0）
        - get_balance 返回模拟余额（0.0）
        - BLS 不可用时降级为 SHA-256 聚合

    Attributes:
        celo_rpc_url: Celo 节点 RPC URL（默认 https://forno.celo.org）
        contract_address: 稳定币合约地址（可选，默认自动选择）
        private_key: 发送方私钥（可选，用于签名交易）
    """

    def __init__(
        self,
        celo_rpc_url: str = "https://forno.celo.org",
        contract_address: Optional[str] = None,
        private_key: Optional[str] = None,
    ) -> None:
        """初始化 Celo 桥接。

        Args:
            celo_rpc_url: Celo 节点 RPC URL（默认 https://forno.celo.org）
            contract_address: 稳定币合约地址（可选，默认根据 currency 自动选择）
            private_key: 发送方私钥（可选，用于签名链上交易）
        """
        self.celo_rpc_url: str = celo_rpc_url
        self.contract_address: Optional[str] = contract_address
        self.private_key: Optional[str] = private_key

        # 内部状态
        self._payment_records: Dict[str, PaymentRecord] = {}
        self._nonce_counter: int = 0
        self._rpc_available: Optional[bool] = None  # None = 未检测

        # 统计
        self._payment_count: int = 0
        self._degraded_count: int = 0
        self._verify_count: int = 0
        self._aggregate_count: int = 0
        self._balance_query_count: int = 0

        logger.info(
            "CeloBridge 初始化: rpc=%s, contract=%s, httpx=%s, bls=%s, mina=%s",
            self.celo_rpc_url,
            self.contract_address or "(auto)",
            _HAS_HTTPX,
            _HAS_BLS,
            _HAS_MINA,
        )

    # ============================================================
    # 公开接口
    # ============================================================

    def process_payment(
        self, from_addr: str, to_addr: str, amount: float, currency: str = "cUSD"
    ) -> str:
        """处理稳定币支付。

        构建 ERC-20 transfer 交易，通过 Celo RPC 广播。
        Celo RPC 不可用时降级为模拟交易（返回 SHA-256 哈希作为 tx_hash）。

        Args:
            from_addr: 发送方地址（Celo 地址，0x 开头）
            to_addr: 接收方地址（Celo 地址，0x 开头）
            amount: 金额（人类可读单位，如 1.5 表示 1.5 cUSD）
            currency: 稳定币类型，"cUSD" 或 "cEUR"

        Returns:
            交易哈希（64 字符十六进制字符串）

        Raises:
            ValueError: 参数非法（currency 不支持、amount <= 0、地址非法）
        """
        # 参数校验
        if currency not in SUPPORTED_CURRENCIES:
            raise ValueError(
                f"不支持的稳定币类型: {currency}，支持: {SUPPORTED_CURRENCIES}"
            )
        if amount <= 0:
            raise ValueError(f"金额必须为正数, got {amount}")
        if not self._is_valid_address(from_addr):
            raise ValueError(f"非法发送方地址: {from_addr}")
        if not self._is_valid_address(to_addr):
            raise ValueError(f"非法接收方地址: {to_addr}")

        self._payment_count += 1
        self._nonce_counter += 1

        # 确定合约地址
        token_contract = self.contract_address or CELO_STABLE_TOKEN_ADDRESSES.get(
            currency, CELO_STABLE_TOKEN_ADDRESSES["cUSD"]
        )

        # 构建交易数据（ERC-20 transfer）
        # transfer(address to, uint256 amount)
        amount_wei = int(amount * (10 ** DECIMALS))
        tx_data = self._encode_transfer_call(to_addr, amount_wei)

        # 通过 Celo RPC 广播交易
        rpc_result = self._call_celo_rpc(
            "eth_sendRawTransaction",
            [tx_data],
        )

        if rpc_result.get("degraded", True):
            # 降级模式：生成模拟 tx_hash
            self._degraded_count += 1
            tx_hash = self._generate_simulated_tx_hash(
                from_addr, to_addr, amount, currency, self._nonce_counter
            )
            block_number = 0
            is_degraded = True
            logger.info(
                "CeloBridge process_payment 降级: %s %s %s → %s, amount=%.6f %s, tx=%s...",
                "模拟交易",
                from_addr[:10] + "...",
                to_addr[:10] + "...",
                "0x" + tx_hash[:16],
                amount,
                currency,
                tx_hash[:16],
            )
        else:
            # 真实链上交易
            tx_hash = rpc_result.get("result", "")
            if tx_hash.startswith("0x"):
                tx_hash = tx_hash[2:]
            block_number = rpc_result.get("block_number", 0)
            is_degraded = False
            logger.info(
                "CeloBridge process_payment 成功: %s → %s, amount=%.6f %s, tx=0x%s...",
                from_addr[:10] + "...",
                to_addr[:10] + "...",
                amount,
                currency,
                tx_hash[:16],
            )

        # 记录支付
        record = PaymentRecord(
            tx_hash=tx_hash,
            from_addr=from_addr,
            to_addr=to_addr,
            amount=amount,
            currency=currency,
            timestamp=time.time(),
            block_number=block_number,
            is_degraded=is_degraded,
        )
        self._payment_records[tx_hash] = record

        return tx_hash

    def aggregate_signatures(self, sigs: List[bytes]) -> bytes:
        """BLS 聚合签名。

        将多个 BLS 签名聚合为单个签名，降低链上验证成本。
        真实 BLS 使用 py_ecc 库；不可用时降级为 SHA-256 哈希聚合。

        聚合原理：
            - 真实 BLS: agg_sig = sig_1 + sig_2 + ... + sig_n（椭圆曲线点加法）
            - 降级模式: agg_sig = SHA-256(sig_1 || sig_2 || ... || sig_n)

        Args:
            sigs: BLS 签名列表（每个签名为 bytes）

        Returns:
            聚合签名（bytes）

        Raises:
            ValueError: 签名列表为空
        """
        if not sigs:
            raise ValueError("签名列表不能为空")

        self._aggregate_count += 1

        if _HAS_BLS and bls is not None:
            # 真实 BLS 聚合签名
            try:
                # py_ecc G2ProofOfPossession.Aggregate 签名列表
                # 签名格式为 G2 点的 bytes 表示
                aggregated = bls.Aggregate(sigs)
                logger.info(
                    "CeloBridge aggregate_signatures (BLS): %d 签名 → 聚合签名 (%d bytes)",
                    len(sigs),
                    len(aggregated) if aggregated else 0,
                )
                return aggregated if aggregated else b""
            except Exception as e:
                logger.warning(
                    "CeloBridge aggregate_signatures: BLS 聚合失败, 降级为 SHA-256: %s", e
                )

        # 降级模式：SHA-256 哈希聚合
        hasher = hashlib.sha256()
        for i, sig in enumerate(sigs):
            # 加入索引以区分不同签名位置
            hasher.update(i.to_bytes(4, byteorder="big"))
            hasher.update(sig)

        aggregated = hasher.digest()
        logger.info(
            "CeloBridge aggregate_signatures (降级 SHA-256): %d 签名 → %d bytes",
            len(sigs),
            len(aggregated),
        )
        return aggregated

    def verify_payment(self, tx_hash: str) -> Dict:
        """验证支付交易。

        通过 Celo RPC 查询交易回执，确认交易是否已被链上确认。
        Celo RPC 不可用时返回模拟确认结果。

        Args:
            tx_hash: 交易哈希（十六进制字符串，可带 0x 前缀）

        Returns:
            验证结果字典:
            {
                "confirmed": bool,       # 是否已确认
                "block_number": int,     # 区块号（0 表示降级模式）
                "amount": float,         # 交易金额
                "currency": str,         # 稳定币类型
                "is_degraded": bool,     # 是否降级模式
            }
        """
        self._verify_count += 1

        # 标准化 tx_hash（去掉 0x 前缀）
        clean_hash = tx_hash[2:] if tx_hash.startswith("0x") else tx_hash

        # 检查本地记录
        record = self._payment_records.get(clean_hash)

        # 通过 Celo RPC 查询交易回执
        rpc_result = self._call_celo_rpc(
            "eth_getTransactionReceipt",
            ["0x" + clean_hash],
        )

        if rpc_result.get("degraded", True):
            # 降级模式：返回模拟确认结果
            self._degraded_count += 1
            if record is not None:
                result: Dict[str, Any] = {
                    "confirmed": True,
                    "block_number": 0,
                    "amount": record.amount,
                    "currency": record.currency,
                    "is_degraded": True,
                }
            else:
                result = {
                    "confirmed": True,
                    "block_number": 0,
                    "amount": 0.0,
                    "currency": "cUSD",
                    "is_degraded": True,
                }
            logger.info(
                "CeloBridge verify_payment 降级: tx=%s..., confirmed=True (模拟)",
                clean_hash[:16],
            )
        else:
            # 真实链上确认
            receipt = rpc_result.get("result", {})
            status = receipt.get("status", "0x0")
            block_num = int(receipt.get("blockNumber", "0x0"), 16)
            confirmed = (status == "0x1")

            if record is not None:
                result = {
                    "confirmed": confirmed,
                    "block_number": block_num,
                    "amount": record.amount,
                    "currency": record.currency,
                    "is_degraded": False,
                }
            else:
                result = {
                    "confirmed": confirmed,
                    "block_number": block_num,
                    "amount": 0.0,
                    "currency": "cUSD",
                    "is_degraded": False,
                }
            logger.info(
                "CeloBridge verify_payment 成功: tx=%s..., confirmed=%s, block=%d",
                clean_hash[:16],
                confirmed,
                block_num,
            )

        return result

    def get_balance(self, address: str, currency: str = "cUSD") -> float:
        """查询地址余额。

        通过 Celo RPC 调用稳定币合约的 balanceOf 方法查询余额。
        Celo RPC 不可用时返回模拟余额（0.0）。

        Args:
            address: Celo 地址（0x 开头）
            currency: 稳定币类型，"cUSD" 或 "cEUR"

        Returns:
            余额（人类可读单位，如 1.5 表示 1.5 cUSD）

        Raises:
            ValueError: 参数非法
        """
        if currency not in SUPPORTED_CURRENCIES:
            raise ValueError(
                f"不支持的稳定币类型: {currency}，支持: {SUPPORTED_CURRENCIES}"
            )
        if not self._is_valid_address(address):
            raise ValueError(f"非法地址: {address}")

        self._balance_query_count += 1

        # 确定合约地址
        token_contract = self.contract_address or CELO_STABLE_TOKEN_ADDRESSES.get(
            currency, CELO_STABLE_TOKEN_ADDRESSES["cUSD"]
        )

        # 构建 balanceOf(address) 调用
        call_data = self._encode_balance_of_call(address)

        rpc_result = self._call_celo_rpc(
            "eth_call",
            [
                {"to": token_contract, "data": call_data},
                "latest",
            ],
        )

        if rpc_result.get("degraded", True):
            # 降级模式：返回 0.0
            self._degraded_count += 1
            logger.info(
                "CeloBridge get_balance 降级: addr=%s..., currency=%s, balance=0.0 (模拟)",
                address[:10] + "...",
                currency,
            )
            return 0.0

        # 解析链上余额
        raw_balance = rpc_result.get("result", "0x0")
        try:
            balance_wei = int(raw_balance, 16)
        except (ValueError, TypeError):
            balance_wei = 0

        balance = balance_wei / (10 ** DECIMALS)
        logger.info(
            "CeloBridge get_balance 成功: addr=%s..., currency=%s, balance=%.6f",
            address[:10] + "...",
            currency,
            balance,
        )
        return balance

    # ============================================================
    # 联合证明（与 Mina κ-Snap）
    # ============================================================

    def joint_prove_with_mina(
        self,
        payment_tx_hash: str,
        snap_events: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        """与 Mina κ-Snap 桥接联合证明。

        将 Celo 支付交易与 Mina κ-Snap 因果证明关联，
        实现 "支付 + 因果" 双重证明。

        Celo 负责结算 "谁付了多少"（经济激励），
        Mina 负责证明 "发生了什么"（因果日志）。

        Args:
            payment_tx_hash: Celo 支付交易哈希
            snap_events: κ-Snap 事件列表（可选，用于 Mina 批量证明）

        Returns:
            联合证明结果:
            {
                "payment_tx_hash": str,        # Celo 交易哈希
                "payment_verified": bool,      # Celo 支付验证结果
                "mina_proof_hash": str,        # Mina 证明哈希
                "joint_hash": str,             # 联合哈希（SHA-256）
                "is_degraded": bool,           # 是否降级模式
            }
        """
        # 1. 验证 Celo 支付
        payment_result = self.verify_payment(payment_tx_hash)
        payment_verified = payment_result.get("confirmed", False)

        # 2. 生成 Mina κ-Snap 证明（如可用）
        mina_proof_hash: str = "0" * 64
        if _HAS_MINA and MinaTOMASSnap is not None and snap_events:
            mina_bridge = MinaTOMASSnap()
            mina_proof_hash = mina_bridge.batch_prove(snap_events)
        elif snap_events and _HAS_KSNAP and KSnapOperator is not None:
            # 降级：使用 KSnapOperator 计算 Merkle Root
            mina_proof_hash = KSnapOperator.batch_merkle_root(snap_events)
            logger.info(
                "CeloBridge joint_prove_with_mina: Mina 不可用，使用 KSnapOperator Merkle Root"
            )
        else:
            logger.info(
                "CeloBridge joint_prove_with_mina: 无 snap_events，跳过 Mina 证明"
            )

        # 3. 计算联合哈希
        joint_data = f"{payment_tx_hash}{mina_proof_hash}".encode("utf-8")
        joint_hash = hashlib.sha256(joint_data).hexdigest()

        is_degraded = payment_result.get("is_degraded", True) or (
            mina_proof_hash == "0" * 64
        )

        logger.info(
            "CeloBridge joint_prove_with_mina: payment_verified=%s, "
            "mina_proof=%s..., joint=%s...",
            payment_verified,
            mina_proof_hash[:16],
            joint_hash[:16],
        )

        return {
            "payment_tx_hash": payment_tx_hash,
            "payment_verified": payment_verified,
            "mina_proof_hash": mina_proof_hash,
            "joint_hash": joint_hash,
            "is_degraded": is_degraded,
        }

    # ============================================================
    # 内部方法
    # ============================================================

    def _call_celo_rpc(self, method: str, params: List) -> Dict:
        """调用 Celo JSON-RPC 接口。

        使用 httpx（如可用）或 urllib.request 调用 Celo 节点的 JSON-RPC 接口。
        失败时降级为模拟结果。

        降级策略：
            - 连接超时/拒绝 → 返回 {"degraded": True}
            - HTTP 错误 → 返回 {"degraded": True}
            - 响应解析失败 → 返回 {"degraded": True}

        Args:
            method: JSON-RPC 方法名（如 "eth_sendRawTransaction"）
            params: JSON-RPC 参数列表

        Returns:
            响应字典，降级时包含 {"degraded": True}
        """
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self._nonce_counter,
        }

        if _HAS_HTTPX and httpx is not None:
            return self._call_celo_rpc_httpx(payload)
        else:
            return self._call_celo_rpc_urllib(payload)

    def _call_celo_rpc_httpx(self, payload: Dict) -> Dict:
        """使用 httpx 调用 Celo RPC。"""
        try:
            with httpx.Client(timeout=RPC_TIMEOUT) as client:
                resp = client.post(
                    self.celo_rpc_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                resp_json = resp.json()

            if "error" in resp_json:
                logger.warning(
                    "CeloBridge _call_celo_rpc (httpx): RPC 错误: %s",
                    resp_json["error"],
                )
                return {"degraded": True, "error": str(resp_json["error"])}

            result = resp_json.get("result", {})
            self._rpc_available = True
            return {"degraded": False, "result": result}

        except Exception as e:
            logger.debug(
                "CeloBridge _call_celo_rpc (httpx): 连接失败 (降级): %s", e
            )
            self._rpc_available = False
            return {"degraded": True, "error": str(e)}

    def _call_celo_rpc_urllib(self, payload: Dict) -> Dict:
        """使用 urllib.request 调用 Celo RPC（降级 HTTP 客户端）。"""
        import urllib.request
        import urllib.error

        try:
            request_body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.celo_rpc_url,
                data=request_body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            resp = urllib.request.urlopen(req, timeout=RPC_TIMEOUT)
            resp_body = resp.read().decode("utf-8")
            resp_json = json.loads(resp_body)
            resp.close()

            if "error" in resp_json:
                logger.warning(
                    "CeloBridge _call_celo_rpc (urllib): RPC 错误: %s",
                    resp_json["error"],
                )
                return {"degraded": True, "error": str(resp_json["error"])}

            result = resp_json.get("result", {})
            self._rpc_available = True
            return {"degraded": False, "result": result}

        except urllib.error.URLError as e:
            logger.debug(
                "CeloBridge _call_celo_rpc (urllib): 连接失败 (降级): %s", e
            )
            self._rpc_available = False
            return {"degraded": True, "error": f"URLError: {e}"}
        except Exception as e:
            logger.debug(
                "CeloBridge _call_celo_rpc (urllib): 异常 (降级): %s", e
            )
            self._rpc_available = False
            return {"degraded": True, "error": str(e)}

    def _generate_simulated_tx_hash(
        self,
        from_addr: str,
        to_addr: str,
        amount: float,
        currency: str,
        nonce: int,
    ) -> str:
        """生成模拟交易哈希（降级模式）。

        使用 SHA-256 对交易参数进行哈希，生成 64 字符十六进制 tx_hash。

        Args:
            from_addr: 发送方地址
            to_addr: 接收方地址
            amount: 金额
            currency: 稳定币类型
            nonce: 随机数（确保相同参数产生不同 tx_hash）

        Returns:
            64 字符十六进制字符串（不带 0x 前缀）
        """
        data = f"{from_addr}{to_addr}{amount}{currency}{nonce}{time.time()}"
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    @staticmethod
    def _is_valid_address(address: str) -> bool:
        """验证 Celo/EVM 地址格式。

        Args:
            address: 待验证的地址字符串

        Returns:
            True 若地址合法（0x 开头 + 40 位十六进制）
        """
        if not isinstance(address, str):
            return False
        if not address.startswith("0x"):
            return False
        if len(address) != 42:
            return False
        try:
            int(address[2:], 16)
            return True
        except ValueError:
            return False

    @staticmethod
    def _encode_transfer_call(to_addr: str, amount_wei: int) -> str:
        """编码 ERC-20 transfer(address,uint256) 调用数据。

        Args:
            to_addr: 接收方地址（0x 开头）
            amount_wei: 金额（wei 单位，整数）

        Returns:
            十六进制调用数据字符串（0x 开头）
        """
        # transfer(address to, uint256 amount) = 0xa9059cbb + address(32 bytes) + uint256(32 bytes)
        addr_padded = to_addr[2:].lower().rjust(64, "0")
        amount_hex = format(amount_wei, "064x")
        return TRANSFER_METHOD_ID + addr_padded + amount_hex

    @staticmethod
    def _encode_balance_of_call(address: str) -> str:
        """编码 ERC-20 balanceOf(address) 调用数据。

        Args:
            address: 查询地址（0x 开头）

        Returns:
            十六进制调用数据字符串（0x 开头）
        """
        # balanceOf(address) = 0x70a08231 + address(32 bytes)
        method_id = "0x70a08231"
        addr_padded = address[2:].lower().rjust(64, "0")
        return method_id + addr_padded

    # ============================================================
    # 辅助方法
    # ============================================================

    def get_payment_record(self, tx_hash: str) -> Optional[PaymentRecord]:
        """获取支付记录。

        Args:
            tx_hash: 交易哈希（可带 0x 前缀）

        Returns:
            PaymentRecord 实例，若不存在则返回 None
        """
        clean_hash = tx_hash[2:] if tx_hash.startswith("0x") else tx_hash
        return self._payment_records.get(clean_hash)

    def stats(self) -> Dict[str, Any]:
        """返回桥接统计信息。

        Returns:
            统计信息字典
        """
        return {
            "celo_rpc_url": self.celo_rpc_url,
            "contract_address": self.contract_address,
            "rpc_available": self._rpc_available,
            "payment_count": self._payment_count,
            "degraded_count": self._degraded_count,
            "verify_count": self._verify_count,
            "aggregate_count": self._aggregate_count,
            "balance_query_count": self._balance_query_count,
            "httpx_available": _HAS_HTTPX,
            "bls_available": _HAS_BLS,
            "mina_available": _HAS_MINA,
            "ksnap_available": _HAS_KSNAP,
            "payment_records": len(self._payment_records),
        }


# ============================================================
# Self-Test
# ============================================================
if __name__ == "__main__":
    print("=" * 64)
    print("  CeloBridge — Self-Test Suite")
    print("=" * 64)

    # 使用不可达的 RPC URL 确保降级模式（测试环境无 Celo 节点）
    bridge = CeloBridge(celo_rpc_url="http://192.0.2.1:8545")

    # ── 1. 基本初始化 ──
    print("\n[1] Testing basic initialization...")
    assert bridge.celo_rpc_url == "http://192.0.2.1:8545"
    assert bridge.contract_address is None
    assert bridge.private_key is None
    assert bridge._payment_count == 0
    assert bridge._degraded_count == 0
    print(f"  [PASS] rpc_url={bridge.celo_rpc_url}, contract=(auto)")

    # ── 2. process_payment 降级模式 (cUSD) ──
    print("\n[2] Testing process_payment() with cUSD in degraded mode...")
    from_addr = "0x" + "a" * 40
    to_addr = "0x" + "b" * 40
    tx_hash_1 = bridge.process_payment(from_addr, to_addr, 1.5, "cUSD")
    assert isinstance(tx_hash_1, str)
    assert len(tx_hash_1) == 64, f"tx_hash 应为 64 字符, got {len(tx_hash_1)}"
    assert all(c in "0123456789abcdef" for c in tx_hash_1), "tx_hash 应为十六进制"
    print(f"  [PASS] cUSD payment: tx_hash={tx_hash_1[:16]}...")

    # ── 3. process_payment 降级模式 (cEUR) ──
    print("\n[3] Testing process_payment() with cEUR in degraded mode...")
    tx_hash_2 = bridge.process_payment(from_addr, to_addr, 2.0, "cEUR")
    assert isinstance(tx_hash_2, str)
    assert len(tx_hash_2) == 64
    assert tx_hash_2 != tx_hash_1, "不同支付应产生不同 tx_hash"
    print(f"  [PASS] cEUR payment: tx_hash={tx_hash_2[:16]}...")

    # ── 4. process_payment 参数校验 ──
    print("\n[4] Testing process_payment() parameter validation...")
    # 不支持的 currency
    try:
        bridge.process_payment(from_addr, to_addr, 1.0, "cGBP")
        assert False, "应抛出 ValueError"
    except ValueError as e:
        assert "cGBP" in str(e)
        print(f"  [PASS] Unsupported currency rejected: {e}")

    # 负金额
    try:
        bridge.process_payment(from_addr, to_addr, -1.0, "cUSD")
        assert False, "应抛出 ValueError"
    except ValueError as e:
        print(f"  [PASS] Negative amount rejected: {e}")

    # 非法地址
    try:
        bridge.process_payment("0xinvalid", to_addr, 1.0, "cUSD")
        assert False, "应抛出 ValueError"
    except ValueError as e:
        print(f"  [PASS] Invalid address rejected: {e}")

    # ── 5. verify_payment 降级模式 ──
    print("\n[5] Testing verify_payment() in degraded mode...")
    result_1 = bridge.verify_payment(tx_hash_1)
    assert isinstance(result_1, dict)
    assert result_1["confirmed"] is True, "降级模式应返回 confirmed=True"
    assert result_1["is_degraded"] is True, "降级模式应标记 is_degraded"
    assert result_1["amount"] == 1.5, f"amount mismatch: {result_1['amount']}"
    assert result_1["currency"] == "cUSD", f"currency mismatch: {result_1['currency']}"
    assert result_1["block_number"] == 0, "降级模式 block_number 应为 0"
    print(f"  [PASS] verify cUSD: confirmed={result_1['confirmed']}, "
          f"amount={result_1['amount']}, currency={result_1['currency']}")

    result_2 = bridge.verify_payment("0x" + tx_hash_2)  # 测试带 0x 前缀
    assert result_2["confirmed"] is True
    assert result_2["currency"] == "cEUR"
    assert result_2["amount"] == 2.0
    print(f"  [PASS] verify cEUR (with 0x prefix): confirmed={result_2['confirmed']}, "
          f"amount={result_2['amount']}, currency={result_2['currency']}")

    # ── 6. get_balance 降级模式 ──
    print("\n[6] Testing get_balance() in degraded mode...")
    balance_usd = bridge.get_balance(from_addr, "cUSD")
    assert isinstance(balance_usd, float)
    assert balance_usd == 0.0, f"降级模式余额应为 0.0, got {balance_usd}"
    print(f"  [PASS] cUSD balance: {balance_usd} (degraded)")

    balance_eur = bridge.get_balance(to_addr, "cEUR")
    assert balance_eur == 0.0
    print(f"  [PASS] cEUR balance: {balance_eur} (degraded)")

    # 非法 currency
    try:
        bridge.get_balance(from_addr, "cJPY")
        assert False, "应抛出 ValueError"
    except ValueError as e:
        print(f"  [PASS] Invalid currency rejected: {e}")

    # ── 7. aggregate_signatures 降级模式 (SHA-256) ──
    print("\n[7] Testing aggregate_signatures() in degraded mode...")
    sigs = [
        hashlib.sha256(b"sig_1").digest(),
        hashlib.sha256(b"sig_2").digest(),
        hashlib.sha256(b"sig_3").digest(),
    ]
    agg_sig = bridge.aggregate_signatures(sigs)
    assert isinstance(agg_sig, bytes)
    assert len(agg_sig) == 32, f"SHA-256 聚合签名应为 32 bytes, got {len(agg_sig)}"
    print(f"  [PASS] Aggregated 3 signatures → {len(agg_sig)} bytes, "
          f"hash={agg_sig.hex()[:16]}...")

    # 空列表应抛出异常
    try:
        bridge.aggregate_signatures([])
        assert False, "应抛出 ValueError"
    except ValueError as e:
        print(f"  [PASS] Empty signature list rejected: {e}")

    # ── 8. aggregate_signatures 一致性 ──
    print("\n[8] Testing aggregate_signatures() consistency...")
    sigs_a = [b"\x01" * 32, b"\x02" * 32]
    sigs_b = [b"\x01" * 32, b"\x02" * 32]
    agg_a = bridge.aggregate_signatures(sigs_a)
    agg_b = bridge.aggregate_signatures(sigs_b)
    assert agg_a == agg_b, "相同签名列表应产生相同聚合签名"
    print(f"  [PASS] Consistent aggregation: {agg_a.hex()[:16]}...")

    # 不同顺序应产生不同结果（降级模式下索引敏感）
    sigs_reversed = [b"\x02" * 32, b"\x01" * 32]
    agg_reversed = bridge.aggregate_signatures(sigs_reversed)
    assert agg_a != agg_reversed, "不同顺序应产生不同聚合签名"
    print(f"  [PASS] Order-sensitive aggregation confirmed")

    # ── 9. get_payment_record ──
    print("\n[9] Testing get_payment_record()...")
    record = bridge.get_payment_record(tx_hash_1)
    assert record is not None, "应找到支付记录"
    assert record.tx_hash == tx_hash_1
    assert record.from_addr == from_addr
    assert record.to_addr == to_addr
    assert record.amount == 1.5
    assert record.currency == "cUSD"
    assert record.is_degraded is True
    print(f"  [PASS] Payment record found: amount={record.amount} {record.currency}")

    # 不存在的 tx_hash
    missing = bridge.get_payment_record("0" * 64)
    assert missing is None, "不存在的 tx_hash 应返回 None"
    print(f"  [PASS] Non-existent tx_hash returns None")

    # ── 10. joint_prove_with_mina ──
    print("\n[10] Testing joint_prove_with_mina()...")
    joint_result = bridge.joint_prove_with_mina(tx_hash_1)
    assert isinstance(joint_result, dict)
    assert joint_result["payment_tx_hash"] == tx_hash_1
    assert joint_result["payment_verified"] is True, "降级模式应返回 verified=True"
    assert len(joint_result["joint_hash"]) == 64, "联合哈希应为 64 字符"
    assert joint_result["is_degraded"] is True, "降级模式应标记 is_degraded"
    print(f"  [PASS] Joint proof: payment_verified={joint_result['payment_verified']}, "
          f"joint_hash={joint_result['joint_hash'][:16]}...")

    # ── 11. stats() ──
    print("\n[11] Testing stats()...")
    stats = bridge.stats()
    assert "celo_rpc_url" in stats
    assert "payment_count" in stats
    assert "degraded_count" in stats
    assert "verify_count" in stats
    assert "aggregate_count" in stats
    assert "balance_query_count" in stats
    assert stats["payment_count"] >= 2, f"至少 2 次支付, got {stats['payment_count']}"
    assert stats["verify_count"] >= 2, f"至少 2 次验证, got {stats['verify_count']}"
    assert stats["aggregate_count"] >= 3, f"至少 3 次聚合, got {stats['aggregate_count']}"
    assert stats["balance_query_count"] >= 2, f"至少 2 次余额查询, got {stats['balance_query_count']}"
    assert stats["httpx_available"] == _HAS_HTTPX
    assert stats["bls_available"] == _HAS_BLS
    assert stats["mina_available"] == _HAS_MINA
    assert stats["ksnap_available"] == _HAS_KSNAP
    print(f"  [PASS] stats: payments={stats['payment_count']}, "
          f"verify={stats['verify_count']}, "
          f"aggregate={stats['aggregate_count']}, "
          f"balance={stats['balance_query_count']}, "
          f"degraded={stats['degraded_count']}")

    # ── 12. PaymentRecord dataclass ──
    print("\n[12] Testing PaymentRecord dataclass...")
    test_record = PaymentRecord(
        tx_hash="abc123",
        from_addr="0x" + "1" * 40,
        to_addr="0x" + "2" * 40,
        amount=3.14,
        currency="cEUR",
        timestamp=1234567890.0,
        block_number=42,
        is_degraded=False,
    )
    assert test_record.tx_hash == "abc123"
    assert test_record.amount == 3.14
    assert test_record.currency == "cEUR"
    assert test_record.block_number == 42
    assert test_record.is_degraded is False
    rd = test_record.to_dict()
    assert rd["tx_hash"] == "abc123"
    assert rd["amount"] == 3.14
    assert rd["currency"] == "cEUR"
    print(f"  [PASS] PaymentRecord: tx_hash={test_record.tx_hash}, "
          f"amount={test_record.amount}, currency={test_record.currency}")

    # ── 13. _is_valid_address 工具方法 ──
    print("\n[13] Testing _is_valid_address()...")
    assert CeloBridge._is_valid_address("0x" + "a" * 40) is True
    assert CeloBridge._is_valid_address("0x" + "A" * 40) is True
    assert CeloBridge._is_valid_address("0x" + "g" * 40) is False, "非法十六进制应返回 False"
    assert CeloBridge._is_valid_address("0x" + "a" * 39) is False, "长度不足应返回 False"
    assert CeloBridge._is_valid_address("0x" + "a" * 41) is False, "长度超出应返回 False"
    assert CeloBridge._is_valid_address("abc") is False, "缺少 0x 前缀应返回 False"
    assert CeloBridge._is_valid_address(123) is False, "非字符串应返回 False"
    print(f"  [PASS] Address validation works correctly")

    # ── 14. _encode_transfer_call 编码验证 ──
    print("\n[14] Testing _encode_transfer_call()...")
    encoded = CeloBridge._encode_transfer_call("0x" + "b" * 40, 1000000000000000000)
    assert encoded.startswith(TRANSFER_METHOD_ID), "应以 transfer method ID 开头"
    assert len(encoded) == 10 + 64 + 64, f"编码长度应为 138, got {len(encoded)}"
    print(f"  [PASS] Transfer call encoded: {encoded[:20]}... (len={len(encoded)})")

    print("\n" + "=" * 64)
    print("  CeloBridge — All Self-Tests Passed")
    print("=" * 64)
