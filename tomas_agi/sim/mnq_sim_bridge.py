"""
金灵球仿真器 v3.1 桥接 (MNQ-GSB Bridge)
=========================================

将金灵球仿真器 (mnq-golden-spirit-ball-simulator) 的实验能力
接入 TOMAS 后端，通过子进程调用仿真器并解析输出转换为 TOMAS EML 格式。

核心类:
    GoldenSpiritBallBridge — 金灵球仿真器桥接器

方法:
    run_experiment(config) -> RunResult   启动金灵球实验
    parse_output(raw) -> EMLGraph         结果解析 → TOMAS EML 格式
    get_status(run_id) -> dict            查询实验状态

作者: TOMAS 团队
日期: 2026-06-21
版本: v3.1
"""

import hashlib
import json
import logging
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ============================================================
# 数据结构
# ============================================================

@dataclass
class RunResult:
    """金灵球实验运行结果。

    Attributes:
        run_id:          运行唯一标识
        status:          运行状态 ('running' | 'completed' | 'failed')
        output:          仿真器原始输出文本
        eml_graph:       解析后的 EML 超图（若成功）
        error:           错误信息（若失败）
        started_at:      启动时间戳
        completed_at:    完成时间戳
    """
    run_id: str
    status: str = "running"
    output: str = ""
    eml_graph: Optional[Any] = None
    error: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0


@dataclass
class EMLGraph:
    """TOMAS EML 超图格式。

    Attributes:
        vertices:   顶点列表 [{'id', 'concept', 'octonion', 'delta'}]
        edges:      超边列表 [{'edge_id', 'nodes', 'i_value', 'edge_type'}]
        metadata:   元数据 {'run_id', 'simulator', 'timestamp'}
    """
    vertices: List[Dict] = field(default_factory=list)
    edges: List[Dict] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


# ============================================================
# 金灵球仿真器桥接器
# ============================================================

