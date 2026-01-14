import shutil
import hashlib
import json
import sys
import time
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.tree import Tree
from rich.panel import Panel
from rich.logging import RichHandler
import logging
import hashlib


from .profiles import PROFILE_STRUCTURES, PROFILE_NEXT_STEPS
from .utils import write_organizer_log


from .organizer import organize_folder
from .lister import list_organizer_log

console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(console=console)],
)
log = logging.getLogger("organizer")


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
    executed_by: str = "system",
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


def execute_profile_scaffold(
    root: Path,
    profile: str,
    *,
    apply: bool = False,
    dry_run: bool = False,
    executed_by: str = "system",
):
    root = Path(root).resolve()
    profile = profile.lower()

    if profile not in PROFILE_STRUCTURES:
        raise ValueError(f"Unknown profile: {profile}")

    console.rule(f"[bold cyan]Indexly Organize — Profile: {profile}")

    tree = Tree(f"📁 {root}")
    created = []
    audit_log = {
        "profile": profile,
        "root": str(root),
        "executed_by": executed_by,
        "timestamp": datetime.utcnow().isoformat(),
        "created": [],
    }

    for rel in PROFILE_STRUCTURES[profile]:
        p = root / rel
        tree.add(f"📂 {rel}")
        if apply:
            p.mkdir(parents=True, exist_ok=True)
            created.append(str(p))
            audit_log["created"].append(str(p))

    console.print(tree)

    if dry_run:
        console.print(
            Panel.fit(
                "Dry-run only. No directories were created.",
                title="Mode",
                style="yellow",
            )
        )
        return

    if apply:
        console.print(
            Panel.fit(
                f"{len(created)} directories created successfully.",
                title="Status",
                style="green",
            )
        )

        if profile == "health":
            audit_log["audit"] = {
                "hashing": True,
                "strict_logging": True,
            }

        write_organizer_log(
            audit_log,
            root / "log" / f"profile_{profile}_scaffold.json",
        )

    console.print(
        Panel.fit(
            PROFILE_NEXT_STEPS[profile],
            title="Recommended Next Steps",
            style="cyan",
        )
    )
