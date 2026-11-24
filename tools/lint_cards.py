#!/usr/bin/env python3
"""Sprezzatura cluster-card anti-bloat linter (Python 3.9+ stdlib only).

Usage:
    python tools/lint_cards.py [--clusters-dir DIR] [--skip-sync-check]

Checks every *.md card in the clusters dir:
  * YAML frontmatter with `id` (kebab-case, unique), `name`, `category`
  * <= 45 total lines, <= 250 body words (frontmatter excluded)
  * exactly the 5 required H2 sections, each once
  * Per-Stack Applicability holds both "Applies:" and "Ignore/Safe:"
  * Seed Probes holds 3-5 sequentially numbered items
  * (default dir only) card ids == fingerprint.py CLUSTER_IDS
Exit 0 when every card passes, 1 otherwise.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CLUSTERS_DIR = os.path.join(REPO_ROOT, "skill", "sprezzatura", "references", "clusters")
FINGERPRINT_PY = os.path.join(REPO_ROOT, "skill", "sprezzatura", "scripts", "fingerprint.py")

MAX_LINES = 45
MAX_WORDS = 250
MIN_PROBES, MAX_PROBES = 3, 5
REQUIRED_KEYS = ("id", "name", "category")
REQUIRED_HEADINGS = (
    "Hostile World-State",
    "Per-Stack Applicability",
    "Seed Probes",
    "Retire / Disproof Rule",
    "Real Incident Anchor",
)
KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FM_LINE = re.compile(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$")
PROBE_LINE = re.compile(r"^\s*(\d+)\.\s+\S")
WORD_CHAR = re.compile(r"[^\W_]", re.UNICODE)


def parse_frontmatter(lines: List[str]) -> Tuple[Optional[Dict[str, str]], int, List[str]]:
    """Return (fields, body_start_index, errors)."""
    errors: List[str] = []
    if not lines or lines[0].strip() != "---":
        return None, 0, ["missing YAML frontmatter (first line must be '---')"]
    fields: Dict[str, str] = {}
    for i in range(1, len(lines)):
        raw = lines[i]
        if raw.strip() == "---":
            return fields, i + 1, errors
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m = FM_LINE.match(raw)
        if not m:
            errors.append("frontmatter line {} is not 'key: value': {!r}".format(i + 1, raw))
            continue
        key, value = m.group(1), m.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if key in fields:
            errors.append("duplicate frontmatter key '{}'".format(key))
        fields[key] = value
    return None, 0, ["unterminated YAML frontmatter (no closing '---')"]


def split_sections(body: List[str]) -> Tuple[Dict[str, List[str]], List[str]]:
    sections: Dict[str, List[str]] = {}
    order: List[str] = []
    current: Optional[str] = None
    for line in body:
        if line.startswith("## "):
            current = line[3:].strip()
            order.append(current)
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)
    return sections, order


def lint_card(path: str) -> Tuple[Optional[str], List[str]]:
    errors: List[str] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        return None, ["cannot read as UTF-8: {}".format(exc)]
    if text.startswith("﻿"):
        text = text[1:]
    lines = text.splitlines()

    if len(lines) > MAX_LINES:
        errors.append("{} lines > {} line limit".format(len(lines), MAX_LINES))

    fields, body_start, fm_errors = parse_frontmatter(lines)
    errors.extend(fm_errors)
    card_id: Optional[str] = None
    if fields is not None:
        for key in REQUIRED_KEYS:
            if not fields.get(key):
                errors.append("frontmatter missing required key '{}'".format(key))
        card_id = fields.get("id") or None
        if card_id and not KEBAB.match(card_id):
            errors.append("id '{}' is not kebab-case".format(card_id))

    body = lines[body_start:]
    # A "word" is a whitespace-delimited token holding at least one letter/digit,
    # so bare markdown markers (`##`, `-`, `->`, `|`) do not count.
    words = sum(1 for tok in " ".join(body).split() if WORD_CHAR.search(tok))
    if words > MAX_WORDS:
        errors.append("{} body words > {} word limit".format(words, MAX_WORDS))

    sections, order = split_sections(body)
    for heading in REQUIRED_HEADINGS:
        n = order.count(heading)
        if n == 0:
            errors.append("missing required heading '## {}'".format(heading))
        elif n > 1:
            errors.append("heading '## {}' appears {} times".format(heading, n))
    for heading in order:
        if heading not in REQUIRED_HEADINGS:
            errors.append("unexpected H2 heading '## {}' (exactly 5 required sections allowed)".format(heading))

    psa = "\n".join(sections.get("Per-Stack Applicability", []))
    if "Per-Stack Applicability" in sections:
        for marker in ("Applies:", "Ignore/Safe:"):
            if marker not in psa:
                errors.append("'## Per-Stack Applicability' lacks '{}'".format(marker))

    if "Seed Probes" in sections:
        nums = [int(m.group(1)) for m in (PROBE_LINE.match(l) for l in sections["Seed Probes"]) if m]
        if not MIN_PROBES <= len(nums) <= MAX_PROBES:
            errors.append("'## Seed Probes' has {} numbered probes (need {}-{})".format(len(nums), MIN_PROBES, MAX_PROBES))
        elif nums != list(range(1, len(nums) + 1)):
            errors.append("'## Seed Probes' numbering is not sequential 1..{}: {}".format(len(nums), nums))

    return card_id, errors


def load_cluster_ids() -> Optional[Tuple[str, ...]]:
    spec = importlib.util.spec_from_file_location("sprezzatura_fingerprint", FINGERPRINT_PY)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return tuple(getattr(module, "CLUSTER_IDS", ()))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Lint Sprezzatura cluster cards.")
    ap.add_argument("--clusters-dir", default=None, help="cards dir (default: skill/sprezzatura/references/clusters)")
    ap.add_argument("--skip-sync-check", action="store_true", help="skip CLUSTER_IDS parity check against fingerprint.py")
    args = ap.parse_args(argv)

    clusters_dir = os.path.abspath(args.clusters_dir or DEFAULT_CLUSTERS_DIR)
    is_default = os.path.normcase(os.path.realpath(clusters_dir)) == os.path.normcase(os.path.realpath(DEFAULT_CLUSTERS_DIR))
    if not os.path.isdir(clusters_dir):
        print("FAIL: clusters dir not found: {}".format(clusters_dir))
        return 1

    cards = sorted(f for f in os.listdir(clusters_dir) if f.lower().endswith(".md"))
    if not cards:
        print("FAIL: no *.md cards in {}".format(clusters_dir))
        return 1

    failures = 0
    ids: Dict[str, str] = {}
    for name in cards:
        card_id, errors = lint_card(os.path.join(clusters_dir, name))
        if card_id:
            if card_id in ids:
                errors.append("duplicate id '{}' (also in {})".format(card_id, ids[card_id]))
            else:
                ids[card_id] = name
        if errors:
            failures += 1
            print("FAIL {}".format(name))
            for err in errors:
                print("  - {}".format(err))
        else:
            print("ok   {} ({})".format(name, card_id))

    sync_errors: List[str] = []
    if is_default and not args.skip_sync_check:
        try:
            cluster_ids = load_cluster_ids()
        except Exception as exc:  # noqa: BLE001 - report any import failure
            cluster_ids = None
            sync_errors.append("cannot import fingerprint.py CLUSTER_IDS: {}".format(exc))
        if cluster_ids is not None:
            missing = sorted(set(cluster_ids) - set(ids))
            extra = sorted(set(ids) - set(cluster_ids))
            if missing:
                sync_errors.append("CLUSTER_IDS without a card: {}".format(", ".join(missing)))
            if extra:
                sync_errors.append("cards missing from fingerprint.py CLUSTER_IDS: {}".format(", ".join(extra)))
        elif not sync_errors:
            sync_errors.append("fingerprint.py not loadable: {}".format(FINGERPRINT_PY))
    for err in sync_errors:
        print("FAIL sync: {}".format(err))

    total_fail = failures + (1 if sync_errors else 0)
    if total_fail:
        print("\n{} of {} card(s) failed{}.".format(failures, len(cards), "; id sync failed" if sync_errors else ""))
        return 1
    print("\nAll {} cards pass{}.".format(len(cards), " (CLUSTER_IDS in sync)" if is_default and not args.skip_sync_check else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
