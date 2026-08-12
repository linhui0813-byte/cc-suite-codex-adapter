#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import tempfile
from pathlib import Path

from _lib import ROOT, UPSTREAM_REF, UPSTREAM_WEB, adapter_version, download_archive, load_config, package_version, query_package_release, sha256_file, write_json
from build_plugin import build
from _lib import extract_archive


def main() -> None:
    parser = argparse.ArgumentParser(description="Pin, fetch, transform, and build cc-suite")
    parser.add_argument("--version")
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--commit")
    parser.add_argument("--synced-at")
    parser.add_argument("--offline-verified", action="store_true", help="accept caller-supplied verified commit, version, and archive")
    args = parser.parse_args()
    explicit = any((args.version, args.commit, args.archive))
    if explicit:
        if not args.offline_verified or not all((args.version, args.commit, args.archive)):
            raise SystemExit("explicit source requires --offline-verified, --version, --commit, and --archive")
        release = {"commit": args.commit, "ref": UPSTREAM_REF, "version": args.version}
    else:
        if args.offline_verified:
            raise SystemExit("--offline-verified requires explicit source arguments")
        release = query_package_release()
    version = release["version"]
    commit = release["commit"]
    config = load_config()
    with tempfile.TemporaryDirectory(prefix="cc-suite-sync-") as temp_name:
        temp = Path(temp_name)
        archive = args.archive or temp / f"cc-suite-{commit}.tar.gz"
        if not args.archive:
            download_archive(commit, archive)
        archive_hash = sha256_file(archive)
        source = extract_archive(archive, commit, temp / "source")
        archived_version = package_version((source / "package.json").read_text(encoding="utf-8"))
        if archived_version != version:
            raise SystemExit(
                f"upstream package version mismatch at {commit}: expected {version}, got {archived_version}"
            )
        license_hash = sha256_file(source / "LICENSE")
        synced_at = args.synced_at or dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        lock = {
            "adapter": {
                "repository": config["adapter_repository"],
                "revision": config["adapter_revision"],
                "runtime_files": config["runtime_files"],
                "selected_skills": config["selected_skills"],
                "sync_time": synced_at,
                "version": adapter_version(version, config["adapter_revision"]),
            },
            "artifact": {"plugin_path": f"plugins/{config['plugin_name']}"},
            "schema_version": 2,
            "upstream": {
                "archive_sha256": archive_hash,
                "archive_url": f"{UPSTREAM_WEB}/archive/{commit}.tar.gz",
                "commit": commit,
                "license_sha256": license_hash,
                "package_path": "package.json",
                "ref": UPSTREAM_REF,
                "repository": UPSTREAM_WEB,
                "version": version,
            },
        }
        write_json(ROOT / "provenance.lock.json", lock)
        lock["artifact"]["tree_sha256"] = build(source, lock)
        write_json(ROOT / "provenance.lock.json", lock)
        print(json.dumps(lock, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
