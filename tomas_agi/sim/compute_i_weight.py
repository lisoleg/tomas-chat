# -*- coding: utf-8 -*-
"""
i_weight 后计算脚本（修复版 v4.1）
==============================================

在 OwnThink 导入完成后运行，为所有 i_weight = 1.0（默认值）的行计算 κ-gate 语义权重。

公式: i_weight = 1.0 + ln(1 + subject_freq) / 10.0
  - subject_freq = 该主体在 knowledge_triples 中的出现次数

v4.1 修复:
  - SELECT 加 WHERE i_weight = 1.0 过滤（只扫待计算行）
  - 批次大小降至 500（减少持锁时间）
  - 加 database is locked 重试逻辑（指数退避）
  - 每 10 批做一次 WAL checkpoint（防止 WAL 无限增长）

用法:
    python compute_i_weight.py
    python compute_i_weight.py --dry-run
    python compute_i_weight.py --batch 500

Author: TOMAS Team
"""

from __future__ import annotations

import argparse
import math
import os
import sqlite3
import sys
import time

DB_PATH = os.environ.get("TOMAS_DB_PATH", "D:/tomas-data/tomas.db")
DEFAULT_BATCH_SIZE = 500   # 每批 UPDATE 的 subject 数（更小 = 持锁更短）
DEFAULT_I_WEIGHT = 1.0
CHECKPOINT_INTERVAL = 10  # 每 N 批做一次 WAL checkpoint


def _execute_with_retry(conn, sql, params, max_retries=5):
    """带锁重试的执行（指数退避）"""
    for attempt in range(max_retries):
        try:
            if isinstance(params, (list, tuple)):
                return conn.execute(sql, params)
            else:
                return conn.execute(sql)
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < max_retries - 1:
                wait = 2 ** attempt  # 1s, 2s, 4s, 8s, 16s
                print(f"    ⏳ DB 锁重试 {attempt+1}/{max_retries}，等待 {wait}s: {e}")
                time.sleep(wait)
                continue
            raise


def _executemany_with_retry(conn, sql, batch, max_retries=5):
    """带锁重试的 executemany"""
    for attempt in range(max_retries):
        try:
            conn.executemany(sql, batch)
            return
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"    ⏳ DB 锁重试 {attempt+1}/{max_retries}，等待 {wait}s: {e}")
                time.sleep(wait)
                continue
            raise


