"""
SWE-bench Lite 评估脚本框架
=====================================

运行 TOMAS-AGI against SWE-bench Lite (300 instances).

用法：
  python swe_bench_eval.py --data-path data/swe_bench_lite.json --output results/swe_bench_lite.csv
  python swe_bench_eval.py --dry-run  # 测试前 3 个实例
"""

import json
import csv
import os
import sys
import time
import argparse
from datetime import datetime
from typing import Dict, List, Optional

# ── 配置 ────────────────────────────────────────────────────────────────────
SWE_BENCH_LITE_URL = "https://github.com/princeton-nlp/SWE-bench/blob/main/data/swe_bench_lite.json"
DEFAULT_OUTPUT_DIR = "results"
# ────────────────────────────────────────────────────────────────────────────────


def download_swe_bench_lite(output_path: str) -> str:
    """
    下载 SWE-bench Lite 数据集（如果不存在）。

    实际部署时需要：
      import requests
      r = requests.get(SWE_BENCH_LITE_URL)
      with open(output_path, 'w') as f: f.write(r.text)
    """
    if os.path.exists(output_path):
        return output_path

    print(f"[SWE-Bench] 数据集不存在: {output_path}")
    print(f"[SWE-Bench] 请手动下载: {SWE_BENCH_LITE_URL}")
    print(f"[SWE-Bench] 然后放置到: {output_path}")
    sys.exit(1)


def load_instances(data_path: str, max_instances: int = 0) -> List[Dict]:
    """加载 SWE-bench Lite 实例。"""
    with open(data_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    instances = data if isinstance(data, list) else data.get('instances', [])
    if max_instances > 0:
        instances = instances[:max_instances]

    print(f"[SWE-Bench] 加载了 {len(instances)} 个实例")
    return instances


def evaluate_instance(instance: Dict, tomas_api_url: str = "http://localhost:5000") -> Dict:
    """
    评估单个 SWE-bench 实例。

    流程：
      1. 构造 prompt（instance['problem_statement']）
      2. 调用 TOMAS API（/api/chat 或 /api/route）
      3. 提取预测（patch 或 fixed code）
      4. 与 instance['patch'] 比较（或运行测试）
    """
    instance_id = instance.get('instance_id', 'unknown')
    problem = instance.get('problem_statement', '')
    repo = instance.get('repo', '')
    patch = instance.get('patch', '')

    result = {
        'instance_id': instance_id,
        'repo': repo,
        'has_patch': bool(patch),
        'prediction': None,
        'correct': None,
        'error': None,
        'duration_sec': 0.0,
    }

    start = time.time()
    try:
        # TODO: 实际调用 TOMAS API
        # import requests
        # resp = requests.post(
        #     f"{tomas_api_url}/api/chat",
        #     json={'query': problem, 'use_eml': True},
        #     timeout=120,
        # )
        # result['prediction'] = resp.json().get('answer', '')

        # 占位：模拟评估
        result['prediction'] = f"[PLACEHOLDER] Would query TOMAS with: {problem[:100]}..."
        result['correct'] = None  # 需要与实际 patch 比较

    except Exception as e:
        result['error'] = str(e)

    result['duration_sec'] = round(time.time() - start, 2)
    return result


def run_evaluation(instances: List[Dict], output_path: str, tomas_api_url: str = "http://localhost:5000") -> None:
    """运行完整评估并写入 CSV。"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    fieldnames = ['instance_id', 'repo', 'has_patch', 'prediction', 'correct', 'error', 'duration_sec']
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for i, instance in enumerate(instances, 1):
            print(f"[SWE-Bench] 评估实例 {i}/{len(instances)}: {instance.get('instance_id', '')}")
            result = evaluate_instance(instance, tomas_api_url)
            writer.writerow(result)
            f.flush()  # 实时写入

    print(f"\n[SWE-Bench] 评估完成，结果写入: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="SWE-bench Lite 评估脚本框架",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 干跑前 3 个实例（测试脚本逻辑）
  python swe_bench_eval.py --dry-run

  # 完整评估（需要先下载数据集）
  python swe_bench_eval.py --data-path data/swe_bench_lite.json --output results/swe_bench_lite.csv
"""
    )
    parser.add_argument('--data-path', '-i', type=str, default='data/swe_bench_lite.json',
                        help='SWE-bench Lite 数据集路径')
    parser.add_argument('--output', '-o', type=str, default='results/swe_bench_lite.csv',
                        help='输出 CSV 路径')
    parser.add_argument('--api-url', type=str, default='http://localhost:5000',
                        help='TOMAS API URL')
    parser.add_argument('--max-instances', type=int, default=0,
                        help='最大评估实例数（0=全部）')
    parser.add_argument('--dry-run', action='store_true',
                        help='干跑前 3 个实例（测试脚本逻辑）')
    args = parser.parse_args()

    # 下载/检查数据集
    if not args.dry_run:
        args.data_path = download_swe_bench_lite(args.data_path)

    # 加载实例
    instances = load_instances(args.data_path, args.max_instances if not args.dry_run else 3)

    # 运行评估
    if args.dry_run:
        print("[SWE-Bench] 干跑模式：测试前 3 个实例的脚本逻辑")
    run_evaluation(instances, args.output, args.api_url)

    print(f"\n{'='*60}")
    print("  SWE-bench Lite 评估完成")
    print(f"{'='*60}")
    print(f"  结果文件: {args.output}")
    print(f"  实例数: {len(instances)}")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