class GoldenSpiritBallBridge:
    """
    金灵球仿真器桥接器: 连接 mnq-golden-spirit-ball-simulator

    通过子进程调用金灵球仿真器 CLI，解析 JSON 输出，
    转换为 TOMAS EML 超图格式。

    支持两种模式:
        1. 实际模式: 调用 sim/mnq_gsb_sim/ 子模块（需 submodule 初始化）
        2. 模拟模式: 无 submodule 时使用内置模拟器（用于测试）
    """

    # 仿真器 CLI 路径（相对于 sim/ 目录）
    SIMULATOR_PATH = os.path.join(os.path.dirname(__file__), "mnq_gsb_sim", "run_sim.py")

    def __init__(self, use_mock: bool = False):
        """初始化桥接器。

        Args:
            use_mock: 是否使用模拟模式（无真实仿真器时）
        """
        self.use_mock = use_mock
        self._runs: Dict[str, RunResult] = {}

        # 检测仿真器可用性
        self._simulator_available = os.path.exists(self.SIMULATOR_PATH)
        if not self._simulator_available and not self.use_mock:
            logger.warning(
                "金灵球仿真器 submodule 未初始化，自动切换为模拟模式"
            )
            self.use_mock = True

        logger.info(
            "GoldenSpiritBallBridge 初始化: mock=%s, sim_available=%s",
            self.use_mock, self._simulator_available,
        )

    def run_experiment(self, config: Dict) -> RunResult:
        """
        启动金灵球实验

        Args:
            config: 实验配置字典，包含:
                - experiment_type: 实验类型 ('spin' | 'energy' | 'phi_field')
                - parameters: 实验参数 {'temperature', 'spin_count', ...}
                - duration: 实验持续时间 (秒)

        Returns:
            RunResult: 实验运行结果
        """
        run_id = f"gsb_{uuid.uuid4().hex[:12]}"
        started_at = time.time()

        logger.info("启动金灵球实验: run_id=%s, config=%s", run_id, config)

        if self.use_mock:
            result = self._run_mock_experiment(run_id, config, started_at)
        else:
            result = self._run_real_experiment(run_id, config, started_at)

        self._runs[run_id] = result
        return result

    def _run_mock_experiment(
        self, run_id: str, config: Dict, started_at: float
    ) -> RunResult:
        """模拟模式: 生成模拟实验结果"""
        exp_type = config.get("experiment_type", "spin")
        params = config.get("parameters", {})
        duration = config.get("duration", 10)

        # 模拟仿真器 JSON 输出
        n_concepts = params.get("spin_count", 8)
        n_relations = max(1, n_concepts // 2)

        mock_output = {
            "experiment_id": run_id,
            "type": exp_type,
            "status": "completed",
            "results": {
                "concepts": [
                    {
                        "id": i,
                        "name": f"gsb_{exp_type}_concept_{i}",
                        "phi_field": np.random.randn(8).tolist(),
                        "info_existence": 0.3 + 0.7 * np.random.rand(),
                        "spin_energy": 0.1 * np.random.rand(),
                    }
                    for i in range(n_concepts)
                ],
                "relations": [
                    {
                        "source": i,
                        "target": (i + 1) % n_concepts,
                        "type": "golden_spirit_link",
                        "strength": 0.5 + 0.5 * np.random.rand(),
                    }
                    for i in range(n_relations)
                ],
                "metadata": {
                    "simulator": "mnq-gsb-v3.1-mock",
                    "timestamp": time.time(),
                    "duration": duration,
                },
            },
        }

        raw_output = json.dumps(mock_output, ensure_ascii=False)
        eml_graph = self.parse_output(raw_output)

        completed_at = time.time()

        return RunResult(
            run_id=run_id,
            status="completed",
            output=raw_output,
            eml_graph=eml_graph,
            error="",
            started_at=started_at,
            completed_at=completed_at,
        )

    def _run_real_experiment(
        self, run_id: str, config: Dict, started_at: float
    ) -> RunResult:
        """实际模式: 子进程调用金灵球仿真器"""
        try:
            # 构建命令行参数
            args = [
                sys.executable,
                self.SIMULATOR_PATH,
                "--experiment-type", config.get("experiment_type", "spin"),
                "--output-format", "json",
                "--run-id", run_id,
            ]

            # 添加参数
            for key, value in config.get("parameters", {}).items():
                args.extend([f"--{key}", str(value)])

            duration = config.get("duration", 10)
            args.extend(["--duration", str(duration)])

            # 执行子进程
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=max(duration * 2, 30),
                cwd=os.path.dirname(self.SIMULATOR_PATH),
            )

            completed_at = time.time()

            if proc.returncode != 0:
                return RunResult(
                    run_id=run_id,
                    status="failed",
                    output=proc.stderr,
                    eml_graph=None,
                    error=f"仿真器返回非零退出码: {proc.returncode}",
                    started_at=started_at,
                    completed_at=completed_at,
                )

            raw_output = proc.stdout
            eml_graph = self.parse_output(raw_output)

            return RunResult(
                run_id=run_id,
                status="completed",
                output=raw_output,
                eml_graph=eml_graph,
                error="",
                started_at=started_at,
                completed_at=completed_at,
            )

        except subprocess.TimeoutExpired:
            return RunResult(
                run_id=run_id,
                status="failed",
                output="",
                eml_graph=None,
                error="仿真器执行超时",
                started_at=started_at,
                completed_at=time.time(),
            )
        except Exception as e:
            logger.error("金灵球仿真器执行异常: %s", e)
            return RunResult(
                run_id=run_id,
                status="failed",
                output="",
                eml_graph=None,
                error=str(e),
                started_at=started_at,
                completed_at=time.time(),
            )

    def parse_output(self, raw: str) -> EMLGraph:
        """
        解析金灵球仿真器输出，转换为 TOMAS EML 格式

        解析流程:
        1. 解析 JSON 输出
        2. 提取概念 (concepts) → EML 顶点
        3. 提取关系 (relations) → EML 超边
        4. 构建 EML 超图结构

        Args:
            raw: 仿真器原始 JSON 输出字符串

        Returns:
            EMLGraph: TOMAS EML 超图
        """
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error("金灵球输出解析失败: %s", e)
            return EMLGraph(metadata={"error": str(e)})

        results = data.get("results", {})
        concepts = results.get("concepts", [])
        relations = results.get("relations", [])
        meta = results.get("metadata", {})

        # 转换概念 → EML 顶点
        vertices = []
        for c in concepts:
            vertex = {
                "id": c.get("id", 0),
                "concept": c.get("name", f"concept_{c.get('id', 0)}"),
                "octonion": c.get("phi_field", [0.0] * 8),
                "delta": c.get("info_existence", 0.5),
                "info_existence": c.get("info_existence", 0.5),
                "spin_energy": c.get("spin_energy", 0.0),
            }
            vertices.append(vertex)

        # 转换关系 → EML 超边
        edges = []
        for r in relations:
            src_id = r.get("source", 0)
            dst_id = r.get("target", 0)
            edge = {
                "edge_id": f"gsb_{src_id}_{dst_id}_{hashlib.md5(
                    f'{src_id}-{dst_id}'.encode()
                ).hexdigest()[:8]}",
                "nodes": [src_id, dst_id],
                "i_value": r.get("strength", 0.5),
                "edge_type": r.get("type", "golden_spirit_link"),
            }
            edges.append(edge)

        return EMLGraph(
            vertices=vertices,
            edges=edges,
            metadata={
                "run_id": data.get("experiment_id", ""),
                "simulator": meta.get("simulator", "mnq-gsb-v3.1"),
                "timestamp": meta.get("timestamp", time.time()),
                "duration": meta.get("duration", 0),
            },
        )

    def get_status(self, run_id: str) -> Dict:
        """
        查询实验状态

        Args:
            run_id: 运行唯一标识

        Returns:
            状态字典
        """
        result = self._runs.get(run_id)
        if result is None:
            return {"status": "not_found", "run_id": run_id}
        return {
            "run_id": result.run_id,
            "status": result.status,
            "error": result.error,
            "started_at": result.started_at,
            "completed_at": result.completed_at,
            "num_vertices": len(result.eml_graph.vertices) if result.eml_graph else 0,
            "num_edges": len(result.eml_graph.edges) if result.eml_graph else 0,
        }

    def list_runs(self) -> List[Dict]:
        """列出所有实验运行"""
        return [self.get_status(run_id) for run_id in self._runs]


