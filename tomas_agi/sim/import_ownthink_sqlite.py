"""
OwnThink 批量导入器 — CSV → SQLite (SQLAlchemy)
=================================================

将 OwnThink 格式三元组 CSV 全量导入到 D:/tomas-data/tomas.db
的 knowledge_triples 表。

CSV 格式：实体,属性,值  （8 GB, ~1.4 亿行）

用法：
  # 试运行（仅统计）
  python import_ownthink_sqlite.py --dry-run

  # 限制导入行数（测试用）
  python import_ownthink_sqlite.py --limit 100000

  # 全量导入
  python import_ownthink_sqlite.py
"""

import os
import sys
import csv
import re
import time
import argparse
from datetime import datetime

# 确保可以导入 models
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import get_engine, KnowledgeTriple, KnowledgeItem, DB_PATH
from sqlalchemy import text

# ---- 配置 ----
DEFAULT_CSV = "D:/ownthink_v2/ownthink_v2.csv"
BATCH_SIZE = 50000          # 每批 INSERT 行数
PROGRESS_INTERVAL = 200000  # 每 N 行打印一次进度


# ===================================================================
# 伪概念过滤器（与 ownthink_importer.py 对齐，去掉 numpy 依赖）
# ===================================================================

_DATE_PATTERNS = [
    re.compile(r'^\d{4}年\d{1,2}月\d{1,2}日?$'),
    re.compile(r'^\d{4}年\d{1,2}月$'),
    re.compile(r'^\d{4}年$'),
    re.compile(r'^公元前\d+年'),
    re.compile(r'^公元\d+年'),
    re.compile(r'^\d{1,2}世纪(\d{1,2})?年代?$'),
    re.compile(r'^[春夏秋冬]季$'),
    re.compile(r'^\d{1,2}[月日号]$'),
    re.compile(r'^(?:周|星期)[一二三四五六日天]$'),
    re.compile(r'^\d{4}-\d{2}-\d{2}$'),
    re.compile(r'^\d{2}:\d{2}(:\d{2})?$'),
]

_NUMBER_PATTERNS = [
    re.compile(r'^[\d\s.,，。、%％‰+\-×÷=<>≥≤π∞]+$'),
    re.compile(r'^[\d.]+(?:万|亿|k|K|M|G|T)?(?:个|条|人|次|项)?$'),
    re.compile(r'^v?\d+(\.\d+)*([a-zA-Z]*)$'),
    re.compile(r'^第?[一二三四五六七八九十百千\d]+[章节卷册页版]$'),
]

_MEASURE_PATTERN = re.compile(
    r'^[\d.]+(?:km|m|cm|mm|kg|g|mg|℃|℉|%|公里|米|厘米|毫米|千克|克|毫升|升|公顷|亩|秒分小时天周年)$',
    re.IGNORECASE,
)


def is_pseudo_concept(s):
    s = s.strip()
    if len(s) == 0:
        return True
    if len(s) < 2:
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
    if re.match(r'^[\d\-+\s()（）]{7,15}$', s):
        return True
    return False


# ===================================================================
# 主导入逻辑
# ===================================================================

