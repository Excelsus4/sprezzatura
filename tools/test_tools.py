#!/usr/bin/env python3
"""Sprezzatura tool tests (Python 3.9+ stdlib unittest only).

Run:  python -m unittest tools/test_tools.py -v
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from typing import Dict, List, Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLUSTERS_DIR = os.path.join(REPO_ROOT, "skill", "sprezzatura", "references", "clusters")
FINGERPRINT = os.path.join(REPO_ROOT, "skill", "sprezzatura", "scripts", "fingerprint.py")
LINT = os.path.join(REPO_ROOT, "tools", "lint_cards.py")
INSTALL_PS1 = os.path.join(REPO_ROOT, "tools", "install.ps1")
INSTALL_SH = os.path.join(REPO_ROOT, "tools", "install.sh")
IS_WINDOWS = os.name == "nt"
PLUGIN_FIELDS = {"name", "displayName", "version", "description", "suggestedPrompts"}


def _load_fingerprint():
    spec = importlib.util.spec_from_file_location("sprezzatura_fingerprint_test", FINGERPRINT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


fp = _load_fingerprint()


def run(cmd: List[str], cwd: Optional[str] = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)


def write(root: str, rel: str, content: str) -> None:
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path) or root, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)


def profile(repo: str, *extra: str) -> Dict:
    proc = run([sys.executable, FINGERPRINT, "--repo", repo] + list(extra))
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    return json.loads(proc.stdout.decode("utf-8"))


def signals(result: Dict, cluster: str) -> List[str]:
    for c in result["candidate_clusters"]:
        if c["id"] == cluster:
            return [h["signal"] for h in c["sample_hits"]]
    return []


class TempDirCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="sprezzatura-test-")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# lint_cards.py
# ---------------------------------------------------------------------------
def _good_card(card_id: str = "sample-card", probes: int = 3, extra_lines: int = 0, extra_words: int = 0) -> str:
    probe_lines = "\n".join("{}. Probe number {} with a concrete trigger.".format(i, i) for i in range(1, probes + 1))
    return (
        "---\nid: {id}\nname: Sample Card\ncategory: test\n---\n\n"
        "## Hostile World-State\nA hostile machine state.{words}\n\n"
        "## Per-Stack Applicability\n- **Applies:** C# ToLower().\n- **Ignore/Safe:** Python lower().\n\n"
        "## Seed Probes\n{probes}\n\n"
        "## Retire / Disproof Rule\nRetire when guarded.\n\n"
        "## Real Incident Anchor\nThe Turkey Test.\n{pad}"
    ).format(id=card_id, probes=probe_lines, words=" word" * extra_words, pad="\n" * extra_lines)


class LintCardsTest(TempDirCase):
    def lint(self, *args: str) -> subprocess.CompletedProcess:
        return run([sys.executable, LINT] + list(args))

    def lint_fixture(self, content: str, name: str = "01_sample.md") -> subprocess.CompletedProcess:
        write(self.tmp, name, content)
        return self.lint("--clusters-dir", self.tmp, "--skip-sync-check")

    def test_real_cards_pass_and_ids_in_sync(self) -> None:
        proc = self.lint()
        out = proc.stdout.decode("utf-8", "replace")
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn("All 12 cards pass", out)

    def test_real_card_ids_match_cluster_ids(self) -> None:
        ids = set()
        for name in os.listdir(CLUSTERS_DIR):
            if name.endswith(".md"):
                with open(os.path.join(CLUSTERS_DIR, name), encoding="utf-8") as fh:
                    for line in fh:
                        if line.startswith("id:"):
                            ids.add(line.split(":", 1)[1].strip())
                            break
        self.assertEqual(ids, set(fp.CLUSTER_IDS))
        self.assertEqual(len(fp.CLUSTER_IDS), 12)

    def test_good_fixture_passes(self) -> None:
        proc = self.lint_fixture(_good_card())
        self.assertEqual(proc.returncode, 0, proc.stdout.decode())

    def test_too_many_lines_fails(self) -> None:
        proc = self.lint_fixture(_good_card(extra_lines=40))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("line limit", proc.stdout.decode())

    def test_too_many_words_fails(self) -> None:
        proc = self.lint_fixture(_good_card(extra_words=260))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("word limit", proc.stdout.decode())

    def test_too_many_probes_fails(self) -> None:
        proc = self.lint_fixture(_good_card(probes=6))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("6 numbered probes", proc.stdout.decode())

    def test_too_few_probes_fails(self) -> None:
        proc = self.lint_fixture(_good_card(probes=2))
        self.assertEqual(proc.returncode, 1)

    def test_missing_heading_fails(self) -> None:
        proc = self.lint_fixture(_good_card().replace("## Real Incident Anchor", "## Something Else"))
        out = proc.stdout.decode()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("missing required heading '## Real Incident Anchor'", out)

    def test_missing_applicability_markers_fails(self) -> None:
        proc = self.lint_fixture(_good_card().replace("Ignore/Safe:", "Safe:"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Ignore/Safe:", proc.stdout.decode())

    def test_bad_frontmatter_fails(self) -> None:
        proc = self.lint_fixture(_good_card(card_id="Not_Kebab").replace("category: test\n", ""))
        out = proc.stdout.decode()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("kebab-case", out)
        self.assertIn("'category'", out)

    def test_duplicate_ids_fail(self) -> None:
        write(self.tmp, "01_a.md", _good_card("dup-id"))
        proc = self.lint_fixture(_good_card("dup-id"), name="02_b.md")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("duplicate id", proc.stdout.decode())


# ---------------------------------------------------------------------------
# fingerprint.py --hash
# ---------------------------------------------------------------------------
class HashTest(unittest.TestCase):
    def cli_hash(self, *args: str) -> str:
        proc = run([sys.executable, FINGERPRINT, "--hash"] + list(args))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.decode("utf-8").strip()

    def test_deterministic_and_format(self) -> None:
        a = self.cli_hash("locale-casing", "src/app.cs", "Foo.Bar", "p1")
        b = self.cli_hash("locale-casing", "src/app.cs", "Foo.Bar", "p1")
        self.assertEqual(a, b)
        self.assertRegex(a, r"^[0-9a-f]{10}$")
        import hashlib
        self.assertEqual(a, hashlib.sha1(b"locale-casing|src/app.cs|Foo.Bar|p1").hexdigest()[:10])

    def test_path_and_case_normalization(self) -> None:
        base = self.cli_hash("locale-casing", "src/app.cs", "Foo.Bar", "p1")
        self.assertEqual(base, self.cli_hash("Locale-Casing", ".\\src\\app.cs", "Foo.Bar", "P1"))
        self.assertEqual(base, self.cli_hash("LOCALE-CASING", "./src/app.cs", "Foo.Bar", "p1"))
        self.assertEqual(base, fp.finding_hash("locale-casing", "src\\app.cs", "Foo.Bar", "p1"))

    def test_distinct_inputs_differ(self) -> None:
        base = self.cli_hash("locale-casing", "src/app.cs", "Foo.Bar", "p1")
        self.assertNotEqual(base, self.cli_hash("locale-casing", "src/app.cs", "Foo.Baz", "p1"))
        self.assertNotEqual(base, self.cli_hash("locale-casing", "src/app.cs", "Foo.Bar", "p2"))
        # symbol is case-sensitive (identifiers are)
        self.assertNotEqual(base, self.cli_hash("locale-casing", "src/app.cs", "foo.bar", "p1"))


# ---------------------------------------------------------------------------
# fingerprint.py stack-aware filtering
# ---------------------------------------------------------------------------
class StackFilterTest(TempDirCase):
    def scan(self, rel: str, content: str) -> Dict:
        write(self.tmp, rel, content)
        return profile(self.tmp, "--scope", "repo")

    def assertCluster(self, result: Dict, cluster: str, signal: Optional[str] = None) -> None:
        ids = [c["id"] for c in result["candidate_clusters"]]
        self.assertIn(cluster, ids, json.dumps(result, indent=1))
        if signal:
            self.assertIn(signal, signals(result, cluster))

    def assertNotCluster(self, result: Dict, cluster: str) -> None:
        self.assertIn(cluster, result["unmatched_clusters"], json.dumps(result["candidate_clusters"], indent=1))

    def test_output_schema(self) -> None:
        r = self.scan("a.py", "x = 1\n")
        for key in ("repo", "revision", "scope_requested", "scope_used", "detected_stacks", "heavy_build",
                    "target_file_count", "target_files", "candidate_clusters", "unmatched_clusters"):
            self.assertIn(key, r)
        self.assertEqual(r["scope_used"], "repo")
        self.assertEqual(r["target_files"], ["a.py"])
        self.assertEqual(sorted(r["unmatched_clusters"] + [c["id"] for c in r["candidate_clusters"]]),
                         sorted(fp.CLUSTER_IDS))

    def test_python_lower_is_safe(self) -> None:
        r = self.scan("a.py", "def norm(s):\n    return s.lower().upper()\n")
        self.assertNotCluster(r, "locale-casing")
        self.assertIn("python", r["detected_stacks"])

    def test_js_tolowercase_is_safe(self) -> None:
        r = self.scan("a.js", "export const k = (s) => s.toLowerCase() + s.toUpperCase();\n")
        self.assertNotCluster(r, "locale-casing")

    def test_csharp_tolower_triggers(self) -> None:
        r = self.scan("A.cs", "class A { string K(string s) => s.ToLower(); }\n")
        self.assertCluster(r, "locale-casing", "cs-culture-tolower")
        self.assertIn("csharp", r["detected_stacks"])

    def test_csharp_tolowerinvariant_is_safe(self) -> None:
        r = self.scan("A.cs", "class A { bool K(string s) => s.ToLowerInvariant() == \"id\" ||"
                              " string.Equals(s, \"x\", StringComparison.OrdinalIgnoreCase); }\n")
        self.assertNotCluster(r, "locale-casing")

    def test_java_root_locale_is_safe_default_triggers(self) -> None:
        r = self.scan("A.java", "class A { String k(String s) { return s.toLowerCase(Locale.ROOT); } }\n")
        self.assertNotCluster(r, "locale-casing")
        r = self.scan("A.java", "class A { String k(String s) { return s.toUpperCase(); } }\n")
        self.assertCluster(r, "locale-casing", "java-default-locale-case")

    def test_js_tolocalelowercase_triggers(self) -> None:
        r = self.scan("a.ts", "export const k = (s: string) => s.toLocaleLowerCase();\n")
        self.assertCluster(r, "locale-casing", "js-tolocale-case")

    def test_commented_code_ignored(self) -> None:
        r = self.scan("A.cs", "// legacy: s.ToLower()\nclass A {}\n")
        self.assertNotCluster(r, "locale-casing")

    def test_powershell_convertto_json_triggers(self) -> None:
        r = self.scan("build.ps1", "$m = @{ a = 1 }\n$m | ConvertTo-Json | Set-Content -Encoding utf8 out.json\n")
        self.assertCluster(r, "wire-serialization", "ps-convertto-json")
        self.assertIn("powershell", r["detected_stacks"])

    def test_python_open_without_encoding_triggers(self) -> None:
        r = self.scan("a.py", "with open(path) as fh:\n    data = fh.read()\n")
        self.assertCluster(r, "fs-paths-unicode", "py-open-no-encoding")

    def test_python_open_with_encoding_or_binary_is_safe(self) -> None:
        r = self.scan("a.py", "with open(path, encoding='utf-8') as fh:\n    pass\n"
                              "with open(\n    path,\n    'rb',\n) as fh:\n    pass\n")
        self.assertNotIn("py-open-no-encoding", signals(r, "fs-paths-unicode"))

    def test_requests_without_timeout_triggers(self) -> None:
        r = self.scan("a.py", "import requests\nresp = requests.get(url)\n")
        self.assertCluster(r, "network-hostile", "py-requests-no-timeout")

    def test_requests_with_timeout_is_safe(self) -> None:
        r = self.scan("a.py", "import requests\nresp = requests.get(\n    url,\n    timeout=10,\n)\n")
        self.assertNotIn("py-requests-no-timeout", signals(r, "network-hostile"))

    def test_unity_project_sets_heavy_build(self) -> None:
        write(self.tmp, "ProjectSettings/ProjectVersion.txt", "m_EditorVersion: 6000.0.1f1\n")
        r = self.scan("Assets/Scripts/Player.cs", "class Player {}\n")
        self.assertTrue(r["heavy_build"])
        self.assertIn("unity", r["detected_stacks"])

    def test_plain_repo_not_heavy(self) -> None:
        r = self.scan("a.py", "x = 1\n")
        self.assertFalse(r["heavy_build"])

    def test_skip_dirs_and_large_and_binary_files(self) -> None:
        write(self.tmp, "node_modules/lib/x.js", "fetch(u)\n")
        write(self.tmp, "big.py", "x = 1\n" * 100000)
        with open(os.path.join(self.tmp, "blob.py"), "wb") as fh:
            fh.write(b"\x00\x01binary")
        r = self.scan("ok.py", "x = 1\n")
        self.assertEqual(r["target_files"], ["ok.py"])

    def test_max_files_cap(self) -> None:
        for i in range(5):
            write(self.tmp, "f{}.py".format(i), "x = 1\n")
        r = profile(self.tmp, "--scope", "repo", "--max-files", "3")
        self.assertEqual(r["target_file_count"], 3)
        self.assertEqual(r.get("truncated_at_max_files"), 3)

    def test_candidates_sorted_by_score(self) -> None:
        r = self.scan("a.py", "import requests\nrequests.get(a)\nrequests.post(b)\nopen(p)\n")
        scores = [c["score"] for c in r["candidate_clusters"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        for c in r["candidate_clusters"]:
            self.assertTrue(c["card_path"].startswith("references/clusters/"))
            self.assertLessEqual(len(c["sample_hits"]), 5)

    def test_unicode_path_utf8_json(self) -> None:
        r = self.scan("경로/파일.py", "x = 1\n")
        self.assertEqual(r["target_files"], ["경로/파일.py"])

    def test_cache_log_and_egg_info_dirs_skipped(self) -> None:
        for d in (".cache", ".mypy_cache", ".ruff_cache", "logs", "sample_pkg_agent.egg-info",
                  "src/pkg.egg-info"):
            write(self.tmp, d + "/x.py", "import requests\nrequests.get(u)\n")
        r = self.scan("src/app.py", "x = 1\n")
        self.assertEqual(r["target_files"], ["src/app.py"])
        self.assertNotCluster(r, "network-hostile")
        self.assertTrue(fp._is_skipped_rel("a/b.egg-info/c.py"))
        self.assertFalse(fp._is_skipped_rel("src/egg_info.py"))

    def test_godot_project_detected_heavy(self) -> None:
        write(self.tmp, "project.godot", "config_version=5\n")
        write(self.tmp, "shaders/water.gdshader", "shader_type spatial;\n")
        r = self.scan("scripts/player.gd", "extends Node\nvar day = 86400\n# 86400 in comment\n")
        self.assertTrue(r["heavy_build"])
        self.assertIn("gdscript", r["detected_stacks"])
        self.assertIn("godot", r["detected_stacks"])
        self.assertNotIn("unity", r["detected_stacks"])
        self.assertIn("scripts/player.gd", r["target_files"])
        self.assertIn("shaders/water.gdshader", r["target_files"])
        hits = [h for c in r["candidate_clusters"] for h in c["sample_hits"] if h["signal"] == "fixed-day-seconds"]
        self.assertEqual([(h["file"], h["line"]) for h in hits], [("scripts/player.gd", 2)])

    def test_gd_files_without_project_godot(self) -> None:
        r = self.scan("addon/tool.gd", "extends Node\n")
        self.assertIn("gdscript", r["detected_stacks"])
        self.assertNotIn("godot", r["detected_stacks"])
        self.assertFalse(r["heavy_build"])


# ---------------------------------------------------------------------------
# fingerprint.py test-file exclusion
# ---------------------------------------------------------------------------
class TestFileExclusionTest(TempDirCase):
    NET = "import requests\nrequests.get(u)\nrequests.post(u)\n"

    def setUp(self) -> None:
        super().setUp()
        write(self.tmp, "src/app.py", "import requests\nrequests.get(u, timeout=5)\nx = 1\n")
        write(self.tmp, "tools/test_foo.py", self.NET)
        write(self.tmp, "tests/helpers.py", self.NET)
        write(self.tmp, "web/__tests__/a.js", "fetch(u)\n")
        write(self.tmp, "web/a.spec.ts", "fetch(u)\n")
        write(self.tmp, "pkg/b_test.go", "package b\n")

    def cluster(self, r: Dict, cid: str) -> Optional[Dict]:
        return next((c for c in r["candidate_clusters"] if c["id"] == cid), None)

    def test_classifier(self) -> None:
        for p in ("tools/test_foo.py", "tests/helpers.py", "test/x.cs", "web/__tests__/a.js",
                  "web/a.spec.ts", "web/a.test.js", "pkg/b_test.go", "conftest.py", "Assets/Tests/T.cs"):
            self.assertTrue(fp.is_test_path(p), p)
        for p in ("src/app.py", "src/testing.py", "src/contest.py", "latest/x.py", "src/attest_util.py"):
            self.assertFalse(fp.is_test_path(p), p)

    def test_default_excludes_test_files_from_scoring(self) -> None:
        r = profile(self.tmp, "--scope", "repo")
        self.assertTrue(r["tests_excluded"])
        self.assertEqual(r["test_file_count"], 5)
        self.assertIn("tools/test_foo.py", r["target_files"])  # still listed
        self.assertIsNone(self.cluster(r, "network-hostile"))
        for c in r["candidate_clusters"]:
            self.assertFalse([f for f in c["matched_files"] if fp.is_test_path(f)], c)

    def test_include_tests_opt_in(self) -> None:
        r = profile(self.tmp, "--scope", "repo", "--include-tests")
        self.assertFalse(r["tests_excluded"])
        c = self.cluster(r, "network-hostile")
        self.assertIsNotNone(c)
        self.assertIn("tools/test_foo.py", c["matched_files"])
        self.assertIn("web/a.spec.ts", c["matched_files"])

    def test_explicit_test_path_includes_tests(self) -> None:
        r = profile(self.tmp, "--path", "tests")
        self.assertFalse(r["tests_excluded"])
        self.assertEqual(r["target_files"], ["tests/helpers.py"])
        self.assertIn("tests/helpers.py", self.cluster(r, "network-hostile")["matched_files"])

    def test_explicit_single_test_file_includes_tests(self) -> None:
        r = profile(self.tmp, "--path", "tools/test_foo.py")
        self.assertFalse(r["tests_excluded"])
        self.assertIsNotNone(self.cluster(r, "network-hostile"))

    def test_non_test_path_still_excludes(self) -> None:
        r = profile(self.tmp, "--path", "tools")
        self.assertTrue(r["tests_excluded"])
        self.assertIsNone(self.cluster(r, "network-hostile"))


# ---------------------------------------------------------------------------
# fingerprint.py git scope cascade
# ---------------------------------------------------------------------------
@unittest.skipUnless(shutil.which("git"), "git not installed")
class GitScopeTest(TempDirCase):
    def git(self, *args: str) -> None:
        proc = run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", "-C", self.tmp] + list(args))
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))

    def setUp(self) -> None:
        super().setUp()
        self.git("init", "-q")
        self.git("symbolic-ref", "HEAD", "refs/heads/main")
        write(self.tmp, "src/app.py", "x = 1\n")
        write(self.tmp, "src/other.py", "y = 2\n")
        write(self.tmp, "lib/util.cs", "class U {}\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "init")

    def test_clean_main_needs_target(self) -> None:
        r = profile(self.tmp)
        self.assertEqual(r["scope_used"], "clean-needs-target")
        self.assertEqual(r["target_files"], [])
        self.assertRegex(r["revision"], r"^[0-9a-f]{4,}$")

    def test_working_diff_staged_unstaged_untracked(self) -> None:
        write(self.tmp, "src/app.py", "import requests\nrequests.get(u)\n")   # unstaged
        write(self.tmp, "src/new.py", "z = 3\n")                             # untracked
        write(self.tmp, "lib/util.cs", "class U { string K(string s) => s.ToLower(); }\n")
        self.git("add", "lib/util.cs")                                        # staged
        r = profile(self.tmp)
        self.assertEqual(r["scope_used"], "working-diff")
        self.assertEqual(r["target_files"], ["lib/util.cs", "src/app.py", "src/new.py"])
        ids = [c["id"] for c in r["candidate_clusters"]]
        self.assertIn("network-hostile", ids)
        self.assertIn("locale-casing", ids)

    def test_merge_base_on_feature_branch(self) -> None:
        self.git("checkout", "-q", "-b", "feature")
        write(self.tmp, "src/other.py", "y = requests.get(u)\n")
        self.git("commit", "-q", "-am", "feature work")
        r = profile(self.tmp)
        self.assertEqual(r["scope_used"], "merge-base")
        self.assertEqual(r["target_files"], ["src/other.py"])
        self.assertEqual(r.get("merge_base_ref"), "main")

    def test_explicit_repo_scope(self) -> None:
        r = profile(self.tmp, "--scope", "repo")
        self.assertEqual(r["scope_used"], "repo")
        self.assertEqual(r["target_files"], ["lib/util.cs", "src/app.py", "src/other.py"])
        self.assertIn("csharp", r["detected_stacks"])
        self.assertIn("python", r["detected_stacks"])

    def test_explicit_path_overrides_cascade(self) -> None:
        write(self.tmp, "lib/util.cs", "class U {}\n// changed\n")  # dirty file outside the path
        r = profile(self.tmp, "--path", "src")
        self.assertEqual(r["scope_used"], "path")
        self.assertEqual(r["target_files"], ["src/app.py", "src/other.py"])

    def _add_ignored_fixture(self) -> None:
        write(self.tmp, ".gitignore", ".env\ntarget/\nsrc/gen/\n")
        self.git("add", ".gitignore")
        self.git("commit", "-q", "-m", "ignore")
        write(self.tmp, ".env", "API_KEY = 'sk_live_0123456789abcdef0123'\n")
        write(self.tmp, "target/release/gen.py", "x = 1\n")
        write(self.tmp, "src/gen/out.py", "y = 1\n")
        write(self.tmp, "src/new.py", "z = 3\n")                 # untracked, not ignored
        write(self.tmp, "Assets/Ignored.unity", "x\n")           # must not count: see below
        with open(os.path.join(self.tmp, ".gitignore"), "a", encoding="utf-8", newline="\n") as fh:
            fh.write("Assets/\n")

    def test_repo_scope_honors_gitignore(self) -> None:
        self._add_ignored_fixture()
        r = profile(self.tmp, "--scope", "repo")
        self.assertEqual(r["target_files"],
                         [".gitignore", "lib/util.cs", "src/app.py", "src/new.py", "src/other.py"])
        self.assertFalse(r["heavy_build"])
        self.assertNotIn("unity", r["detected_stacks"])

    def test_non_git_dir_falls_back_to_walk(self) -> None:
        plain = os.path.join(self.tmp, "..", os.path.basename(self.tmp) + "-plain")
        plain = os.path.realpath(plain)
        os.makedirs(plain)
        self.addCleanup(shutil.rmtree, plain, True)
        write(plain, ".gitignore", ".env\ntarget/\n")
        write(plain, ".env", "x = 1\n")
        write(plain, "target/release/gen.py", "x = 1\n")
        write(plain, "src/app.py", "x = 1\n")
        r = profile(plain, "--scope", "repo")
        self.assertEqual(r["target_files"], [".env", ".gitignore", "src/app.py", "target/release/gen.py"])

    def test_path_scope_honors_gitignore(self) -> None:
        self._add_ignored_fixture()
        r = profile(self.tmp, "--scope", "path", "--path", "src")
        self.assertEqual(r["scope_used"], "path")
        self.assertEqual(r["target_files"], ["src/app.py", "src/new.py", "src/other.py"])

    def test_explicit_ignored_single_file_still_audited(self) -> None:
        self._add_ignored_fixture()
        r = profile(self.tmp, "--path", "target/release/gen.py")
        self.assertEqual(r["target_files"], ["target/release/gen.py"])

    def test_deleted_cached_file_skipped(self) -> None:
        os.remove(os.path.join(self.tmp, "src", "other.py"))
        r = profile(self.tmp, "--scope", "repo")
        self.assertEqual(r["target_files"], ["lib/util.cs", "src/app.py"])

    def test_unicode_path_listed_via_git(self) -> None:
        write(self.tmp, "src/한글 파일.py", "k = 1\n")
        r = profile(self.tmp, "--scope", "repo")
        self.assertIn("src/한글 파일.py", r["target_files"])

    def test_repo_scope_max_files_with_git(self) -> None:
        r = profile(self.tmp, "--scope", "repo", "--max-files", "2")
        self.assertEqual(r["target_files"], ["lib/util.cs", "src/app.py"])
        self.assertEqual(r.get("truncated_at_max_files"), 2)

    def test_profiler_is_read_only(self) -> None:
        write(self.tmp, "src/app.py", "changed = 1\n")
        index = os.path.join(self.tmp, ".git", "index")
        before = os.path.getmtime(index)
        profile(self.tmp)
        self.assertEqual(before, os.path.getmtime(index))


# ---------------------------------------------------------------------------
# installers
# ---------------------------------------------------------------------------
class InstallerTest(TempDirCase):
    def run_installer(self, *args: str, home: Optional[str] = None) -> subprocess.CompletedProcess:
        home = home or self.tmp
        if IS_WINDOWS:
            exe = shutil.which("powershell") or shutil.which("pwsh")
            if not exe:
                self.skipTest("PowerShell not available")
            ps_args = []
            for a in args:
                ps_args.append({"--dry-run": "-DryRun", "--target": "-Target", "--agy-mode": "-AgyMode",
                                "--source": "-Source"}.get(a, a))
            cmd = [exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", INSTALL_PS1, "-HomeDir", home] + ps_args
        else:
            if not shutil.which("bash"):
                self.skipTest("bash not available")
            cmd = ["bash", INSTALL_SH, "--home", home] + list(args)
        return run(cmd)

    def out(self, proc: subprocess.CompletedProcess) -> str:
        return proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")

    def listing(self) -> List[str]:
        found = []
        for dirpath, _dirs, files in os.walk(self.tmp):
            for f in files:
                found.append(os.path.relpath(os.path.join(dirpath, f), self.tmp))
        return found

    def test_dry_run_all_writes_nothing(self) -> None:
        proc = self.run_installer("--target", "all", "--dry-run")
        out = self.out(proc)
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(self.listing(), [])
        for frag in ("skills", "plugin.json", "suggestedPrompts", "Dry run complete"):
            self.assertIn(frag, out)
        self.assertIn(os.path.join(".codex", "skills", "sprezzatura") if IS_WINDOWS else ".codex/skills/sprezzatura", out)

    def test_install_all_targets(self) -> None:
        proc = self.run_installer("--target", "all")
        out = self.out(proc)
        self.assertEqual(proc.returncode, 0, out)
        j = lambda *p: os.path.join(self.tmp, *p)  # noqa: E731
        self.assertTrue(os.path.isfile(j(".claude", "skills", "sprezzatura", "SKILL.md")))
        self.assertTrue(os.path.isfile(j(".claude", "skills", "sprezzatura", "scripts", "fingerprint.py")))
        self.assertTrue(os.path.isfile(j(".claude", "commands", "sprezzatura.md")))
        self.assertTrue(os.path.isfile(j(".claude", "commands", "spz.md")))
        self.assertTrue(os.path.isfile(j(".codex", "skills", "sprezzatura", "SKILL.md")))
        plugin_root = j(".gemini", "config", "plugins", "sprezzatura")
        self.assertTrue(os.path.isfile(os.path.join(plugin_root, "skills", "sprezzatura", "SKILL.md")))
        self.assertFalse(os.path.exists(j(".gemini", "config", "skills", "sprezzatura")))
        with open(os.path.join(plugin_root, "plugin.json"), "rb") as fh:
            raw = fh.read()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), "plugin.json must be UTF-8 without BOM")
        manifest = json.loads(raw.decode("utf-8"))
        self.assertEqual(set(manifest), PLUGIN_FIELDS)
        self.assertEqual(manifest["name"], "sprezzatura")
        self.assertIsInstance(manifest["suggestedPrompts"], list)
        self.assertEqual(len(manifest["suggestedPrompts"]), 3)
        self.assertTrue(all(isinstance(p, str) and p for p in manifest["suggestedPrompts"]))
        self.assertTrue(all(isinstance(manifest[k], str) and manifest[k] for k in PLUGIN_FIELDS - {"suggestedPrompts"}))
        self.assertFalse([p for p in self.listing() if "__pycache__" in p])

    def test_reinstall_replaces(self) -> None:
        self.assertEqual(self.run_installer("--target", "codex").returncode, 0)
        stale = os.path.join(self.tmp, ".codex", "skills", "sprezzatura", "stale.txt")
        write(self.tmp, os.path.relpath(stale, self.tmp), "old")
        self.assertEqual(self.run_installer("--target", "codex").returncode, 0)
        self.assertFalse(os.path.exists(stale))

    def test_agy_skill_mode(self) -> None:
        proc = self.run_installer("--target", "agy", "--agy-mode", "skill")
        self.assertEqual(proc.returncode, 0, self.out(proc))
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, ".gemini", "config", "skills", "sprezzatura", "SKILL.md")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, ".gemini", "config", "plugins")))

    def test_auto_detects_existing_dirs(self) -> None:
        os.makedirs(os.path.join(self.tmp, ".codex"))
        proc = self.run_installer("--target", "auto")
        self.assertEqual(proc.returncode, 0, self.out(proc))
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, ".codex", "skills", "sprezzatura", "SKILL.md")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, ".claude")))

    def test_bad_source_fails_cleanly(self) -> None:
        empty = os.path.join(self.tmp, "empty-src")
        os.makedirs(empty)
        proc = self.run_installer("--target", "claude", "--source", empty, home=os.path.join(self.tmp, "h"))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("SKILL.md not found", self.out(proc))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "h")))


def _posix_bash() -> Optional[str]:
    """A POSIX bash (Git Bash / MSYS on Windows; never the WSL launcher in System32)."""
    if IS_WINDOWS:
        for cand in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe"):
            if os.path.isfile(cand):
                return cand
        found = shutil.which("bash")
        return found if found and "system32" not in found.lower() else None
    return shutil.which("bash")


class InstallShReadOnlySourceTest(TempDirCase):
    """Regression: reinstalling from a read-only source (0555 dirs / 0444 files) hit EACCES."""

    def setUp(self) -> None:
        super().setUp()
        self.bash = _posix_bash()
        if not self.bash:
            self.skipTest("POSIX bash not available")
        self.src = os.path.join(self.tmp, "src")
        self.home = os.path.join(self.tmp, "home")
        shutil.copytree(os.path.join(REPO_ROOT, "skill"), os.path.join(self.src, "skill"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(os.path.join(REPO_ROOT, "commands"), os.path.join(self.src, "commands"))
        self.sh("chmod -R a-w src")

    def tearDown(self) -> None:
        self.sh("chmod -R u+w .", check=False)
        super().tearDown()

    def sh(self, script: str, check: bool = True) -> subprocess.CompletedProcess:
        proc = subprocess.run([self.bash, "-c", script], cwd=self.tmp, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if check:
            self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        return proc

    def install(self) -> subprocess.CompletedProcess:
        return subprocess.run([self.bash, INSTALL_SH, "--home", "home", "--source", "src", "--target", "all"],
                              cwd=self.tmp, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_reinstall_over_read_only_copy(self) -> None:
        for attempt in (1, 2, 3):
            proc = self.install()
            out = (proc.stdout + proc.stderr).decode("utf-8", "replace")
            self.assertEqual(proc.returncode, 0, "install #{} failed:\n{}".format(attempt, out))
            if attempt == 1:
                # Simulate an older installer that left read-only copies behind.
                self.sh("chmod -R a-w home/.claude/skills/sprezzatura home/.claude/commands/*.md "
                        "home/.codex/skills/sprezzatura")
        skill = os.path.join(self.home, ".claude", "skills", "sprezzatura")
        self.assertTrue(os.path.isfile(os.path.join(skill, "SKILL.md")))
        self.assertTrue(os.path.isfile(os.path.join(self.home, ".claude", "commands", "spz.md")))
        self.assertTrue(os.access(os.path.join(skill, "SKILL.md"), os.W_OK))
        self.assertTrue(os.access(os.path.join(self.home, ".claude", "commands", "spz.md"), os.W_OK))


class InstallShArgsTest(unittest.TestCase):
    """A value-taking flag passed last must fail with exit 2 and a message, not a silent abort."""

    def setUp(self) -> None:
        self.bash = _posix_bash()
        if not self.bash:
            self.skipTest("POSIX bash not available")

    def test_missing_flag_values(self) -> None:
        for flag in ("--target", "--agy-mode", "--home", "--source"):
            with self.subTest(flag=flag):
                proc = subprocess.run([self.bash, INSTALL_SH, "--dry-run", flag],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                err = proc.stderr.decode("utf-8", "replace")
                self.assertEqual(proc.returncode, 2, err)
                self.assertIn("error: {} requires a value".format(flag), err)

    def test_install_sh_has_lf_endings(self) -> None:
        with open(INSTALL_SH, "rb") as fh:
            self.assertNotIn(b"\r", fh.read())


# ---------------------------------------------------------------------------
# installer metadata parity (D-05)
# ---------------------------------------------------------------------------
FORBIDDEN_METADATA_WORDS = ("turkey test", "weaponiz", "torture", "stress-test", "skeptical", "hostile world")


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8-sig") as fh:
        return fh.read()


def _static_ps1_metadata() -> Dict:
    import re
    text = _read_text(INSTALL_PS1)
    sq = r"'((?:[^']|'')*)'"
    desc = re.search(r"^\$PluginDescription\s*=\s*" + sq + r"\s*$", text, re.M)
    block = re.search(r"^\$SuggestedPrompts\s*=\s*@\((.*?)^\)", text, re.M | re.S)
    assert desc and block, "could not locate metadata in install.ps1"
    prompts = [m.replace("''", "'") for m in re.findall(sq, block.group(1))]
    return {"description": desc.group(1).replace("''", "'"), "suggestedPrompts": prompts}


def _static_sh_metadata() -> Dict:
    import re
    text = _read_text(INSTALL_SH)

    def var(name: str) -> str:
        m = re.search(r'^' + name + r'="([^"$`\\]*)"\s*$', text, re.M)
        assert m, "could not locate {} in install.sh".format(name)
        return m.group(1)

    return {"description": var("PLUGIN_DESCRIPTION"),
            "suggestedPrompts": [var("PROMPT_{}".format(i)) for i in (1, 2, 3)]}


class InstallerMetadataParityTest(TempDirCase):
    """install.ps1 and install.sh must emit byte-identical plugin.json description/suggestedPrompts."""

    def _manifest(self, home: str) -> Dict:
        path = os.path.join(home, ".gemini", "config", "plugins", "sprezzatura", "plugin.json")
        with open(path, "rb") as fh:
            raw = fh.read()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        data = json.loads(raw.decode("utf-8"))
        return {"description": data["description"], "suggestedPrompts": data["suggestedPrompts"]}

    def _ps1_runtime(self) -> Optional[Dict]:
        exe = shutil.which("powershell") or shutil.which("pwsh")
        if not exe:
            return None
        home = os.path.join(self.tmp, "ps_home")
        proc = run([exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", INSTALL_PS1,
                    "-HomeDir", home, "-Target", "agy"])
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        return self._manifest(home)

    def _sh_runtime(self) -> Optional[Dict]:
        bash = _posix_bash()
        if not bash:
            return None
        proc = subprocess.run([bash, INSTALL_SH, "--home", "sh_home", "--target", "agy"],
                              cwd=self.tmp, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        return self._manifest(os.path.join(self.tmp, "sh_home"))

    def assertCleanMetadata(self, meta: Dict, label: str) -> None:
        desc = meta["description"]
        self.assertLessEqual(len(desc), 140, label)
        self.assertTrue(desc.isascii(), label)
        self.assertEqual(len(meta["suggestedPrompts"]), 3, label)
        for text in [desc] + list(meta["suggestedPrompts"]):
            lowered = text.lower()
            for word in FORBIDDEN_METADATA_WORDS:
                self.assertNotIn(word, lowered, "{}: forbidden '{}' in {!r}".format(label, word, text))

    def test_static_parity(self) -> None:
        ps1, sh = _static_ps1_metadata(), _static_sh_metadata()
        self.assertEqual(ps1["description"].encode("utf-8"), sh["description"].encode("utf-8"))
        self.assertEqual([p.encode("utf-8") for p in ps1["suggestedPrompts"]],
                         [p.encode("utf-8") for p in sh["suggestedPrompts"]])
        self.assertCleanMetadata(ps1, "install.ps1")
        self.assertCleanMetadata(sh, "install.sh")

    def test_runtime_parity(self) -> None:
        results = {k: v for k, v in (("install.ps1", self._ps1_runtime()), ("install.sh", self._sh_runtime())) if v}
        if not results:
            self.skipTest("neither PowerShell nor POSIX bash available")
        expected = _static_ps1_metadata()
        for label, meta in results.items():
            self.assertEqual(json.dumps(meta, ensure_ascii=False).encode("utf-8"),
                             json.dumps(expected, ensure_ascii=False).encode("utf-8"), label)
            self.assertCleanMetadata(meta, label)


if __name__ == "__main__":
    unittest.main()
