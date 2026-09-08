"""几何工具：多边形规范化、墙段合并、矩形构造等（基于 shapely）。"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

from shapely import geometry as shp

Point = Tuple[float, float]
# 共线/平行判断的角容差（弧度）：仅用于合并完全共线的相邻墙段
_ANGLE_TOL = 1e-6


def signed_area(points: Sequence[Point]) -> float:
    """多边形有向面积（鞋带公式），正值为逆时针。"""
    total = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def clean_polygon(boundary: Sequence[Point]) -> shp.Polygon:
    """由顶点构造房间多边形：去重、修复自交、统一为逆时针、面积校验。"""
    ring = [(float(x), float(y)) for x, y in boundary]
    if len(ring) >= 2 and ring[0] == ring[-1]:
        ring = ring[:-1]
    if len(ring) < 3:
        raise ValueError("boundary 至少需要 3 个顶点")
    # 去掉因浮点冗余导致的重复/近重复点，避免 shapely 报 invalid
    cleaned: List[Point] = []
    for p in ring:
        if cleaned and math.hypot(p[0] - cleaned[-1][0], p[1] - cleaned[-1][1]) < 1e-9:
            continue
        cleaned.append(p)
    if len(cleaned) < 3:
        raise ValueError("boundary 顶点过少")
    poly = shp.Polygon(cleaned)
    if not poly.is_valid:
        poly = poly.buffer(0)  # 修复轻微自交
    if poly.is_empty or poly.area <= 1e-9:
        raise ValueError("boundary 围成的面积必须大于 0")
    if poly.exterior.is_ccw is False:
        poly = shp.Polygon(list(poly.exterior.coords)[::-1])
    return poly


def _collinear(p1: Point, p2: Point, p3: Point) -> bool:
    """相邻三点是否共线（p2 为中间点，两条边方向一致）。"""
    dx1, dy1 = p2[0] - p1[0], p2[1] - p1[1]
    dx2, dy2 = p3[0] - p2[0], p3[1] - p2[1]
    len1 = math.hypot(dx1, dy1)
    len2 = math.hypot(dx2, dy2)
    if len1 <= 1e-12 or len2 <= 1e-12:
        return False
    cross = abs(dx1 * dy2 - dy1 * dx2)
    return cross <= _ANGLE_TOL * len1 * len2


def merge_walls(polygon: shp.Polygon) -> List[Tuple[Point, Point]]:
    """把共线的相邻边界段合并为最长墙段，返回 [(p1, p2), ...]。

    结果按多边形外环逆时针顺序排列。
    """
    ring = list(polygon.exterior.coords)[:-1]
    walls: List[Tuple[Point, Point]] = []
    start = ring[0]
    end = ring[1]
    for i in range(2, len(ring) + 1):
        point = ring[i % len(ring)]
        if i < len(ring) and _collinear(start, end, point):
            end = point
        else:
            if math.hypot(end[0] - start[0], end[1] - start[1]) > 1e-9:
                walls.append((start, end))
            start, end = end, point
    # 闭合环的最后一段墙（回到起点前）
    if math.hypot(end[0] - start[0], end[1] - start[1]) > 1e-9:
        walls.append((start, end))
    return walls


def rect_polygon(center: Point, theta_deg: float, length: float, width: float) -> shp.Polygon:
    """构造物品矩形。

    length 方向与 +x 轴夹角为 theta_deg（逆时针），width 方向与其垂直；
    center 为矩形中心。返回 ccw 多边形。
    """
    cx, cy = float(center[0]), float(center[1])
    th = math.radians(theta_deg)
    ux, uy = math.cos(th), math.sin(th)
    vx, vy = -uy, ux
    h_l = length / 2.0
    h_w = width / 2.0
    corners = [
        (cx + ux * h_l + vx * h_w, cy + uy * h_l + vy * h_w),
        (cx - ux * h_l + vx * h_w, cy - uy * h_l + vy * h_w),
        (cx - ux * h_l - vx * h_w, cy - uy * h_l - vy * h_w),
        (cx + ux * h_l - vx * h_w, cy + uy * h_l - vy * h_w),
    ]
    return shp.Polygon(corners)


def collinear_overlap_length(seg_a: Tuple[Point, Point], seg_b: Tuple[Point, Point], tol: float) -> float:
    """两条共线线段的重合长度；不共线或不相交时返回 0。"""
    a1, a2 = seg_a
    b1, b2 = seg_b
    dx, dy = a2[0] - a1[0], a2[1] - a1[1]
    length = math.hypot(dx, dy)
    if length <= 1e-12:
        return 0.0
    ux, uy = dx / length, dy / length
    # b 的两个端点在 a 直线上的垂距
    cross_b1 = abs(ux * (b1[1] - a1[1]) - uy * (b1[0] - a1[0]))
    cross_b2 = abs(ux * (b2[1] - a1[1]) - uy * (b2[0] - a1[0]))
    if cross_b1 > tol or cross_b2 > tol:
        return 0.0
    # 把各端点投影到 a 的方向上，求区间重叠
    def _proj(point: Point) -> float:
        return (point[0] - a1[0]) * ux + (point[1] - a1[1]) * uy

    lo = max(0.0, min(_proj(b1), _proj(b2)))
    hi = min(length, max(_proj(b1), _proj(b2)))
    return max(0.0, hi - lo)
