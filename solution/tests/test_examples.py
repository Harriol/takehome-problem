"""4 个既定样例的求解验收。

口径（已确认）：冰箱开门净空深度 = 冰箱宽度值；内/外开门均保留 N x N 门净空区。
按该口径 example3/example4 的房间几何无法容纳冰箱（需连续 2660mm，房间最大只有
2150mm/2460mm），判定为不可行。
"""

import json
from pathlib import Path

import pytest

import config
from solver import io_model, rules, search
from verify import check_result

DATA = Path(__file__).resolve().parent.parent / "data"


def _solve(stem: str):
    payload = json.loads((DATA / f"{stem}.json").read_text(encoding="utf-8"))
    parsed = io_model.parse_input(payload)
    scene = rules.build_scene(parsed["boundary"], parsed["door"],
                              parsed["is_open_inward"], config.TOL)
    result = search.Solver(scene, parsed["items"], config).solve()
    return payload, parsed, scene, result


@pytest.mark.parametrize("stem", ["example1", "example2"])
def test_feasible_examples(stem):
    payload, parsed, scene, result = _solve(stem)
    assert result is not None and not result.timed_out, "应能找到可行解"
    output = search.format_result(result, [item.name for item in parsed["items"]],
                                  config.ROUND_DIGITS)
    assert output["feasible"]
    assert check_result(payload, output, config) == []
    assert all(p.wall_touched >= 1 for p in result.placements), "阶段一应全贴墙"


@pytest.mark.parametrize("stem", ["example3", "example4"])
def test_infeasible_examples(stem):
    payload, parsed, scene, result = _solve(stem)
    assert result is None or result.timed_out, "按既定口径应为不可行"
