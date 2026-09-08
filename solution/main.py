"""命令行入口：python main.py <input.json> [--out-dir output/]

流程：读取输入 -> 求解 -> 内部校验 -> 写 result.json -> 生成结果图 PNG。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import config
from solver import io_model, rules, search


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def solve_case(input_payload: dict) -> dict:
    """求解单条输入，返回题目约定格式的输出 JSON。"""
    parsed = io_model.parse_input(input_payload)
    scene = rules.build_scene(parsed["boundary"], parsed["door"],
                              parsed["is_open_inward"], config.TOL)

    total_item_area = sum(item.area for item in parsed["items"])
    zone_area = scene.door_zone.area if scene.door_zone is not None else 0.0
    room_area = scene.room_polygon.area
    if total_item_area > room_area - zone_area + 1e-6:
        return search.not_feasible_result(
            f"物品总面积 {total_item_area / 1e6:.2f} m² 超过房间可用面积 "
            f"{(room_area - zone_area) / 1e6:.2f} m²（已扣除门净空）")

    started = time.monotonic()
    solver = search.Solver(scene, parsed["items"], config)
    result = solver.solve()
    if result is None:
        return search.not_feasible_result("穷举所有候选摆放后未找到可行解")
    if result.timed_out:
        return search.not_feasible_result(f"求解超时（>{config.TIME_LIMIT_SECONDS}s）")

    output = search.format_result(result, [item.name for item in parsed["items"]],
                                  config.ROUND_DIGITS)
    output["_stats"] = {
        "phase": result.phase,
        "wall_touched_items": sum(1 for p in result.placements if p.wall_touched > 0),
        "solve_seconds": round(time.monotonic() - started, 3),
    }
    return output


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="居灵 TakeHome 矩形摆放求解器")
    parser.add_argument("input", type=Path, help="输入 JSON 文件路径")
    parser.add_argument("--out-dir", type=Path, default=Path("output"),
                        help="输出目录（默认 ./output）")
    parser.add_argument("--no-visualize", action="store_true", help="跳过结果图生成")
    args = parser.parse_args(argv)

    try:
        input_payload = _load_json(args.input)
        result = solve_case(input_payload)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"[error] 输入处理失败: {exc}", file=sys.stderr)
        return 2

    stem = args.input.stem
    stats = result.pop("_stats", None)  # 统计信息只打印，不写入输出 JSON
    result_path = args.out_dir / f"{stem}.result.json"
    _write_json(result, result_path)
    print(f"[ok] 结果写入: {result_path}")

    from verify import check_result  # 独立于搜索过程的输出校验
    errors = check_result(input_payload, result, config)
    if errors:
        for message in errors:
            print(f"[error] 内部校验: {message}", file=sys.stderr)
        return 3
    print(f"[ok] 内部校验通过（feasible={result['feasible']}）")

    if stats:
        print(f"     阶段={stats['phase']} 贴墙物品="
              f"{stats['wall_touched_items']}/{len(result['placements'])} "
              f"耗时={stats['solve_seconds']}s")
    if not args.no_visualize:
        try:
            from visualize import render_result
            png_path = args.out_dir / f"{stem}.png"
            render_result(input_payload, result, str(png_path))
            print(f"[ok] 结果图写入: {png_path}")
        except ImportError:
            print("[warn] 未安装 matplotlib，跳过结果图", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
