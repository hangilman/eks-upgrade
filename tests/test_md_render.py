from eks_precheck.md_render import inline, render_html


def test_escapes_html_from_release_notes():
    out = render_html("- <script>alert(1)</script> `<b>` [x](javascript:alert(1))")
    assert "<script>" not in out and "&lt;script&gt;" in out
    assert "<code>&lt;b&gt;</code>" in out
    assert 'href="javascript' not in out  # http(s) 링크만 허용


def test_inline_formatting():
    out = inline("**굵게** _기울임_ snake_case [#7](https://gh/i/7?a=1&b=2)")
    assert "<strong>굵게</strong>" in out and "<em>기울임</em>" in out and "snake_case" in out
    assert '<a href="https://gh/i/7?a=1&amp;b=2" target="_blank" rel="noopener noreferrer">#7</a>' in out


def test_blocks():
    md = """# 제목

| a | b \\| c |
|---|---|
| 1 | 2 |

- 상위
  - 하위
- [ ] 체크

> 🔴 인용

```bash
aws eks list-clusters
```
"""
    out = render_html(md)
    assert '<h1 id="제목">제목</h1>' in out
    assert "<th>b | c</th>" in out and "<td>2</td>" in out
    assert out.count("<ul>") == 2 and out.count("</ul>") == 2
    assert 'type="checkbox"' in out
    assert "<blockquote>🔴 인용</blockquote>" in out
    assert "<pre><code>aws eks list-clusters</code></pre>" in out
