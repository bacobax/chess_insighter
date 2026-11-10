"""One-off import of the legacy file-based ``.cache/`` state into MongoDB Atlas.

Idempotent: every record is upserted by its id/key, so it is safe to re-run.
The ``.cache/`` directory is only read, never modified or deleted.

    uv run python migrate_cache_to_mongo.py            # import everything
    uv run python migrate_cache_to_mongo.py --dry-run  # only count what would be imported

Not migrated (they are offline build artifacts, not app state): ``.cache/opening_popularity*``
checkpoints written by ``build_opening_popularity.py``, and the scratch ``report_configs/`` YAMLs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.services.cache_service import PLAYER_VECTORS_NAMESPACE, REPORTS_NAMESPACE
from backend.services.mongo_service import BLOBS, blob_put, get_database
from backend.services.report_analysis_service import REPORT_ANALYSIS_NAMESPACE, TRAINING_ANALYSIS_NAMESPACE
from backend.services.training_plan_service import TRAINING_PLANS_NAMESPACE


ROOT = Path(__file__).resolve().parent / ".cache"
APP_COLLECTIONS = ("users", "email_verifications", "sessions", "target_players", "reports", "audit_events")


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def migrate_app_db(dry_run: bool) -> dict[str, int]:
    path = ROOT / "app_db.json"
    counts: dict[str, int] = {}
    if not path.exists():
        return counts
    data = _read(path)
    db = None if dry_run else get_database()
    for name in APP_COLLECTIONS:
        records = data.get(name) or []
        counts[name] = len(records)
        if db is None:
            continue
        for record in records:
            db[name].replace_one({"_id": record["id"]}, {"_id": record["id"], **record}, upsert=True)
    return counts


def migrate_reports(dry_run: bool) -> int:
    files = sorted((ROOT / "reports").glob("*.json"))
    for path in files:
        if not dry_run:
            blob_put(REPORTS_NAMESPACE, path.stem, _read(path))
    return len(files)


def migrate_player_vectors(dry_run: bool) -> int:
    path = ROOT / "player_vectors.json"
    if not path.exists():
        return 0
    entries = _read(path)
    for key_id, entry in entries.items():
        if not dry_run:
            username = str((entry.get("cache_key") or {}).get("username") or "").strip().lower()
            blob_put(PLAYER_VECTORS_NAMESPACE, key_id, entry, username=username)
    return len(entries)


def migrate_analysis_tree(directory: str, namespace: str, dry_run: bool) -> int:
    root = ROOT / directory
    files = sorted(path for path in root.rglob("*.json") if not path.name.startswith(".")) if root.exists() else []
    for path in files:
        if not dry_run:
            blob_put(namespace, path.relative_to(root).as_posix(), _read(path))
    return len(files)


def migrate_training_plans(dry_run: bool) -> int:
    root = ROOT / "training_plans"
    files = sorted(root.glob("*/*.json")) if root.exists() else []
    for path in files:
        if not dry_run:
            plan = _read(path)
            key = f"{path.parent.name}/{path.stem}"
            blob_put(
                TRAINING_PLANS_NAMESPACE,
                key,
                plan,
                username_key=str(plan.get("username") or "").strip().lower(),
            )
    return len(files)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Count source records without writing.")
    args = parser.parse_args()

    summary = {
        "app_db": migrate_app_db(args.dry_run),
        REPORTS_NAMESPACE: migrate_reports(args.dry_run),
        PLAYER_VECTORS_NAMESPACE: migrate_player_vectors(args.dry_run),
        REPORT_ANALYSIS_NAMESPACE: migrate_analysis_tree("report_analysis", REPORT_ANALYSIS_NAMESPACE, args.dry_run),
        TRAINING_ANALYSIS_NAMESPACE: migrate_analysis_tree("training_analysis", TRAINING_ANALYSIS_NAMESPACE, args.dry_run),
        TRAINING_PLANS_NAMESPACE: migrate_training_plans(args.dry_run),
    }
    print(("Would import" if args.dry_run else "Imported") + " from .cache/:")
    print(json.dumps(summary, indent=2))

    if not args.dry_run:
        db = get_database()
        stored = {name: db[name].count_documents({}) for name in APP_COLLECTIONS}
        for namespace in summary:
            if namespace != "app_db":
                stored[f"blob:{namespace}"] = db[BLOBS].count_documents({"namespace": namespace})
        print("Now in MongoDB:")
        print(json.dumps(stored, indent=2))


if __name__ == "__main__":
    main()
