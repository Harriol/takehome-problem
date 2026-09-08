"""规则层：贴墙判定、冰箱净空带、集合校验。"""

import pytest

import config
from solver import geometry_utils as geo
from solver import io_model, rules

ROOM = [[0.0, 0.0], [10000.0, 0.0], [10000.0, 10000.0], [0.0, 10000.0]]
DOOR = [[2000.0, 0.0], [2800.0, 0.0]]  # 底边门，宽 800


@pytest.fixture()
def scene():
    return rules.build_scene(ROOM, DOOR, True, config.TOL)


def _item(name="shelf-1", length=1000.0, width=400.0):
    return io_model.ItemSpec(name, length, width, io_model.detect_kind(name))


def test_walls_touched_axis_flush(scene):
    rect = geo.rect_polygon((500.0, 200.0), 0, 1000.0, 400.0)  # 贴底边
    assert rules.walls_touched(scene, rect, config.TOL, config.WALL_TOUCH_LEN_MIN) >= 1
    rect2 = geo.rect_polygon((5000.0, 5000.0), 0, 1000.0, 400.0)  # 悬空
    assert rules.walls_touched(scene, rect2, config.TOL, config.WALL_TOUCH_LEN_MIN) == 0


def test_fridge_clearance_rules(scene):
    fridge = _item("fridge", 1220.0, 1330.0)
    # 大房间中部：至少一侧能留出 1330 净空带 -> 合法
    center = (5000.0, 6000.0)
    rect = geo.rect_polygon(center, 0, fridge.length, fridge.width)
    assert rules.validate_set(scene, [(fridge, center, 0.0, rect)],
                              config.FRIDGE_OPEN_CLEARANCE, config.TOL,
                              config.AREA_TOL) == []
    # 高仅 2000 的房间：本体(1330)能放下，但上下净空带(各1330)必有一侧不足 -> 非法
    low_room = rules.build_scene([[0.0, 0.0], [5000.0, 0.0],
                                  [5000.0, 2000.0], [0.0, 2000.0]],
                                 [[100.0, 0.0], [500.0, 0.0]], False, config.TOL)
    rect_low = geo.rect_polygon((2500.0, 1000.0), 0, fridge.length, fridge.width)
    errors = rules.validate_set(low_room, [(fridge, (2500.0, 1000.0), 0.0, rect_low)],
                                config.FRIDGE_OPEN_CLEARANCE, config.TOL,
                                config.AREA_TOL)
    assert any("净空" in message for message in errors)


def test_set_validation_detects_overlap(scene):
    item = _item()
    rect1 = geo.rect_polygon((1000.0, 1000.0), 0, 1000.0, 400.0)
    rect2 = geo.rect_polygon((1200.0, 1100.0), 0, 1000.0, 400.0)  # 与 rect1 重叠
    errors = rules.validate_set(scene, [(item, (1000.0, 1000.0), 0.0, rect1),
                                        (item, (1200.0, 1100.0), 0.0, rect2)],
                                config.FRIDGE_OPEN_CLEARANCE, config.TOL,
                                config.AREA_TOL)
    assert any("重叠" in message for message in errors)


def test_door_zone_blocking(scene):
    item = _item()
    # 门宽 800、深 800；贴底边门洞正前方的货架应被拒绝
    rect = geo.rect_polygon((2400.0, 200.0), 0, 1000.0, 400.0)
    errors = rules.validate_set(scene, [(item, (2400.0, 200.0), 0.0, rect)],
                                config.FRIDGE_OPEN_CLEARANCE, config.TOL,
                                config.AREA_TOL)
    assert any("门" in message for message in errors)
