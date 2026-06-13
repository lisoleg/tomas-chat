"""
OwnThink 知识图谱 → TOMAS EML 导入器
=============================================

将 OwnThink / 通用三元组 CSV 转换为 TOMAS 的 EML 二进制格式 +
concepts.json（含 domain 标注）。

用法：
  python ownthink_importer.py --input data/ownthink.csv --output data/ownthink.eml --domain 通用知识
  python ownthink_importer.py --input data/physics_triples.csv --output data/physics.eml --domain physics

输入 CSV 格式（自动检测）：
  格式A（OwnThink 原始）：  实体, 属性, 值
  格式B（三元组）：      实体, 关系, 实体

输出：
  <output>.eml                EML 二进制图谱
  <output>.concepts.json      概念名称 + domain 映射
"""

import os
import sys
import json
import csv
import struct
import argparse
import numpy as np
from typing import List, Dict, Tuple, Optional, Set
from collections import defaultdict


# ===================================================================
# 伪概念过滤器（与 llm_distiller.py 对齐）
# ===================================================================

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


def is_pseudo_concept(s: str) -> Tuple[bool, str]:
    s = s.strip()
    if len(s) == 0:
        return True, "空字符串"
    if len(s) < 2:
        return True, f"过短({len(s)}字符)"
    for p in _DATE_PATTERNS:
        if p.match(s):
            return True, "日期/时间格式"
    for p in _NUMBER_PATTERNS:
        if p.match(s):
            return True, "纯数字/数量"
    if _MEASURE_PATTERN.match(s):
        return True, "度量单位值"
    if s.startswith(('http://', 'https://', 'www.', 'ftp://')):
        return True, "URL"
    if '@' in s and '.' in s.split('@')[-1]:
        return True, "邮箱"
    if _re.match(r'^[\d\-+\s()（）]{7,15}$', s):
        return True, "电话号码"
    return False, ""


# ===================================================================
# EML 二进制写入器（不依赖 llm_distiller 模块）
# ===================================================================

