import pytest

from eks_precheck import versions


def test_parse_variants():
    assert versions.parse("v1.18.0") == (1, 18, 0)
    assert versions.parse("1.19.0-eksbuild.1") == (1, 19, 0)
    assert versions.parse("1.31") == (1, 31, 0)
    assert versions.parse("helm-chart-2.30.0") is None


def test_prerelease():
    assert versions.is_prerelease("v1.0.0-rc.1")
    assert not versions.is_prerelease("v1.19.0-eksbuild.2")
    assert not versions.is_prerelease("v1.19.0")


def test_upgrade_path():
    assert versions.upgrade_path("1.29", "1.31") == ["1.30", "1.31"]
    assert versions.upgrade_path("v1.30.4", "1.31") == ["1.31"]
    with pytest.raises(ValueError):
        versions.upgrade_path("1.31", "1.31")
    with pytest.raises(ValueError):
        versions.parse_minor("latest")
