"""输入输出 JSON 的数据模型与解析。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class ItemSpec:
    """一个待摆放物品：名字、尺寸（length x width）、类型。"""

    name: str
    length: float
    width: float
    kind: str

    @property
    def area(self) -> float:
        return self.length * self.width


def detect_kind(name: str) -> str:
    """按物品名识别类型；识别不到时归为普通物品。"""
    lower = name.lower()
    if "fridge" in lower:
        return "fridge"
    if "overshelf" in lower:
        return "overShelf"
    if "shelf" in lower:
        return "shelf"
    if "icemaker" in lower:
        return "iceMaker"
    return "other"


def parse_input(payload: Dict[str, Any]) -> Dict[str, Any]:
    """解析并校验输入 JSON，返回规范化后的内部结构。

    返回: {"boundary": [[x, y], ...], "door": [[x1, y1], [x2, y2]],
            "is_open_inward": bool, "items": [ItemSpec, ...]}
    """
    if not isinstance(payload, dict):
        raise ValueError("输入不是 JSON 对象")
    boundary = payload.get("boundary")
    door = payload.get("door")
    algo_to_place = payload.get("algoToPlace")
    if not boundary or len(boundary) < 3:
        raise ValueError("boundary 至少需要 3 个顶点")
    if not door or len(door) != 2:
        raise ValueError("door 需要两个端点")
    if not algo_to_place or not isinstance(algo_to_place, dict):
        raise ValueError("algoToPlace 需要是非空对象")

    def _to_point(pair: Any, label: str):
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError(f"{label} 顶点必须是 [x, y]")
        return [float(pair[0]), float(pair[1])]

    coords = [_to_point(p, "boundary") for p in boundary]
    door_pts = [_to_point(p, "door") for p in door]
    if math.hypot(door_pts[1][0] - door_pts[0][0], door_pts[1][1] - door_pts[0][1]) <= 0:
        raise ValueError("door 两个端点重合")

    items: List[ItemSpec] = []
    for raw_name, dims in algo_to_place.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise ValueError("物品名不能为空")
        if not isinstance(dims, (list, tuple)) or len(dims) != 2:
            raise ValueError(f"物品 {raw_name} 尺寸必须是 [length, width]")
        length, width = float(dims[0]), float(dims[1])
        if length <= 0 or width <= 0:
            raise ValueError(f"物品 {raw_name} 尺寸必须为正数")
        items.append(ItemSpec(raw_name, length, width, detect_kind(raw_name)))

    return {
        "boundary": coords,
        "door": door_pts,
        "is_open_inward": bool(payload.get("isOpenInward", False)),
        "items": items,
    }
