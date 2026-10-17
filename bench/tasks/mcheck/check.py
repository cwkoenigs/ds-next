"""Checks for `mcheck`. Run: python check.py <repo>"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness import case, no_traceback, run, static, summary, tmp  # noqa: E402

INDEX = {"standards": [{"id": "alpha", "version": 2, "title": "A"}, {"id": "beta", "version": 1, "title": "B"},
                       {"id": "gamma", "version": 3, "title": "C"}]}
GOOD = """[adopted.alpha]
version = 2
date = 2026-10-01

[adopted.beta]
version = 1
date = 2026-10-01

[declined.gamma]
version = 3
reason = "We do not ship a service."
revisit = 2027-01-01
"""


def mcheck(manifest: str | None, index: dict | str | None = None, docs: dict[str, str] | None = None):
    d = tmp()
    if manifest is not None:
        (d / "manifest.toml").write_text(manifest)
    idx = INDEX if index is None else index
    (d / "index.json").write_text(idx if isinstance(idx, str) else json.dumps(idx))
    args = [str(d / "manifest.toml"), "--index", str(d / "index.json")]
    if docs is not None:
        for rel, text in docs.items():
            (d / "docs" / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / "docs" / rel).write_text(text)
        args += ["--docs", str(d / "docs")]
    r = run("mcheck", *args, cwd=d)
    return r, [ln for ln in r.stdout.splitlines() if ln.strip()]


def has(lines, kind, ident):
    return any(ln.startswith(f"{kind} {ident}") for ln in lines)


static()


@case("a clean manifest: no output, exit 0")
def _():
    r, lines = mcheck(GOOD)
    return r.returncode == 0 and lines == [], str(lines)[:150]


@case("adopted at an older version is PENDING, exit 1")
def _():
    r, lines = mcheck(GOOD.replace("[adopted.alpha]\nversion = 2", "[adopted.alpha]\nversion = 1"))
    return r.returncode == 1 and has(lines, "PENDING", "alpha") and not any(ln.startswith("ERROR") for ln in lines), str(lines)


@case("a standard the manifest never mentions is PENDING")
def _():
    m = GOOD.replace("[adopted.beta]\nversion = 1\ndate = 2026-10-01\n", "")
    r, lines = mcheck(m)
    return r.returncode == 1 and has(lines, "PENDING", "beta"), str(lines)


@case("a newer version reopens a decline (PENDING)")
def _():
    r, lines = mcheck(GOOD.replace("[declined.gamma]\nversion = 3", "[declined.gamma]\nversion = 2"))
    return r.returncode == 1 and has(lines, "PENDING", "gamma"), str(lines)


@case("an id the catalogue lacks is an ERROR, exit 2")
def _():
    r, lines = mcheck(GOOD + "\n[adopted.zeta]\nversion = 1\ndate = 2026-10-01\n")
    return r.returncode == 2 and has(lines, "ERROR", "zeta"), str(lines)


@case("a version the catalogue never had is an ERROR (too high, or zero)")
def _():
    r1, l1 = mcheck(GOOD.replace("[adopted.alpha]\nversion = 2", "[adopted.alpha]\nversion = 5"))
    r2, l2 = mcheck(GOOD.replace("[adopted.beta]\nversion = 1", "[adopted.beta]\nversion = 0"))
    return r1.returncode == 2 and has(l1, "ERROR", "alpha") and r2.returncode == 2 and has(l2, "ERROR", "beta"), str(l1 + l2)


@case("a datetime is not a date")
def _():
    r, lines = mcheck(GOOD.replace("date = 2026-10-01\n\n[adopted.beta]", "date = 2026-10-01T07:32:00\n\n[adopted.beta]"))
    return r.returncode == 2 and has(lines, "ERROR", "alpha"), str(lines)


@case("a decline needs a non-empty text reason and a revisit date")
def _():
    cases = [GOOD.replace('reason = "We do not ship a service."', 'reason = ""'),
             GOOD.replace('reason = "We do not ship a service."', "reason = 5"),
             GOOD.replace('reason = "We do not ship a service."', 'reason = "   "'),
             GOOD.replace("revisit = 2027-01-01\n", ""),
             GOOD.replace("revisit = 2027-01-01", 'revisit = "soon"')]
    res = [mcheck(m) for m in cases]
    bad = [i for i, (r, lines) in enumerate(res) if not (r.returncode == 2 and has(lines, "ERROR", "gamma"))]
    return not bad, f"missed cases {bad}"


@case("a version must be an integer (not a string, float or boolean)")
def _():
    res = [mcheck(GOOD.replace("[adopted.alpha]\nversion = 2", f"[adopted.alpha]\nversion = {v}"))
           for v in ('"2"', "2.0", "true")]
    bad = [i for i, (r, lines) in enumerate(res) if not (r.returncode == 2 and has(lines, "ERROR", "alpha"))]
    return not bad, f"missed cases {bad}"


@case("malformed or wrongly shaped input is an ERROR line, never a traceback")
def _():
    cases = ["[adopted.alpha\nversion = ", "adopted = 3\n", "[adopted]\nalpha = 2\n", "[[adopted]]\nx = 1\n",
             "[adopted.alpha]\nversion = 2\n"]          # last: date missing
    res = [mcheck(m) for m in cases]
    bad = [i for i, (r, lines) in enumerate(res)
           if not (r.returncode == 2 and no_traceback(r) and any(ln.startswith("ERROR") for ln in lines))]
    return not bad, f"bad cases {bad}"


@case("a missing manifest or a broken index is an ERROR, exit 2")
def _():
    r1, l1 = mcheck(None)
    r2, l2 = mcheck(GOOD, index="{not json")
    r3, l3 = mcheck(GOOD, index={"standards": "nope"})
    ok = [r.returncode == 2 and no_traceback(r) and any(ln.startswith("ERROR") for ln in lines)
          for r, lines in ((r1, l1), (r2, l2), (r3, l3))]
    return all(ok), str(ok)


@case("findings are sorted")
def _():
    m = GOOD.replace("[adopted.alpha]\nversion = 2", "[adopted.alpha]\nversion = 1").replace(
        "[declined.gamma]\nversion = 3", "[declined.gamma]\nversion = 1") + "\n[adopted.zeta]\nversion = 1\ndate = 2026-10-01\n"
    r, lines = mcheck(m)
    return len(lines) >= 3 and lines == sorted(lines), str(lines)


DOC = """# Notes

We follow [[alpha]] and [[alpha@2]], and once had [[beta@1]].
This one is wrong: [[nosuch]]. So is this pin: [[gamma@9]].

Inline code is not a claim: `[[inline-fake]]`.

```markdown
[[fenced-fake]]
```

~~~
[[tilde-fake]]
~~~

````
```
[[nested-fake]]
```
````
"""


@case("--docs: unknown ids and impossible pins are ERRORs")
def _():
    r, lines = mcheck(GOOD, docs={"notes.md": DOC})
    text = "\n".join(lines)
    return (r.returncode == 2 and "[[nosuch]]" in text and "[[gamma@9]]" in text
            and "[[alpha@2]]" not in text and "[[beta@1]]" not in text), str(lines)


@case("--docs: pointers in code (fences, tildes, nested, inline) are ignored")
def _():
    r, lines = mcheck(GOOD, docs={"sub/notes.md": DOC})
    text = "\n".join(lines)
    leaked = [x for x in ("inline-fake", "fenced-fake", "tilde-fake", "nested-fake") if x in text]
    return not leaked and "nosuch" in text, f"leaked {leaked}"


summary()
