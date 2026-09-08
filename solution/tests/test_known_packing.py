"""已知可解的小规模构造，验证搜索（含 90 度旋转）。"""

import config
from solver import io_model, rules, search
from verify import check_result


def _run(payload):
    parsed = io_model.parse_input(payload)
    scene = rules.build_scene(parsed["boundary"], parsed["door"],
                              parsed["is_open_inward"], config.TOL)
    result = search.Solver(scene, parsed["items"], config).solve()
    assert result is not None and not result.timed_out, "应能找到可行解"
    output = search.format_result(result, [i.name for i in parsed["items"]],
                                  config.ROUND_DIGITS)
    assert check_result(payload, output, config) == []
    return result


def test_three_shelves_line():
    # 3000 x 2000 房间，门在底边中段；三个货架沿底边一字排开必可解
    payload = {
        "boundary": [[0.0, 0.0], [3000.0, 0.0], [3000.0, 2000.0], [0.0, 2000.0]],
        "door": [[1000.0, 0.0], [1500.0, 0.0]],
        "isOpenInward": False,
        "algoToPlace": {"shelf-1": [900, 400], "shelf-2": [900, 400],
                        "shelf-3": [900, 400]},
    }
    _run(payload)


def test_needs_90_degree_rotation():
    # 房间高仅 500：length=300/width=900 横放(y 占 900)必越界，必须旋转 90 度
    payload = {
        "boundary": [[0.0, 0.0], [3000.0, 0.0], [3000.0, 500.0], [0.0, 500.0]],
        "door": [[100.0, 0.0], [500.0, 0.0]],
        "isOpenInward": False,
        "algoToPlace": {"shelf-1": [300, 900], "shelf-2": [300, 900]},
    }
    result = _run(payload)
    assert any(abs(p.theta_deg - 90.0) < 1e-6 for p in result.placements)
