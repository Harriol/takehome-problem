"""几何基础与门净空区单元测试。"""

import pytest
from shapely.geometry import Point

import config
from solver import geometry_utils as geo
from solver import rules


def _square_room():
    """10000 x 10000 房间，门在底边。"""
    boundary = [[0.0, 0.0], [10000.0, 0.0], [10000.0, 10000.0], [0.0, 10000.0]]
    door = [[3000.0, 0.0], [4000.0, 0.0]]
    return boundary, door


def test_clean_polygon_ccw():
    poly = geo.clean_polygon(_square_room()[0])
    assert poly.exterior.is_ccw
    assert abs(poly.area - 1e8) < 1.0


def test_merge_walls_drops_collinear_points():
    # 底边中间加三个共线点，应合并成 4 条墙
    boundary = [[0.0, 0.0], [2000.0, 0.0], [4000.0, 0.0], [6000.0, 0.0],
                [6000.0, 6000.0], [0.0, 6000.0]]
    poly = geo.clean_polygon(boundary)
    walls = geo.merge_walls(poly)
    assert len(walls) == 4
    lengths = sorted(round(((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5, 1)
                     for a, b in walls)
    assert lengths == [6000.0, 6000.0, 6000.0, 6000.0]


def test_door_zone_inside_room():
    boundary, door = _square_room()
    scene = rules.build_scene(boundary, door, False, config.TOL)
    assert scene.door_width == pytest.approx(1000.0)
    assert scene.door_zone.area == pytest.approx(1e6, rel=1e-6)
    # 净空区应在房间内，且覆盖门正前方区域
    assert scene.door_zone.within(scene.room_polygon)
    assert scene.room_polygon.buffer(-config.TOL).contains(Point(3500.0, 500.0))


def test_rect_polygon_axis_and_rotated():
    rect0 = geo.rect_polygon((0.0, 0.0), 0, 200.0, 100.0)
    assert abs(rect0.area - 20000.0) < 1e-6
    rect90 = geo.rect_polygon((0.0, 0.0), 90, 200.0, 100.0)
    assert rect90.bounds == pytest.approx((-50.0, -100.0, 50.0, 100.0))