# ============================================================
# 自测
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("=" * 60)
    print("GoldenSpiritBallBridge 自测")
    print("=" * 60)

    bridge = GoldenSpiritBallBridge(use_mock=True)

    # 1. 运行实验
    print("\n[1] 运行金灵球实验...")
    config = {
        "experiment_type": "spin",
        "parameters": {"temperature": 300, "spin_count": 5},
        "duration": 10,
    }
    result = bridge.run_experiment(config)
    print(f"  run_id={result.run_id}, status={result.status}")
    assert result.status == "completed", f"实验应完成，实际: {result.status}"

    if result.eml_graph:
        print(f"  EML 顶点数: {len(result.eml_graph.vertices)}")
        print(f"  EML 超边数: {len(result.eml_graph.edges)}")
        assert len(result.eml_graph.vertices) == 5, "顶点数应为 5"

    # 2. 查询状态
    print("\n[2] 查询实验状态...")
    status = bridge.get_status(result.run_id)
    print(f"  status={status['status']}, num_vertices={status['num_vertices']}")
    assert status["status"] == "completed"

    # 3. 解析输出
    print("\n[3] 测试输出解析...")
    test_json = json.dumps({
        "results": {
            "concepts": [
                {"id": 0, "name": "test_concept", "phi_field": [1, 0, 0, 0, 0, 0, 0, 0],
                 "info_existence": 0.8},
            ],
            "relations": [
                {"source": 0, "target": 0, "type": "self_link", "strength": 0.9},
            ],
            "metadata": {"simulator": "test"},
        },
    })
    parsed = bridge.parse_output(test_json)
    print(f"  parsed vertices: {len(parsed.vertices)}, edges: {len(parsed.edges)}")
    assert len(parsed.vertices) == 1
    assert len(parsed.edges) == 1

    # 4. 列出所有运行
    print("\n[4] 列出运行...")
    runs = bridge.list_runs()
    print(f"  运行数: {len(runs)}")
    assert len(runs) >= 1

    # 5. 未知 run_id
    print("\n[5] 测试未知 run_id...")
    unknown_status = bridge.get_status("nonexistent")
    print(f"  status={unknown_status['status']}")
    assert unknown_status["status"] == "not_found"

    print("\n" + "=" * 60)
    print("GoldenSpiritBallBridge 自测全部通过!")
    print("=" * 60)
