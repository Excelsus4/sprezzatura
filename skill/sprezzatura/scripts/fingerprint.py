#!/usr/bin/env python3
"""Sprezzatura deterministic surface profiler + finding hasher.

Pure Python 3.9+ standard library. Strictly read-only: never writes to the
target repository (git is invoked with GIT_OPTIONAL_LOCKS=0 so even
`git status` does not refresh the index).

Mode A (surface profiler, default):
    python fingerprint.py --repo <dir> [--scope auto|diff|merge-base|path|repo]
                          [--path <subpath>] [--max-files 200] [--include-tests]
    Emits UTF-8 JSON describing scope, detected stacks and candidate fault
    clusters backed by concrete file:line API/boundary signals. Test files
    (tests/, test_*.py, *.spec.ts, ...) stay listed in target_files but are
    excluded from cluster scoring unless --include-tests is given or --path
    itself targets a test directory / test file.

Mode B (stable finding fingerprint):
    python fingerprint.py --hash <cluster> <rel_path> <symbol> <probe_id>
    Prints sha1("cluster|norm_path|symbol|probe_id")[:10].
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import os
import re
import subprocess
import sys
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Cluster registry (must stay in sync with references/clusters/*.md;
# tools/lint_cards.py cross-checks this).
# ---------------------------------------------------------------------------
CLUSTER_CARDS: Dict[str, str] = {
    "locale-casing": "01_locale_casing.md",
    "locale-format": "02_locale_format.md",
    "clock-dst-sleep": "03_clock_dst_sleep.md",
    "fs-paths-unicode": "04_fs_paths_unicode.md",
    "crash-partial-write": "05_crash_partial_write.md",
    "concurrency-idempotency": "06_concurrency_idempotency.md",
    "numeric-boundary": "07_numeric_boundary.md",
    "wire-serialization": "08_wire_serialization.md",
    "network-hostile": "09_network_hostile.md",
    "resource-scale-lifetime": "10_resource_scale_lifetime.md",
    "auth-trust-boundary": "11_auth_trust_boundary.md",
    "cold-start-migration": "12_cold_start_migration.md",
}
CLUSTER_IDS: Tuple[str, ...] = tuple(CLUSTER_CARDS)

SKIP_DIRS = frozenset({
    ".git", "node_modules", "__pycache__", ".venv", "venv", "Library", "Temp",
    "Obj", "bin", "obj", "dist", "build", ".sprezzatura",
    ".cache", ".mypy_cache", ".ruff_cache", ".pytest_cache", ".godot", "logs",
})
SKIP_DIR_SUFFIXES = (".egg-info",)


def _skip_dir(name: str) -> bool:
    return name in SKIP_DIRS or name.endswith(SKIP_DIR_SUFFIXES)


# --- test-file classification ------------------------------------------------
TEST_DIRS = frozenset({"test", "tests", "__tests__"})
_TEST_NAME_RX = re.compile(
    r"^(?:test_.*\.py|conftest\.py|.*_test\.[^.]+|.*\.(?:test|spec)\.[^.]+)$", re.IGNORECASE)


def is_test_path(rel: str) -> bool:
    """True if repo-relative POSIX `rel` is a test file (by directory or file name)."""
    parts = rel.split("/")
    if any(p.lower() in TEST_DIRS for p in parts[:-1]):
        return True
    return bool(_TEST_NAME_RX.match(parts[-1]))
MAX_FILE_BYTES = 512 * 1024
BINARY_EXTS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".tga", ".psd",
    ".exr", ".hdr", ".tif", ".tiff", ".mp3", ".wav", ".ogg", ".flac", ".mp4",
    ".mov", ".avi", ".webm", ".zip", ".gz", ".tgz", ".bz2", ".xz", ".7z",
    ".rar", ".tar", ".jar", ".war", ".class", ".exe", ".dll", ".so", ".dylib",
    ".a", ".lib", ".o", ".obj", ".pdb", ".pyc", ".pyo", ".whl", ".bin", ".dat",
    ".db", ".sqlite", ".sqlite3", ".pdf", ".ttf", ".otf", ".woff", ".woff2",
    ".fbx", ".blend", ".glb", ".gltf", ".unitypackage", ".asset", ".mat",
    ".prefab", ".meta", ".ds_store",
})

# --- stacks -----------------------------------------------------------------
PY, CS, JS, TS, PS, SH = "python", "csharp", "javascript", "typescript", "powershell", "bash"
JAVA, GO, RS, C, SQL = "java", "go", "rust", "c_cpp", "sql"
GD = "gdscript"
GODOT_MARKER = "project.godot"
UNITY_MARKER = "ProjectSettings/ProjectVersion.txt"

EXT_STACK = {
    ".py": PY, ".pyw": PY,
    ".cs": CS,
    ".js": JS, ".mjs": JS, ".cjs": JS, ".jsx": JS,
    ".ts": TS, ".tsx": TS, ".mts": TS, ".cts": TS,
    ".ps1": PS, ".psm1": PS, ".psd1": PS,
    ".sh": SH, ".bash": SH, ".zsh": SH,
    ".java": JAVA, ".go": GO, ".rs": RS,
    ".c": C, ".h": C, ".cc": C, ".cpp": C, ".cxx": C, ".hpp": C, ".hh": C, ".hxx": C,
    ".sql": SQL,
    ".gd": GD, ".gdshader": GD,
}
ROOT_MARKERS = {
    "package.json": JS, "tsconfig.json": TS, "pyproject.toml": PY, "setup.py": PY,
    "setup.cfg": PY, "requirements.txt": PY, "go.mod": GO, "Cargo.toml": RS,
    "pom.xml": JAVA, "build.gradle": JAVA, "build.gradle.kts": JAVA,
    "CMakeLists.txt": C, GODOT_MARKER: GD,
}
COMMENT_PREFIXES = {
    PY: ("#",), PS: ("#", "<#"), SH: ("#",), SQL: ("--",),
    CS: ("//", "/*", "*"), JS: ("//", "/*", "*"), TS: ("//", "/*", "*"),
    JAVA: ("//", "/*", "*"), GO: ("//", "/*", "*"), RS: ("//", "/*", "*"),
    C: ("//", "/*", "*"), GD: ("#",),
}

JSTS = frozenset({JS, TS})
ALL = None  # applies to every recognised code stack


class Rule:
    __slots__ = ("cluster", "signal", "stacks", "rx", "weight", "line_exclude",
                 "args_exclude", "args_require")

    def __init__(self, cluster: str, signal: str, stacks: Optional[Iterable[str]],
                 pattern: str, weight: int = 1, flags: int = 0,
                 line_exclude: Optional[str] = None, args_exclude: Optional[str] = None,
                 args_require: Optional[str] = None) -> None:
        assert cluster in CLUSTER_CARDS, cluster
        self.cluster = cluster
        self.signal = signal
        self.stacks: Optional[FrozenSet[str]] = frozenset(stacks) if stacks is not None else None
        self.rx = re.compile(pattern, flags | re.MULTILINE)
        self.weight = weight
        self.line_exclude = re.compile(line_exclude) if line_exclude else None
        self.args_exclude = re.compile(args_exclude) if args_exclude else None
        self.args_require = re.compile(args_require) if args_require else None


def _s(*stacks: str) -> FrozenSet[str]:
    return frozenset(stacks)


I = re.IGNORECASE
_INVARIANT = r"InvariantCulture|CultureInfo|NumberFormatInfo|IFormatProvider|provider"

# NOTE (locale-casing stack gate): Python str.lower()/upper(), JS/TS
# toLowerCase()/toUpperCase(), C# ToLowerInvariant()/OrdinalIgnoreCase, Java
# toLowerCase(Locale.ROOT), Go strings.ToLower and Rust to_ascii_lowercase are
# locale-independent and intentionally have NO rule here.
RULES: Tuple[Rule, ...] = (
    # ---------------------------------------------------------------- locale-casing
    Rule("locale-casing", "cs-culture-tolower", _s(CS), r"\.To(?:Lower|Upper)\(\s*(?:CultureInfo\.CurrentCulture\s*)?\)", 3),
    Rule("locale-casing", "cs-currentculture-ignorecase", _s(CS), r"\bCurrentCultureIgnoreCase\b|\bStringComparison\.CurrentCulture\b", 3),
    Rule("locale-casing", "cs-regex-ignorecase-culture", _s(CS), r"\bRegexOptions\.IgnoreCase\b", 2, line_exclude=r"CultureInvariant"),
    Rule("locale-casing", "cs-string-compare-ignorecase", _s(CS), r"\b[Ss]tring\.Compare\([^;\n]*,\s*true\s*\)", 2),
    Rule("locale-casing", "cs-culture-string-prefix", _s(CS), r"\.(?:StartsWith|EndsWith|IndexOf)\(\s*\"[^\"]*\"\s*\)", 1),
    Rule("locale-casing", "java-default-locale-case", _s(JAVA), r"\.to(?:Lower|Upper)Case\(\s*\)", 3),
    Rule("locale-casing", "js-tolocale-case", JSTS, r"\.toLocale(?:Lower|Upper)Case\(", 3),
    Rule("locale-casing", "js-localecompare", JSTS, r"\.localeCompare\(", 2),
    Rule("locale-casing", "js-intl-collator", JSTS, r"\bnew\s+Intl\.Collator\(", 1),
    Rule("locale-casing", "ps-dotnet-culture-tolower", _s(PS), r"\.To(?:Lower|Upper)\(\s*\)", 2),
    Rule("locale-casing", "sql-lower-upper", _s(SQL), r"\b(?:LOWER|UPPER)\s*\(", 2, I),
    Rule("locale-casing", "c-setlocale", _s(C), r"\bsetlocale\s*\(", 2),
    Rule("locale-casing", "c-strcasecmp", _s(C), r"\b(?:strn?casecmp|_stricmp|_strnicmp|stricmp|_wcsicmp)\s*\(", 2),
    Rule("locale-casing", "c-tolower-ctype", _s(C), r"\b(?:tolower|toupper|towlower|towupper)\s*\(", 1),

    # ---------------------------------------------------------------- locale-format
    Rule("locale-format", "cs-parse-no-culture", _s(CS),
         r"\b(?:float|double|decimal|Single|Double|Decimal|DateTime|DateTimeOffset|TimeSpan)\.(?:Try)?Parse(?:Exact)?\(", 3,
         args_exclude=_INVARIANT),
    Rule("locale-format", "cs-convert-no-culture", _s(CS), r"\bConvert\.To(?:Double|Decimal|Single|DateTime)\(", 2, args_exclude=_INVARIANT),
    Rule("locale-format", "cs-format-string-no-culture", _s(CS), r"\.ToString\(\s*\"[^\"]*\"\s*\)|\bstring\.Format\(", 1, line_exclude=r"InvariantCulture"),
    Rule("locale-format", "cs-interp-numeric-format", _s(CS), r"\$\"[^\"\n]*\{[^}\n]*:[NFCPnfcp]\d*\}", 1),
    Rule("locale-format", "java-numberformat-default", _s(JAVA), r"\bNumberFormat\.get\w*Instance\(\s*\)|\bnew\s+DecimalFormat\(", 2),
    Rule("locale-format", "java-format-default-locale", _s(JAVA), r"\bString\.format\(\s*\"", 1),
    Rule("locale-format", "java-dateformat-default", _s(JAVA), r"\bnew\s+SimpleDateFormat\(", 2, args_exclude=r"Locale"),
    Rule("locale-format", "java-scanner", _s(JAVA), r"\bnew\s+Scanner\(", 1),
    Rule("locale-format", "c-locale-numeric-parse", _s(C), r"\b(?:strtod|strtof|atof|sscanf|scanf|fscanf)\s*\(", 1),
    Rule("locale-format", "js-tofixed-money", JSTS, r"\.toFixed\(\s*2\s*\)", 1),
    Rule("locale-format", "js-tolocale-string", JSTS, r"\.toLocale(?:String|DateString|TimeString)\(|\bnew\s+Intl\.(?:NumberFormat|DateTimeFormat)\(", 1),
    Rule("locale-format", "js-date-string-parse", JSTS, r"\bDate\.parse\(|\bnew\s+Date\(\s*['\"`]", 1),
    Rule("locale-format", "js-parsefloat", JSTS, r"\bparseFloat\(", 1),
    Rule("locale-format", "py-locale-module", _s(PY), r"\blocale\.(?:setlocale|atof|atoi|format_string|currency|str|localeconv|getlocale)\(", 2),
    Rule("locale-format", "py-strptime-locale-directive", _s(PY), r"\bstrptime\([^)\n]*%[aAbBcxXp]", 2),
    Rule("locale-format", "py-strftime-locale-directive", _s(PY), r"\bstrftime\([^)\n]*%[aAbBcxXp]", 1),
    Rule("locale-format", "py-manual-decimal-comma", _s(PY), r"\bfloat\([^)\n]*\.replace\(\s*['\"],", 1),
    Rule("locale-format", "ps-parse-no-culture", _s(PS),
         r"\[(?:double|decimal|single|float|datetime)\]::(?:Try)?Parse(?:Exact)?\(", 3, I, args_exclude=_INVARIANT),
    Rule("locale-format", "ps-culture-format", _s(PS), r"\bGet-Date\s+-Format\b|\.ToString\(\s*['\"][NFCP]|\{0:[NFCP]\d*\}", 1, I),
    Rule("locale-format", "sql-format-convert", _s(SQL), r"\bFORMAT\s*\(|\bTO_CHAR\s*\(|\bCONVERT\s*\(\s*N?VARCHAR", 1, I),

    # ---------------------------------------------------------------- clock-dst-sleep
    Rule("clock-dst-sleep", "py-wall-clock-time", _s(PY), r"\btime\.time\(\)", 2),
    Rule("clock-dst-sleep", "py-naive-now", _s(PY), r"\bdatetime\.(?:datetime\.)?now\(\s*\)|\.utcnow\(\)|\bdate\.today\(\)", 2),
    Rule("clock-dst-sleep", "py-local-time", _s(PY), r"\btime\.(?:localtime|mktime)\(", 1),
    Rule("clock-dst-sleep", "cs-datetime-now", _s(CS), r"\bDateTime(?:Offset)?\.(?:Now|Today)\b", 2),
    Rule("clock-dst-sleep", "cs-datetime-utcnow", _s(CS), r"\bDateTime\.UtcNow\b", 1),
    Rule("clock-dst-sleep", "cs-tickcount-wrap", _s(CS), r"\bEnvironment\.TickCount\b(?!64)", 2),
    Rule("clock-dst-sleep", "unity-deltatime", _s(CS), r"\bTime\.(?:deltaTime|time|realtimeSinceStartup)\b", 1),
    Rule("clock-dst-sleep", "cs-local-timezone", _s(CS), r"\bTimeZoneInfo\.Local\b|\.ToLocalTime\(", 1),
    Rule("clock-dst-sleep", "js-date-now", JSTS, r"\bDate\.now\(\)|\bnew\s+Date\(\)\.getTime\(\)", 2),
    Rule("clock-dst-sleep", "js-local-date-math", JSTS, r"\.set(?:Hours|Date)\([^)\n]*\.get(?:Hours|Date)\(\)\s*\+", 2),
    Rule("clock-dst-sleep", "java-wall-clock", _s(JAVA), r"\bSystem\.currentTimeMillis\(\)|\bLocalDateTime\.now\(\)|\bnew\s+Date\(\)|\bCalendar\.getInstance\(\)", 2),
    Rule("clock-dst-sleep", "go-wall-clock", _s(GO), r"\btime\.Now\(\)\.Unix\w*\(\)|\btime\.Local\b", 1),
    Rule("clock-dst-sleep", "rust-system-time", _s(RS), r"\bSystemTime::now\(\)", 2),
    Rule("clock-dst-sleep", "ps-get-date", _s(PS), r"\bGet-Date\b|\[DateTime\]::(?:Now|Today)", 1, I),
    Rule("clock-dst-sleep", "sh-epoch-date", _s(SH), r"\bdate\s+\+%s\b|\bcrontab\b", 2),
    Rule("clock-dst-sleep", "sql-server-now", _s(SQL), r"\b(?:NOW|GETDATE|SYSDATETIME)\s*\(|\b(?:CURRENT_TIMESTAMP|LOCALTIMESTAMP)\b", 1, I),
    Rule("clock-dst-sleep", "fixed-day-seconds", ALL, r"\b86400(?:000)?\b|\b24\s*\*\s*60\s*\*\s*60\b", 2),

    # ---------------------------------------------------------------- fs-paths-unicode
    Rule("fs-paths-unicode", "py-open-no-encoding", _s(PY), r"(?<![\w.])open\(", 3,
         line_exclude=r"\bdef\s+open\b",
         args_exclude=r"\bencoding\s*=|['\"][rwaxt+]*b[rwaxt+]*['\"]|\bmode\s*=\s*['\"][^'\"]*b"),
    Rule("fs-paths-unicode", "py-pathlib-text-no-encoding", _s(PY), r"\.(?:read_text|write_text)\(", 2, args_exclude=r"\bencoding\s*="),
    Rule("fs-paths-unicode", "py-shell-true", _s(PY), r"\bshell\s*=\s*True\b", 3),
    Rule("fs-paths-unicode", "py-os-system", _s(PY), r"\bos\.(?:system|popen)\(", 3),
    Rule("fs-paths-unicode", "py-subprocess-string-cmd", _s(PY), r"\bsubprocess\.\w+\(\s*f?['\"]", 2),
    Rule("fs-paths-unicode", "path-separator-split", ALL, r"\.split\(\s*['\"](?:/|\\\\)['\"]\s*\)", 2, I),
    Rule("fs-paths-unicode", "path-separator-concat", ALL, r"\+\s*@?['\"](?:/|\\\\)", 1),
    Rule("fs-paths-unicode", "cs-encoding-default", _s(CS), r"\bEncoding\.Default\b", 2),
    Rule("fs-paths-unicode", "cs-process-start", _s(CS), r"\bProcess\.Start\(", 1),
    Rule("fs-paths-unicode", "max-path-260", _s(CS, C), r"\bMAX_PATH\b", 2),
    Rule("fs-paths-unicode", "js-child-process-exec", JSTS, r"\b(?:exec|execSync)\(\s*[`'\"\w]", 2, line_exclude=r"\.exec\(\s*\w+\s*\)\s*;?\s*$|\bregex|RegExp"),
    Rule("fs-paths-unicode", "js-shell-true", JSTS, r"\bshell\s*:\s*true\b", 3),
    Rule("fs-paths-unicode", "js-dirname-concat", JSTS, r"\b__dirname\s*\+|\bprocess\.cwd\(\)\s*\+", 2),
    Rule("fs-paths-unicode", "ps-invoke-expression", _s(PS), r"\b(?:Invoke-Expression|iex)\b", 3, I),
    Rule("fs-paths-unicode", "ps-cmd-c", _s(PS, SH), r"\bcmd(?:\.exe)?\s+/c\b", 2, I),
    Rule("fs-paths-unicode", "ps-text-io-no-encoding", _s(PS), r"\b(?:Set-Content|Add-Content|Out-File|Get-Content)\b", 2, I, line_exclude=r"(?i)-Encoding\b"),
    Rule("fs-paths-unicode", "ps-start-process", _s(PS), r"\bStart-Process\b", 1, I),
    Rule("fs-paths-unicode", "sh-unquoted-var-path", _s(SH), r"\b(?:rm|cp|mv|cd|cat|mkdir|ls|tar|touch|source)\s+(?:-[\w-]+\s+)*\$\{?\w", 2),
    Rule("fs-paths-unicode", "sh-eval", _s(SH), r"\beval\s", 2),
    Rule("fs-paths-unicode", "sh-for-in-ls", _s(SH), r"\bfor\s+\w+\s+in\s+\$\(\s*ls\b|\bfor\s+\w+\s+in\s+`ls\b", 3),
    Rule("fs-paths-unicode", "java-runtime-exec", _s(JAVA), r"\bRuntime\.getRuntime\(\)\.exec\(", 3),
    Rule("fs-paths-unicode", "java-default-charset-io", _s(JAVA),
         r"\bnew\s+(?:FileReader|FileWriter|InputStreamReader|OutputStreamWriter|PrintWriter)\(", 2,
         args_exclude=r"UTF_8|[Cc]harset|\"UTF-8\""),
    Rule("fs-paths-unicode", "java-getbytes-default", _s(JAVA), r"\.getBytes\(\s*\)", 2),
    Rule("fs-paths-unicode", "c-system-popen", _s(C), r"\b(?:system|popen|_popen|_wsystem)\s*\(", 3),
    Rule("fs-paths-unicode", "c-fopen-narrow", _s(C), r"\bfopen\s*\(", 1),
    Rule("fs-paths-unicode", "go-shell-command", _s(GO), r"\bexec\.Command\(\s*\"(?:sh|bash|cmd|powershell)\"", 3),
    Rule("fs-paths-unicode", "rust-shell-command", _s(RS), r"\bCommand::new\(\s*\"(?:sh|bash|cmd|powershell)\"", 3),

    # ---------------------------------------------------------------- crash-partial-write
    Rule("crash-partial-write", "py-inplace-overwrite", _s(PY), r"(?<![\w.])open\(", 2,
         line_exclude=r"\bdef\s+open\b", args_require=r"['\"]w[bt+]*['\"]|\bmode\s*=\s*['\"]w"),
    Rule("crash-partial-write", "py-pathlib-write", _s(PY), r"\.(?:write_text|write_bytes)\(", 2),
    Rule("crash-partial-write", "py-json-dump", _s(PY), r"\bjson\.dump\(", 1),
    Rule("crash-partial-write", "py-os-rename", _s(PY), r"\bos\.rename\(|\bshutil\.move\(", 2),
    Rule("crash-partial-write", "cs-file-writeall", _s(CS), r"\bFile\.(?:WriteAllText|WriteAllBytes|WriteAllLines|AppendAllText)\(", 2),
    Rule("crash-partial-write", "cs-file-move-no-overwrite", _s(CS), r"\bFile\.Move\(", 2, args_exclude=r"\btrue\b"),
    Rule("crash-partial-write", "cs-filemode-truncate", _s(CS), r"\bFileMode\.(?:Create|Truncate)\b", 2),
    Rule("crash-partial-write", "js-writefile", JSTS, r"\bwriteFile(?:Sync)?\(", 2),
    Rule("crash-partial-write", "js-rename", JSTS, r"\brename(?:Sync)?\(", 1),
    Rule("crash-partial-write", "ps-overwrite-file", _s(PS), r"\b(?:Set-Content|Out-File|Move-Item)\b", 1, I),
    Rule("crash-partial-write", "java-file-overwrite", _s(JAVA), r"\bnew\s+FileOutputStream\(|\bFiles\.(?:write|writeString)\(|\.renameTo\(", 2),
    Rule("crash-partial-write", "go-file-overwrite", _s(GO), r"\b(?:os|ioutil)\.WriteFile\(|\bos\.Create\(|\bos\.Rename\(", 2),
    Rule("crash-partial-write", "rust-file-overwrite", _s(RS), r"\bfs::write\(|\bFile::create\(|\bfs::rename\(", 2),
    Rule("crash-partial-write", "c-fopen-write", _s(C), r"\bfopen\s*\([^)\n]*\"w", 2),
    Rule("crash-partial-write", "sh-redirect-overwrite", _s(SH), r"(?<![<>&\d-])>\s*[\"']?\$\{?\w", 2),
    Rule("crash-partial-write", "sh-sed-inplace", _s(SH), r"\bsed\s+-i\b", 1),
    Rule("crash-partial-write", "pid-lock-file", ALL, r"['\"][^'\"\n]*\.(?:pid|lock)['\"]|\blockfile\b|\bO_EXCL\b|\bflock\b", 2, I),

    # ---------------------------------------------------------------- concurrency-idempotency
    Rule("concurrency-idempotency", "py-threads-async", _s(PY), r"\bthreading\.Thread\(|\bThreadPoolExecutor\b|\bProcessPoolExecutor\b|\basyncio\.(?:gather|create_task)\(|\bmultiprocessing\b", 2),
    Rule("concurrency-idempotency", "py-mutating-endpoint", _s(PY), r"@\w+\.(?:post|put|patch|delete)\(|methods\s*=\s*\[[^\]]*['\"]POST", 2),
    Rule("concurrency-idempotency", "js-effect-async", JSTS, r"\buseEffect\(|\bonClick=\{\s*async\b", 1),
    Rule("concurrency-idempotency", "js-mutating-endpoint", JSTS, r"\b(?:app|router|server)\.(?:post|put|patch|delete)\(", 2),
    Rule("concurrency-idempotency", "js-parallel", JSTS, r"\bPromise\.(?:all|race|allSettled)\(|\bnew\s+Worker\(", 1),
    Rule("concurrency-idempotency", "cs-async-void", _s(CS), r"\basync\s+void\b", 3),
    Rule("concurrency-idempotency", "cs-threads", _s(CS), r"\bTask\.Run\(|\bnew\s+Thread\(|\bParallel\.For(?:Each)?\(|\bThreadPool\.", 2),
    Rule("concurrency-idempotency", "cs-shared-static-collection", _s(CS), r"\bstatic\s+(?:readonly\s+)?(?:List|Dictionary|HashSet|Queue)<", 2),
    Rule("concurrency-idempotency", "cs-mutating-endpoint", _s(CS), r"\[Http(?:Post|Put|Patch|Delete)\b", 2),
    Rule("concurrency-idempotency", "unity-coroutine", _s(CS), r"\bStartCoroutine\(", 1),
    Rule("concurrency-idempotency", "java-concurrency", _s(JAVA), r"\bnew\s+Thread\(|\bExecutorService\b|\bCompletableFuture\b|@(?:Post|Put|Patch|Delete)Mapping\b", 2),
    Rule("concurrency-idempotency", "go-goroutine", _s(GO), r"^\s*go\s+(?:func\b|[\w.]+\()|\bsync\.(?:Mutex|RWMutex|WaitGroup)\b", 2),
    Rule("concurrency-idempotency", "rust-spawn", _s(RS), r"\b(?:thread|tokio)::spawn\(|\bArc<Mutex<", 2),
    Rule("concurrency-idempotency", "ps-parallel-jobs", _s(PS), r"\bStart-(?:Thread)?Job\b|\bForEach-Object\s+-Parallel\b|\bRegister-ObjectEvent\b", 2, I),
    Rule("concurrency-idempotency", "sh-background-jobs", _s(SH), r"&\s*$|\bxargs\s+[^|\n]*-P\b|\bparallel\s", 1),
    Rule("concurrency-idempotency", "webhook-handler", ALL, r"\bwebhook", 1, I),

    # ---------------------------------------------------------------- numeric-boundary
    Rule("numeric-boundary", "js-falsy-default", JSTS, r"\|\|\s*(?:\d|['\"`]|\[|\{|null\b|undefined\b|false\b)", 1),
    Rule("numeric-boundary", "js-falsy-guard", JSTS, r"\bif\s*\(\s*!\s*[\w$.]+\s*\)", 1),
    Rule("numeric-boundary", "js-parseint-no-radix", JSTS, r"\bparseInt\(\s*[^,()\n]+\)", 1),
    Rule("numeric-boundary", "js-json-number-ids", JSTS, r"\bJSON\.parse\(", 1),
    Rule("numeric-boundary", "py-falsy-guard", _s(PY), r"\bif\s+not\s+[\w.\[\]'\"]+\s*:", 1),
    Rule("numeric-boundary", "py-or-default", _s(PY), r"=\s*[\w.\[\]'\"()]+\s+or\s+(?:\d|['\"\[{]|None\b)", 1),
    Rule("numeric-boundary", "float-equality", _s(PY, JS, TS, CS, JAVA, C, GO), r"[!=]==?\s*-?\d+\.\d+f?\b", 1),
    Rule("numeric-boundary", "unguarded-division", _s(PY, JS, TS, CS, JAVA, C, GO),
         r"(?<![/*])/\s*(?:len\(|[\w.]*(?:count|total|sum|size|length|norm|magnitude|len)\b)", 1, I),
    Rule("numeric-boundary", "int-cast-truncation", _s(CS, JAVA, C), r"\(int\)\s*[\w(]", 1),
    Rule("numeric-boundary", "cs-normalize", _s(CS), r"\.normalized\b|\.Normalize\(\)", 1),
    Rule("numeric-boundary", "go-narrowing-cast", _s(GO), r"\b(?:int8|int16|int32|uint8|uint16|uint32|float32)\(", 1),
    Rule("numeric-boundary", "rust-as-cast", _s(RS), r"\bas\s+(?:i8|i16|i32|u8|u16|u32|usize|isize|f32)\b", 1),
    Rule("numeric-boundary", "ps-falsy-or-float", _s(PS), r"-eq\s*-?\d+\.\d+|\bif\s*\(\s*(?:-not\s+|!)\$\w+\s*\)", 1, I),
    Rule("numeric-boundary", "sql-division-aggregate", _s(SQL), r"/\s*(?:COUNT|SUM)\s*\(", 1, I),

    # ---------------------------------------------------------------- wire-serialization
    Rule("wire-serialization", "ps-convertto-json", _s(PS), r"\bConvertTo-Json\b", 3, I),
    Rule("wire-serialization", "ps-convertfrom-json", _s(PS), r"\bConvertFrom-Json\b", 2, I),
    Rule("wire-serialization", "ps-manual-split", _s(PS), r"-split\s*['\"][,;|\\t]['\"]", 1, I),
    Rule("wire-serialization", "py-unsafe-yaml-load", _s(PY), r"\byaml\.(?:unsafe_)?load\(", 3, args_exclude=r"SafeLoader"),
    Rule("wire-serialization", "py-pickle-marshal", _s(PY), r"\b(?:pickle|cPickle|marshal|dill)\.loads?\(|\bshelve\.open\(", 3),
    Rule("wire-serialization", "py-eval", _s(PY), r"(?<![\w.])eval\(", 3),
    Rule("wire-serialization", "manual-csv-split", ALL, r"\.split\(\s*['\"][,;|]['\"]\s*\)|\.Split\(\s*'[,;|]'\s*\)", 2),
    Rule("wire-serialization", "js-eval", JSTS, r"(?<![\w.])eval\(|\bnew\s+Function\(", 3),
    Rule("wire-serialization", "cs-unsafe-deserializer", _s(CS), r"\bBinaryFormatter\b|\bTypeNameHandling\.(?:All|Auto|Objects)\b", 3),
    Rule("wire-serialization", "cs-json-deserialize", _s(CS), r"\bJsonConvert\.DeserializeObject\b|\bJsonSerializer\.Deserialize\b|\bJsonUtility\.FromJson\b", 1),
    Rule("wire-serialization", "cs-enum-parse", _s(CS), r"\bEnum\.(?:Try)?Parse\b", 2),
    Rule("wire-serialization", "java-unsafe-deserializer", _s(JAVA), r"\bObjectInputStream\b|\bFAIL_ON_UNKNOWN_PROPERTIES\b|\bEnum\.valueOf\(", 2),
    Rule("wire-serialization", "go-strict-json", _s(GO), r"\bDisallowUnknownFields\(|\bjson\.Unmarshal\(", 1),
    Rule("wire-serialization", "rust-strict-serde", _s(RS), r"\bdeny_unknown_fields\b|\bserde_json::from_str\b", 1),
    Rule("wire-serialization", "sh-manual-delimiter", _s(SH), r"\bIFS=['\"]?[,;|]|\bcut\s+-d\s*['\"]?[,;|]|\bawk\s+-F\s*['\"]?[,;|]", 2),

    # ---------------------------------------------------------------- network-hostile
    Rule("network-hostile", "py-requests-no-timeout", _s(PY), r"\brequests\.(?:get|post|put|patch|delete|head|options|request)\(", 3, args_exclude=r"\btimeout\b"),
    Rule("network-hostile", "py-urlopen-no-timeout", _s(PY), r"\burlopen\(", 3, args_exclude=r"\btimeout\b"),
    Rule("network-hostile", "py-raw-connection-no-timeout", _s(PY), r"\bHTTPS?Connection\(|\bsocket\.create_connection\(|\baiohttp\.ClientSession\(", 2, args_exclude=r"\btimeout\b"),
    Rule("network-hostile", "js-fetch-no-signal", JSTS, r"(?<![\w.])fetch\(", 3, args_exclude=r"\bsignal\b|\btimeout\b"),
    Rule("network-hostile", "js-axios-no-timeout", JSTS, r"\baxios(?:\.(?:get|post|put|patch|delete|request))?\(", 2, args_exclude=r"\btimeout\b"),
    Rule("network-hostile", "js-node-http", JSTS, r"\bhttps?\.(?:request|get)\(|\bnew\s+WebSocket\(", 2),
    Rule("network-hostile", "cs-new-httpclient", _s(CS), r"\bnew\s+HttpClient\(", 3),
    Rule("network-hostile", "cs-network-client", _s(CS), r"\bHttpClient\b|\bUnityWebRequest\b|\bWebClient\b|\bTcpClient\b", 1),
    Rule("network-hostile", "cs-infinite-timeout", _s(CS), r"\bTimeout\.InfiniteTimeSpan\b", 3),
    Rule("network-hostile", "java-http", _s(JAVA), r"\bopenConnection\(|\bHttpClient\.newHttpClient\(|\bRestTemplate\b", 2),
    Rule("network-hostile", "go-default-http-client", _s(GO), r"\bhttp\.(?:Get|Post|Head|PostForm)\(|\bhttp\.DefaultClient\b|&http\.Client\{\s*\}", 3),
    Rule("network-hostile", "rust-reqwest", _s(RS), r"\breqwest::(?:get|Client::new)\(", 2),
    Rule("network-hostile", "ps-web-no-timeout", _s(PS), r"\b(?:Invoke-WebRequest|Invoke-RestMethod|iwr|irm)\b", 3, I, line_exclude=r"(?i)-TimeoutSec\b"),
    Rule("network-hostile", "sh-curl-no-timeout", _s(SH, PS), r"\bcurl(?:\.exe)?\s", 2, line_exclude=r"--max-time|\s-m\s*\d|--connect-timeout"),
    Rule("network-hostile", "sh-wget-no-timeout", _s(SH), r"\bwget\s", 2, line_exclude=r"--timeout|\s-T\s*\d"),
    Rule("network-hostile", "c-network", _s(C), r"\bcurl_easy_perform\(|\brecv\s*\(|\bconnect\s*\(", 1),
    Rule("network-hostile", "retry-loop", ALL, r"\bretr(?:y|ies|ying)\b", 1, I),

    # ---------------------------------------------------------------- resource-scale-lifetime
    Rule("resource-scale-lifetime", "py-open-without-with", _s(PY), r"=\s*open\(", 2),
    Rule("resource-scale-lifetime", "py-unscoped-connection", _s(PY), r"=\s*(?:sqlite3\.connect|subprocess\.Popen|socket\.socket)\(", 2),
    Rule("resource-scale-lifetime", "py-unbounded-cache", _s(PY), r"lru_cache\(\s*maxsize\s*=\s*None|@(?:functools\.)?cache\b|^_?\w*cache\w*\s*(?::[^=\n]+)?=\s*(?:\{\}|dict\(\))", 2, I),
    Rule("resource-scale-lifetime", "py-read-all", _s(PY), r"\.readlines\(\)|\.read\(\)", 1),
    Rule("resource-scale-lifetime", "cs-event-subscribe", _s(CS), r"\.AddListener\(|\b\w+\.\w+\s*\+=\s*(?:new\s+\w+\(|\w+\s*;|\([^)]*\)\s*=>|\w+\s*=>)", 2),
    Rule("resource-scale-lifetime", "cs-unmanaged-resource", _s(CS), r"\bnew\s+(?:Texture2D|RenderTexture|ComputeBuffer|Mesh|FileStream|StreamReader|StreamWriter|SqlConnection)\(", 2, line_exclude=r"\busing\b"),
    Rule("resource-scale-lifetime", "cs-repeating-timer", _s(CS), r"\bInvokeRepeating\(|\bnew\s+Timer\(", 1),
    Rule("resource-scale-lifetime", "js-listener-timer", JSTS, r"\baddEventListener\(|\bsetInterval\(|\.on\(\s*['\"]", 1),
    Rule("resource-scale-lifetime", "js-module-cache", JSTS, r"^(?:export\s+)?(?:const|let|var)\s+\w*cache\w*\s*=\s*(?:new\s+Map\(|\{\})", 2, I),
    Rule("resource-scale-lifetime", "java-unclosed-stream", _s(JAVA), r"\bnew\s+(?:FileInputStream|BufferedReader|FileReader|Socket)\(", 1, line_exclude=r"^\s*try\s*\("),
    Rule("resource-scale-lifetime", "go-time-tick-leak", _s(GO), r"\btime\.Tick\(", 2),
    Rule("resource-scale-lifetime", "ps-array-append", _s(PS), r"\$\w+\s*\+=\s*", 2),
    Rule("resource-scale-lifetime", "sql-unbounded-select", _s(SQL), r"\bSELECT\s+\*\s+FROM\b", 1, I, line_exclude=r"(?i)\bLIMIT\b|\bTOP\b"),
    Rule("resource-scale-lifetime", "c-manual-alloc", _s(C), r"\bmalloc\s*\(|\bnew\s+\w+\s*\[", 1),
    Rule("resource-scale-lifetime", "nested-scan", ALL, r"\bfor\b[^\n]*\bin\b[^\n]*:\s*$\n\s+for\b|\bindexOf\([^)\n]*\)\s*(?:===?|!==?|<|>=)\s*-?1", 1),

    # ---------------------------------------------------------------- auth-trust-boundary
    Rule("auth-trust-boundary", "py-sql-interpolation", _s(PY), r"\.execute\(\s*f['\"]|\.execute\([^)\n]*(?:%\s*\(|\.format\(|\+\s*\w)", 3),
    Rule("auth-trust-boundary", "py-archive-extractall", _s(PY), r"\.extractall\(|\.extract\(", 3, args_exclude=r"\bfilter\s*=\s*['\"]data"),
    Rule("auth-trust-boundary", "py-request-input", _s(PY), r"\brequest\.(?:args|form|json|files|values|GET|POST|query_params|path_params)\b", 1),
    Rule("auth-trust-boundary", "py-tls-verify-off", _s(PY), r"\bverify\s*=\s*False\b|\b_create_unverified_context\b", 3),
    Rule("auth-trust-boundary", "py-path-from-request", _s(PY), r"\bos\.path\.join\([^)\n]*request\.|\bsend_file\(|\bsend_from_directory\(", 2),
    Rule("auth-trust-boundary", "js-sql-template", JSTS, r"\.(?:query|execute|raw)\(\s*`[^`]*\$\{", 3),
    Rule("auth-trust-boundary", "js-request-input", JSTS, r"\breq\.(?:params|query|body)\b", 1),
    Rule("auth-trust-boundary", "js-xss-sink", JSTS, r"\.innerHTML\s*=|\bdangerouslySetInnerHTML\b", 3),
    Rule("auth-trust-boundary", "js-tls-off", JSTS, r"\brejectUnauthorized\s*:\s*false\b|NODE_TLS_REJECT_UNAUTHORIZED", 3),
    Rule("auth-trust-boundary", "js-path-from-request", JSTS, r"\bpath\.(?:join|resolve)\([^)\n]*req\.|\bres\.sendFile\(", 2),
    Rule("auth-trust-boundary", "cs-sql-concat", _s(CS), r"\b(?:SqlCommand|FromSqlRaw|ExecuteSqlRaw)\(\s*(?:\$\"|\"[^\"\n]*\"\s*\+)", 3),
    Rule("auth-trust-boundary", "cs-zip-extract", _s(CS), r"\bExtractToDirectory\(|\.ExtractToFile\(", 3),
    Rule("auth-trust-boundary", "cs-tls-callback", _s(CS), r"\bServerCertificateCustomValidationCallback\b|\bServerCertificateValidationCallback\b", 3),
    Rule("auth-trust-boundary", "cs-path-from-request", _s(CS), r"\bPath\.Combine\([^)\n]*\bRequest\b|\[AllowAnonymous\]", 2),
    Rule("auth-trust-boundary", "java-sql-concat", _s(JAVA), r"\b(?:executeQuery|executeUpdate|execute)\(\s*\"[^\"\n]*\"\s*\+|\bcreateStatement\(\)", 3),
    Rule("auth-trust-boundary", "java-request-input", _s(JAVA), r"@(?:RequestParam|PathVariable|RequestBody)\b|\bZipEntry\b", 1),
    Rule("auth-trust-boundary", "go-sql-sprintf", _s(GO), r"\bfmt\.Sprintf\(\s*\"\s*(?:SELECT|INSERT|UPDATE|DELETE)\b", 3, I),
    Rule("auth-trust-boundary", "go-tls-skip", _s(GO), r"\bInsecureSkipVerify\s*:\s*true\b", 3),
    Rule("auth-trust-boundary", "go-request-input", _s(GO), r"\br\.URL\.Query\(\)|\bmux\.Vars\(|\bfilepath\.Join\([^)\n]*\br\.", 1),
    Rule("auth-trust-boundary", "ps-plaintext-secret", _s(PS), r"\bConvertTo-SecureString\b[^\n]*-AsPlainText|\bExpand-Archive\b", 2, I),
    Rule("auth-trust-boundary", "sh-pipe-to-shell", _s(SH, PS), r"\b(?:curl|wget|iwr|irm)\b[^|\n]*\|\s*(?:ba|z)?sh\b|\|\s*iex\b", 3, I),
    Rule("auth-trust-boundary", "sh-xtrace", _s(SH), r"^\s*set\s+-\w*x", 1),
    Rule("auth-trust-boundary", "sql-dynamic-exec", _s(SQL), r"\bEXEC(?:UTE)?\s*\(\s*@|\bsp_executesql\b|\bEXECUTE\s+format\(", 3, I),
    Rule("auth-trust-boundary", "c-unsafe-string", _s(C), r"\b(?:gets|strcpy|strcat|sprintf)\s*\(", 2),
    Rule("auth-trust-boundary", "secret-logging", ALL,
         r"\b(?:print|console\.\w+|log(?:ger)?\.\w+|Debug\.Log\w*|Write-(?:Host|Output|Verbose)|echo|Console\.Write\w*)\b[^\n]*(?:password|passwd|secret|api_?key|apikey|token|authorization)", 2, I),
    Rule("auth-trust-boundary", "hardcoded-secret", ALL, r"\b(?:api[_-]?key|secret|password|passwd|access[_-]?token)\b\s*[:=]\s*['\"][^'\"\s]{8,}['\"]", 3, I),

    # ---------------------------------------------------------------- cold-start-migration
    Rule("cold-start-migration", "py-environ-index", _s(PY), r"\bos\.environ\[", 2),
    Rule("cold-start-migration", "py-mkdir-no-exist-ok", _s(PY), r"\bos\.makedirs\(|\.mkdir\(", 1, args_exclude=r"\bexist_ok\s*=\s*True"),
    Rule("cold-start-migration", "py-write-next-to-code", _s(PY), r"\bos\.path\.dirname\(\s*(?:os\.path\.(?:abspath|realpath)\(\s*)?(?:__file__|sys\.executable)|\bPath\(\s*__file__\s*\)\.(?:resolve\(\)\.)?parent", 1),
    Rule("cold-start-migration", "py-config-load", _s(PY), r"\bjson\.load\(|\bconfigparser\.|\btomllib\.load\(|\bsqlite3\.connect\(", 1),
    Rule("cold-start-migration", "cs-env-var", _s(CS), r"\bEnvironment\.GetEnvironmentVariable\(", 1),
    Rule("cold-start-migration", "cs-write-next-to-exe", _s(CS), r"\bAppDomain\.CurrentDomain\.BaseDirectory\b|\bAppContext\.BaseDirectory\b|\bApplication\.(?:dataPath|streamingAssetsPath)\b", 2),
    Rule("cold-start-migration", "cs-persisted-state", _s(CS), r"\bApplication\.persistentDataPath\b|\bPlayerPrefs\.Get\w+\(|\bFile\.Read\w*\(", 1),
    Rule("cold-start-migration", "js-env-no-default", JSTS, r"\bprocess\.env\.\w+", 2, line_exclude=r"\?\?|\|\|"),
    Rule("cold-start-migration", "js-persisted-state", JSTS, r"\blocalStorage\.getItem\(|\bJSON\.parse\(\s*localStorage", 2),
    Rule("cold-start-migration", "js-mkdir-nonrecursive", JSTS, r"\bmkdir(?:Sync)?\(", 1, args_exclude=r"\brecursive\b"),
    Rule("cold-start-migration", "java-env", _s(JAVA), r"\bSystem\.getenv\(|\buser\.dir\b", 1),
    Rule("cold-start-migration", "go-env-mkdir", _s(GO), r"\bos\.Getenv\(|\bos\.Mkdir\(", 1),
    Rule("cold-start-migration", "rust-env-unwrap", _s(RS), r"\benv::var\([^)\n]*\)\s*\.(?:unwrap|expect)\(", 2),
    Rule("cold-start-migration", "ps-script-root-state", _s(PS), r"\$PSScriptRoot\b|\$env:\w+", 1, I),
    Rule("cold-start-migration", "ps-new-dir-no-force", _s(PS), r"\bNew-Item\b[^\n]*-ItemType\s+Directory", 1, I, line_exclude=r"(?i)-Force\b"),
    Rule("cold-start-migration", "sh-mkdir-no-p", _s(SH), r"\bmkdir\s+(?!-\w*p)", 2),
    Rule("cold-start-migration", "sql-schema-change", _s(SQL, PY, CS, JS, TS, JAVA, GO),
         r"\bCREATE\s+TABLE\s+(?!IF\s+NOT\s+EXISTS)|\bALTER\s+TABLE\b|\bADD\s+COLUMN\b", 2, I),
    Rule("cold-start-migration", "migration-marker", ALL, r"\bmigrat(?:e|ion|ions)\b|\bschema_version\b|\buser_version\b", 1, I),
)

MAX_HITS_PER_FILE_SIGNAL = 5
MAX_SAMPLE_HITS = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _posix(path: str) -> str:
    return path.replace("\\", "/")


def normalize_rel_path(rel_path: str) -> str:
    p = _posix(rel_path.strip())
    while p.startswith("./"):
        p = p[2:]
    while "//" in p:
        p = p.replace("//", "/")
    return p


def finding_hash(cluster: str, rel_path: str, symbol: str, probe_id: str) -> str:
    key = "{}|{}|{}|{}".format(cluster.strip().lower(), normalize_rel_path(rel_path),
                               symbol.strip(), probe_id.strip().lower())
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


def stack_for(path: str) -> Optional[str]:
    return EXT_STACK.get(os.path.splitext(path)[1].lower())


def _is_skipped_rel(rel: str) -> bool:
    return any(_skip_dir(part) for part in rel.split("/")[:-1])


def _is_text_candidate(abs_path: str) -> bool:
    ext = os.path.splitext(abs_path)[1].lower()
    if ext in BINARY_EXTS or os.path.basename(abs_path).lower() in BINARY_EXTS:
        return False
    try:
        if os.path.getsize(abs_path) > MAX_FILE_BYTES:
            return False
        with open(abs_path, "rb") as fh:
            return b"\x00" not in fh.read(8192)
    except OSError:
        return False


def _git(repo: str, *args: str) -> Optional[str]:
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env.setdefault("LC_ALL", "C")
    try:
        proc = subprocess.run(["git", "-c", "core.quotepath=false", "-C", repo] + list(args),
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
    except (OSError, ValueError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", errors="replace")


def _walk(root: str, rel_base: str, limit: int) -> Tuple[List[str], bool]:
    """Walk `root` (abs), returning repo-relative POSIX paths (sorted, capped)."""
    out: List[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not _skip_dir(d))
        for name in sorted(filenames):
            abs_path = os.path.join(dirpath, name)
            if not _is_text_candidate(abs_path):
                continue
            rel = _posix(os.path.relpath(abs_path, rel_base))
            if len(out) >= limit:
                return out, True
            out.append(rel)
    return out, False


def _under(rel: str, prefix: Optional[str]) -> bool:
    if not prefix:
        return True
    return rel == prefix or rel.startswith(prefix.rstrip("/") + "/")


class GitInfo:
    def __init__(self, repo: str) -> None:
        self.repo = repo
        top = _git(repo, "rev-parse", "--show-toplevel")
        self.toplevel = os.path.realpath(top.strip()) if top else None
        head = _git(repo, "rev-parse", "--short", "HEAD") if self.toplevel else None
        self.head = head.strip() if head else None

    @property
    def ok(self) -> bool:
        return self.toplevel is not None

    def _to_repo_rel(self, top_rel: str) -> Optional[str]:
        assert self.toplevel is not None
        abs_path = os.path.join(self.toplevel, top_rel)
        rel = _posix(os.path.relpath(abs_path, self.repo))
        if rel.startswith("../") or rel == "..":
            return None
        return rel

    def working_diff(self) -> List[str]:
        out = _git(self.repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
        if not out:
            return []
        entries = out.split("\0")
        files: List[str] = []
        i = 0
        while i < len(entries):
            entry = entries[i]
            i += 1
            if len(entry) < 4:
                continue
            status, path = entry[:2], entry[3:]
            if status[0] in "RC":
                i += 1  # skip the original path that follows a rename/copy
            rel = self._to_repo_rel(path)
            if rel is not None:
                files.append(rel)
        return files

    def merge_base_diff(self) -> Tuple[List[str], Optional[str]]:
        for base in ("main", "master", "origin/main", "origin/master"):
            if _git(self.repo, "rev-parse", "--verify", "--quiet", base + "^{commit}") is None:
                continue
            mb = _git(self.repo, "merge-base", "HEAD", base)
            if not mb:
                continue
            out = _git(self.repo, "diff", "--name-only", "-z", "--no-renames", mb.strip(), "HEAD")
            files = [r for r in (self._to_repo_rel(p) for p in (out or "").split("\0") if p) if r]
            if files:
                return files, base
        return [], None

    def ls_files(self) -> Optional[List[str]]:
        """Tracked + untracked-but-not-ignored files (repo-relative POSIX), or None on failure.

        Paths are relative to `self.repo` (git prints them relative to the -C directory).
        Deleted-but-still-cached entries are returned too; callers filter with isfile().
        Callers scope to --path with _under(), so one listing serves targeting and
        engine detection alike.
        """
        if not self.ok:
            return None
        out = _git(self.repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
        if out is None:
            return None
        return sorted({_posix(p) for p in out.split("\0") if p})


def _filter_existing(repo: str, rels: Sequence[str], prefix: Optional[str], limit: int) -> Tuple[List[str], bool]:
    seen = set()
    out: List[str] = []
    for rel in sorted(set(rels)):
        if rel in seen or not _under(rel, prefix) or _is_skipped_rel(rel):
            continue
        seen.add(rel)
        abs_path = os.path.join(repo, rel)
        if not os.path.isfile(abs_path) or not _is_text_candidate(abs_path):
            continue
        if len(out) >= limit:
            return out, True
        out.append(rel)
    return out, False


def _has_marker(repo: str, marker: str) -> bool:
    """`marker` at the repo root or one directory level down."""
    if os.path.isfile(os.path.join(repo, marker)):
        return True
    try:
        return any(not _skip_dir(c) and os.path.isfile(os.path.join(repo, c, marker)) for c in os.listdir(repo))
    except OSError:
        return False


def _listed_marker(listed: Sequence[str], marker: str) -> bool:
    """`marker` at the repo root or one directory level down, among git-listed files."""
    for rel in listed:
        if rel == marker:
            return True
        head, sep, rest = rel.partition("/")
        if sep and rest == marker and not _skip_dir(head):
            return True
    return False


def _detect_engines(repo: str, target_files: Sequence[str],
                    listed: Optional[Sequence[str]] = None) -> Tuple[bool, bool]:
    """Return (unity, godot). Either one makes the project a heavy build.

    `listed` (git ls-files, ignore-aware) replaces the filesystem walk when given, so
    gitignored build/vendor dirs cannot trigger a false engine detection.
    """
    if listed is not None:
        godot = _listed_marker(listed, GODOT_MARKER) or any(f.rsplit("/", 1)[-1] == GODOT_MARKER for f in target_files)
        unity = _listed_marker(listed, UNITY_MARKER) or any(f.lower().endswith(".unity") for f in target_files)
        if unity or godot:
            return unity, godot
        for rel in listed:
            if _is_skipped_rel(rel):
                continue
            name = rel.rsplit("/", 1)[-1]
            if name.lower().endswith(".unity"):
                unity = True
            elif name == GODOT_MARKER:
                godot = True
            if unity and godot:
                break
        return unity, godot
    godot = _has_marker(repo, GODOT_MARKER) or any(f.rsplit("/", 1)[-1] == GODOT_MARKER for f in target_files)
    unity = _has_marker(repo, UNITY_MARKER) or any(f.lower().endswith(".unity") for f in target_files)
    if unity or godot:
        return unity, godot
    budget = 5000
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = [d for d in dirnames if not _skip_dir(d)]
        for name in filenames:
            if name.lower().endswith(".unity"):
                unity = True
            elif name == GODOT_MARKER:
                godot = True
        if unity or godot:
            return unity, godot
        budget -= len(filenames) + 1
        if budget <= 0:
            break
    return unity, godot


def _detect_heavy_build(repo: str, target_files: Sequence[str]) -> bool:
    return any(_detect_engines(repo, target_files))


def _detect_stacks(repo: str, target_files: Sequence[str], heavy: bool,
                   engines: Optional[Tuple[bool, bool]] = None) -> List[str]:
    stacks = {s for s in (stack_for(f) for f in target_files) if s}
    try:
        names = os.listdir(repo)
    except OSError:
        names = []
    for name in names:
        if name in ROOT_MARKERS:
            stacks.add(ROOT_MARKERS[name])
        low = name.lower()
        if low.endswith((".csproj", ".sln")):
            stacks.add(CS)
    unity, godot = engines if engines is not None else (heavy, False)
    if godot:
        stacks.add("godot")
        stacks.add(GD)
    if unity:
        stacks.add("unity")
        stacks.add(CS)
    return sorted(stacks)


def _path_targets_tests(repo_abs: str, prefix: Optional[str]) -> bool:
    """An explicit --path into a test dir (or at a single test file) opts tests in."""
    if not prefix:
        return False
    if any(p.lower() in TEST_DIRS for p in prefix.split("/")):
        return True
    return os.path.isfile(os.path.join(repo_abs, prefix)) and is_test_path(prefix)


def _call_args(text: str, open_idx: int, limit: int = 600) -> str:
    depth = 0
    end = min(len(text), open_idx + limit)
    for j in range(open_idx, end):
        ch = text[j]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1:j]
    return text[open_idx + 1:end]


def scan_file(rel: str, text: str) -> List[Tuple[Rule, int]]:
    stack = stack_for(rel)
    if stack is None:
        return []
    lines = text.splitlines()
    line_starts = [0]
    for m in re.finditer(r"\n", text):
        line_starts.append(m.end())
    prefixes = COMMENT_PREFIXES.get(stack, ())
    hits: List[Tuple[Rule, int]] = []
    for rule in RULES:
        if rule.stacks is not None and stack not in rule.stacks:
            continue
        count = 0
        seen_lines = set()
        for m in rule.rx.finditer(text):
            lineno = bisect.bisect_right(line_starts, m.start())
            if lineno in seen_lines:
                continue
            line = lines[lineno - 1] if lineno - 1 < len(lines) else ""
            stripped = line.lstrip()
            if prefixes and stripped.startswith(prefixes):
                continue
            if rule.line_exclude and rule.line_exclude.search(line):
                continue
            if rule.args_exclude or rule.args_require:
                paren = text.rfind("(", m.start(), m.end())
                args = _call_args(text, paren) if paren >= 0 else ""
                if rule.args_exclude and rule.args_exclude.search(args):
                    continue
                if rule.args_require and not rule.args_require.search(args):
                    continue
            seen_lines.add(lineno)
            hits.append((rule, lineno))
            count += 1
            if count >= MAX_HITS_PER_FILE_SIGNAL:
                break
    return hits


def _read_text(abs_path: str) -> Optional[str]:
    try:
        with open(abs_path, "rb") as fh:
            data = fh.read(MAX_FILE_BYTES + 1)
    except OSError:
        return None
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    elif data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    return data.decode("utf-8", errors="replace")


def profile(repo: str, scope: str = "auto", path: Optional[str] = None, max_files: int = 200,
            include_tests: bool = False) -> Dict[str, object]:
    repo_abs = os.path.realpath(repo)
    if not os.path.isdir(repo_abs):
        raise SystemExit("error: --repo is not a directory: {}".format(repo))
    prefix: Optional[str] = None
    if path:
        p_abs = os.path.realpath(os.path.join(repo_abs, path))
        prefix = _posix(os.path.relpath(p_abs, repo_abs))
        if prefix == ".." or prefix.startswith("../"):
            raise SystemExit("error: --path must stay inside --repo: {}".format(path))
        if not os.path.exists(p_abs):
            raise SystemExit("error: --path does not exist: {}".format(path))
        if prefix == ".":
            prefix = None
    if scope == "path" and not path:
        raise SystemExit("error: --scope path requires --path")

    git = GitInfo(repo_abs)
    target: List[str] = []
    truncated = False
    scope_used = "clean-needs-target"
    base_ref: Optional[str] = None

    listed = git.ls_files() if git.ok else None

    def walk_path() -> Tuple[List[str], bool]:
        if prefix and os.path.isfile(os.path.join(repo_abs, prefix)):
            # Explicit single file: audit it even if gitignored or untracked.
            return _filter_existing(repo_abs, [prefix], None, max_files)
        if listed is not None:
            # Ignore-aware listing; _filter_existing drops deleted-but-cached, skipped,
            # oversized and binary files, then sorts and caps.
            return _filter_existing(repo_abs, listed, prefix, max_files)
        return _walk(os.path.join(repo_abs, prefix) if prefix else repo_abs, repo_abs, max_files)

    if scope == "repo":
        target, truncated = walk_path()
        scope_used = "repo"
    elif scope == "path" or (scope == "auto" and path):
        target, truncated = walk_path()
        scope_used = "path"
    else:
        if git.ok and scope in ("auto", "diff"):
            target, truncated = _filter_existing(repo_abs, git.working_diff(), prefix, max_files)
            if target:
                scope_used = "working-diff"
        if not target and git.ok and git.head and scope in ("auto", "merge-base"):
            files, base_ref = git.merge_base_diff()
            target, truncated = _filter_existing(repo_abs, files, prefix, max_files)
            if target:
                scope_used = "merge-base"
            else:
                base_ref = None

    engines = _detect_engines(repo_abs, target, listed)
    heavy = any(engines)
    stacks = _detect_stacks(repo_abs, target, heavy, engines)
    tests_excluded = not (include_tests or _path_targets_tests(repo_abs, prefix))
    test_files = frozenset(f for f in target if is_test_path(f))

    per_cluster: Dict[str, Dict[str, object]] = {
        cid: {"score": 0, "files": set(), "hits": []} for cid in CLUSTER_IDS
    }
    for rel in target:
        if tests_excluded and rel in test_files:
            continue
        text = _read_text(os.path.join(repo_abs, rel))
        if text is None:
            continue
        for rule, lineno in scan_file(rel, text):
            bucket = per_cluster[rule.cluster]
            bucket["score"] = int(bucket["score"]) + rule.weight  # type: ignore[arg-type]
            bucket["files"].add(rel)  # type: ignore[union-attr]
            bucket["hits"].append({"file": rel, "line": lineno, "signal": rule.signal})  # type: ignore[union-attr]

    candidates = []
    unmatched = []
    for cid in CLUSTER_IDS:
        b = per_cluster[cid]
        if not b["score"]:
            unmatched.append(cid)
            continue
        hits = b["hits"]  # type: ignore[assignment]
        # Prefer diverse samples: first hit of each distinct (file, signal), then the rest.
        samples, seen = [], set()
        for h in hits:  # type: ignore[union-attr]
            key = (h["file"], h["signal"])
            if key not in seen:
                seen.add(key)
                samples.append(h)
        for h in hits:  # type: ignore[union-attr]
            if len(samples) >= MAX_SAMPLE_HITS:
                break
            if h not in samples:
                samples.append(h)
        candidates.append({
            "id": cid,
            "card_path": "references/clusters/" + CLUSTER_CARDS[cid],
            "score": b["score"],
            "matched_files": sorted(b["files"]),  # type: ignore[arg-type]
            "sample_hits": samples[:MAX_SAMPLE_HITS],
        })
    candidates.sort(key=lambda c: (-int(c["score"]), CLUSTER_IDS.index(str(c["id"]))))

    result: Dict[str, object] = {
        "repo": _posix(repo_abs),
        "revision": git.head or "working-tree",
        "scope_requested": scope,
        "scope_used": scope_used,
        "detected_stacks": stacks,
        "heavy_build": heavy,
        "target_file_count": len(target),
        "target_files": target,
        "tests_excluded": tests_excluded,
        "test_file_count": len(test_files),
        "candidate_clusters": candidates,
        "unmatched_clusters": unmatched,
    }
    if truncated:
        result["truncated_at_max_files"] = max_files
    if base_ref:
        result["merge_base_ref"] = base_ref
    if path:
        result["path_filter"] = prefix or "."
    return result


def _emit(text: str) -> None:
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")
    sys.stdout.buffer.flush()


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Sprezzatura deterministic surface profiler / finding hasher (stdlib only).")
    ap.add_argument("--repo", default=".", help="target repository root (default: .)")
    ap.add_argument("--scope", default="auto", choices=("auto", "diff", "merge-base", "path", "repo"))
    ap.add_argument("--path", default=None, help="subpath (relative to --repo) to audit")
    ap.add_argument("--max-files", type=int, default=200)
    ap.add_argument("--include-tests", action="store_true",
                    help="also score test files (default: listed but not scored, unless --path targets tests)")
    ap.add_argument("--hash", nargs=4, metavar=("CLUSTER", "REL_PATH", "SYMBOL", "PROBE_ID"),
                    help="print the stable 10-char finding fingerprint and exit")
    args = ap.parse_args(argv)

    if args.hash:
        _emit(finding_hash(*args.hash))
        return 0
    if args.max_files < 1:
        ap.error("--max-files must be >= 1")
    result = profile(args.repo, args.scope, args.path, args.max_files, args.include_tests)
    _emit(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
