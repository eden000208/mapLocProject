import math


def valid_coordinate(lng: float, lat: float) -> bool:
    return (
        math.isfinite(lng)
        and math.isfinite(lat)
        and -180 <= lng <= 180
        and -90 <= lat <= 90
    )


def _offset(lng: float, lat: float) -> tuple[float, float]:
    x, y = lng - 105, lat - 35
    dlat = -100 + 2 * x + 3 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    dlng = 300 + x + 2 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    wave = (20 * math.sin(6 * x * math.pi) + 20 * math.sin(2 * x * math.pi)) * 2 / 3
    dlat += wave + (20 * math.sin(y * math.pi) + 40 * math.sin(y / 3 * math.pi)) * 2 / 3
    dlat += (
        (160 * math.sin(y / 12 * math.pi) + 320 * math.sin(y * math.pi / 30)) * 2 / 3
    )
    dlng += wave + (20 * math.sin(x * math.pi) + 40 * math.sin(x / 3 * math.pi)) * 2 / 3
    dlng += (
        (150 * math.sin(x / 12 * math.pi) + 300 * math.sin(x / 30 * math.pi)) * 2 / 3
    )
    rad = lat * math.pi / 180
    magic = 1 - 0.00669342162296594323 * math.sin(rad) ** 2
    dlat = (
        dlat * 180 / ((6378245 * (1 - 0.00669342162296594323)) / (magic**1.5) * math.pi)
    )
    dlng = dlng * 180 / (6378245 / math.sqrt(magic) * math.cos(rad) * math.pi)
    return dlng, dlat


def wgs_to_gcj(lng: float, lat: float) -> tuple[float, float]:
    if not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271):
        return lng, lat
    dx, dy = _offset(lng, lat)
    return lng + dx, lat + dy


def gcj_to_wgs(lng: float, lat: float) -> tuple[float, float]:
    x, y = lng, lat
    for _ in range(8):
        gx, gy = wgs_to_gcj(x, y)
        x, y = x - (gx - lng), y - (gy - lat)
    return x, y


def gcj_to_bd(lng: float, lat: float) -> tuple[float, float]:
    z = math.hypot(lng, lat) + 0.00002 * math.sin(lat * math.pi * 3000 / 180)
    theta = math.atan2(lat, lng) + 0.000003 * math.cos(lng * math.pi * 3000 / 180)
    return z * math.cos(theta) + 0.0065, z * math.sin(theta) + 0.006


def bd_to_gcj(lng: float, lat: float) -> tuple[float, float]:
    x, y = lng - 0.0065, lat - 0.006
    z = math.hypot(x, y) - 0.00002 * math.sin(y * math.pi * 3000 / 180)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * math.pi * 3000 / 180)
    return z * math.cos(theta), z * math.sin(theta)


def to_wgs(lng: float, lat: float, coord_sys: str) -> tuple[float, float]:
    if not valid_coordinate(lng, lat):
        raise ValueError("经纬度超出范围")
    if coord_sys == "WGS84":
        return lng, lat
    if coord_sys == "GCJ02":
        return gcj_to_wgs(lng, lat)
    if coord_sys == "BD09":
        return gcj_to_wgs(*bd_to_gcj(lng, lat))
    raise ValueError("坐标系必须为 WGS84、GCJ02 或 BD09")


def distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    x1, y1, x2, y2 = map(math.radians, (*a, *b))
    h = (
        math.sin((y2 - y1) / 2) ** 2
        + math.cos(y1) * math.cos(y2) * math.sin((x2 - x1) / 2) ** 2
    )
    return 6371008.8 * 2 * math.asin(min(1, math.sqrt(h)))
