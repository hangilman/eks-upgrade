from eks_precheck import cluster


class FakeEks:
    """boto3 EKS client 대체 (paginator 없는 경로로 동작)."""

    def can_paginate(self, op):
        return False

    def describe_cluster(self, name):
        return {"cluster": {"version": "1.30", "platformVersion": "eks.20"}}

    def list_addons(self, clusterName):
        return {"addons": ["vpc-cni"]}

    def describe_addon(self, clusterName, addonName):
        return {"addon": {"addonVersion": "v1.18.0-eksbuild.1"}}

    def describe_addon_versions(self, addonName, kubernetesVersion, nextToken=None):
        table = {
            "1.30": [("v1.18.0-eksbuild.1", True), ("v1.19.0-eksbuild.1", False)],
            "1.31": [("v1.19.0-eksbuild.1", True), ("v1.19.2-eksbuild.1", False)],
        }
        return {"addons": [{"addonVersions": [
            {"addonVersion": v, "compatibilities": [{"clusterVersion": kubernetesVersion, "defaultVersion": d}]}
            for v, d in table[kubernetesVersion]
        ]}]}

    def list_nodegroups(self, clusterName):
        return {"nodegroups": ["ng1"]}

    def describe_nodegroup(self, clusterName, nodegroupName):
        return {"nodegroup": {"version": "1.30", "amiType": "AL2023_x86_64_STANDARD", "releaseVersion": "1.30.0-2024"}}

    def list_insights(self, clusterName, filter, nextToken=None):
        assert filter == {"categories": ["UPGRADE_READINESS"]}
        if nextToken is None:
            return {"insights": [{"id": "a", "name": "Deprecated APIs", "kubernetesVersion": "1.31",
                                  "insightStatus": {"status": "WARNING", "reason": "usage found"}}], "nextToken": "p2"}
        return {"insights": [{"id": "b", "name": "Kubelet skew", "kubernetesVersion": "1.31",
                              "insightStatus": {"status": "PASSING", "reason": ""}}]}

    def describe_insight(self, clusterName, id):
        assert id == "a"  # PASSING 은 상세 조회하지 않음
        return {"insight": {"recommendation": "update manifests", "categorySpecificSummary": {
            "deprecationDetails": [{"usage": "/apis/flowcontrol.apiserver.k8s.io/v1beta3/flowschemas",
                                    "replacedWith": "/apis/flowcontrol.apiserver.k8s.io/v1/flowschemas",
                                    "stopServingVersion": "1.32", "clientStats": []}]}}}


def test_collect(monkeypatch):
    monkeypatch.setattr(cluster, "_eks_client", lambda region, profile: (FakeEks(), "ap-northeast-2"))
    monkeypatch.setattr(cluster, "detect_image_versions", lambda comps, ctx: ({}, "kubectl 없음"))
    state, warnings = cluster.collect("c", None, None, "1.31", {"vpc-cni": {"eks_addon": "vpc-cni"}})

    assert state.version == "1.30" and state.addons == {"vpc-cni": "v1.18.0-eksbuild.1"}
    per = state.addon_compat["vpc-cni"].per_minor
    assert per["1.30"]["current_compatible"] is True
    assert per["1.31"]["current_compatible"] is False
    assert per["1.31"]["default"] == "v1.19.0-eksbuild.1" and per["1.31"]["latest"] == "v1.19.2-eksbuild.1"
    assert state.addon_defaults == {"vpc-cni": "v1.19.0-eksbuild.1"}
    assert [i.status for i in state.insights] == ["WARNING", "PASSING"]  # nextToken 페이지네이션
    assert state.insights[0].deprecations[0]["stopServingVersion"] == "1.32"
    assert warnings == ["kubectl 없음"]
