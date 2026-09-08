"""独立校验器：重读输入与输出，逐条复核所有约束。

独立使用：python verify.py <input.json> <result.json>
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import List

import config
from solver import geometry_utils as geo
from solver import io_model, rules


def _rotation_allowed(rotation: float, orientations: List[float], tol: float) -> bool:
    """旋转角是否属于允许朝向（矩形 180° 对称，归一化到 [0,180) 比较）。"""
    norm = rotation % 180.0
    return any(min(abs(norm - allowed), 180.0 - abs(norm - allowed)) <= tol
               for allowed in orientations)


def check_result(input_payload: dict, result: dict, config) -> List[str]:
    """复核一条输出；返回错误消息列表（为空即通过）。"""
    errors: List[str] = []
    try:
        parsed = io_model.parse_input(input_payload)
        scene = rules.build_scene(parsed["boundary"], parsed["door"],
                                  parsed["is_open_inward"], config.TOL)
    except ValueError as exc:
        return [f"输入数据非法: {exc}"]

    feasible = result.get("feasible")
    placements = result.get("placements") or []
    if not feasible:
        if placements:
            errors.append("feasible=false 时 placements 应为空")
        return errors

    specs = {item.name: item for item in parsed["items"]}
    names = []
    entries = []
    for index, placement in enumerate(placements):
        name = placement.get("name")
        center = placement.get("center")
        rotation = placement.get("rotation")
        label = f"第 {index + 1} 个摆放（{name}）"
        if name not in specs:
            errors.append(f"{label}: 物品名不在输入中")
            continue
        if not isinstance(center, (list, tuple)) or len(center) != 2:
            errors.append(f"{label}: center 必须是 [x, y]")
            continue
        if not isinstance(rotation, (int, float)) or not math.isfinite(rotation):
            errors.append(f"{label}: rotation 必须是数值")
            continue
        item = specs[name]
        cx, cy = float(center[0]), float(center[1])
        theta = float(rotation)
        if not _rotation_allowed(theta, scene.orientations_deg, 1e-3):
            errors.append(f"{label}: rotation {theta} 不属于允许朝向")
        names.append(name)
        entries.append((item, (cx, cy), theta,
                        geo.rect_polygon((cx, cy), theta, item.length, item.width)))

    if len(names) != len(set(names)):
        errors.append("placements 存在重复物品名")
    for name in specs:
        if name not in names:
            errors.append(f"物品 {name} 未出现在 placements 中")
    if not entries:
        errors.append("feasible=true 但没有任何有效摆放")
        return errors

    errors.extend(rules.validate_set(scene, entries, config.FRIDGE_OPEN_CLEARANCE,
                                     config.TOL, config.AREA_TOL))
    return errors


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 2:
        print("用法: python verify.py <input.json> <result.json>", file=sys.stderr)
        return 2
    input_path, result_path = args
    input_payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
    result = json.loads(Path(result_path).read_text(encoding="utf-8"))
    errors = check_result(input_payload, result, config)
    if errors:
        for message in errors:
            print(f"[error] {message}", file=sys.stderr)
        return 1
    print("[ok] 校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
