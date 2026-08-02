from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_REPO = "https://github.com/xiaolai/cc-suite.git"
UPSTREAM_WEB = "https://github.com/xiaolai/cc-suite"
STABLE_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def load_config() -> dict:
    import tomllib
    return tomllib.loads((ROOT / "adapter.toml").read_text(encoding="utf-8"))


def parse_ls_remote(text: str) -> dict[str, dict[str, str]]:
    tags: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        sha, ref = line.split("\t", 1)
        prefix = "refs/tags/"
        if not ref.startswith(prefix):
            continue
        name = ref[len(prefix):]
        peeled = name.endswith("^{}")
        if peeled:
            name = name[:-3]
        if not STABLE_RE.fullmatch(name):
            continue
        entry = tags.setdefault(name, {})
        entry["commit" if peeled else "tag_object"] = sha
    for entry in tags.values():
        entry.setdefault("commit", entry.get("tag_object", ""))
    return tags


def latest_stable(tags: dict[str, dict[str, str]]) -> tuple[str, dict[str, str]]:
    if not tags:
        raise ValueError("no stable release tags found")
    tag = max(tags, key=lambda x: tuple(map(int, STABLE_RE.fullmatch(x).groups())))
    return tag, tags[tag]


def query_tags() -> dict[str, dict[str, str]]:
    result = subprocess.run(
        ["git", "ls-remote", "--tags", UPSTREAM_REPO],
        check=True, text=True, capture_output=True, timeout=60,
    )
    return parse_ls_remote(result.stdout)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(p for p in path.rglob("*") if p.is_file()):
        rel = item.relative_to(path).as_posix().encode()
        digest.update(len(rel).to_bytes(4, "big"))
        digest.update(rel)
        digest.update(item.read_bytes())
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def download_archive(tag: str, destination: Path) -> None:
    url = f"{UPSTREAM_WEB}/archive/refs/tags/{tag}.tar.gz"
    request = urllib.request.Request(url, headers={"User-Agent": "cc-suite-codex-adapter/1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        destination.write_bytes(response.read())


def extract_archive(archive: Path, tag: str, destination: Path) -> Path:
    version = tag.removeprefix("v")
    expected_root = f"cc-suite-{version}"
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            parts = Path(member.name).parts
            if not parts or parts[0] != expected_root or ".." in parts or member.issym() or member.islnk():
                raise ValueError(f"unsafe or unexpected archive member: {member.name}")
        bundle.extractall(destination, filter="data")
    source = destination / expected_root
    if not source.is_dir():
        raise ValueError(f"archive root {expected_root} is missing")
    return source


def adapter_version(tag: str, revision: int) -> str:
    return f"{tag.removeprefix('v')}+adapter.{revision}"

