"""规则层：门净空、冰箱开门净空、贴墙判定，以及场景构建。"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from shapely import geometry as shp

from . import geometry_utils as geo
from .io_model import ItemSpec

Point = Tuple[float, float]
# 一条摆放记录：(物品, 中心点, 朝向角度(度), 矩形)
Entry = Tuple[ItemSpec, Point, float, shp.Polygon]


@dataclass
class Wall:
    """房间的一条最长墙段（已合并共线段），方向沿外环。"""

    p1: Point
    p2: Point

    @property
    def dx(self) -> float:
        return self.p2[0] - self.p1[0]

    @property
    def dy(self) -> float:
        return self.p2[1] - self.p1[1]

    @property
    def length(self) -> float:
        return math.hypot(self.dx, self.dy)

    def angle_deg(self) -> float:
        """墙方向角，归一化到 [0, 180)。"""
        return math.degrees(math.atan2(self.dy, self.dx)) % 180.0


@dataclass
class Scene:
    """求解场景：房间、墙、门净空区与允许的物品朝向。"""

    room_polygon: shp.Polygon
    walls: List[Wall]
    door_zone: Optional[shp.Polygon]
    door_width: float
    is_open_inward: bool
    orientations_deg: List[float] = field(default_factory=list)
    # 门所在墙在 walls 中的下标；door_points 为门端点（世界坐标）
    door_wall_index: Optional[int] = None
    door_points: Optional[List[Point]] = None


def _point_segment_distance(point: Point, a: Point, b: Point) -> float:
    """点到线段距离。"""
    px, py = point
    ax, ay = a
    bx, by = b
    vx, vy = bx - ax, by - ay
    length_sq = vx * vx + vy * vy
    if length_sq <= 1e-18:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * vx + (py - ay) * vy) / length_sq
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * vx, ay + t * vy
    return math.hypot(px - cx, py - cy)


def _find_door_wall(walls: List[Wall], door: Sequence[Point], tol: float) -> Wall:
    """找到门段所在的墙段。"""
    for wall in walls:
        on_a = _point_segment_distance(door[0], wall.p1, wall.p2) <= tol
        on_b = _point_segment_distance(door[1], wall.p1, wall.p2) <= tol
        if on_a and on_b:
            return wall
    raise ValueError("door 不在 boundary 的任何一条边上")


def _choose_inward_zone(polygon: shp.Polygon, door: Sequence[Point],
                        depth: float, tol: float) -> shp.Polygon:
    """门内侧 N x N 净空区：门段为一边、向室内推进 depth。

    法向两侧各生成一个候选，取整体落在房间内的那一侧。
    """
    a, b = door[0], door[1]
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    if length <= 0:
        raise ValueError("door 长度必须大于 0")
    ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    candidates = []
    for sign in (1.0, -1.0):
        nx, ny = -uy * sign, ux * sign
        zone = shp.Polygon([
            a,
            b,
            (b[0] + nx * depth, b[1] + ny * depth),
            (a[0] + nx * depth, a[1] + ny * depth),
        ])
        if zone.area > 0:
            candidates.append(zone)
    for zone in candidates:
        if zone.within(polygon.buffer(tol)):
            return zone
    for zone in candidates:
        if polygon.buffer(-tol).contains(zone.representative_point()):
            return zone
    raise ValueError("无法确定门的室内侧方向")


def build_scene(boundary: Sequence[Point], door: Sequence[Point],
                is_open_inward: bool, tol: float) -> Scene:
    """由输入数据构建求解场景。"""
    polygon = geo.clean_polygon(boundary)
    walls = [Wall(a, b) for a, b in geo.merge_walls(polygon)]
    door_wall = _find_door_wall(walls, door, max(tol, 1e-6))
    door_width = math.hypot(door[1][0] - door[0][0], door[1][1] - door[0][1])
    # 门端点按墙段方向排列，保证净空矩形角点顺序正确
    wdx, wdy = door_wall.dx, door_wall.dy
    if door_width > 0 and (wdx * (door[1][0] - door[0][0]) + wdy * (door[1][1] - door[0][1])) < 0:
        ordered_door = [door[1], door[0]]
    else:
        ordered_door = list(door)
    zone = _choose_inward_zone(polygon, ordered_door, door_width, tol)
    door_wall_index = walls.index(door_wall)
    door_points = [tuple(p) for p in door]
    # 允许朝向：0/90 加上各斜墙方向角与其垂直方向（3 位小数去重）
    orientations = {0.0, 90.0}
    for wall in walls:
        angle = wall.angle_deg()
        orientations.add(round(angle, 5))
        orientations.add(round((angle + 90.0) % 180.0, 5))
    return Scene(
        room_polygon=polygon,
        walls=walls,
        door_zone=zone,
        door_width=door_width,
        is_open_inward=bool(is_open_inward),
        orientations_deg=sorted(orientations),
        door_wall_index=door_wall_index,
        door_points=door_points,
    )


def _rect_edges(rect: shp.Polygon) -> List[Tuple[Point, Point]]:
    """返回矩形四条边。"""
    coords = list(rect.exterior.coords)[:-1]
    return [(coords[i], coords[(i + 1) % len(coords)]) for i in range(len(coords))]


def walls_touched(scene: Scene, rect: shp.Polygon, tol: float,
                  min_overlap: float) -> int:
    """统计矩形与多少条墙段存在有效贴墙接触（共线重合 ≥ min_overlap mm）。"""
    count = 0
    edges = _rect_edges(rect)
    for wall in scene.walls:
        for edge in edges:
            if geo.collinear_overlap_length(edge, (wall.p1, wall.p2), tol) >= min_overlap:
                count += 1
                break
    return count


def _fridge_side_open(scene: Scene, center: Point, theta_deg: float,
                      item: ItemSpec, depth: float, other_rects: Sequence[shp.Polygon],
                      tol: float, area_tol: float) -> bool:
    """冰箱任一开门边外侧净空带可用：完整在室内且不与其他物品重叠。"""
    th = math.radians(theta_deg)
    vx, vy = -math.sin(th), math.cos(th)
    room_in = scene.room_polygon.buffer(tol)
    for sign in (1.0, -1.0):
        offset = item.width / 2.0 + depth / 2.0
        strip_center = (center[0] + sign * offset * vx,
                        center[1] + sign * offset * vy)
        strip = geo.rect_polygon(strip_center, theta_deg, item.length, depth)
        if not strip.within(room_in):
            continue
        if _rects_overlap_any(strip, other_rects, area_tol):
            continue
        return True
    return False


def _rects_overlap_any(rect: shp.Polygon, others: Sequence[shp.Polygon], area_tol: float) -> bool:
    """矩形是否与任一给定区域重叠（相交面积超过容差视为重叠）。"""
    for other in others:
        if rect.intersection(other).area > area_tol:
            return True
    return False


def validate_set(scene: Scene, entries: Sequence[Entry], clearance: Optional[float],
                 tol: float, area_tol: float) -> List[str]:
    """校验一组摆放是否满足全部约束。

    覆盖：整体在室内、物品两两不重叠、不压门净空区，且每个冰箱都保留
    至少一侧可用的开门净空带。返回错误描述列表，为空表示合法。
    """
    errors: List[str] = []
    room_in = scene.room_polygon.buffer(tol)
    rects = [entry[3] for entry in entries]
    for index, (item, center, theta_deg, rect) in enumerate(entries):
        label = f"{item.name}({index + 1})"
        if not rect.within(room_in):
            errors.append(f"{label} 越出房间轮廓")
        if scene.door_zone is not None and rect.intersection(scene.door_zone).area > area_tol:
            errors.append(f"{label} 遮挡门或压到门净空区")
        if item.kind == "fridge":
            depth = clearance if clearance is not None else item.width
            others = [r for i, r in enumerate(rects) if i != index]
            if not _fridge_side_open(scene, center, theta_deg, item, depth,
                                     others, tol, area_tol):
                errors.append(f"{label} 开门边两侧净空带都不足（深度 {depth}mm）")
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            if rects[i].intersection(rects[j]).area > area_tol:
                errors.append(f"{entries[i][0].name} 与 {entries[j][0].name} 相互重叠")
    return errors
