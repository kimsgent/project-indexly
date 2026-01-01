from pathlib import Path
import shutil
import tempfile
import json
from .paths import ensure_backup_dirs
from .registry import load_registry
from .decrypt import decrypt_archive, is_encrypted
from .extract import extract_archive
from .metadata_restore import apply_metadata
from .verify import verify_checksum

from getpass import getpass
from tarfile import ReadError

def restore_backup(
    backup_name: str,
    target: Path | None = None,
    password: str | None = None,
):
    dirs = ensure_backup_dirs()
    registry = load_registry(dirs["root"] / "index.json")

    entry = next(
        (b for b in registry.get("backups", [])
         if Path(b["archive"]).name == backup_name),
        None,
    )
    if not entry:
        print(f"⚠️ Backup '{backup_name}' not found")
        return

    # ------------------------------
    # Resolve restore chain
    # ------------------------------
    restore_steps: list[dict] = []

    if entry["type"] == "full":
        restore_steps = [{
            "archive": entry["archive"],
            "manifest": entry["manifest"],
        }]
    else:
        registry_backups = registry.get("backups", [])
        current = entry
        while True:
            restore_steps.insert(0, {
                "archive": current["archive"],
                "manifest": current["manifest"],
            })

            chain = current.get("chain", [])
            if not chain:
                break

            parent_archive = Path(chain[0]["archive"]).name
            current = next(
                (b for b in registry_backups
                 if Path(b["archive"]).name == parent_archive),
                None,
            )
            if current is None:
                print("❌ Restore chain is broken")
                return

    target = target or Path.cwd()
    target.mkdir(parents=True, exist_ok=True)

    print(f"📂 Restoring backup '{backup_name}' to '{target}'...\n")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)

        for step in restore_steps:
            archive = Path(step["archive"])
            print(f"🔍 Verifying checksum for {archive.name}...")
            verify_checksum(archive, archive.with_suffix(".sha256"))
            print("✅ Checksum verified")

            work_file = archive

            # ------------------------------
            # Handle decryption (3 attempts)
            # ------------------------------
            if is_encrypted(work_file):
                for attempt in range(1, 4):
                    if password is None:
                        password = getpass(
                            f"🔐 Enter password for '{archive.name}' (attempt {attempt}/3): "
                        )
                    try:
                        print(f"🔓 Decrypting archive {archive.name}...")
                        work_file = decrypt_archive(work_file, password, tmp)
                        print(f"✅ Decryption successful → {work_file.name}")
                        break
                    except Exception:
                        password = None
                        print("❌ Wrong password\n")
                    if attempt == 3:
                        print("🚫 Restore cancelled (failed 3 attempts)")
                        return

            # ------------------------------
            # Extraction (separate)
            # ------------------------------
            try:
                print(f"📦 Extracting {work_file.name}...")
                extract_archive(work_file, tmp)
                print("✅ Extraction successful\n")
            except Exception as e:
                print(f"❌ Extraction failed: {e}\n")
                print("🚫 Restore cancelled (archive may be corrupt)")
                return

        # ------------------------------
        # Apply metadata if exists
        # ------------------------------
        meta = tmp / "metadata.json"
        if meta.exists():
            print("🛠 Applying metadata...")
            apply_metadata(json.loads(meta.read_text("utf-8")), tmp)
            print("✅ Metadata applied")

        # ------------------------------
        # Move restored files to target
        # ------------------------------
        print("🚚 Moving restored files into target directory...")
        for item in tmp.iterdir():
            if item.name != "metadata.json":
                dest = target / item.name
                if dest.exists():
                    shutil.rmtree(dest, ignore_errors=True) if dest.is_dir() else dest.unlink()
                shutil.move(item, dest)

    print("\n🎉 Restore completed successfully")

