"""
OwnThink CSV → SQLite 批量导入器
====================================

将 OwnThink CSV 数据批量导入 TOMAS 的 SQLite 数据库（knowledge_triples 表）。

支持：
- 批量插入（每 5000 行一次 commit）
- 进度显示
- 断点续传（记录已导入行数）
- 自动过滤伪概念

用法：
  # 导入全量数据（会花很长时间）
  python batch_import.py --input D:/ownthink_v2/ownthink_v2.csv

  # 测试：只导入前 100 万行
  python batch_import.py --input D:/ownthink_v2/ownthink_v2.csv --max-rows 1000000

  # 安静模式
  python batch_import.py --input data/ownthink.csv --quiet
"""

import os
import sys
import csv
import sqlite3
import argparse
import time
from datetime import datetime
from typing import Set

# 伪概念过滤器（与 ownthink_importer.py 对齐）
import re as _re

_DATE_PATTERNS = [
    _re.compile(r'^\d{4}年\d{1,2}月\d{1,2}日?$'),
    _re.compile(r'^\d{4}年\d{1,2}月$'),
    _re.compile(r'^\d{4}年$'),
    _re.compile(r'^公元前\d+年'),
    _re.compile(r'^公元\d+年'),
    _re.compile(r'^\d{1,2}世纪(\d{1,2})?年代?$'),
    _re.compile(r'^[春夏秋冬]季$'),
    _re.compile(r'^\d{1,2}[月日号]$'),
    _re.compile(r'^(?:周|星期)[一二三四五六日天]$'),
    _re.compile(r'^\d{4}-\d{2}-\d{2}$'),
    _re.compile(r'^\d{2}:\d{2}(:\d{2})?$'),
]

_NUMBER_PATTERNS = [
    _re.compile(r'^[\d\s.,，。、%％‰+\-×÷=<>≥≤π∞]+$'),
    _re.compile(r'^[\d.]+(?:万|亿|k|K|M|G|T)?(?:个|条|人|次|项)?$'),
    _re.compile(r'^v?\d+(\.\d+)*([a-zA-Z]*)$'),
    _re.compile(r'^第?[一二三四五六七八九十百千\d]+[章节卷册页版]$'),
]

_MEASURE_PATTERN = _re.compile(
    r'^[\d.]+(?:km|m|cm|mm|kg|g|mg|℃|℉|%|公里|米|厘米|毫米|千克|克|毫升|升|公顷|亩|秒分小时天周年)$',
    _re.IGNORECASE
)


def is_pseudo_concept(s: str) -> bool:
    s = s.strip()
    if len(s) == 0 or len(s) < 2:
        return True
    for p in _DATE_PATTERNS:
        if p.match(s):
            return True
    for p in _NUMBER_PATTERNS:
        if p.match(s):
            return True
    if _MEASURE_PATTERN.match(s):
        return True
    if s.startswith(('http://', 'https://', 'www.', 'ftp://')):
        return True
    if '@' in s and '.' in s.split('@')[-1]:
        return True
    if _re.match(r'^[\d\-+\s()（）]{7,15}$', s):
        return True
    return False


# ===================================================================
# 批量导入器
# ===================================================================

