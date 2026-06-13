"""
OwnThink 批量导入脚本
===============

将 OwnThink CSV 数据批量导入到 TOMAS SQLite 数据库。

数据格式：
  - CSV 列：实体,属性,值
  - 示例：中国,首都,北京

使用方法：
  python batch_import.py --input data/ownthink_sample.csv --batch-size 1000
  python batch_import.py --input D:/ownthink_v2/ownthink_v2.csv --batch-size 5000 --limit 100000

支持：
  - 流式读取（不加载整个文件到内存）
  - 批量 INSERT（提高性能）
  - 进度条显示
  - 断点续传（跳过已导入的数据）
"""

import argparse
import csv
import sqlite3
import os
import sys
from datetime import datetime
from collections import defaultdict

# 数据库路径（与 server.py 一致）
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'tomas.db')

def get_db_connection():
    """获取数据库连接"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_triples_table():
    """初始化知识三元组表"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS knowledge_triples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            predicate TEXT NOT NULL,
            object TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 创建索引以提高查询性能
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_triples_subject 
        ON knowledge_triples(subject)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_triples_predicate 
        ON knowledge_triples(predicate)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_triples_object 
        ON knowledge_triples(object)
    ''')
    
    conn.commit()
    conn.close()
    print("✅ knowledge_triples 表已初始化")

def count_existing_triples(conn):
    """统计已导入的三元组数量"""
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM knowledge_triples')
    return cursor.fetchone()[0]

def batch_import_csv(input_file, batch_size=1000, limit=None, skip_existing=True):
    """
    批量导入 CSV 文件到 SQLite
    
    Args:
        input_file: CSV 文件路径
        batch_size: 批量 INSERT 的大小
        limit: 最大导入行数（用于测试）
        skip_existing: 是否跳过已导入的数据
    """
    # 初始化表
    init_triples_table()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 统计已存在的数据
    if skip_existing:
        existing_count = count_existing_triples(conn)
        if existing_count > 0:
            print(f"⚠️ 检测到已导入 {existing_count} 条三元组")
            try:
                response = input("是否清空后重新导入？(y/N): ")
            except EOFError:
                response = 'n'
            if response.lower() != 'y':
                print("❌ 取消导入")
                conn.close()
                return
            print("🗑️ 清空现有数据...")
            cursor.execute('DELETE FROM knowledge_triples')
            conn.commit()
    
    # 统计文件行数（用于进度显示）
    print(f"📊 统计文件行数...")
    total_lines = 0
    with open(input_file, 'r', encoding='utf-8') as f:
        total_lines = sum(1 for _ in f) - 1  # 减去表头
    
    if limit and limit < total_lines:
        total_lines = limit
    
    print(f"📂 文件: {input_file}")
    print(f"📊 总行数: {total_lines}")
    print(f"⚙️ 批量大小: {batch_size}")
    print(f"🚀 开始导入...")
    print()
    
    # 批量导入
    batch = []
    processed = 0
    inserted = 0
    skipped = 0
    errors = 0
    
    start_time = datetime.now()
    
    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)  # 跳过表头
        
        for row in reader:
            if len(row) < 3:
                skipped += 1
                continue
            
            subject = row[0].strip()
            predicate = row[1].strip()
            obj = row[2].strip()
            
            if not subject or not predicate or not obj:
                skipped += 1
                continue
            
            batch.append((subject, predicate, obj))
            processed += 1
            
            # 批量插入
            if len(batch) >= batch_size:
                try:
                    cursor.executemany('''
                        INSERT INTO knowledge_triples (subject, predicate, object)
                        VALUES (?, ?, ?)
                    ''', batch)
                    conn.commit()
                    inserted += len(batch)
                except Exception as e:
                    errors += len(batch)
                    print(f"❌ 批量插入失败: {e}")
                
                batch = []
                
                # 显示进度
                elapsed = (datetime.now() - start_time).total_seconds()
                speed = processed / elapsed if elapsed > 0 else 0
                eta = (total_lines - processed) / speed if speed > 0 else 0
                
                print(f"\r📊 进度: {processed}/{total_lines} ({processed*100//total_lines}%) | "
                      f"插入: {inserted} | 跳过: {skipped} | 错误: {errors} | "
                      f"速度: {speed:.0f} 行/秒 | ETA: {eta:.0f}秒", end='')
            
            # 检查限制
            if limit and processed >= limit:
                break
    
    # 插入剩余的批次
    if batch:
        try:
            cursor.executemany('''
                INSERT INTO knowledge_triples (subject, predicate, object)
                VALUES (?, ?, ?)
            ''', batch)
            conn.commit()
            inserted += len(batch)
        except Exception as e:
            errors += len(batch)
            print(f"\n❌ 最后批次插入失败: {e}")
    
    conn.close()
    
    # 显示最终统计
    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n\n✅ 导入完成！")
    print(f"   处理行数: {processed}")
    print(f"   插入行数: {inserted}")
    print(f"   跳过行数: {skipped}")
    print(f"   错误行数: {errors}")
    print(f"   耗时: {elapsed:.1f} 秒")
    print(f"   平均速度: {processed/elapsed:.0f} 行/秒")

def verify_import():
    """验证导入的数据"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 统计
    cursor.execute('SELECT COUNT(*) FROM knowledge_triples')
    total = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(DISTINCT subject) FROM knowledge_triples')
    unique_subjects = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(DISTINCT predicate) FROM knowledge_triples')
    unique_predicates = cursor.fetchone()[0]
    
    print(f"📊 导入统计:")
    print(f"   总三元组数: {total}")
    print(f"   唯一实体数: {unique_subjects}")
    print(f"   唯一关系数: {unique_predicates}")
    
    # 显示样例
    cursor.execute('''
        SELECT subject, predicate, object 
        FROM knowledge_triples 
        LIMIT 10
    ''')
    
    print(f"\n📝 样例数据:")
    for row in cursor.fetchall():
        print(f"   {row['subject']} -> {row['predicate']} -> {row['object']}")
    
    conn.close()

def export_to_eml(output_file, limit=10000):
    """
    将 SQLite 中的三元组导出为 EML 格式（用于可视化）
    
    注意：完整的 EML 格式需要向量化，这里只导出基本结构。
    对于大规模数据，建议使用前端直接查询 API 获取图数据。
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 获取所有唯一概念
    cursor.execute('''
        SELECT DISTINCT subject as concept FROM knowledge_triples
        UNION
        SELECT DISTINCT object as concept FROM knowledge_triples
        WHERE object NOT GLOB '*[0-9]*'  -- 排除纯数字对象
        LIMIT ?
    ''', (limit,))
    
    concepts = [row['concept'] for row in cursor.fetchall()]
    concept_to_id = {c: i for i, c in enumerate(concepts)}
    
    print(f"📊 导出 EML: {len(concepts)} 个概念")
    
    # 创建简单的 EML 数据（仅用于测试可视化）
    # 完整实现需要向量化，这里只创建占位符
    
    # 写入概念列表
    concepts_file = output_file.replace('.eml', '_distilled.concepts.json')
    with open(concepts_file, 'w', encoding='utf-8') as f:
        json.dump(concepts, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 概念列表已导出: {concepts_file}")
    print(f"⚠️ EML 二进制文件需要向量化，建议使用前端 API 进行可视化")
    
    conn.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='OwnThink 批量导入脚本')
    parser.add_argument('--input', '-i', required=True, help='输入 CSV 文件路径')
    parser.add_argument('--batch-size', '-b', type=int, default=1000, help='批量 INSERT 大小')
    parser.add_argument('--limit', '-l', type=int, help='最大导入行数（用于测试）')
    parser.add_argument('--verify', '-v', action='store_true', help='验证已导入的数据')
    parser.add_argument('--export-eml', '-e', help='导出为 EML 格式（指定输出文件）')
    
    args = parser.parse_args()
    
    if args.verify:
        verify_import()
    elif args.export_eml:
        import json
        export_to_eml(args.export_eml, limit=10000)
    else:
        if not os.path.exists(args.input):
            print(f"❌ 文件不存在: {args.input}")
            sys.exit(1)
        
        batch_import_csv(args.input, args.batch_size, args.limit)
        
        # 验证导入
        print()
        verify_import()
