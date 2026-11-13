from eks_precheck.classify import classify_release, split_body
from eks_precheck.models import CRITICAL, INFO, REVIEW, SECURITY

BODY = """\
## Breaking Changes
* Dropped the `--enable-foo` flag

## What's Changed
* feat!: change default NodePool disruption budget by @someone in #1
* fix: bump golang.org/x/net to fix CVE-2024-45338
* Deprecate `AWS_VPC_K8S_CNI_EXTERNALSNAT` env in favor of new option
  * nested detail line
* chore: update README
<!-- hidden comment -->
**Full Changelog**: https://github.com/x/y/compare/v1...v2
"""


def test_split_body_merges_nested_and_drops_noise():
    items = split_body(BODY)
    texts = [t for _, t in items]
    assert any("nested detail line" in t and t.startswith("Deprecate") for t in texts)
    assert not any("Full Changelog" in t or "hidden comment" in t for t in texts)


def test_classify_release():
    found = {f.text.split()[0]: f.severity for f in classify_release(BODY, "v2.0.0", "u")}
    assert found["Dropped"] == CRITICAL  # Breaking 제목 아래
    assert found["feat!:"] == CRITICAL  # conventional commit breaking marker
    assert found["fix:"] == SECURITY
    assert found["Deprecate"] == REVIEW
    assert found["chore:"] == INFO