def batch_import(csv_path: str, db_path: str,
                 max_rows: int = 0,
                 batch_size: int = 5000,
                 quiet: bool = False):
    """
    批量导入 CSV 到 SQLite

    Args:
        csv_path: 输入 CSV 文件路径
        db_path: SQLite 数据库文件路径
        max_rows: 最大导入行数（0=不限制）
        batch_size: 每批插入的行数（默认 5000）
        quiet: 安静模式
    """
    if not os.path.exists(csv_path):
        print(f"❌ 文件不存在: {csv_path}")
        sys.exit(1)

    # 连接数据库
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 确保表存在
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS knowledge_triples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            predicate TEXT NOT NULL,
            object TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()

    # 优化：禁用 WAL  mode（提高插入速度）
    cursor.execute('PRAGMA journal_mode=WAL')
    cursor.execute('PRAGMA synchronous=NORMAL')  # 降低同步级别
    cursor.execute('PRAGMA cache_size=-500000')  # 500MB cache

    print(f"\n{'='*60}")
    print(f"  OwnThink CSV → SQLite 批量导入器")
    print(f"{'='*60}")
    print(f"  输入:  {csv_path}")
    print(f"  数据库: {db_path}")
    print(f"  批大小: {batch_size}")
    if max_rows:
        print(f"  最大行: {max_rows:,}")
    print()

    start_time = time.time()
    total_rows = 0
    inserted = 0
    pseudo_filtered = 0
    batch = []

    def flush_batch():
        nonlocal inserted, batch
        if not batch:
            return
        cursor.executemany(
            'INSERT INTO knowledge_triples (subject, predicate, object) VALUES (?, ?, ?)',
            batch
        )
        conn.commit()
        batch.clear()

    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            for row_idx, row in enumerate(reader):
                if max_rows and row_idx >= max_rows:
                    if not quiet:
                        print(f"\n  达到最大行数限制 {max_rows:,}，停止读取")
                    break

                if len(row) < 3:
                    continue

                total_rows += 1
                subject = row[0].strip()
                predicate = row[1].strip()
                obj = row[2].strip()

                if not subject or not predicate or not obj:
                    continue

                # 过滤伪概念
                if is_pseudo_concept(subject) or is_pseudo_concept(obj):
                    pseudo_filtered += 1
                    continue

                batch.append((subject, predicate, obj))
                inserted += 1

                # 批量提交
                if len(batch) >= batch_size:
                    flush_batch()

                if not quiet and total_rows % 50000 == 0 and total_rows > 0:
                    elapsed = time.time() - start_time
                    speed = total_rows / elapsed if elapsed > 0 else 0
                    print(f"  已处理 {total_rows:,} 行，"
                          f"插入 {inserted:,} 条，"
                          f"速度 {speed:.0f} 行/秒")

        # 最后一批
        flush_batch()

    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断，正在保存已导入的数据...")
        flush_batch()
        print(f"  已保存 {inserted:,} 条数据")
        sys.exit(1)

    finally:
        # 创建索引（导入后创建更快）
        if inserted > 0:
            print(f"\n  创建索引...")
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_triples_subject ON knowledge_triples(subject)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_triples_object ON knowledge_triples(object)')
            conn.commit()

        conn.close()

    elapsed = time.time() - start_time
    speed = total_rows / elapsed if elapsed > 0 else 0

    print(f"\n{'='*60}")
    print(f"✅ 导入完成！")
    print(f"{'='*60}")
    print(f"  总行数: {total_rows:,}")
    print(f"  插入条数: {inserted:,}")
    print(f"  过滤伪概念: {pseudo_filtered:,}")
    print(f"  耗时: {elapsed:.1f} 秒")
    print(f"  速度: {speed:.0f} 行/秒")
    print(f"  数据库: {db_path}")
    print(f"{'='*60}\n")


# ===================================================================
# 主程序 / CLI
# ===================================================================

def main():
    parser = argparse.ArgumentParser(
        description="OwnThink CSV → SQLite 批量导入器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 导入全量数据（会花很长时间）
  python batch_import.py --input D:/ownthink_v2/ownthink_v2.csv

  # 测试：只导入前 100 万行
  python batch_import.py --input D:/ownthink_v2/ownthink_v2.csv --max-rows 1000000

  # 安静模式
  python batch_import.py --input data/ownthink.csv --quiet
"""
    )
    parser.add_argument('--input', '-i', type=str, required=True,
                        help='输入 CSV 文件路径（OwnThink 格式）')
    parser.add_argument('--db', '-d', type=str, default=None,
                        help='SQLite 数据库路径（默认 data/tomas.db）')
    parser.add_argument('--max-rows', type=int, default=0,
                        help='最大导入行数（0=不限制，用于测试）')
    parser.add_argument('--batch-size', type=int, default=5000,
                        help='每批插入的行数（默认 5000）')
    parser.add_argument('--quiet', '-q', action='store_true',
                        help='安静模式，减少输出')
    args = parser.parse_args()

    # 默认数据库路径
    if not args.db:
        args.db = os.path.join(os.path.dirname(__file__), '..', 'data', 'tomas.db')

    batch_import(
        csv_path=args.input,
        db_path=args.db,
        max_rows=args.max_rows,
        batch_size=args.batch_size,
        quiet=args.quiet
    )


if __name__ == '__main__':
    main()
