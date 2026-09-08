"""两阶段回溯搜索：先求全贴墙解，再放宽到一般可行解。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional

from shapely import geometry as shp

from . import candidates, rules
from .geometry_utils import rect_polygon
from .io_model import ItemSpec
from .rules import Entry, Scene, validate_set, walls_touched

Point = tuple


@dataclass
class Placement:
    item: ItemSpec
    center: Point
    theta_deg: float
    rect: shp.Polygon
    wall_touched: int = 0


@dataclass
class SolveResult:
    placements: List[Placement]
    phase: str
    timed_out: bool = False


class _Timeout(Exception):
    """求解超过时间预算。"""


class Solver:
    """两阶段确定性求解器。"""

    def __init__(self, scene: Scene, items: List[ItemSpec], config) -> None:
        self.scene = scene
        self.items = items
        self.config = config
        # 面积大的先放（确定性：同面积按名称排序）
        self._order = sorted(range(len(items)),
                             key=lambda i: (-items[i].area, items[i].name))
        self._time_start = 0.0

    def solve(self) -> Optional[SolveResult]:
        """依次尝试阶段一（全贴墙）与阶段二（任意可行解）。"""
        for mode in ("wall_only", "all"):
            self._time_start = time.monotonic()
            try:
                placed = self._dfs(0, [], mode)
            except _Timeout:
                return SolveResult(placements=[], phase=mode, timed_out=True)
            if placed is not None:
                return SolveResult(placements=placed, phase=mode)
        return None

    def _check_timeout(self) -> None:
        if time.monotonic() - self._time_start > self.config.TIME_LIMIT_SECONDS:
            raise _Timeout()

    def _dfs(self, depth: int, placed: List[Placement], mode: str) -> Optional[List[Placement]]:
        self._check_timeout()
        if depth == len(self._order):
            return list(placed)
        item = self.items[self._order[depth]]

        # 剪枝：剩余物品总面积超过剩余可用面积
        remaining_min_area = sum(self.items[i].area for i in self._order[depth + 1:])
        used_area = sum(p.rect.area for p in placed)
        zone_area = self.scene.door_zone.area if self.scene.door_zone is not None else 0.0
        free_area = self.scene.room_polygon.area - used_area - zone_area
        if remaining_min_area > free_area + 1e-6:
            return None

        candidates = self._collect_candidates(item, placed, mode)
        placed_rects = [p.rect for p in placed]
        for center, theta_deg in candidates:
            rect = rect_polygon(center, theta_deg, item.length, item.width)
            entries: List[Entry] = [(p.item, p.center, p.theta_deg, p.rect) for p in placed]
            entries.append((item, center, theta_deg, rect))
            errors = validate_set(self.scene, entries, self.config.FRIDGE_OPEN_CLEARANCE,
                                  self.config.TOL, self.config.AREA_TOL)
            if not errors:
                placed.append(Placement(item=item, center=center, theta_deg=theta_deg,
                                        rect=rect,
                                        wall_touched=walls_touched(
                                            self.scene, rect, self.config.TOL,
                                            self.config.WALL_TOUCH_LEN_MIN)))
                result = self._dfs(depth + 1, placed, mode)
                if result is not None:
                    return result
                placed.pop()
        return None

    def _collect_candidates(self, item: ItemSpec, placed: List[Placement],
                            mode: str) -> List[Point]:
        """生成并排序候选：贴墙优先、坐标确定性。"""
        placed_rects = [p.rect for p in placed]
        scored = []
        seen = set()
        for theta_deg in self.scene.orientations_deg:
            for center in candidates.generate_candidates(
                    self.scene, item, theta_deg, placed_rects, mode, self.config):
                key = (round(center[0], 3), round(center[1], 3), round(theta_deg, 4))
                if key in seen:
                    continue
                seen.add(key)
                rect = rect_polygon(center, theta_deg, item.length, item.width)
                touched = walls_touched(self.scene, rect, self.config.TOL,
                                        self.config.WALL_TOUCH_LEN_MIN)
                if mode == "wall_only" and touched < 1:
                    continue
                scored.append((-touched, center[0], center[1], theta_deg))
        scored.sort(key=lambda t: (t[0], t[1], t[2], t[3]))
        return [( (t[1], t[2]), t[3]) for t in scored]


def format_result(solve_result: SolveResult, input_order: List[str], round_digits: int) -> dict:
    """转为题目约定的输出 JSON（按输入顺序排序物品）。"""
    by_name = {p.item.name: p for p in solve_result.placements}
    placements = []
    for name in input_order:
        placement = by_name.get(name)
        if placement is not None:
            placements.append({
                "name": name,
                "center": [round(placement.center[0], round_digits),
                           round(placement.center[1], round_digits)],
                "rotation": round(placement.theta_deg, round_digits),
            })
    return {"feasible": True, "placements": placements}


def not_feasible_result(reason: str) -> dict:
    """不可行输出结构。"""
    return {"feasible": False, "placements": [], "reason": reason}