def compute_i_weight(
    db_path: str = DB_PATH,
    batch_size: int = DEFAULT_BATCH_SIZE,
    dry_run: bool = False,
):
    """
    单遍索引顺序扫描，计算所有行的 i_weight。
    利用 subject 索引 + WHERE i_weight=1.0 过滤，只扫待计算行。
    """
    print("=" * 60)
    print("  i_weight 后计算（κ-Gate 语义权重）— 索引扫描版 v4.1")
    print("=" * 60)
    print(f"  数据库: {db_path}")
    print(f"  批次大小: {batch_size:,} subjects/batch")
    print(f"  模式: {'DRY RUN（只统计）' if dry_run else 'UPDATE（实际更新）'}")
    print()

    if not os.path.exists(db_path):
        print(f"  ❌ 数据库不存在: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path, timeout=300)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=300000")   # 5 分钟
        conn.execute("PRAGMA cache_size=-500000")      # 500MB 缓存
        conn.execute("PRAGMA temp_store=0")           # 临时表用磁盘
        # 禁用 autocommit，手动控制事务（事务在内层按需开启）
        conn.isolation_level = None

        # 1. 统计总行数和待计算行数（读操作，不需要事务）
        start = time.time()
        total_count = _execute_with_retry(
            conn, "SELECT COUNT(*) FROM knowledge_triples", None
        ).fetchone()[0]
        pending_count = _execute_with_retry(
            conn,
            "SELECT COUNT(*) FROM knowledge_triples WHERE ABS(i_weight - 1.0) < 0.0001",
            ()
        ).fetchone()[0]

        print(f"  总行数:        {total_count:>12,}")
        print(f"  待计算行数:    {pending_count:>12,}")
        print(f"  已有 i_weight:  {total_count - pending_count:>12,}")
        print()

        if pending_count == 0:
            print("  ✅ 所有行已有 i_weight，无需计算")
            conn.close()
            return

        if dry_run:
            # Dry run: 统计前 10 个 subject 的频率
            print("  [DRY RUN] 扫描前 10 个 subject 的频率...")
            cur = _execute_with_retry(
                conn,
            "SELECT subject, COUNT(*) as cnt FROM knowledge_triples "
            "WHERE ABS(i_weight - 1.0) < 0.0001 GROUP BY subject ORDER BY subject LIMIT 10",
            ()
            )
            for row in cur:
                s, cnt = row[0], row[1]
                iw = 1.0 + math.log(1.0 + cnt) / 10.0
                print(f"    {s[:40]:40s} freq={cnt:>6}  i_weight={iw:.4f}")
            print(f"  [DRY RUN] 结束（未实际更新）")
            conn.close()
            return

        # 2. 索引顺序扫描（只扫 i_weight=1.0 的行）
        print("  🔄 索引顺序扫描 + 批量 UPDATE...")
        print("  （利用 idx_kt_subject + i_weight 过滤，只扫待计算行）")
        print()

        # 用索引扫描：subject 有序，且只取 i_weight=1.0 的行
        # 技巧：GROUP BY subject 利用索引，一次性拿到每个 subject 的频率
        # 但由于 GROUP BY 可能 OOM，改逐行扫描 + 内存计数（O(distinct subjects) 内存）
        # 如果 distinct subjects 太多（3000万），还是会 OOM
        #
        # 最终方案：按 subject 前缀分批（每个前缀组独立处理，内存 O(1)）
        # 用 SUBSTR(subject,1,2) 前缀，约 1 万个前缀组，每组 ~1 万 subject
        print("  📋 方案: 按 subject 前缀分批（前缀长度=2，约 1 万组）")
        print("  （每组独立扫描 + UPDATE，内存 O(1)，无 OOM 风险）")
        print()

        total_subjects_updated = 0
        total_rows_updated = 0
        checkpoint_batch = 0
        last_report = time.time()
        t0 = time.time()

        # 获取所有待处理的前缀（DISTINCT SUBSTR 很快，因为用了索引）
        prefixes = []
        cur = _execute_with_retry(
            conn,
            "SELECT DISTINCT SUBSTR(subject, 1, 2) "
            "FROM knowledge_triples WHERE ABS(i_weight - 1.0) < 0.0001 AND subject IS NOT NULL",
            ()
        )
        for row in cur:
            prefixes.append(row[0])
        # 无需 ROLLBACK：isolation_level=None 时 SELECT 不在事务中
        print(f"  📊 前缀数: {len(prefixes):,}")
        print()

        for prefix_idx, prefix in enumerate(prefixes):
            # 确保没有活跃事务（SELECT 可能开启了隐式事务）
            try:
                conn.execute("ROLLBACK")
            except:
                pass
            # 为当前前缀开启写事务
            conn.execute("BEGIN IMMEDIATE")

            # 扫描该前缀的所有 subject（利用索引，ORDER BY subject）
            cur = _execute_with_retry(
                conn,
                "SELECT subject FROM knowledge_triples "
                "WHERE ABS(i_weight - 1.0) < 0.0001 AND subject LIKE ? "
                "ORDER BY subject",
                (prefix + "%",)
            )

            current_subject = None
            current_count = 0
            batch = []

            for row in cur:
                subject = row[0]

                if subject != current_subject:
                    if current_subject is not None:
                        iw = 1.0 + math.log(1.0 + current_count) / 10.0
                        batch.append((iw, current_subject))
                        if len(batch) >= batch_size:
                            _executemany_with_retry(
                                conn,
                                "UPDATE knowledge_triples SET i_weight = ? WHERE subject = ? AND ABS(i_weight - 1.0) < 0.0001",
                                batch
                            )
                            conn.execute("COMMIT")
                            checkpoint_batch += 1
                            batch = []
                            # 重新开启事务
                            conn.execute("BEGIN IMMEDIATE")
                    current_subject = subject
                    current_count = 1
                else:
                    current_count += 1

            # 处理最后一个 subject
            if current_subject is not None:
                iw = 1.0 + math.log(1.0 + current_count) / 10.0
                batch.append((iw, current_subject))

            # 处理批次尾部
            if batch:
                _executemany_with_retry(
                    conn,
                    "UPDATE knowledge_triples SET i_weight = ? WHERE subject = ? AND ABS(i_weight - 1.0) < 0.0001",
                    batch
                )
                conn.execute("COMMIT")
                checkpoint_batch += 1
                total_rows_updated += len(batch)  # 实际更新行数
                batch = []
            
            # 定期 WAL checkpoint（防止 WAL 文件无限增长）
            if checkpoint_batch >= CHECKPOINT_INTERVAL:
                conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
                checkpoint_batch = 0

            # 进度报告
            now = time.time()
            if now - last_report >= 10.0 or prefix_idx == len(prefixes) - 1:
                elapsed = now - t0
                pct = (prefix_idx + 1) / len(prefixes) * 100
                rate = (prefix_idx + 1) / elapsed if elapsed > 0 else 0
                remaining = (len(prefixes) - prefix_idx - 1) / rate if rate > 0 else 0
                print(
                    f"  📊 前缀 {prefix_idx+1:,}/{len(prefixes):,} "
                    f"({pct:.1f}%) | {rate:.1f} 前缀/s | ETA {remaining/60:.1f}min "
                    f"| prefix={prefix!r}"
                )
                last_report = now

        t1 = time.time()
        print()
        print(f"  ✅ 完成！共更新 {total_rows_updated:,} 行")
        print(f"  耗时: {t1 - t0:.1f}s")
        print()

    except Exception as e:
        print(f"  ❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        try:
            conn.execute("ROLLBACK")
        except:
            pass
        sys.exit(1)
    finally:
        try:
            conn.close()
        except:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="i_weight 后计算（κ-Gate 语义权重）")
    parser.add_argument("--db", default=DB_PATH, help="数据库路径")
    parser.add_argument("--batch", type=int, default=DEFAULT_BATCH_SIZE, help="批次大小")
    parser.add_argument("--dry-run", action="store_true", help="Dry run（不实际更新）")
    parser.add_argument("--prefix-len", type=int, default=2, help="前缀长度（默认 2）")
    args = parser.parse_args()

    compute_i_weight(
        db_path=args.db,
        batch_size=args.batch,
        dry_run=args.dry_run,
    )
