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
UPSTREAM_REF = "refs/heads/main"
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def load_config() -> dict:
    import tomllib
    return tomllib.loads((ROOT / "adapter.toml").read_text(encoding="utf-8"))


def parse_head(text: str, ref: str = UPSTREAM_REF) -> str:
    for line in text.splitlines():
        if not line.strip():
            continue
        sha, found_ref = line.split("\t", 1)
        if found_ref == ref and SHA_RE.fullmatch(sha):
            return sha
    raise ValueError(f"upstream ref is missing or invalid: {ref}")


def package_version(text: str) -> str:
    payload = json.loads(text)
    if payload.get("name") != "cc-suite":
        raise ValueError("upstream package.json has an unexpected package name")
    version = payload.get("version")
    if not isinstance(version, str) or not SEMVER_RE.fullmatch(version):
        raise ValueError("upstream package.json has an invalid semantic version")
    return version


def package_release(commit: str, text: str, ref: str = UPSTREAM_REF) -> dict[str, str]:
    if not SHA_RE.fullmatch(commit):
        raise ValueError("upstream commit must be a full SHA")
    return {"commit": commit, "ref": ref, "version": package_version(text)}


def query_head() -> str:
    result = subprocess.run(
        ["git", "ls-remote", UPSTREAM_REPO, UPSTREAM_REF],
        check=True, text=True, capture_output=True, timeout=60,
    )
    return parse_head(result.stdout)


def fetch_upstream_file(commit: str, path: str) -> str:
    if not SHA_RE.fullmatch(commit):
        raise ValueError("upstream commit must be a full SHA")
    url = f"https://raw.githubusercontent.com/xiaolai/cc-suite/{commit}/{path}"
    request = urllib.request.Request(url, headers={"User-Agent": "cc-suite-codex-adapter/1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8")


def query_package_release() -> dict[str, str]:
    commit = query_head()
    return package_release(commit, fetch_upstream_file(commit, "package.json"))


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


def download_archive(commit: str, destination: Path) -> None:
    if not SHA_RE.fullmatch(commit):
        raise ValueError("upstream commit must be a full SHA")
    url = f"{UPSTREAM_WEB}/archive/{commit}.tar.gz"
    request = urllib.request.Request(url, headers={"User-Agent": "cc-suite-codex-adapter/1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        destination.write_bytes(response.read())


def extract_archive(archive: Path, commit: str, destination: Path) -> Path:
    if not SHA_RE.fullmatch(commit):
        raise ValueError("upstream commit must be a full SHA")
    expected_root = f"cc-suite-{commit}"
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


def adapter_version(version: str, revision: int) -> str:
    if not SEMVER_RE.fullmatch(version):
        raise ValueError("upstream version must be valid semantic version")
    release, separator, build = version.partition("+")
    metadata = f"{build}." if separator else ""
    return f"{release}+{metadata}codex.adapter-{revision}"
