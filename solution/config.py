"""全局可调参数：几何容差、门/冰箱净空、求解预算。

所有距离单位均为毫米（mm），与输入坐标一致。
"""

# 几何容差：判共线、判接触等使用的长度容差
TOL = 1e-3
# 面积容差（mm^2）：输出坐标四舍五入后，紧贴的物品可能产生约
# (1e-4mm x 最长边 ~1.4m) ≈ 0.2mm² 的数值斜片；允许 <= 1mm² 视为仅接触
AREA_TOL = 1.0
# 贴墙判定：物品边与墙线段共线且重合长度达到该值（mm）才算贴墙
WALL_TOUCH_LEN_MIN = 1.0

# 门内侧净空区深度（沿垂直门墙方向）；None 表示取门宽 N（即 N x N 净空区）
DOOR_CLEAR_DEPTH = None
# 冰箱开门边外侧净空带深度；None 表示取该冰箱自身的宽度（尺寸对第 2 个数）
FRIDGE_OPEN_CLEARANCE = None

# 求解超时（秒）
TIME_LIMIT_SECONDS = 60.0
# 兜底网格候选：步长 = min(length, width) * GRID_STEP_FACTOR，下限见 GRID_STEP_MIN
GRID_STEP_FACTOR = 0.5
GRID_STEP_MIN = 50.0
# 兜底网格候选点数上限，超过时自动放大步长
GRID_MAX_CANDIDATES = 3000

# 输出 JSON 中坐标/角度的保留小数位
ROUND_DIGITS = 4
