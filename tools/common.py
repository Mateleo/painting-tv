"""JSON state and file-hash helpers shared by the collection tools (standard library only)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COLLECTIONS = ROOT / "catalog" / "collections.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def state_records(path: Path | None) -> dict[str, Any]:
    """Return the ``records`` of a resumable state file, or nothing when it is absent."""
    return read_json(path).get("records", {}) if path and path.exists() else {}


def write_json(path: Path, value: Any, *, compact: bool = False) -> None:
    """Replace ``path`` atomically so an interrupted run never leaves truncated JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    layout: dict[str, Any] = {"separators": (",", ":")} if compact else {"indent": 2}
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, **layout) + "\n", encoding="utf-8")
    temporary.replace(path)


def enrich_collection_metadata(paintings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Set each painting's ``collection`` label from ``catalog/collections.json``.

    The map is the only source of collection labels, so a painting it omits
    has none. The research behind it stays outside the repository.
    """
    labels = read_json(COLLECTIONS) if COLLECTIONS.exists() else {}
    result = []
    for painting in paintings:
        item = {key: value for key, value in painting.items() if key != "collectionResearch"}
        label = labels.get(str(item.get("id", "")))
        if label:
            item["collection"] = label
        else:
            item.pop("collection", None)
        result.append(item)
    return result


def file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
