"""Build docs/knowledge-base/.manifest.json for KB input files.

The manifest tracks repo-side knowledge-base input artifacts so skills can
detect when staged markdown inputs changed, without depending on ignored local
source documents.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_SCAN_DIRS = [
    "docs/knowledge-base/.staging",
    "docs/knowledge-base/.staging-binary-md",
    "docs/knowledge-base/.manual-rules",
    "docs/knowledge-base/.wiki-ingest-src",
    "docs/医院材料学习",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def rel_path(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def build_entries(root: Path, scan_dirs: list[Path]) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    source_docs_root = (root / "docs" / "医院材料学习").resolve()
    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for file_path in sorted(p for p in scan_dir.rglob("*") if p.is_file()):
            if source_docs_root in file_path.resolve().parents or file_path.resolve() == source_docs_root:
                if file_path.suffix.lower() != ".md":
                    continue
            stat = file_path.stat()
            entries.append(
                {
                    "path": rel_path(file_path, root),
                    "group": scan_dir.name,
                    "size": stat.st_size,
                    "modified_at": datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ).isoformat(),
                    "hash": sha256_file(file_path),
                }
            )
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description="Update KB manifest")
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root (defaults to current directory)",
    )
    parser.add_argument(
        "--output",
        default="docs/knowledge-base/.manifest.json",
        help="Manifest output path",
    )
    parser.add_argument(
        "--dir",
        action="append",
        dest="dirs",
        default=[],
        help="Additional directory to scan (may be repeated)",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = (root / args.output).resolve()
    scan_dirs = [root / path for path in DEFAULT_SCAN_DIRS]
    scan_dirs.extend((root / path).resolve() for path in args.dirs)

    entries = build_entries(root, scan_dirs)
    manifest = {
        "last_updated": datetime.now(tz=timezone.utc).isoformat(),
        "files": entries,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote manifest with {len(entries)} file(s) to {output}")


if __name__ == "__main__":
    main()
