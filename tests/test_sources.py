from eks_precheck.sources import eks_docs, k8s


def test_changelog_extracts_only_minor_zero_section(fixture_text):
    sec = k8s.release_section(fixture_text("CHANGELOG-1.31.md"), "1.31")
    assert sec is not None
    assert "patch note" not in sec and "rc note" not in sec

    urgent = k8s.urgent_notes(sec)
    assert len(urgent) == 3
    assert any("--keep-terminated-pod-volumes" in u for u in urgent)
    # 작성자/SIG 꼬리표는 제거되고 PR 링크는 유지
    assert all("[SIG" not in u and "@carlory" not in u for u in urgent)
    assert "[#122082](https://github.com/kubernetes/kubernetes/pull/122082)" in urgent[1]

    deps = k8s.kind_items(sec, "Deprecation")
    assert any("CephFS" in d for d in deps)
    api = k8s.api_changes(sec)
    assert api and all(
        any(w in a.lower() for w in ("remov", "deprecat", "no longer", "breaking", "action required", "serving"))
        for a in api
    )


def test_removed_apis(fixture_text):
    guide = fixture_text("deprecation-guide.md")
    removed = k8s.removed_apis(guide, "1.29")
    assert [r.resource for r in removed] == ["Flow control resources"]
    assert "flowcontrol.apiserver.k8s.io/v1beta2" in removed[0].summary
    assert removed[0].bullets
    assert k8s.removed_apis(guide, "1.31") == []


def test_eks_section(fixture_text):
    doc = fixture_text("kubernetes-versions-extended.adoc")
    notes = eks_docs.parse_section(eks_docs.find_section(doc, "1.32"))
    assert len(notes.important) == 3
    assert any("Amazon Linux 2" in i for i in notes.important)
    assert [t for t, _ in notes.subsections] == ["Anonymous authentication changes", "Amazon Linux 2 AMI deprecation"]
    assert all("is now available" not in n for n in notes.notes)

    n133 = eks_docs.parse_section(eks_docs.find_section(doc, "1.33"))
    assert any("{aws}" not in i and "AWS is not releasing" in i for i in n133.important)
    assert eks_docs.find_section(doc, "1.28") is None


def test_adoc_links():
    md = eks_docs.adoc_to_md("see https://example.com/a[Doc] and <<al2023,AL2023 guide>> by {aws}")
    assert md == "see [Doc](https://example.com/a) and AL2023 guide by AWS"
