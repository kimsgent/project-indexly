import shutil
import hashlib
import json
import sys
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Iterable

from rich.console import Console
from rich.tree import Tree
from rich.panel import Panel
from rich.logging import RichHandler

from indexly.organize.placement_planner import build_placement_plan
from indexly.organize.profiles import PROFILE_RULES
from indexly.organize.utils import safe_move, write_organizer_log

from .organizer import organize_folder
from .lister import list_organizer_log
from .profile_structures import (
    PROFILE_STRUCTURES,
    PROFILE_NEXT_STEPS,
    build_data_project_structure,
    build_media_shoot_structure,
)
from .log_schema import (
    empty_meta,
    empty_summary,
    file_entry_template,
    empty_organizer_log,
)


console = Console()


logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(console=console)],
)
log = logging.getLogger("organizer")


def _hash_file(path: Path, algo="sha256") -> str | None:
    """Return file hash or None if file cannot be read."""
    h = hashlib.new(algo)
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, FileNotFoundError) as e:
        log.warning(f"⚠️ Cannot hash file (skipped): {path} — {e}")
        return None


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
    dry_run: bool = False,  # ✅ new parameter
):
    """Execute organizer: move/copy files, detect duplicates, write log with feedback"""

    root = Path(root).resolve()
    log_dir = log_dir or (root / "log")
    root_name = root.name

    print(f"📂 Building organization plan for {root}...")
    plan = organize_folder(
        root, sort_by=sort_by, executed_by=executed_by, dry_run=dry_run
    )
    total_files = len(plan["files"])
    print(f"✅ Plan ready: {total_files} files to organize.\n")

    backup_mapping = {}
    if backup_root and not dry_run:
        backup_root.mkdir(parents=True, exist_ok=True)

    max_name_len = max(len(Path(f["new_path"]).name) for f in plan["files"])

    for idx, f in enumerate(plan["files"], 1):
        src = Path(f["original_path"])
        dst = Path(f["new_path"])

        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)

            src_hash = _hash_file(src)
            if src_hash is None:
                continue

            if dst.exists():
                dst_hash = _hash_file(dst)
                f["unchanged"] = src_hash == dst_hash
            else:
                f["unchanged"] = False

            try:
                safe_move(src, dst)
            except (OSError, shutil.Error) as e:
                log.warning(f"⚠️ Cannot move file (skipped): {src} → {dst} — {e}")
                continue

            if backup_root and not f.get("unchanged"):
                bkp_path = backup_root / dst.relative_to(root)
                bkp_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(dst, bkp_path)
                    backup_mapping[str(dst)] = str(bkp_path)
                except (OSError, shutil.Error) as e:
                    log.warning(
                        f"⚠️ Cannot backup file (skipped): {dst} → {bkp_path} — {e}"
                    )

        # Dry-run feedback
        sys.stdout.write(
            f"\rProcessing file {idx}/{total_files}: "
            f"{Path(f['new_path']).name.ljust(max_name_len)}"
        )
        sys.stdout.flush()
        time.sleep(0.01)

    if dry_run:
        print(f"\n📄 Dry-run only: {total_files} files would be organized.")
        return plan, {}

    print("\n📄 Writing log...")
    log_path = _write_log_atomic(plan, log_dir, root_name)

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


# --------------------------------------------------
# SCAFFOLD (FIXED — patient-scoped health only)
# --------------------------------------------------


def execute_profile_scaffold(
    root: Path,
    profile: str,
    *,
    category: str | None = None,
    apply: bool = False,
    dry_run: bool = False,
    executed_by: str = "system",
    project_name: str | None = None,
    shoot_name: str | None = None,
    patient_id: str | None = None,
):
    root = Path(root).resolve()
    profile = profile.lower()

    if profile not in PROFILE_STRUCTURES:
        raise ValueError(f"Unknown profile: {profile}")

    console.rule(f"[bold cyan]Indexly Organize — Profile: {profile}")
    tree = Tree(f"📁 {root}")
    created: list[str] = []

    audit_log = {
        "profile": profile,
        "category": category,
        "root": str(root),
        "executed_by": executed_by,
        "timestamp": datetime.utcnow().isoformat(),
        "created": [],
    }

    # --------------------------------------------------
    # HEALTH (patient-scoped ONLY when --id is present)
    # --------------------------------------------------
    resolved_patient_id = None
    if profile == "health" and patient_id is not None:
        resolved_patient_id = (
            _next_health_patient_id(root)
            if patient_id == "" or patient_id is True
            else patient_id
        )

        patient_root = root / "Health" / "Patients" / resolved_patient_id
        tree.add(f"🆔 Health/Patients/{resolved_patient_id}")

        if apply:
            patient_root.mkdir(parents=True, exist_ok=True)
            created.append(str(patient_root))
            audit_log["created"].append(str(patient_root))

            for folder in [
                "Reports",
                "Imaging",
                "Lab",
                "Admin",
                "Guidelines",
                "Archive",
            ]:
                p = patient_root / folder
                p.mkdir(parents=True, exist_ok=True)
                created.append(str(p))
                audit_log["created"].append(str(p))

            meta_path = patient_root / ".patient.json"
            if not meta_path.exists():
                meta = {
                    "patient_id": resolved_patient_id,
                    "created_at": datetime.utcnow().isoformat(),
                    "created_by": executed_by,
                    "profile": "health",
                    "hashing": True,
                    "strict_logging": True,
                    "version": "1.0",
                }
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)

    # --------------------------------------------------
    # NON-HEALTH or GLOBAL PROFILES
    # --------------------------------------------------
    elif profile != "health":
        struct = PROFILE_STRUCTURES[profile]

        if isinstance(struct, dict):
            resolved_category = category or "default"

            if resolved_category not in struct:
                raise ValueError(
                    f"Invalid category '{resolved_category}' for profile '{profile}'. "
                    f"Available: {', '.join(struct.keys())}"
                )

            paths = list(struct[resolved_category])
        else:
            paths = list(struct)

        if profile == "data" and project_name:
            paths.extend(build_data_project_structure(project_name))

        if profile == "media":
            paths.extend(build_media_shoot_structure(shoot_name))

        for rel in paths:
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
        write_organizer_log(
            audit_log,
            root / "log" / f"profile_{profile}_scaffold.json",
        )

        console.print(
            Panel.fit(
                f"{len(created)} directories created successfully.",
                title="Status",
                style="green",
            )
        )

    next_steps_msg = (
        f"Patient folder scaffolded: {resolved_patient_id}."
        if profile == "health" and resolved_patient_id
        else PROFILE_NEXT_STEPS[profile]
    )

    console.print(
        Panel.fit(
            next_steps_msg,
            title="Recommended Next Steps",
            style="cyan",
        )
    )


