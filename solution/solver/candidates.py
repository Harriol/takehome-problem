"""候选摆放位生成。

思路：在物品自身坐标系（length 轴为 x）下做离散化——所有"贴墙/贴物
滑动"的锚点取自特征线（墙端点、房间顶点、已放物品边等在物品坐标系中
的投影线）。覆盖：贴墙候选、贴已放物品候选、兜底网格。
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Set, Tuple

from shapely import geometry as shp

from .io_model import ItemSpec
from .rules import Scene

Point = Tuple[float, float]
# 候选中心去重坐标精度（mm）
_DEDUP_DIGITS = 3


def _to_frame(point: Point, u: Tuple[float, float], v: Tuple[float, float]) -> Point:
    """世界坐标 -> 物品坐标系（纯旋转，不缩放）。"""
    return (point[0] * u[0] + point[1] * u[1], point[0] * v[0] + point[1] * v[1])


def _to_world(q: Point, u: Tuple[float, float], v: Tuple[float, float]) -> Point:
    """物品坐标系 -> 世界坐标。"""
    return (q[0] * u[0] + q[1] * v[0], q[0] * u[1] + q[1] * v[1])


def _collect_features(scene: Scene, placed_rects: Sequence[shp.Polygon],
                      u: Tuple[float, float], v: Tuple[float, float]) -> Tuple[Set[float], Set[float]]:
    """收集物品坐标系下的特征线（垂直线的 x、水平线的 y）。

    来源：房间顶点、门净空区角点、已放物品角点。
    """
    xs: Set[float] = set()
    ys: Set[float] = set()
    sources: List[Point] = list(scene.room_polygon.exterior.coords)
    if scene.door_zone is not None:
        sources.extend(scene.door_zone.exterior.coords)
    for rect in placed_rects:
        sources.extend(rect.exterior.coords)
    for point in sources:
        qx, qy = _to_frame(point, u, v)
        xs.add(qx)
        ys.add(qy)
    return xs, ys


def _door_frame_span(scene: Scene, wall_index: int, horizontal: bool,
                     u: Tuple[float, float], v: Tuple[float, float]) -> Optional[Tuple[float, float]]:
    """门墙在物品坐标系中的门段坐标范围（沿接触轴），非门墙返回 None。"""
    if scene.door_wall_index != wall_index or not scene.door_points:
        return None
    qs = [_to_frame(p, u, v) for p in scene.door_points]
    axis = 0 if horizontal else 1
    values = [q[axis] for q in qs]
    return min(values), max(values)


def _free_spans(lo: float, hi: float,
                door_span: Optional[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """墙段允许贴合的沿墙范围 [lo, hi]，扣除门段所在区域（仅门墙）。"""
    if door_span is None:
        return [(lo, hi)]
    da, db = door_span
    parts = []
    if lo < da - 1e-9:
        parts.append((lo, min(hi, da)))
    if db + 1e-9 < hi:
        parts.append((max(lo, db), hi))
    return [p for p in parts if p[1] - p[0] > 1e-9]


def _interval_inside(lo: float, hi: float, span_lo: float, span_hi: float, tol: float) -> bool:
    return lo >= span_lo - tol and hi <= span_hi + tol


def _add_flush_frame(scene: Scene, item: ItemSpec, u: Tuple[float, float], v: Tuple[float, float],
                     fx: Set[float], fy: Set[float], centers: List[Point]) -> None:
    """生成物品坐标系下贴墙候选。

    - 水平墙：物品的 length 边贴墙（沿 x 的边长为 L），候选 cy = 墙y ± W/2；
      滑动的 cx 取特征垂直线的 ±L/2，并要求接触区间在墙段内、避开门口。
    - 垂直墙：对称处理（length 轴垂直墙）。
    """
    half_l = item.length / 2.0
    half_w = item.width / 2.0
    tol = 1e-3
    for wall_index, wall in enumerate(scene.walls):
        p1 = _to_frame(wall.p1, u, v)
        p2 = _to_frame(wall.p2, u, v)
        if abs(p1[1] - p2[1]) <= tol and abs(p1[0] - p2[0]) > tol:
            # 水平墙：接触区间为 [cx-L/2, cx+L/2]，须落在可用 span 内
            x0, x1 = min(p1[0], p2[0]), max(p1[0], p2[0])
            spans = _free_spans(x0, x1, _door_frame_span(scene, wall_index, True, u, v))
            y0 = p1[1]
            for cy in (y0 + half_w, y0 - half_w):
                candidate_cx = [x0 + half_l, x1 - half_l]
                for f in fx:
                    candidate_cx.append(f - half_l)
                    candidate_cx.append(f + half_l)
                for cx in candidate_cx:
                    for span_lo, span_hi in spans:
                        if _interval_inside(cx - half_l, cx + half_l, span_lo, span_hi, tol):
                            centers.append((cx, cy))
                            break
        elif abs(p1[0] - p2[0]) <= tol and abs(p1[1] - p2[1]) > tol:
            # 垂直墙：接触区间为 [cy-W/2, cy+W/2]
            y0, y1 = min(p1[1], p2[1]), max(p1[1], p2[1])
            spans = _free_spans(y0, y1, _door_frame_span(scene, wall_index, False, u, v))
            x0 = p1[0]
            for cx in (x0 + half_l, x0 - half_l):
                candidate_cy = [y0 + half_w, y1 - half_w]
                for f in fy:
                    candidate_cy.append(f - half_w)
                    candidate_cy.append(f + half_w)
                for cy in candidate_cy:
                    for span_lo, span_hi in spans:
                        if _interval_inside(cy - half_w, cy + half_w, span_lo, span_hi, tol):
                            centers.append((cx, cy))
                            break


def _add_adjacent_frame(scene: Scene, item: ItemSpec, placed_rects: Sequence[shp.Polygon],
                        u: Tuple[float, float], v: Tuple[float, float],
                        fx: Set[float], fy: Set[float], centers: List[Point]) -> None:
    """贴已放物品的边放置（物品坐标系下），接触区间须落在该边上。"""
    half_l = item.length / 2.0
    half_w = item.width / 2.0
    tol = 1e-3
    for rect in placed_rects:
        qs = [_to_frame(p, u, v) for p in rect.exterior.coords]
        qx = [q[0] for q in qs]
        qy = [q[1] for q in qs]
        x0, x1 = min(qx), max(qx)
        y0, y1 = min(qy), max(qy)
        # 水平边（y0/y1）：接触沿 x，区间 [cx-L/2, cx+L/2] ⊂ [x0, x1]
        for edge_y in (y0, y1):
            for cy in (edge_y + half_w, edge_y - half_w):
                candidate_cx = [x0 + half_l, x1 - half_l]
                for f in fx:
                    candidate_cx.append(f - half_l)
                    candidate_cx.append(f + half_l)
                for cx in candidate_cx:
                    if _interval_inside(cx - half_l, cx + half_l, x0, x1, tol):
                        centers.append((cx, cy))
        # 垂直边（x0/x1）：接触沿 y，区间 [cy-W/2, cy+W/2] ⊂ [y0, y1]
        for edge_x in (x0, x1):
            for cx in (edge_x + half_l, edge_x - half_l):
                candidate_cy = [y0 + half_w, y1 - half_w]
                for f in fy:
                    candidate_cy.append(f - half_w)
                    candidate_cy.append(f + half_w)
                for cy in candidate_cy:
                    if _interval_inside(cy - half_w, cy + half_w, y0, y1, tol):
                        centers.append((cx, cy))


def _add_grid_frame(scene: Scene, item: ItemSpec,
                    u: Tuple[float, float], v: Tuple[float, float],
                    config, centers: List[Point]) -> None:
    """兜底：按物品最小边尺寸在房间包围盒内撒网格中心。"""
    step = max(config.GRID_STEP_MIN, min(item.length, item.width) * config.GRID_STEP_FACTOR)
    frame_points = [_to_frame(p, u, v) for p in scene.room_polygon.exterior.coords]
    xs = [p[0] for p in frame_points]
    ys = [p[1] for p in frame_points]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    count_x = int((xmax - xmin) / step) + 1
    count_y = int((ymax - ymin) / step) + 1
    while count_x * count_y > config.GRID_MAX_CANDIDATES:
        step *= 2.0
        count_x = int((xmax - xmin) / step) + 1
        count_y = int((ymax - ymin) / step) + 1
    x = xmin
    while x <= xmax:
        y = ymin
        while y <= ymax:
            centers.append((x, y))
            y += step
        x += step


def generate_candidates(scene: Scene, item: ItemSpec, theta_deg: float,
                        placed_rects: Sequence[shp.Polygon], mode: str,
                        config) -> List[Point]:
    """生成某物品在某朝向下所有候选中心（世界坐标）。

    mode: "wall_only" 只贴墙（阶段一）；"all" 贴墙 + 贴物 + 网格（阶段二）。
    """
    th = math.radians(theta_deg)
    u = (math.cos(th), math.sin(th))
    v = (-math.sin(th), math.cos(th))
    fx, fy = _collect_features(scene, placed_rects, u, v)
    centers: List[Point] = []
    _add_flush_frame(scene, item, u, v, fx, fy, centers)
    if mode == "all":
        _add_adjacent_frame(scene, item, placed_rects, u, v, fx, fy, centers)
        _add_grid_frame(scene, item, u, v, config, centers)
    # 去重（物品坐标系取整，避免贴物/贴墙重复与浮点抖动）
    seen = set()
    result: List[Point] = []
    for cx, cy in centers:
        key = (round(cx, _DEDUP_DIGITS), round(cy, _DEDUP_DIGITS))
        if key not in seen:
            seen.add(key)
            result.append(_to_world((cx, cy), u, v))
    return result
