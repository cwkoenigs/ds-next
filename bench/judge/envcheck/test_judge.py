"""Hidden acceptance tests for the `envcheck` console command."""

import os
import re
import subprocess

import pytest

VAR_LINE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*="')
ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", '"': '"', "$": "$"}


# ---------------------------------------------------------------- helpers


def run(cwd, *args):
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        [os.environ["TARGET_BIN"], *[str(a) for a in args]],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=60,
    )


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def schema_for(vars_):
    """vars_: dict NAME -> dict of TOML key -> python value (str/bool/list)."""
    out = []
    for name, spec in vars_.items():
        out.append(f"[vars.{name}]")
        for key, val in spec.items():
            if isinstance(val, bool):
                out.append(f"{key} = {'true' if val else 'false'}")
            elif isinstance(val, list):
                items = ", ".join(toml_str(v) for v in val)
                out.append(f"{key} = [{items}]")
            else:
                out.append(f"{key} = {toml_str(val)}")
        out.append("")
    return "\n".join(out)


def toml_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def error_lines(res):
    text = res.stdout + "\n" + res.stderr
    return [ln for ln in text.splitlines() if ln.startswith("ERROR ")]


def unquote(s):
    assert len(s) >= 2 and s[0] == '"' and s[-1] == '"', s
    body = s[1:-1]
    out = []
    i = 0
    while i < len(body):
        c = body[i]
        if c == "\\":
            assert i + 1 < len(body), s
            assert body[i + 1] in ESCAPES, s
            out.append(ESCAPES[body[i + 1]])
            i += 2
        else:
            assert c != '"', f"unescaped quote in {s!r}"
            out.append(c)
            i += 1
    return "".join(out)


def printed(res):
    """Return list of (name, decoded value) from --print output, in order."""
    result = []
    for ln in res.stdout.splitlines():
        if VAR_LINE.match(ln):
            name, _, raw = ln.partition("=")
            result.append((name, unquote(raw)))
    return result


def no_traceback(res):
    assert "Traceback" not in res.stderr
    assert "Traceback" not in res.stdout


def setup(tmp_path, vars_, *envs):
    s = write(tmp_path / "schema.toml", schema_for(vars_))
    paths = []
    for i, content in enumerate(envs):
        paths.append(write(tmp_path / f"f{i}.env", content))
    return s, paths


STR = {"type": "string"}


# ---------------------------------------------------------------- basics


def test_valid_file_exits_zero_without_errors(tmp_path):
    s, (e,) = setup(tmp_path, {"NAME": STR, "PORT": {"type": "port"}}, "NAME=app\nPORT=8080\n")
    res = run(tmp_path, s, e)
    no_traceback(res)
    assert res.returncode == 0
    assert error_lines(res) == []


def test_empty_and_comment_only_env_file(tmp_path):
    s, (e1, e2) = setup(tmp_path, {"A": STR}, "", "# just a comment\n\n   \n# another\n")
    res = run(tmp_path, s, e1, e2)
    assert res.returncode == 0
    assert error_lines(res) == []


def test_required_missing_is_error(tmp_path):
    s, (e,) = setup(tmp_path, {"DB": {"type": "string", "required": True}, "A": STR}, "A=x\n")
    res = run(tmp_path, s, e)
    no_traceback(res)
    assert res.returncode == 1
    errs = error_lines(res)
    assert len(errs) == 1
    assert errs[0].startswith("ERROR DB:")


def test_required_missing_with_default_is_ok(tmp_path):
    s, (e,) = setup(
        tmp_path, {"DB": {"type": "string", "required": True, "default": "sqlite"}}, ""
    )
    res = run(tmp_path, s, e)
    assert res.returncode == 0
    assert error_lines(res) == []


def test_optional_missing_is_ok(tmp_path):
    s, (e,) = setup(tmp_path, {"A": STR, "B": {"type": "int", "required": False}}, "A=1\n")
    res = run(tmp_path, s, e)
    assert res.returncode == 0
    assert error_lines(res) == []


