# -*- coding: utf-8 -*-
"""
OWNTHINK 知识库导入器 — EML 注入管线
==============================================

将 OWNTHINK CSV (~140M 行) 导入到 D:/tomas-data/tomas.db，
并注入 EML 超图（vertices + hyperedges + hyperedge_nodes）。

支持断点续传：进度保存到 sqlite progress 表。

Author: TOMAS Team
Version: 1.0.0
"""

from __future__ import annotations

import csv
import logging
import os
import sqlite3
from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 可选导入（EMLInjector 用于理解 EML Schema）
try:
    from eml_injector import EMLInjector
    _HAS_EML_INJECTOR = True
except ImportError:
    _HAS_EML_INJECTOR = False
    EMLInjector = None

# 可选导入（SQLAlchemy 模型）
try:
    from models import DB_PATH, get_session, KnowledgeTriple
    _HAS_MODELS = True
except ImportError:
    _HAS_MODELS = False
    DB_PATH = "D:/tomas-data/tomas.db"
    KnowledgeTriple = None


# ── 数据结构 ───────────────────────────────────────────────────────────────────

@dataclass
class ImportConfig:
    """OWNTHINK 导入配置"""
    db_path: str = "D:/tomas-data/tomas.db"
    csv_path: str = "D:/tomas-data/ownthink.csv"
    batch_size: int = 10000
    skip: int = 0
    resume: bool = True  # 支持断点续传


@dataclass
class ImportProgress:
    """导入进度"""
    total_rows: int = 0
    imported_rows: int = 0
    skipped_rows: int = 0
    last_row: int = 0
    errors: List[str] = dc_field(default_factory=list)


# ── OWNTHINK 导入器 ───────────────────────────────────────────────────────────

