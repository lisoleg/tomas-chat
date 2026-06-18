#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask API 端点测试脚本
测试 TOMAS AGI 系统的关键 API 端点可用性和响应格式
"""

import argparse
import sys
import requests

# 默认基础 URL
DEFAULT_BASE_URL = "http://localhost:5000"

# 超时时间（秒）
TIMEOUT = 5


def test_endpoint(base_url: str, path: str, description: str,
                  expected_status: int = 200,
                  check_json: bool = False,
                  json_check: dict = None,
                  accept_unavailable: bool = False) -> bool:
    """
    测试单个 API 端点

    Args:
        base_url: 基础 URL
        path: 端点路径
        description: 端点描述
        expected_status: 期望的 HTTP 状态码
        check_json: 是否检查 JSON 响应
        json_check: JSON 字段检查字典 {字段名: 期望值}
        accept_unavailable: 是否接受服务不可用（503 等）

    Returns:
        bool: 测试是否通过
    """
    url = f"{base_url}{path}"
    try:
        response = requests.get(url, timeout=TIMEOUT)
        # 检查状态码
        if accept_unavailable and response.status_code in (503, 404):
            # 服务不可用也算通过（表示端点存在但模块未启动）
            print(f"  ✅ PASS: {description} ({path}) → {response.status_code} (模块未启用，可接受)")
            return True
        if response.status_code != expected_status:
            print(f"  ❌ FAIL: {description} ({path}) → 状态码 {response.status_code}, 期望 {expected_status}")
            return False
        # 检查 JSON 响应
        if check_json:
            try:
                data = response.json()
                if json_check:
                    for key, expected_val in json_check.items():
                        if key not in data:
                            print(f"  ❌ FAIL: {description} ({path}) → 响应缺少字段 '{key}'")
                            return False
                        if expected_val is not None and data[key] != expected_val:
                            print(f"  ❌ FAIL: {description} ({path}) → 字段 '{key}' 值为 {data[key]}, 期望 {expected_val}")
                            return False
                print(f"  ✅ PASS: {description} ({path}) → {response.status_code}, JSON 响应正确")
            except requests.exceptions.JSONDecodeError:
                print(f"  ❌ FAIL: {description} ({path}) → 响应不是有效 JSON")
                return False
        else:
            print(f"  ✅ PASS: {description} ({path}) → {response.status_code}")
        return True
    except requests.exceptions.ConnectionError:
        print(f"  ❌ FAIL: {description} ({path}) → 连接失败（服务器未启动）")
        return False
    except requests.exceptions.Timeout:
        print(f"  ❌ FAIL: {description} ({path}) → 请求超时（{TIMEOUT}s）")
        return False
    except Exception as e:
        print(f"  ❌ FAIL: {description} ({path}) → 异常: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="测试 TOMAS AGI Flask API 端点")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help=f"Flask 服务器基础 URL (默认: {DEFAULT_BASE_URL})")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    print(f"=== TOMAS AGI API 端点测试 ===")
    print(f"基础 URL: {base_url}")
    print()

    # 定义测试端点列表
    endpoints = [
        # 基础端点
        ("/api/health", "健康检查", True, {"status": "ok"}),
        ("/api/corpus", "语料库列表", True, {"success": True}),
        ("/api/sessions", "会话列表", True, None),
        ("/api/knowledge", "知识图谱概览", True, None),

        # 知识图谱子端点
        ("/api/knowledge/triples?limit=5", "知识三元组", True, None),
        ("/api/knowledge/graph?limit=10", "知识图谱数据", True, None),
        ("/api/knowledge/subjects", "知识主体列表", True, None),
        ("/api/knowledge/predicates", "知识谓词列表", True, None),

        # 处理器端点
        ("/api/tprocessor/stats", "T-Processor 统计", True, None),
        ("/api/tshield/stats", "T-Shield 统计", True, None),

        # 模块端点（可能不可用）
        ("/api/ido/stats", "IDO 统计", True, None, True),
        ("/api/fde/status", "FDE 状态", True, None, True),

        # 其他端点
        ("/api/dual-timeline/status", "双时间线状态", True, None),
        ("/api/itot/kpi", "ITOT KPI", True, None),
    ]

    passed = 0
    failed = 0

    for ep in endpoints:
        path = ep[0]
        desc = ep[1]
        check_json = ep[2] if len(ep) > 2 else False
        json_check = ep[3] if len(ep) > 3 else None
        accept_unavailable = ep[4] if len(ep) > 4 else False

        result = test_endpoint(
            base_url=base_url,
            path=path,
            description=desc,
            expected_status=200,
            check_json=check_json,
            json_check=json_check,
            accept_unavailable=accept_unavailable,
        )
        if result:
            passed += 1
        else:
            failed += 1

    print()
    print(f"=== 测试结果 ===")
    print(f"通过: {passed}")
    print(f"失败: {failed}")
    print(f"总计: {passed + failed}")

    if failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
