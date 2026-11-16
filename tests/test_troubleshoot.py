import re

import pytest

from eks_precheck import troubleshoot


def test_data_is_consistent():
    data = troubleshoot.load()
    assert len(data["phases"]) == 5
    ids = {s["id"] for s in data["symptoms"]}
    assert {"crashloop", "imagepull", "node-notready", "drain-stuck"} <= ids
    for s in data["symptoms"]:
        assert s["title"] and s["first"]
        for c in s["causes"]:
            assert c["title"] and c["fix"]


def all_commands(data):
    for p in data["phases"]:
        yield from p.get("commands", [])
    for s in data["symptoms"]:
        yield from s.get("first", [])
        for c in s["causes"]:
            yield from c.get("checks", [])


def test_commands_are_cross_platform():
    for cmd in all_commands(troubleshoot.load()):
        assert re.match(r"^(kubectl|aws|helm|pluto) ", cmd), cmd
        assert "|" not in cmd and "grep" not in cmd, cmd       # PowerShell / bash 공통
        if "$" in cmd:
            assert "'$" in cmd, cmd                            # 변수 해석 방지


def test_validate_catches_broken_reference():
    with pytest.raises(ValueError, match="watch"):
        troubleshoot.validate({"phases": [{"id": "a", "watch": ["nope"]}], "symptoms": []})
