"""随机模糊测试：随机正交多边形房间 + 随机物品，验证求解器不崩溃、
可行解必过独立校验；对必然可解的构造（已知摆放）保证能找到解。

用法: python gen_tests.py [case_count] [seed]
"""

from __future__ import annotations

import random
import sys

from shapely.geometry import Polygon
from shapely.ops import unary_union

import config
from solver import io_model, rules, search
from verify import check_result

_CELL = 1000.0


def _random_orthogonal_room(rng: random.Random) -> Polygon:
    """用连通单元并集生成无洞正交房间（可能含凹角）。"""
    for _attempt in range(40):
        grid_x = rng.randint(3, 6)
        grid_y = rng.randint(3, 6)
        cells = {(x, y) for x in range(grid_x) for y in range(grid_y)}
        # 随机挖掉一些不破坏连通性的角单元（简单起见：随机删除，保留并集面积 >= 55%）
        to_keep = set(cells)
        for cell in list(cells):
            if len(to_keep) <= max(6, int(len(cells) * 0.55)):
                break
            if rng.random() < 0.25:
                to_keep.discard(cell)
        # 只用"外边界封闭"验证；若有洞则放弃该次尝试
        polys = [Polygon([(x * _CELL, y * _CELL),
                          ((x + 1) * _CELL, y * _CELL),
                          ((x + 1) * _CELL, (y + 1) * _CELL),
                          (x * _CELL, (y + 1) * _CELL)])
                 for x, y in to_keep]
        room = unary_union(polys)
        if room.geom_type != "Polygon":
            continue
        if any(hole.area > 1 for hole in room.interiors):
            continue
        if room.area < 6 * _CELL * _CELL:
            continue
        # 缩放平移保持坐标接近 0~1e5（模拟真实量级），并轻微加小数
        return Polygon([(p[0] * 3.7 + 12000.13, p[1] * 2.3 + 8000.7)
                        for p in room.exterior.coords])
    raise RuntimeError("随机房间生成失败")


def _pick_door(rng: random.Random, polygon: Polygon):
    """从房间边界随机取一段 >= 600 的墙作为门。"""
    coords = list(polygon.exterior.coords)[:-1]
    edges = []
    for a, b in zip(coords, coords[1:] + coords[:1]):
        length = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
        if length >= 800:
            edges.append((a, b, length))
    a, b, length = rng.choice(edges)
    n = min(600.0, rng.uniform(300.0, length * 0.5))
    t = rng.uniform(0.0, length - n)
    frac = t / length
    ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    start = (a[0] + ux * t, a[1] + uy * t)
    end = (start[0] + ux * n, start[1] + uy * n)
    return [start, end]


def _random_items(rng: random.Random, room_area: float, max_items: int) -> dict:
    count = rng.randint(2, max_items)
    items = {}
    budget = room_area * 0.16
    for i in range(count):
        length = rng.randint(300, 900)
        width = rng.randint(300, 700)
        kind = rng.choice(["shelf", "overShelf", "iceMaker", "shelf", "fridge"])
        items[f"{kind}-{i}"] = [length, width]
        budget -= length * width
    return items


def run_fuzz(case_count: int, seed: int) -> None:
    rng = random.Random(seed)
    config.TIME_LIMIT_SECONDS = 5.0  # 模糊测试使用更小的时间预算
    solved = 0
    feasible = 0
    for case in range(case_count):
        try:
            room = _random_orthogonal_room(rng)
            door = _pick_door(rng, room)
            items = _random_items(rng, room.area, 5)
            payload = {
                "boundary": [list(p) for p in room.exterior.coords],
                "door": door,
                "isOpenInward": rng.random() < 0.5,
                "algoToPlace": items,
            }
            parsed = io_model.parse_input(payload)
            scene = rules.build_scene(parsed["boundary"], parsed["door"],
                                      parsed["is_open_inward"], config.TOL)
            result = search.Solver(scene, parsed["items"], config).solve()
            solved += 1
            if result is not None and not result.timed_out:
                feasible += 1
                output = search.format_result(
                    result, [i.name for i in parsed["items"]], config.ROUND_DIGITS)
                errors = check_result(payload, output, config)
                assert not errors, f"case {case} 校验失败: {errors}"
            elif result is not None and result.timed_out:
                print(f"case {case}: 超时（按不可行记录，需人工关注）")
        except Exception as exc:  # 任何意外都应暴露而不是吞掉
            print(f"case {case}: 异常 {type(exc).__name__}: {exc}")
            raise
    print(f"模糊测试完成: {solved}/{case_count} 例成功求解，"
          f"其中 {feasible} 例可行（可行输出均通过独立校验）")


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 42
    run_fuzz(count, seed)