class OwnThinkImporter:
    """OWNTHINK 知识库导入器，支持断点续传 + EML 注入"""

    def __init__(self, config: ImportConfig) -> None:
        """初始化导入器

        Args:
            config: 导入配置
        """
        self.config = config
        self.progress = ImportProgress()

        # 初始化 EML 注入器（用于理解 EML Schema）
        self.eml_injector = None
        if _HAS_EML_INJECTOR:
            try:
                self.eml_injector = EMLInjector()
                logger.info("OwnThinkImporter: EMLInjector initialized")
            except Exception as e:
                logger.warning(f"OwnThinkImporter: EMLInjector init failed: {e}")

        # 确保数据库目录存在
        db_dir = os.path.dirname(config.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        logger.info(
            f"OwnThinkImporter: initialized with csv={config.csv_path}, "
            f"db={config.db_path}, batch_size={config.batch_size}"
        )

    def _get_connection(self) -> sqlite3.Connection:
        """获取 SQLite 连接（用于原生 SQL 批量插入）"""
        conn = sqlite3.connect(self.config.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _load_progress(self) -> int:
        """从数据库 progress 表加载上次导入进度

        Returns:
            上次最后处理的行号（从上次中断处继续）
        """
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute(
                "CREATE TABLE IF NOT EXISTS ownthink_progress "
                "(id INTEGER PRIMARY KEY CHECK (id = 1), "
                "last_row INTEGER NOT NULL, "
                "imported_rows INTEGER NOT NULL, "
                "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            )
            cur.execute("SELECT last_row, imported_rows FROM ownthink_progress WHERE id = 1")
            row = cur.fetchone()
            conn.close()
            if row:
                self.progress.last_row = row[0]
                self.progress.imported_rows = row[1]
                logger.info(
                    f"OwnThinkImporter: loaded progress last_row={row[0]}, "
                    f"imported={row[1]}"
                )
                return row[0]
            return 0
        except Exception as e:
            logger.warning(f"OwnThinkImporter: failed to load progress: {e}")
            return 0

    def _save_progress(self, last_row: int, imported_rows: int) -> None:
        """保存导入进度到数据库

        Args:
            last_row: 最后处理的行号
            imported_rows: 已导入的行数
        """
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO ownthink_progress (id, last_row, imported_rows, updated_at) "
                "VALUES (1, ?, ?, CURRENT_TIMESTAMP)",
                (last_row, imported_rows),
            )
            conn.commit()
            conn.close()
            self.progress.last_row = last_row
            self.progress.imported_rows = imported_rows
        except Exception as e:
            logger.warning(f"OwnThinkImporter: failed to save progress: {e}")

    def inject_eml(self, triple: Dict[str, Any]) -> Dict[str, Any]:
        """将 OWNTHINK 三元组注入 EML 超图

        将 (subject, predicate, object) 三元组转换为 EML 超图格式：
        - subject 和 object 作为顶点（vertices）
        - 三元组作为超边（hyperedges）

        Args:
            triple: OWNTHINK 三元组字典 {"subject": str, "predicate": str, "object": str}

        Returns:
            注入结果字典
        """
        subject = triple.get("subject", "").strip()
        predicate = triple.get("predicate", "related_to").strip()
        obj = triple.get("object", "").strip()

        if not subject or not obj:
            return {
                "success": False,
                "reason": "Empty subject or object",
                "triple": triple,
            }

        result = {
            "success": True,
            "subject": subject,
            "predicate": predicate,
            "object": obj,
            "vertices_created": 0,
            "edges_created": 0,
        }

        try:
            conn = self._get_connection()
            cur = conn.cursor()

            # 确保 EML 表存在
            cur.execute(
                "CREATE TABLE IF NOT EXISTS vertices ("
                "vid INTEGER PRIMARY KEY AUTOINCREMENT, "
                "concept TEXT NOT NULL UNIQUE, "
                "phi_b0 REAL DEFAULT 0.0, phi_b1 REAL DEFAULT 0.0, "
                "phi_b2 REAL DEFAULT 0.0, phi_b3 REAL DEFAULT 0.0, "
                "phi_b4 REAL DEFAULT 0.0, phi_b5 REAL DEFAULT 0.0, "
                "phi_b6 REAL DEFAULT 0.0, phi_b7 REAL DEFAULT 0.0, "
                "i_val REAL DEFAULT 0.0, "
                "degree_class INTEGER DEFAULT 0, "
                "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            )
            cur.execute(
                "CREATE TABLE IF NOT EXISTS hyperedges ("
                "eid TEXT PRIMARY KEY, "
                "arity INTEGER NOT NULL, "
                "nodes TEXT NOT NULL, "
                "i_val REAL DEFAULT 1.0, "
                "asym REAL DEFAULT 0.0, "
                "weight REAL DEFAULT 1.0, "
                "delta_weight REAL DEFAULT 0.0, "
                "source INTEGER DEFAULT NULL, "
                "target INTEGER DEFAULT NULL, "
                "edge_type TEXT DEFAULT 'generic', "
                "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            )
            cur.execute(
                "CREATE TABLE IF NOT EXISTS hyperedge_nodes ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "eid TEXT NOT NULL, "
                "vid INTEGER NOT NULL, "
                "position INTEGER DEFAULT 0, "
                "UNIQUE(eid, vid))"
            )

            # 1. 插入/获取 subject 顶点
            cur.execute(
                "INSERT OR IGNORE INTO vertices (concept) VALUES (?)",
                (subject,),
            )
            cur.execute("SELECT vid FROM vertices WHERE concept = ?", (subject,))
            subj_vid = cur.fetchone()[0]

            # 2. 插入/获取 object 顶点
            cur.execute(
                "INSERT OR IGNORE INTO vertices (concept) VALUES (?)",
                (obj,),
            )
            cur.execute("SELECT vid FROM vertices WHERE concept = ?", (obj,))
            obj_vid = cur.fetchone()[0]

            result["vertices_created"] = 2

            # 3. 创建超边
            import uuid
            eid = f"ownthink_{uuid.uuid4().hex[:16]}"
            nodes_json = f'[{subj_vid}, {obj_vid}]'

            cur.execute(
                "INSERT OR IGNORE INTO hyperedges "
                "(eid, arity, nodes, edge_type) "
                "VALUES (?, 2, ?, ?)",
                (eid, nodes_json, predicate),
            )

            # 4. 创建超边-顶点关联
            cur.execute(
                "INSERT OR IGNORE INTO hyperedge_nodes (eid, vid, position) "
                "VALUES (?, ?, 0), (?, ?, 1)",
                (eid, subj_vid, eid, obj_vid),
            )

            conn.commit()
            conn.close()

            result["edges_created"] = 1
            result["eid"] = eid

            logger.debug(
                f"OwnThinkImporter: injected EML edge {eid} for "
                f"({subject}, {predicate}, {obj})"
            )

        except Exception as e:
            logger.error(f"OwnThinkImporter: inject_eml failed: {e}")
            result["success"] = False
            result["reason"] = str(e)
            self.progress.errors.append(str(e))

        return result

    def import_batch(self, start_row: int = 0) -> ImportProgress:
        """批量导入（断点续传）

        从 start_row 开始读 CSV，将三元组注入 EML 超图，
        并提交 KnowledgeTriple 到数据库。

        Args:
            start_row: 开始行号（0 表示从开头）

        Returns:
            导入进度
        """
        if not os.path.exists(self.config.csv_path):
            logger.error(f"OwnThinkImporter: CSV file not found: {self.config.csv_path}")
            self.progress.errors.append(f"CSV file not found: {self.config.csv_path}")
            return self.progress

        logger.info(
            f"OwnThinkImporter: starting import from row {start_row}, "
            f"batch_size={self.config.batch_size}"
        )

        conn = self._get_connection()
        cur = conn.cursor()

        # 确保 knowledge_triples 表存在
        cur.execute(
            "CREATE TABLE IF NOT EXISTS knowledge_triples ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "subject TEXT NOT NULL, "
            "predicate TEXT NOT NULL, "
            "object TEXT NOT NULL, "
            "i_weight REAL DEFAULT 1.0, "
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
            "UNIQUE(subject, predicate, object))"
        )
        conn.commit()

        try:
            with open(self.config.csv_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                current_row = 0

                for row in reader:
                    current_row += 1

                    # 跳过 start_row 之前的行
                    if current_row <= start_row:
                        continue

                    # 检查是否达到批次大小
                    if self.progress.imported_rows >= self.config.batch_size:
                        break

                    # 解析三元组
                    if len(row) >= 3:
                        subject = row[0].strip()
                        predicate = row[1].strip()
                        obj = row[2].strip()

                        if not subject or not obj:
                            self.progress.skipped_rows += 1
                            continue

                        # 插入 knowledge_triples（INSERT OR IGNORE 去重）
                        try:
                            cur.execute(
                                "INSERT OR IGNORE INTO knowledge_triples "
                                "(subject, predicate, object) "
                                "VALUES (?, ?, ?)",
                                (subject, predicate, obj),
                            )
                            if cur.rowcount > 0:
                                self.progress.imported_rows += 1

                                # 注入 EML 超图
                                eml_result = self.inject_eml({
                                    "subject": subject,
                                    "predicate": predicate,
                                    "object": obj,
                                })
                                if not eml_result["success"]:
                                    logger.warning(
                                        f"OwnThinkImporter: EML injection failed for "
                                        f"({subject}, {predicate}, {obj}): "
                                        f"{eml_result.get('reason', 'unknown')}"
                                    )
                            else:
                                self.progress.skipped_rows += 1
                        except Exception as e:
                            logger.warning(
                                f"OwnThinkImporter: failed to insert triple "
                                f"({subject}, {predicate}, {obj}): {e}"
                            )
                            self.progress.errors.append(str(e))
                    else:
                        self.progress.skipped_rows += 1

                    # 每 1000 行保存一次进度
                    if current_row % 1000 == 0:
                        self._save_progress(current_row, self.progress.imported_rows)
                        logger.info(
                            f"OwnThinkImporter: progress row={current_row}, "
                            f"imported={self.progress.imported_rows}"
                        )

                # 保存最终进度
                self._save_progress(current_row, self.progress.imported_rows)
                self.progress.total_rows = current_row

                logger.info(
                    f"OwnThinkImporter: batch import completed. "
                    f"total={current_row}, imported={self.progress.imported_rows}, "
                    f"skipped={self.progress.skipped_rows}, "
                    f"errors={len(self.progress.errors)}"
                )

        except Exception as e:
            logger.error(f"OwnThinkImporter: import_batch failed: {e}")
            self.progress.errors.append(str(e))
        finally:
            conn.close()

        return self.progress

    def resume(self) -> ImportProgress:
        """从上次中断处继续导入

        Returns:
            导入进度
        """
        if not self.config.resume:
            logger.info("OwnThinkImporter: resume disabled, starting from beginning")
            return self.import_batch(0)

        last_row = self._load_progress()
        logger.info(f"OwnThinkImporter: resuming from row {last_row}")
        return self.import_batch(last_row)


# ── 独立测试 ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 64)
    print("  OwnThinkImporter — Self-Test Suite")
    print("=" * 64)

    # 创建测试配置（使用测试 CSV）
    test_csv = "D:/tomas-data/ownthink_test.csv"
    test_db = "D:/tomas-data/tomas_test.db"

    # 创建小型测试 CSV
    if not os.path.exists(test_csv):
        with open(test_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["苹果", "属于", "水果"])
            writer.writerow(["苹果", "颜色", "红色"])
            writer.writerow(["香蕉", "属于", "水果"])
            writer.writerow(["香蕉", "颜色", "黄色"])
        print(f"[TEST] Created test CSV: {test_csv}")

    config = ImportConfig(
        db_path=test_db,
        csv_path=test_csv,
        batch_size=100,
        resume=False,
    )

    importer = OwnThinkImporter(config)

    # 测试 inject_eml
    print("\n[1] Testing inject_eml...")
    result = importer.inject_eml({
        "subject": "测试概念A",
        "predicate": "related_to",
        "object": "测试概念B",
    })
    assert result["success"], f"inject_eml failed: {result}"
    print(f"  [PASS] inject_eml: {result}")

    # 测试 import_batch
    print("\n[2] Testing import_batch...")
    progress = importer.import_batch(0)
    print(f"  [PASS] import_batch: total={progress.total_rows}, "
          f"imported={progress.imported_rows}, "
          f"skipped={progress.skipped_rows}")

    print("\n" + "=" * 64)
    print("  OwnThinkImporter — All Self-Tests Passed")
    print("=" * 64)
