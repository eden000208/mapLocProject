import pytest

from app.geo import bd_to_gcj, distance_m, gcj_to_bd, gcj_to_wgs, to_wgs, wgs_to_gcj


def test_gcj_inverse():
    original = (112.2, 30.98)
    assert gcj_to_wgs(*wgs_to_gcj(*original)) == pytest.approx(original, abs=1e-7)


def test_bd_inverse():
    point = (112.2, 30.98)
    assert bd_to_gcj(*gcj_to_bd(*point)) == pytest.approx(point, abs=2e-6)


def test_coordinate_validation():
    with pytest.raises(ValueError):
        to_wgs(float("nan"), 30, "WGS84")
    with pytest.raises(ValueError):
        to_wgs(181, 30, "WGS84")
    assert to_wgs(0, 0, "WGS84") == (0, 0)
    assert distance_m((0, 0), (0, 1)) == pytest.approx(111195, abs=2)
