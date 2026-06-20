"""
生成 HyperShard 分片文件（用于分布式超图数据库测试）

用法:
    python create_shards.py --shards 4 --sample 100000
    python create_shards.py --shards 8 --full  # 全量分片（耗时较长）
"""
import argparse
import sqlite3
import os
import sys
from pathlib import Path

DB_PATH = "D:/tomas-data/tomas.db"
SHARD_DIR = "D:/tomas-data/shards"


def create_shard_db(shard_id: int, shard_path: str):
    """创建单个分片数据库文件"""
    conn = sqlite3.connect(shard_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS vertices (
            vid INTEGER PRIMARY KEY,
            concept TEXT UNIQUE NOT NULL,
            i_val REAL DEFAULT 1.0,
            asym REAL DEFAULT 0.0,
            weight REAL DEFAULT 1.0
        );
        CREATE TABLE IF NOT EXISTS hyperedges (
            eid INTEGER PRIMARY KEY,
            arity INTEGER DEFAULT 2,
            weight REAL DEFAULT 1.0,
            delta_weight REAL DEFAULT 0.0,
            asym REAL DEFAULT 0.0
        );
        CREATE TABLE IF NOT EXISTS hyperedge_nodes (
            eid INTEGER,
            vid INTEGER,
            PRIMARY KEY (eid, vid)
        );
        CREATE INDEX IF NOT EXISTS idx_hyperedge_nodes_eid ON hyperedge_nodes(eid);
        CREATE INDEX IF NOT EXISTS idx_hyperedge_nodes_vid ON hyperedge_nodes(vid);
    """)
    conn.close()
    print(f"  ✅ Shard {shard_id}: {shard_path}")


def shard_knowledge_triples(num_shards: int, sample_size: int = None, full: bool = False):
    """将 knowledge_triples 分片到多个数据库"""
    os.makedirs(SHARD_DIR, exist_ok=True)
    
    # 创建分片文件
    shard_paths = []
    for i in range(num_shards):
        path = os.path.join(SHARD_DIR, f"shard_{i:02d}.db")
        create_shard_db(i, path)
        shard_paths.append(path)
    
    # 连接主库
    src = sqlite3.connect(DB_PATH)
    src.row_factory = sqlite3.Row
    
    # 获取总数
    if full:
        total = src.execute("SELECT count(*) FROM knowledge_triples").fetchone()[0]
        print(f"📊 全量分片模式: {total:,}  triples")
    else:
        total = sample_size
        print(f"📊 采样分片模式: {sample_size:,}  triples")
    
    # 分片导入
    import hashlib
    
    batch_size = 5000
    imported = 0
    
    print(f"🚀 开始分片（{num_shards} shards, batch={batch_size}）...")
    
    # 打开所有分片连接
    shard_conns = [sqlite3.connect(p) for p in shard_paths]
    
    try:
        if full:
            cursor = src.execute("SELECT subject, predicate, object FROM knowledge_triples")
        else:
            cursor = src.execute(
                "SELECT subject, predicate, object FROM knowledge_triples LIMIT ?", 
                (sample_size,)
            )
        
        batch = []
        for row in cursor:
            batch.append(row)
            if len(batch) >= batch_size:
                _import_batch(batch, shard_conns, num_shards)
                imported += len(batch)
                if imported % 50000 == 0:
                    print(f"  ... {imported:,} / {total:,}")
                batch = []
        
        if batch:
            _import_batch(batch, shard_conns, num_shards)
            imported += len(batch)
    
    finally:
        for c in shard_conns:
            c.close()
        src.close()
    
    print(f"\n✅ 分片完成！共导入 {imported:,}  triples")
    print(f"📁 分片文件: {SHARD_DIR}/")
    for i, p in enumerate(shard_paths):
        size = os.path.getsize(p) / 1024 / 1024
        print(f"  shard_{i:02d}.db: {size:.1f} MB")


def _import_batch(batch, shard_conns, num_shards):
    """导入一批数据到对应分片"""
    import hashlib
    
    for subject, predicate, obj in batch:
        # 根据 subject 哈希决定分片
        h = int(hashlib.md5(subject.encode()).hexdigest(), 16)
        shard_id = h % num_shards
        
        conn = shard_conns[shard_id]
        # 简化的分片存储：只存三元组
        try:
            conn.execute(
                "INSERT OR IGNORE INTO vertices (concept) VALUES (?)",
                (subject,)
            )
            conn.execute(
                "INSERT OR IGNORE INTO vertices (concept) VALUES (?)",
                (obj,)
            )
        except:
            pass
    
    for c in shard_conns:
        c.commit()


def main():
    parser = argparse.ArgumentParser(description="TOMAS HyperShard 分片生成器")
    parser.add_argument("--shards", type=int, default=4, help="分片数（默认4）")
    parser.add_argument("--sample", type=int, default=100000, help="采样大小（默认100K）")
    parser.add_argument("--full", action="store_true", help="全量分片（101M triples，耗时较长）")
    args = parser.parse_args()
    
    if args.full:
        confirm = input(f"⚠️  全量分片 {args.shards} shards × 101M triples，预计耗时>30分钟。确认? (y/N): ")
        if confirm.lower() != 'y':
            print("取消")
            return
    
    shard_knowledge_triples(args.shards, args.sample, args.full)


if __name__ == "__main__":
    main()
