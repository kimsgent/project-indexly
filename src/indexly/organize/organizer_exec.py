from pathlib import Path
from datetime import datetime
import shutil
import hashlib
import json
import sys
import time

from .organizer import organize_folder
from .lister import list_organizer_log

def _hash_file(path: Path, algo="sha256"):
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def _write_log_atomic(log: dict, log_dir: Path, root_name: str):
    log_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    tmp_path = log_dir / f".tmp_{root_name}.json"
    final_path = log_dir / f"organized_{date_str}_{root_name}.json"

    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)

    tmp_path.replace(final_path)
    return final_path

def execute_organizer(
    root: Path,
    sort_by: str = "date",
    executed_by: str = "kims",
    backup_root: Path | None = None,
    log_dir: Path | None = None,
    *,
    lister: bool = False,
    lister_ext: str | None = None,
    lister_category: str | None = None,
    lister_date: str | None = None,
    lister_duplicates: bool = False,
):
    """Execute organizer: move/copy files, detect duplicates, write log with feedback"""

    root = Path(root).resolve()
    log_dir = log_dir or (root / "log")
    root_name = root.name

    print(f"📂 Building organization plan for {root}...")
    plan = organize_folder(root, sort_by=sort_by, executed_by=executed_by)
    total_files = len(plan["files"])
    print(f"✅ Plan ready: {total_files} files to organize.\n")

    backup_mapping = {}
    if backup_root:
        backup_root.mkdir(parents=True, exist_ok=True)

    max_name_len = max(len(Path(f["new_path"]).name) for f in plan["files"])

    for idx, f in enumerate(plan["files"], 1):
        src = Path(f["original_path"])
        dst = Path(f["new_path"])
        dst.parent.mkdir(parents=True, exist_ok=True)

        src_hash = _hash_file(src)
        if dst.exists():
            dst_hash = _hash_file(dst)
            f["unchanged"] = src_hash == dst_hash
        else:
            f["unchanged"] = False

        shutil.move(src, dst)

        if backup_root and not f.get("unchanged"):
            bkp_path = backup_root / dst.relative_to(root)
            bkp_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, bkp_path)
            backup_mapping[str(dst)] = str(bkp_path)

        sys.stdout.write(
            f"\rProcessing file {idx}/{total_files}: "
            f"{Path(f['new_path']).name.ljust(max_name_len)}"
        )
        sys.stdout.flush()

        time.sleep(0.01)

    print("\n📄 Writing log...")
    log_path = _write_log_atomic(plan, log_dir, root_name)

    # ✅ KEEP summary exactly as-is
    summary = plan.get("summary", {})
    print("\n📊 Summary of organization:")
    print(f"  Total files processed: {summary.get('total_files', total_files)}")
    print(f"  Documents: {summary.get('documents', 0)}")
    print(f"  Pictures: {summary.get('pictures', 0)}")
    print(f"  Videos: {summary.get('videos', 0)}")
    print(f"  Duplicates: {summary.get('duplicates', 0)}")
    print(f"✅ Organizer completed. Log saved to {log_path}")
    if backup_root:
        print(f"📦 Backup saved at {backup_root}")

    # ✅ OPTIONAL lister hook (no side effects)
    if lister:
        print("\n📂 Listing organizer results:\n")
        list_organizer_log(
            log_path,
            ext=lister_ext,
            category=lister_category,
            date=lister_date,
            duplicates_only=lister_duplicates,
        )

    return plan, backup_mapping