def test_not_in_schema_exact_format(tmp_path):
    s, (e,) = setup(tmp_path, {"A": STR}, "A=1\nEXTRA_VAR=2\n")
    res = run(tmp_path, s, e)
    assert res.returncode == 1
    assert error_lines(res) == ["ERROR EXTRA_VAR: not in the schema"]


def test_unknown_var_in_two_files_reported_once(tmp_path):
    s, (e1, e2) = setup(tmp_path, {"A": STR}, "X=1\n", "X=2\n")
    res = run(tmp_path, s, e1, e2)
    assert res.returncode == 1
    assert error_lines(res) == ["ERROR X: not in the schema"]


def test_errors_sorted_by_name(tmp_path):
    vars_ = {
        "BBB": {"type": "int"},
        "CCC": {"type": "string", "required": True},
        "DDD": {"type": "bool"},
    }
    s, (e,) = setup(tmp_path, vars_, "DDD=maybe\nBBB=notanint\nAAA=unknown\n")
    res = run(tmp_path, s, e)
    assert res.returncode == 1
    errs = error_lines(res)
    names = [re.match(r"ERROR ([A-Za-z0-9_]+):", ln).group(1) for ln in errs]
    assert names == ["AAA", "BBB", "CCC", "DDD"]
    assert "ERROR AAA: not in the schema" in errs


# ---------------------------------------------------------------- types

VALID = [
    ("string", "anything at all"),
    ("string", "héllo wörld ✓"),
    ("int", "0"),
    ("int", "-17"),
    ("int", "+42"),
    ("int", "007"),
    ("int", "123456789012345678901234567890"),
    ("bool", "true"),
    ("bool", "FALSE"),
    ("bool", "Yes"),
    ("bool", "no"),
    ("bool", "oN"),
    ("bool", "OFF"),
    ("bool", "1"),
    ("bool", "0"),
    ("port", "1"),
    ("port", "443"),
    ("port", "65535"),
    ("url", "https://example.com"),
    ("url", "http://localhost:8080/path?q=1"),
    ("url", "postgres://user:pw@db.internal:5432/app"),
    ("enum", "dev"),
    ("enum", "prod"),
]

INVALID = [
    ("int", "1.5"),
    ("int", "abc"),
    ("int", "12a"),
    ("int", "0x10"),
    ("int", "1e3"),
    ("bool", "2"),
    ("bool", "y"),
    ("bool", "enabled"),
    ("port", "0"),
    ("port", "65536"),
    ("port", "-80"),
    ("port", "http"),
    ("port", "80.0"),
    ("port", "99999999999999999999"),
    ("url", "example.com"),
    ("url", "http://"),
    ("url", "just text"),
    ("enum", "staging"),
    ("enum", "Dev"),
]


def type_schema(t):
    spec = {"type": t}
    if t == "enum":
        spec["values"] = ["dev", "prod"]
    return {"X": spec}


@pytest.mark.parametrize("t,value", VALID)
def test_type_accepts(tmp_path, t, value):
    s, (e,) = setup(tmp_path, type_schema(t), f"X={value}\n")
    res = run(tmp_path, s, e)
    no_traceback(res)
    assert error_lines(res) == []
    assert res.returncode == 0


@pytest.mark.parametrize("t,value", INVALID)
def test_type_rejects(tmp_path, t, value):
    s, (e,) = setup(tmp_path, type_schema(t), f"X={value}\n")
    res = run(tmp_path, s, e)
    no_traceback(res)
    assert res.returncode == 1
    errs = error_lines(res)
    assert len(errs) == 1
    assert errs[0].startswith("ERROR X:")


def test_enum_non_ascii_values(tmp_path):
    vars_ = {"X": {"type": "enum", "values": ["café", "naïve"]}}
    s, (e,) = setup(tmp_path, vars_, "X=café\n")
    res = run(tmp_path, s, e)
    assert res.returncode == 0
    assert error_lines(res) == []


# ---------------------------------------------------------------- merging


