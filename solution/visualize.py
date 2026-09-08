"""结果图渲染：对齐题目参考图（image01-04）的工程平面图风格。

深色网格底 + 青色房间轮廓 + 彩色物品矩形与中文标签 + 门与净空区标注。
用法：visualize.render_result(input_payload, result_json, out_png_path)
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Tuple

import config
from solver import geometry_utils as geo
from solver import io_model, rules

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager, patches
from shapely import geometry as shp

Point = Tuple[float, float]

_BG = "#0d1b2a"
_ROOM_FILL = "#12233b"
_GRID = "#1d3350"
_BOUNDARY = "#42e0c8"
_DOOR = "#ffe066"
_ZONE = "#ff6b6b"
_TEXT = "#e8f1ff"
_DIM = "#a7e8a0"
_KIND_COLORS = {
    "fridge": "#e0524a",
    "shelf": "#4f86c6",
    "overShelf": "#2aa8a0",
    "iceMaker": "#7fb04a",
    "other": "#8f9bb3",
}
_KIND_LABEL = {
    "fridge": "冰箱",
    "shelf": "货架",
    "overShelf": "离地架",
    "iceMaker": "制冰机",
    "other": "物品",
}


def _nice_step(span: float) -> float:
    """网格步长：约 span/18 的 1/2/5 x 10^k 圆整值。"""
    raw = span / 18.0
    power = 10 ** math.floor(math.log10(max(raw, 1e-6)))
    for factor in (1, 2, 5, 10):
        if raw <= factor * power:
            return factor * power
    return 10 * power


def _setup_font() -> None:
    candidates = ["Microsoft YaHei", "SimHei", "PingFang SC",
                  "Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei"]
    available = {f.name for f in font_manager.fontManager.ttflist}
    chosen = next((name for name in candidates if name in available), None)
    if chosen is None:
        # Windows 常见字体兜底（按绝对路径加载）
        for path in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"):
            if Path(path).exists():
                font_manager.fontManager.addfont(path)
                chosen = font_manager.FontProperties(fname=path).get_name()
                break
    plt.rcParams["font.sans-serif"] = [chosen] if chosen else ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def _kind_of(item: io_model.ItemSpec) -> str:
    if item.kind in _KIND_COLORS:
        return item.kind
    return "other"


def _draw_room(ax, polygon: shp.Polygon) -> Tuple[float, float, float, float]:
    xs, ys = polygon.exterior.xy
    ax.add_patch(patches.Polygon(list(zip(xs, ys)), closed=True,
                                 facecolor=_ROOM_FILL, edgecolor=_BOUNDARY,
                                 linewidth=2.2, zorder=2))
    return polygon.bounds


def _interior_side_sign(scene: rules.Scene, a: Point, b: Point) -> int:
    """门墙方向 a->b 时室内在左(+1)还是右(-1)。"""
    room = scene.room_polygon.buffer(config.TOL)
    ux, uy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(ux, uy)
    if length <= 0:
        return 1
    ux, uy = ux / length, uy / length
    # 墙两侧 1e-3 mm 探针，取在多边形内的那一侧
    left = (a[0] - uy * 1e-3, a[1] + ux * 1e-3)
    return 1 if room.contains(shp.Point(*left)) else -1


def _draw_door(ax, scene: rules.Scene) -> None:
    """画门段、净空区与门扇弧线（内开朝室内、外开朝室外）。"""
    door = scene.door_points or []
    if len(door) != 2 or scene.door_width <= 0:
        return
    a, b = door
    ax.plot([a[0], b[0]], [a[1], b[1]], color=_DOOR, linewidth=5,
            solid_capstyle="butt", zorder=6)
    if scene.door_zone is not None:
        zx, zy = scene.door_zone.exterior.xy
        ax.add_patch(patches.Polygon(list(zip(zx, zy)), closed=True,
                                     facecolor=_ZONE, alpha=0.18,
                                     edgecolor=_ZONE, linestyle="--",
                                     linewidth=1.2, hatch="//", zorder=3))
        zcx, zcy = scene.door_zone.representative_point().x, scene.door_zone.representative_point().y
        ax.text(zcx, zcy, "门净空", color=_ZONE, fontsize=9, ha="center",
                va="center", alpha=0.95, zorder=4)

    side = _interior_side_sign(scene, a, b)
    wall_dir = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
    inward_end = wall_dir + 90.0 * side
    if scene.is_open_inward:
        open_end = inward_end          # 门扇向室内转 90°
    else:
        open_end = wall_dir - 90.0 * side  # 向室外转 90°
    theta1, theta2 = wall_dir, open_end
    if abs(theta2 - theta1) > 180.0:
        theta1, theta2 = theta2, theta1
    radius = scene.door_width
    arc = patches.Arc((a[0], a[1]), 2 * radius, 2 * radius,
                      theta1=min(theta1, theta2), theta2=max(theta1, theta2),
                      color=_DOOR, linewidth=1.8, linestyle="--", zorder=5)
    ax.add_patch(arc)
    open_rad = math.radians(open_end)
    ax.plot([a[0], a[0] + radius * math.cos(open_rad)],
            [a[1], a[1] + radius * math.sin(open_rad)],
            color=_DOOR, linewidth=1.6, linestyle=":", zorder=5)
def _draw_item(ax, item: io_model.ItemSpec, center: Point, theta_deg: float,
               rect: shp.Polygon, index: int) -> None:
    kind = _kind_of(item)
    color = _KIND_COLORS[kind]
    xs, ys = rect.exterior.xy
    ax.add_patch(patches.Polygon(list(zip(xs, ys)), closed=True,
                                 facecolor=color, alpha=0.85, edgecolor="#ffffff",
                                 linewidth=1.4, zorder=4))
    label = _KIND_LABEL.get(kind, kind)
    cx, cy = center
    size = min(item.length, item.width)
    font_size = max(5.5, min(11.0, size / 55.0))
    ax.text(cx, cy, f"{label}", ha="center", va="center", color="#ffffff",
            fontsize=font_size, fontweight="bold", zorder=5)
    if size >= 300:
        ax.text(cx, cy - font_size * 0.6, f"{item.length:.0f}\u00d7{item.width:.0f}",
                ha="center", va="top", color="#ffffff", alpha=0.92,
                fontsize=font_size - 1.5, zorder=5)


def _draw_fridge_open_side(ax, scene: rules.Scene, item: io_model.ItemSpec,
                           center: Point, theta_deg: float,
                           rect: shp.Polygon, others: List[shp.Polygon]) -> None:
    """标出冰箱可用的开门边（净空带完整且无物的一侧）。"""
    th = math.radians(theta_deg)
    vx, vy = -math.sin(th), math.cos(th)
    depth = config.FRIDGE_OPEN_CLEARANCE if config.FRIDGE_OPEN_CLEARANCE is not None else item.width
    room_in = scene.room_polygon.buffer(config.TOL)
    for sign in (1.0, -1.0):
        offset = item.width / 2.0 + depth / 2.0
        strip_center = (center[0] + sign * offset * vx, center[1] + sign * offset * vy)
        strip = geo.rect_polygon(strip_center, theta_deg, item.length, depth)
        if not strip.within(room_in):
            continue
        if any(strip.intersection(other).area > config.AREA_TOL for other in others):
            continue
        cx, cy = center
        # 从开门边中点向外画箭头
        edge_center = (cx + sign * (item.width / 2.0) * vx,
                       cy + sign * (item.width / 2.0) * vy)
        tip = (edge_center[0] + sign * min(depth * 0.35, 500.0) * vx,
               edge_center[1] + sign * min(depth * 0.35, 500.0) * vy)
        ax.annotate("", xy=tip, xytext=edge_center,
                    arrowprops=dict(arrowstyle="-|>", color="#ffe066",
                                    lw=2.0, mutation_scale=18), zorder=6)
        ax.text(edge_center[0] + sign * 260.0 * vx,
                edge_center[1] + sign * 260.0 * vy,
                "开门边", color="#ffe066", fontsize=9, ha="center",
                va="center", zorder=6,
                rotation=math.degrees(math.atan2(sign * vy, sign * vx)))
        return


def _draw_dimensions(ax, scene: rules.Scene, bounds: Tuple[float, float, float, float]) -> None:
    """沿墙画关键边长标注。"""
    x0, y0, x1, y1 = bounds
    diag = math.hypot(x1 - x0, y1 - y0)
    for wall in scene.walls:
        if wall.length < 400:
            continue
        mx = (wall.p1[0] + wall.p2[0]) / 2.0
        my = (wall.p1[1] + wall.p2[1]) / 2.0
        dx, dy = wall.dx, wall.dy
        length = wall.length
        angle = math.degrees(math.atan2(dy, dx))
        # 向房间外侧偏移 2% 对角线
        room = scene.room_polygon.buffer(-1.0)
        inward = room.contains(shp.Point(mx + 10.0 * (-dy / length),
                                         my + 10.0 * (dx / length)))
        outward = 1.0 if not inward else -1.0
        ox, oy = -dy / length * outward, dx / length * outward
        off = max(120.0, diag * 0.02)
        tx, ty = mx + ox * off, my + oy * off
        ax.plot([mx - dx * 0.5, mx + dx * 0.5], [my - dy * 0.5, my + dy * 0.5],
                color=_DIM, linewidth=1.0, alpha=0.9, zorder=1)
        ax.text(tx, ty, f"{length:.0f}", color=_DIM, fontsize=8.5,
                ha="center", va="center", rotation=angle, zorder=1)


def render_result(input_payload: dict, result: dict, out_png: str) -> None:
    """渲染单条结果图；infeasible 时画诊断图（标题 = 面积 + 门信息）。"""
    _setup_font()
    parsed = io_model.parse_input(input_payload)
    scene = rules.build_scene(parsed["boundary"], parsed["door"],
                              parsed["is_open_inward"], config.TOL)
    poly = scene.room_polygon
    x0, y0, x1, y1 = poly.bounds
    pad_x = max(700.0, (x1 - x0) * 0.12)
    pad_y = max(700.0, (y1 - y0) * 0.12)

    fig, ax = plt.subplots(figsize=(10, 10 * (y1 - y0 + 2 * pad_y) / (x1 - x0 + 2 * pad_x)))
    fig.patch.set_facecolor(_BG)
    ax.set_facecolor(_BG)
    ax.set_xlim(x0 - pad_x, x1 + pad_x)
    ax.set_ylim(y0 - pad_y, y1 + pad_y)
    step_x = _nice_step(x1 - x0)
    step_y = _nice_step(y1 - y0)
    ax.set_xticks([v for v in _arange_floor(x0 - pad_x, x1 + pad_x, step_x)])
    ax.set_yticks([v for v in _arange_floor(y0 - pad_y, y1 + pad_y, step_y)])
    ax.grid(color=_GRID, linewidth=0.7, alpha=0.6)
    ax.tick_params(colors=_GRID, labelsize=6)
    for spine in ax.spines.values():
        spine.set_color(_GRID)

    bounds = _draw_room(ax, poly)
    _draw_door(ax, scene)
    _draw_dimensions(ax, scene, bounds)

    if result.get("feasible"):
        placements = result.get("placements") or []
        specs = {item.name: item for item in parsed["items"]}
        others: List[shp.Polygon] = []
        for index, placement in enumerate(placements):
            name = placement.get("name")
            if name not in specs:
                continue
            center = placement.get("center")
            rotation = placement.get("rotation")
            rect = geo.rect_polygon(tuple(center), float(rotation),
                                    specs[name].length, specs[name].width)
            _draw_item(ax, specs[name], tuple(center), float(rotation), rect, index)
            others.append(rect)
        for placement in placements:
            name = placement.get("name")
            item = specs.get(name)
            if item is None or item.kind != "fridge":
                continue
            center = placement.get("center")
            rect = geo.rect_polygon(tuple(center), float(placement.get("rotation")),
                                    item.length, item.width)
            _draw_fridge_open_side(ax, scene, item, tuple(center),
                                   float(placement.get("rotation")), rect, others)
    else:
        reason = result.get("reason", "")
        ax.text((x0 + x1) / 2, (y0 + y1) / 2, "不可行：无可摆放方案",
                ha="center", va="center", color="#ffb3b3", fontsize=15,
                fontweight="bold", zorder=7,
                bbox=dict(boxstyle="round,pad=0.6", facecolor="#3a1016",
                          edgecolor=_ZONE))
        ax.text((x0 + x1) / 2, (y0 + y1) / 2 - pad_y * 0.12, reason,
                ha="center", va="center", color="#e8c9c9", fontsize=9, zorder=7)

    ax.set_title(f"储物区面积: {poly.area / 1e6:.2f} m² | "
                 f"门宽 {scene.door_width:.0f} mm（{'内开' if scene.is_open_inward else '外开'}）",
                 color=_TEXT, fontsize=11, pad=12)
    fig.savefig(out_png, dpi=150, facecolor=_BG, bbox_inches="tight")
    plt.close(fig)


def _arange_floor(start: float, stop: float, step: float):
    value = start
    while value <= stop:
        yield value
        value += step