class EMLWriter:
    """
    轻量 EML 二进制格式写入器。
    格式规范与 token_bridge.py:EMLFileLoader 对齐。
    """

    MAGIC   = 0x454D4C47   # "EMLG"
    VERSION = 0x00020000
    HEADER_SIZE = 72
    VERTEX_SIZE = 80
    EDGE_SIZE   = 32

    def __init__(self):
        self.vertices: List[Dict] = []
        self.edges: List[Dict] = []
        self.laplacian_alpha: float = 0.0
        self.graph_delta: float = 1.0
        self.timestamp: int = 0
        self._id_map: Dict[str, int] = {}   # concept_text -> vertex_id
        self._next_id: int = 0

    def _get_or_create_id(self, concept: str) -> int:
        if concept not in self._id_map:
            self._id_map[concept] = self._next_id
            self.vertices.append({
                'id': self._next_id,
                'concept': concept,
                'octonion': [0.0] * 8,
                'delta': 0.5,       # 默认 𝕀(X)，后续可更新
                'info_existence': 0.5,
                'domain': '',
            })
            self._next_id += 1
        return self._id_map[concept]

    def add_concept(self, concept: str, delta: float = 0.5, domain: str = ''):
        vid = self._get_or_create_id(concept)
        v = self.vertices[vid]
        v['delta'] = max(v['delta'], delta)
        v['info_existence'] = max(v['info_existence'], delta)
        if domain:
            v['domain'] = domain
        return vid

    def add_relation(self, src: str, dst: str,
                     weight: float = 1.0,
                     rel_type: str = 'related_to',
                     domain: str = ''):
        src_id = self._get_or_create_id(src)
        dst_id = self._get_or_create_id(dst)
        # associator_flag: causes/导致类 → 1，其余 → 0
        associator_flag = 1 if rel_type in (
            'causes', '导致', '引起', '触发', '造成',
            ' motivated_by', 'inspired_by', '启发'
        ) else 0
        self.edges.append({
            'src': src_id,
            'dst': dst_id,
            'weight': weight,
            'delta_weight': weight * 0.8,
            'associator_flag': associator_flag,
        })
        # 同步更新顶点的 domain
        if domain:
            self.vertices[src_id]['domain'] = domain
            self.vertices[dst_id]['domain'] = domain

    def set_graph_delta(self):
        """用所有顶点的 delta 均值设置 graph_delta"""
        if self.vertices:
            self.graph_delta = float(
                np.mean([v['delta'] for v in self.vertices])
            )

    def save(self, filepath: str):
        self.set_graph_delta()
        num_v = len(self.vertices)
        num_e = len(self.edges)

        with open(filepath, 'wb') as f:
            # ---- Header (72 bytes) ----
            # Layout (aligned with token_bridge.EMLFileLoader):
            #   bytes  0-15:  <IIII  (magic, version, num_v, num_e)         = 16 bytes
            #   bytes 16-31:  <dd    (laplacian_alpha, graph_delta)       = 16 bytes
            #   bytes 32-39:  <Q     (timestamp)                           =  8 bytes
            #   bytes 40-71:  padding                                       = 32 bytes
            h = b''
            h += struct.pack('<IIII', self.MAGIC, self.VERSION, num_v, num_e)
            h += struct.pack('<dd',   self.laplacian_alpha, self.graph_delta)
            h += struct.pack('<Q',    self.timestamp if self.timestamp else 0)
            h  = h.ljust(72, b'\x00')
            f.write(h)

            # ---- Vertices (80 bytes each) ----
            for v in self.vertices:
                # id (i) + pad (i) = 8 bytes
                vid = v['id']
                pad = 0
                # octonion (8d) = 64 bytes
                octo = v.get('octonion', [0.0]*8)[:8]
                # delta (d) = 8 bytes
                delta = float(v.get('delta', 0.5))
                vert_bytes = struct.pack('<ii', vid, pad)
                vert_bytes += struct.pack('<8d', *octo)
                vert_bytes += struct.pack('<d', delta)
                # 补齐到 80 bytes
                vert_bytes = vert_bytes.ljust(self.VERTEX_SIZE, b'\x00')
                f.write(vert_bytes)

            # ---- Edges (32 bytes each) ----
            for e in self.edges:
                # src (i) + dst (i) = 8
                # weight (d) + delta_weight (d) = 16
                # associator_flag (i) + pad (i) = 8
                edge_bytes = struct.pack(
                    '<iiddii',
                    e['src'],
                    e['dst'],
                    float(e.get('weight', 1.0)),
                    float(e.get('delta_weight', 0.8)),
                    int(e.get('associator_flag', 0)),
                    0   # pad
                )
                # 补齐到 32 字节
                edge_bytes = edge_bytes.ljust(self.EDGE_SIZE, b'\x00')
                f.write(edge_bytes)

        print(f"[EMLWriter] 已保存: {filepath}")
        print(f"  顶点数={num_v}, 边数={num_e}, graph_delta={self.graph_delta:.4f}")

    def save_concepts_json(self, filepath: str):
        """保存概念名称 JSON（扩展格式，含 domain）"""
        concept_data = {
            'domain': self.vertices[0]['domain'] if self.vertices else '',
            'concepts': [
                {
                    'id': v['id'],
                    'concept': v['concept'],
                    'importance': v['info_existence'],
                    'domain': v.get('domain', ''),
                }
                for v in self.vertices
            ]
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(concept_data, f, ensure_ascii=False, indent=2)
        print(f"[EMLWriter] 已保存概念映射: {filepath} ({len(self.vertices)} 条)")


# ===================================================================
# OwnThink CSV 解析器
# ===================================================================

def detect_csv_format(csv_path: str, sample_rows: int = 10) -> str:
    """
    检测 CSV 格式：
      'ownthink'  →  (实体, 属性, 值)  如：人工智能, 别名, AI
      'triple'     →  (实体, 关系, 实体) 如：人工智能, 属于, 计算机科学
    返回格式类型字符串。
    """
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        rows = []
        for i, row in enumerate(reader):
            if i >= sample_rows:
                break
            if len(row) >= 3:
                rows.append([c.strip() for c in row[:3]])

    if not rows:
        return 'unknown'

    # 启发式判断：第三列如果是纯数字/日期/短属性值 → ownthink 格式
    # 第三列如果看起来像实体名（中文名词，长度>1，非数字）→ triple 格式
    triple_score = 0
    ownthink_score = 0

    for row in rows:
        col2 = row[2]
        # 如果第三列是伪概念（日期/数字）→ 更可能是 ownthink 的属性值
        is_pseudo, _ = is_pseudo_concept(col2)
        if is_pseudo:
            ownthink_score += 1
        # 如果第三列看起来像实体（非伪概念，长度>1）
        if not is_pseudo and len(col2) > 1:
            triple_score += 1

    # 特判：如果第二列是常见关系谓词
    relation_predicates = {
        '属于', '是一种', '相关', '导致', '用于', '位于', '出生于',
        'is_a', 'part_of', 'related_to', 'causes', 'used_in',
        '别名', '标签', '摘要', '描述', '关键词',
    }
    for row in rows:
        if row[1] in relation_predicates:
            ownthink_score += 2

    print(f"  [格式检测] triple_score={triple_score}, ownthink_score={ownthink_score}")
    if triple_score > ownthink_score:
        return 'triple'
    else:
        return 'ownthink'


def load_ownthink_csv(csv_path: str, domain: str = '',
                      max_rows: int = 500000,
                      verbose: bool = True) -> Tuple[EMLWriter, Dict]:
    """
    加载 OwnThink 格式 CSV 并转为 EML。

    格式A（OwnThink 原始）：实体, 属性, 值
      - 同一实体的多个属性 → 不直接建边，而是存为顶点属性
      - 如果 值 是实体（非伪概念）→ 建关系边
      - 如果 值 是属性值（日期/描述/数字）→ 不建边，仅记录（未来扩展）

    格式B（三元组）：实体, 关系, 实体
      - 直接建边

    返回：(writer, stats)
    """
    fmt = detect_csv_format(csv_path)
    if verbose:
        print(f"\n[OwnThink] 检测格式: {fmt}")
        print(f"  [OwnThink] 文件: {csv_path}")

    writer = EMLWriter()
    stats = {
        'total_rows': 0,
        'concepts_added': 0,
        'relations_added': 0,
        'pseudo_filtered': 0,
        'skipped_property_values': 0,
        'format': fmt,
    }

    # 收集同一实体的所有属性（用于后续扩展）
    entity_properties: Dict[str, List[Tuple[str, str]]] = defaultdict(list)

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        for row_idx, row in enumerate(reader):
            if max_rows and row_idx >= max_rows:
                if verbose:
                    print(f"  [OwnThink] 达到最大行数限制 {max_rows}，停止读取")
                break

            if len(row) < 3:
                continue
            stats['total_rows'] += 1
            entity = row[0].strip()
            predicate = row[1].strip()
            value = row[2].strip()

            if not entity or not predicate:
                continue

            # 过滤伪概念
            pseudo_e, reason_e = is_pseudo_concept(entity)
            if pseudo_e:
                stats['pseudo_filtered'] += 1
                continue

            if fmt == 'ownthink':
                # ---- 格式A：实体, 属性, 值 ----
                # 判断 value 是否像实体（可作为图谱节点）
                pseudo_v, _ = is_pseudo_concept(value)
                entity_properties[entity].append((predicate, value))

                if not pseudo_v and len(value) > 1:
                    # value 是实体 → 建边
                    writer.add_concept(entity, domain=domain)
                    writer.add_concept(value, domain=domain)
                    writer.add_relation(entity, value,
                                        weight=1.0,
                                        rel_type=predicate,
                                        domain=domain)
                    stats['relations_added'] += 1
                else:
                    # value 是属性值 → 仅添加主实体为概念
                    writer.add_concept(entity, domain=domain)
                    stats['skipped_property_values'] += 1
            else:
                # ---- 格式B：实体, 关系, 实体 ----
                pseudo_v, _ = is_pseudo_concept(value)
                if pseudo_v:
                    stats['pseudo_filtered'] += 1
                    continue
                writer.add_concept(entity, domain=domain)
                writer.add_concept(value, domain=domain)
                writer.add_relation(entity, value,
                                    weight=1.0,
                                    rel_type=predicate,
                                    domain=domain)
                stats['relations_added'] += 1

            if verbose and stats['total_rows'] % 50000 == 0 and stats['total_rows'] > 0:
                print(f"  [OwnThink] 已处理 {stats['total_rows']} 行，"
                      f"概念={len(writer.vertices)}，边={len(writer.edges)}")

    stats['concepts_added'] = len(writer.vertices)
    if verbose:
        print(f"\n[OwnThink] 处理完成:")
        print(f"  总行数: {stats['total_rows']}")
        print(f"  概念数: {stats['concepts_added']}")
        print(f"  关系数: {stats['relations_added']}")
        print(f"  过滤伪概念: {stats['pseudo_filtered']}")
        print(f"  跳过属性值: {stats['skipped_property_values']}")
        print(f"  格式: {fmt}")

    return writer, stats


# ===================================================================
# 主程序 / CLI
# ===================================================================

def main():
    parser = argparse.ArgumentParser(
        description="OwnThink 知识图谱 → TOMAS EML 导入器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 导入 OwnThink 通用知识（自动检测格式）
  python ownthink_importer.py --input data/ownthink.csv --output data/ownthink.eml --domain 通用知识

  # 导入物理学科三元组
  python ownthink_importer.py --input data/physics_triples.csv --output data/physics.eml --domain physics

  # 限制读取行数（测试用）
  python ownthink_importer.py --input data/ownthink.csv --output data/test.eml --max-rows 10000

  # 安静模式（不打印处理进度）
  python ownthink_importer.py --input data/ownthink.csv --output data/ownthink.eml --quiet
"""
    )
    parser.add_argument('--input', '-i', type=str, required=True,
                        help='输入 CSV 文件路径（OwnThink 格式或三元组格式）')
    parser.add_argument('--output', '-o', type=str, default='output.eml',
                        help='输出 EML 文件路径（默认 output.eml）')
    parser.add_argument('--domain', '-d', type=str, default='',
                        help='领域标签（如 physics/chemistry/medicine，会写入 concepts.json）')
    parser.add_argument('--max-rows', type=int, default=0,
                        help='最大读取行数（0=不限制，用于测试）')
    parser.add_argument('--quiet', '-q', action='store_true',
                        help='安静模式，减少输出')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ 文件不存在: {args.input}")
        sys.exit(1)

    print("=" * 60)
    print("  OwnThink → TOMAS EML 导入器")
    print("=" * 60)
    print(f"  输入:  {args.input}")
    print(f"  输出:  {args.output}")
    print(f"  领域:  {args.domain or '(未指定)'}")
    if args.max_rows:
        print(f"  最大行: {args.max_rows}")
    print()

    writer, stats = load_ownthink_csv(
        csv_path=args.input,
        domain=args.domain,
        max_rows=args.max_rows or 0,
        verbose=not args.quiet,
    )

    if len(writer.vertices) == 0:
        print("\n❌ 没有成功导入任何概念，请检查 CSV 格式和内容。")
        sys.exit(1)

    # 保存 EML
    eml_path = args.output
    if not eml_path.endswith('.eml'):
        eml_path += '.eml'
    writer.save(eml_path)

    # 保存 concepts.json
    concept_path = eml_path.replace('.eml', '.concepts.json')
    writer.save_concepts_json(concept_path)

    # 同时保存一份三元组文本（方便人工检查）
    txt_path = eml_path.replace('.eml', '_triples.txt')
    with open(txt_path, 'w', encoding='utf-8') as f:
        for e in writer.edges:
            src = writer.vertices[e['src']]['concept']
            dst = writer.vertices[e['dst']]['concept']
            f.write(f"{src}\t{e['associator_flag']}\t{dst}\t{e['weight']:.2f}\n")
    print(f"[OwnThink] 已保存三元组文本: {txt_path}")

    print(f"\n✅ 导入完成！")
    print(f"   接下来可以用以下命令加载到 TOMAS：")
    print(f"   python token_bridge.py --load {eml_path} --concepts {concept_path} --query '查询内容'")
    print(f"   或将 {eml_path} 放到 deepseek-chat/public/ 目录供前端加载")


if __name__ == '__main__':
    main()