# --------------------------------------------------
# PLACEMENT (already aligned, unchanged logic)
# --------------------------------------------------


def execute_profile_placement(
    *,
    source_root: Path,
    destination_root: Path,
    profile: str,
    executed_by: str,
    project_name: str | None = None,
    shoot_name: str | None = None,
    apply: bool = False,
    dry_run: bool = False,
    log_path: Path | None = None,
    patient_id: str | None = None,
    recursive: bool = False,
):
    from indexly.organize.profiles.health_rules import (
        get_destination as health_destination,
    )

    source_root = Path(source_root).resolve()
    destination_root = Path(destination_root).resolve()
    profile = profile.lower()

    if profile not in PROFILE_RULES:
        raise ValueError(f"Unknown profile: {profile}")

    files = (
        [p for p in source_root.rglob("*") if p.is_file()]
        if recursive
        else [p for p in source_root.iterdir() if p.is_file()]
    )
    if not files:
        console.print(
            Panel.fit(
                f"⚠️ No files found in source folder: [yellow]{source_root}[/]",
                title="Info",
                style="yellow",
            )
        )
        return []

    resolved_patient_id = None

    if profile == "health" and patient_id is not None:
        resolved_patient_id = (
            _next_health_patient_id(destination_root)
            if patient_id == ""
            else patient_id
        )

    plan = build_placement_plan(
        source_root=source_root,
        destination_root=destination_root,
        files=files,
        profile=profile,
        project_name=project_name,
        shoot_name=shoot_name,
        patient_id=resolved_patient_id,
    )

    meta = empty_meta(
        root=str(destination_root),
        sorted_by="profile",
        executed_at=datetime.utcnow().isoformat(),
        executed_by=executed_by,
    )
    summary = empty_summary()
    log_files = []

    console.rule(f"[bold cyan]Indexly Organize — Placement Plan ({profile})")

    for entry in plan:
        src = Path(entry["source"])

        if profile == "health" and resolved_patient_id:
            dst = health_destination(
                root=destination_root,
                file_path=src,
                patient_id=resolved_patient_id,
                ensure_patient_folder_exists=True,
            )
        else:
            dst = Path(entry["destination"])

        file_hash = _hash_file(src)
        if file_hash is None:
            # File missing or unreadable — skip and log already done in _hash_file
            continue

        console.print(f"[dim]{src}[/] → [green]{dst}[/] [blue]{file_hash[:8]}[/]")

        try:
            size = src.stat().st_size
            created_at = src.stat().st_ctime
            modified_at = src.stat().st_mtime
        except OSError as e:
            log.warning(f"⚠️ Cannot access file stats (skipped): {src} — {e}")
            continue

        log_files.append(
            file_entry_template(
                original_path=str(src),
                new_path=str(dst),
                extension=src.suffix.lower(),
                category=profile,
                size=size,
                used_date=datetime.utcnow().isoformat(),
                hash_value=file_hash,
                created_at=created_at,
                modified_at=modified_at,
            )
        )
        summary["total_files"] += 1

        if apply:
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                safe_move(src, dst)
            except (OSError, shutil.Error) as e:
                log.warning(f"⚠️ Cannot move file (skipped): {src} → {dst} — {e}")
                continue

    final_log = empty_organizer_log(meta, summary, log_files)
    if not log_path:
        log_path = destination_root / "log" / f"profile_{profile}_placement.json"
    write_organizer_log(final_log, log_path)

    console.print(
        Panel.fit(
            (
                "Dry-run only. No files were moved."
                if dry_run
                else f"{len(plan)} files placed successfully."
            )
            + f"\nLog written to: {log_path}",
            title="Mode" if dry_run else "Status",
            style="yellow" if dry_run else "green",
        )
    )

    return plan


# --------------------------------------------------
# PATIENT ID GENERATOR (unchanged)
# --------------------------------------------------


def _next_health_patient_id(root: Path) -> str:
    today = datetime.utcnow().strftime("%Y%m%d")
    base = root / "Health" / "Patients"
    base.mkdir(parents=True, exist_ok=True)

    prefix = f"{today}-patient-"
    existing = []

    for p in base.iterdir():
        if p.is_dir() and p.name.startswith(prefix):
            try:
                existing.append(int(p.name.split("-")[-1]))
            except ValueError:
                pass

    next_id = max(existing, default=0) + 1
    return f"{prefix}{next_id:05d}"
