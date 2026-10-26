"""The manifest of hand-downloaded files (RBI, NPCI, TRAI and others).

Some sources block scripts, so their files are downloaded by hand and uploaded to the
`raw-inputs` GitHub Release. `data/manifest.yml` records, for each file, where it came from,
when it was downloaded and its SHA-256 fingerprint. Builds refuse files that are missing,
changed or not listed, so every number can be traced to an exact file.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from bharat.ingest.common import sha256_file


class ManifestFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    source: str
    original_url: str
    downloaded_on: date
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    notes: str | None = None


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    files: list[ManifestFile] = Field(default_factory=list)

    def for_source(self, source: str) -> list[ManifestFile]:
        return [f for f in self.files if f.source == source]


def load_manifest(path: Path) -> Manifest:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Manifest.model_validate(data)


def verify_files(manifest: Manifest, folder: Path) -> list[str]:
    """Return problems: listed files that are missing or changed, and files not listed."""
    problems = []
    listed = {f.name for f in manifest.files}
    for entry in manifest.files:
        path = folder / entry.name
        if not path.exists():
            problems.append(f"missing: {entry.name}")
        elif sha256_file(path) != entry.sha256:
            problems.append(f"changed (hash differs from manifest): {entry.name}")
    if folder.exists():
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.name not in listed:
                problems.append(f"not in manifest: {path.name}")
    return problems