def test_later_file_overrides(tmp_path):
    s, files = setup(tmp_path, {"A": STR, "B": STR}, "A=one\nB=one\n", "A=two\n", "A=three\n")
    res = run(tmp_path, s, *files, "--print")
    assert res.returncode == 0
    assert printed(res) == [("A", "three"), ("B", "one")]


def test_override_fixes_bad_value(tmp_path):
    s, (e1, e2) = setup(tmp_path, {"P": {"type": "port"}}, "P=notaport\n", "P=8080\n")
    res = run(tmp_path, s, e1, e2)
    assert res.returncode == 0
    assert error_lines(res) == []


def test_override_breaks_good_value(tmp_path):
    s, (e1, e2) = setup(tmp_path, {"P": {"type": "port"}}, "P=8080\n", "P=70000\n")
    res = run(tmp_path, s, e1, e2)
    assert res.returncode == 1
    errs = error_lines(res)
    assert len(errs) == 1 and errs[0].startswith("ERROR P:")


def test_required_satisfied_by_second_file(tmp_path):
    vars_ = {"A": {"type": "string", "required": True}, "B": STR}
    s, (e1, e2) = setup(tmp_path, vars_, "B=x\n", "A=y\n")
    res = run(tmp_path, s, e1, e2)
    assert res.returncode == 0


# ---------------------------------------------------------------- parsing


@pytest.mark.parametrize(
    "line,expected",
    [
        ("S=plain", "plain"),
        ("export S=exported", "exported"),
        ("S=   hello world   ", "hello world"),
        ("S=hello # trailing comment", "hello"),
        ("S=a=b=c", "a=b=c"),
        ("S='single # not a comment'", "single # not a comment"),
        ("S='lit\\n $X \\\"'", 'lit\\n $X \\"'),
        ('S="dq # not a comment"', "dq # not a comment"),
        ('S="a\\nb\\tc\\\\d\\"e\\$f"', 'a\nb\tc\\d"e$f'),
        ("S=ünïcødé ✓", "ünïcødé ✓"),
        ('S="日本語"', "日本語"),
        ("S=''", ""),
        ('S=""', ""),
    ],
)
def test_value_parsing(tmp_path, line, expected):
    s, (e,) = setup(tmp_path, {"S": STR}, line + "\n")
    res = run(tmp_path, s, e, "--print")
    no_traceback(res)
    assert res.returncode == 0, res.stdout + res.stderr
    assert printed(res) == [("S", expected)]


def test_parse_error_reports_file_and_line(tmp_path):
    s = write(tmp_path / "schema.toml", schema_for({"A": STR}))
    write(tmp_path / "bad.env", "# comment\n\nA=ok\nthis is not valid\n")
    res = run(tmp_path, s, "bad.env")
    no_traceback(res)
    assert res.returncode == 1
    matches = [re.match(r"^ERROR (.+):(\d+): ", ln) for ln in error_lines(res)]
    matches = [m for m in matches if m]
    assert any(m.group(1).endswith("bad.env") and m.group(2) == "4" for m in matches)


@pytest.mark.parametrize(
    "bad",
    ["NOEQUALS", "1ABC=x", "ÄBC=1", "A B=1", "-X=1", 'A="unterminated', "A='unterminated"],
)
def test_unparseable_lines(tmp_path, bad):
    s = write(tmp_path / "schema.toml", schema_for({"A": STR}))
    write(tmp_path / "bad.env", "A=fine\n" + bad + "\n")
    res = run(tmp_path, s, "bad.env")
    no_traceback(res)
    assert res.returncode == 1
    assert any(re.match(r"^ERROR .*bad\.env:2: ", ln) for ln in error_lines(res))


def test_parse_error_names_the_right_file(tmp_path):
    s = write(tmp_path / "schema.toml", schema_for({"A": STR}))
    write(tmp_path / "good.env", "A=1\n")
    write(tmp_path / "second.env", "\n\n!!!\n")
    res = run(tmp_path, s, "good.env", "second.env")
    assert res.returncode == 1
    errs = error_lines(res)
    assert any(re.match(r"^ERROR .*second\.env:3: ", ln) for ln in errs)
    assert not any("good.env:" in ln for ln in errs)