def import_ownthink(csv_path, max_rows=0, dry_run=False, batch_size=BATCH_SIZE):
    if not os.path.exists(csv_path):
        print(f"❌ 文件不存在: {csv_path}")
        sys.exit(1)

    engine = get_engine()
    table_name = KnowledgeTriple.__tablename__

    # 试运行：仅统计
    if dry_run:
        print("=" * 60)
        print("  DRY-RUN 模式 — 仅统计，不写入")
        print("=" * 60)
        total = 0
        pseudo = 0
        valid = 0
        start = time.time()
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) < 3:
                    continue
                total += 1
                if max_rows and total >= max_rows:
                    break
                entity, pred, value = row[0].strip(), row[1].strip(), row[2].strip()
                if is_pseudo_concept(entity):
                    pseudo += 1
                    continue
                if not is_pseudo_concept(value) and len(value) > 1:
                    valid += 1

        elapsed = time.time() - start
        print(f"\n📊 统计结果:")
        print(f"  总行数:        {total:,}")
        print(f"  伪概念过滤:    {pseudo:,}")
        print(f"  有效三元组:    {valid:,}")
        print(f"  耗时:          {elapsed:.1f}s")
        print(f"  速率:          {total / elapsed:,.0f} 行/秒")
        return

    # ---- 全量导入 ----
    print("=" * 60)
    print("  OwnThink → SQLite 批量导入器")
    print("=" * 60)
    print(f"  CSV:      {csv_path}")
    print(f"  数据库:   {DB_PATH}")
    print(f"  批次大小: {BATCH_SIZE:,}")
    if max_rows:
        print(f"  限制行数: {max_rows:,}")
    print()

    total_rows = 0
    pseudo_filtered = 0
    inserted = 0
    duplicates = 0
    skipped_property = 0

    batch = []
    start_time = time.time()
    last_progress_time = start_time

    # 预编译 SQL（使用 INSERT OR IGNORE 避免重复）
    insert_sql = text(f"""
        INSERT OR IGNORE INTO {table_name} (subject, predicate, object, created_at)
        VALUES (:subject, :predicate, :object, :created_at)
    """)

    def flush_batch():
        nonlocal inserted, duplicates, batch
        if not batch:
            return
        with engine.begin() as conn:
            result = conn.execute(insert_sql, batch)
            inserted += result.rowcount
            duplicates += (len(batch) - result.rowcount)
        batch.clear()

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 3:
                continue
            total_rows += 1
            if max_rows and total_rows > max_rows:
                break

            entity = row[0].strip()
            predicate = row[1].strip()
            value = row[2].strip()

            if not entity or not predicate:
                continue

            # 过滤伪概念实体
            if is_pseudo_concept(entity):
                pseudo_filtered += 1
                continue

            # 判断 value 是否像实体
            if is_pseudo_concept(value) or len(value) <= 1:
                skipped_property += 1
                continue

            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            batch.append({
                "subject": entity,
                "predicate": predicate,
                "object": value,
                "created_at": now,
            })

            # 批次满 → 写入
            if len(batch) >= batch_size:
                flush_batch()

            # 进度报告
            if total_rows % PROGRESS_INTERVAL == 0:
                now_t = time.time()
                elapsed = now_t - start_time
                interval_elapsed = now_t - last_progress_time
                rate = total_rows / elapsed if elapsed > 0 else 0
                interval_rate = PROGRESS_INTERVAL / interval_elapsed if interval_elapsed > 0 else 0
                last_progress_time = now_t
                print(
                    f"  📍 {total_rows:>12,} 行 | "
                    f"已导入 {inserted:>10,} | "
                    f"重复 {duplicates:>8,} | "
                    f"过滤 {pseudo_filtered:>8,} | "
                    f"{elapsed/3600:.1f}h | "
                    f"{rate:,.0f} 行/秒"
                )

    # 刷最后一桶
    flush_batch()

    elapsed = time.time() - start_time
    rate = total_rows / elapsed if elapsed > 0 else 0

    print()
    print("=" * 60)
    print("  ✅ 导入完成")
    print("=" * 60)
    print(f"  总行数:        {total_rows:>12,}")
    print(f"  伪概念过滤:    {pseudo_filtered:>12,}")
    print(f"  属性值跳过:    {skipped_property:>12,}")
    print(f"  成功插入:      {inserted:>12,}")
    print(f"  重复跳过:      {duplicates:>12,}")
    print(f"  总耗时:        {elapsed/3600:.2f} 小时 ({elapsed:.0f} 秒)")
    print(f"  平均速率:      {rate:,.0f} 行/秒")
    print(f"  数据库:        {DB_PATH}")


# ===================================================================
# CLI
# ===================================================================

def main():
    parser = argparse.ArgumentParser(
        description="OwnThink CSV → SQLite 批量导入器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python import_ownthink_sqlite.py --dry-run         # 试运行，仅统计
  python import_ownthink_sqlite.py --limit 100000    # 限制导入 10 万行
  python import_ownthink_sqlite.py                   # 全量导入
""",
    )
    parser.add_argument("--input", "-i", type=str, default=DEFAULT_CSV,
                        help=f"输入 CSV 路径（默认: {DEFAULT_CSV}）")
    parser.add_argument("--limit", "-l", type=int, default=0,
                        help="限制导入行数（0=不限制）")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="试运行，仅统计不写入")
    parser.add_argument("--batch", "-b", type=int, default=BATCH_SIZE,
                        help=f"批次大小（默认: {BATCH_SIZE}）")
    args = parser.parse_args()

    import_ownthink(
        csv_path=args.input,
        max_rows=args.limit,
        dry_run=args.dry_run,
        batch_size=args.batch,
    )


if __name__ == "__main__":
    main()