# ---------------------------------------------------------------- schema errors


@pytest.mark.parametrize(
    "schema_text",
    [
        "[vars.A\ntype = 'string'\n",  # invalid TOML
        "[vars.A]\ntype = 'float'\n",  # unknown type
        "[vars.A]\ntype = = 'string'\n",  # invalid TOML
    ],
)
def test_malformed_schema(tmp_path, schema_text):
    s = write(tmp_path / "schema.toml", schema_text)
    e = write(tmp_path / "f.env", "UNKNOWN=1\nnot a valid line\n")
    res = run(tmp_path, s, e)
    no_traceback(res)
    assert res.returncode == 1
    errs = error_lines(res)
    assert errs, res.stdout + res.stderr
    assert all(ln.startswith("ERROR schema: ") for ln in errs)
    assert "UNKNOWN" not in res.stdout + res.stderr


def test_missing_schema_file(tmp_path):
    e = write(tmp_path / "f.env", "A=1\n")
    res = run(tmp_path, tmp_path / "nope.toml", e)
    no_traceback(res)
    assert res.returncode == 1
    errs = error_lines(res)
    assert errs and all(ln.startswith("ERROR schema: ") for ln in errs)


def test_malformed_schema_with_print_prints_no_vars(tmp_path):
    s = write(tmp_path / "schema.toml", "not toml at all [[[\n")
    e = write(tmp_path / "f.env", "A=1\n")
    res = run(tmp_path, s, e, "--print")
    assert res.returncode == 1
    assert printed(res) == []


# ---------------------------------------------------------------- other failures


def test_missing_env_file_no_traceback(tmp_path):
    s = write(tmp_path / "schema.toml", schema_for({"A": STR}))
    res = run(tmp_path, s, tmp_path / "missing.env")
    no_traceback(res)
    assert res.returncode != 0
    assert (res.stdout + res.stderr).strip()


def test_no_arguments_no_traceback(tmp_path):
    res = run(tmp_path)
    no_traceback(res)
    assert res.returncode != 0


def test_only_schema_argument_fails(tmp_path):
    s = write(tmp_path / "schema.toml", schema_for({"A": STR}))
    res = run(tmp_path, s)
    no_traceback(res)
    assert res.returncode != 0


def test_invalid_utf8_env_no_traceback(tmp_path):
    s = write(tmp_path / "schema.toml", schema_for({"A": STR}))
    e = tmp_path / "f.env"
    e.write_bytes(b"A=\xff\xfe\xfa\n")
    res = run(tmp_path, s, e)
    no_traceback(res)
    assert res.returncode in (0, 1) or res.stderr.strip()


def test_env_path_is_directory_no_traceback(tmp_path):
    s = write(tmp_path / "schema.toml", schema_for({"A": STR}))
    (tmp_path / "adir").mkdir()
    res = run(tmp_path, s, tmp_path / "adir")
    no_traceback(res)
    assert res.returncode != 0


# ---------------------------------------------------------------- --print


def test_print_sorted_and_defaults_filled(tmp_path):
    vars_ = {
        "GAMMA": STR,
        "ALPHA": {"type": "port", "default": "8080"},
        "DELTA": {"type": "string", "required": True, "default": "dflt"},
        "BETA": {"type": "int"},
        "OMEGA": {"type": "string"},  # optional, no default, unset
    }
    s, (e,) = setup(tmp_path, vars_, "GAMMA=g\nBETA=5\n")
    res = run(tmp_path, s, e, "--print")
    assert res.returncode == 0
    assert error_lines(res) == []
    assert printed(res) == [("ALPHA", "8080"), ("BETA", "5"), ("DELTA", "dflt"), ("GAMMA", "g")]
    out_lines = [ln for ln in res.stdout.splitlines() if ln.strip()]
    assert out_lines == [
        'ALPHA="8080"',
        'BETA="5"',
        'DELTA="dflt"',
        'GAMMA="g"',
    ]


def test_print_default_not_used_when_set(tmp_path):
    s, (e,) = setup(tmp_path, {"A": {"type": "string", "default": "dflt"}}, "A=mine\n")
    res = run(tmp_path, s, e, "--print")
    assert res.returncode == 0
    assert printed(res) == [("A", "mine")]


def test_print_suppressed_when_errors(tmp_path):
    s, (e,) = setup(tmp_path, {"A": STR, "B": {"type": "int"}}, "A=hello\nB=nope\n")
    res = run(tmp_path, s, e, "--print")
    assert res.returncode == 1
    assert printed(res) == []
    assert "hello" not in res.stdout


def test_no_print_flag_prints_no_vars(tmp_path):
    s, (e,) = setup(tmp_path, {"A": STR}, "A=hello\n")
    res = run(tmp_path, s, e)
    assert res.returncode == 0
    assert printed(res) == []


def test_print_escapes_special_characters(tmp_path):
    s, (e,) = setup(
        tmp_path,
        {"A": STR, "B": STR, "C": STR},
        'A="line1\\nline2\\ttab"\nB=\'back\\slash "quoted" $HOME\'\nC=wörld\n',
    )
    res = run(tmp_path, s, e, "--print")
    assert res.returncode == 0
    lines = [ln for ln in res.stdout.splitlines() if ln.strip()]
    assert len(lines) == 3  # embedded newline must be escaped, not raw
    assert printed(res) == [
        ("A", "line1\nline2\ttab"),
        ("B", 'back\\slash "quoted" $HOME'),
        ("C", "wörld"),
    ]


def test_print_output_round_trips(tmp_path):
    vars_ = {"A": STR, "B": STR, "C": STR, "D": {"type": "int", "default": "-3"}}
    s, (e,) = setup(
        tmp_path,
        vars_,
        'export A="x\\\\y\\"z\\$w\\n"\nB=\'$NOT_EXPANDED \\n\'\nC=  π ≈ 3.14  # pi\n',
    )
    first = run(tmp_path, s, e, "--print")
    assert first.returncode == 0
    out = write(tmp_path / "out.env", first.stdout)
    second = run(tmp_path, s, out, "--print")
    assert second.returncode == 0
    assert second.stdout == first.stdout
    assert printed(first) == [
        ("A", 'x\\y"z$w\n'),
        ("B", "$NOT_EXPANDED \\n"),
        ("C", "π ≈ 3.14"),
        ("D", "-3"),
    ]


# ---------------------------------------------------------------- paths & idempotency


def test_relative_paths_with_dotdot_and_nested_dirs(tmp_path):
    write(tmp_path / "conf" / "schemas" / "s.toml", schema_for({"A": STR, "B": STR}))
    write(tmp_path / "env" / "base" / "a.env", "A=1\nB=1\n")
    write(tmp_path / "env" / "local" / "b.env", "B=2\n")
    work = tmp_path / "work" / "sub"
    work.mkdir(parents=True)
    res = run(
        work,
        "../../conf/schemas/s.toml",
        "../../env/base/a.env",
        "../../env/./local/../local/b.env",
        "--print",
    )
    no_traceback(res)
    assert res.returncode == 0
    assert printed(res) == [("A", "1"), ("B", "2")]


def test_paths_with_spaces_and_non_ascii(tmp_path):
    d = tmp_path / "my dir" / "çonfïg"
    s = write(d / "the schema.toml", schema_for({"A": STR}))
    e = write(d / "döt env.env", "A=ok\n")
    res = run(tmp_path, s, e, "--print")
    assert res.returncode == 0
    assert printed(res) == [("A", "ok")]


def test_rerun_is_idempotent_and_files_untouched(tmp_path):
    vars_ = {"A": STR, "B": {"type": "int"}}
    s, (e,) = setup(tmp_path, vars_, "A=1\nB=x\nC=3\n")
    before = (s.read_bytes(), e.read_bytes())
    r1 = run(tmp_path, s, e)
    r2 = run(tmp_path, s, e)
    assert r1.returncode == r2.returncode == 1
    assert r1.stdout == r2.stdout
    assert error_lines(r1) == error_lines(r2)
    assert (s.read_bytes(), e.read_bytes()) == before
