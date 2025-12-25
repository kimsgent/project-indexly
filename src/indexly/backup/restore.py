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

    chain = entry.get("chain", [])
    if not chain:
        print(f"⚠️ Backup '{backup_name}' has no chain")
        return

    target = target or Path.cwd()
    target.mkdir(parents=True, exist_ok=True)

    print(f"📂 Restoring backup '{backup_name}' to '{target}'...\n")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)

        for step in chain:
            archive = Path(step["archive"])
            print(f"🔍 Verifying checksum for {archive.name}...")
            verify_checksum(archive, archive.with_suffix(".sha256"))
            print("✅ Checksum verified")

            work_file = archive

            for attempt in range(1, 4):
                try:
                    print(f"📦 Extracting {archive.name}...")
                    extract_archive(work_file, tmp)
                    print("✅ Extraction successful\n")
                    break
                except ReadError:
                    if password is None:
                        print("🔐 Backup is encrypted")
                        password = getpass(
                            f"Enter password (attempt {attempt}/3, Ctrl+C to cancel): "
                        )

                    print("🔓 Decrypting archive...")
                    try:
                        work_file = decrypt_archive(archive, password, tmp)
                        print("✅ Password accepted")
                    except Exception:
                        password = None
                        print("❌ Wrong password\n")

                if attempt == 3:
                    print("🚫 Restore cancelled (password mismatch)")
                    return

        meta = tmp / "metadata.json"
        if meta.exists():
            print("🛠 Applying metadata...")
            apply_metadata(json.loads(meta.read_text("utf-8")), tmp)
            print("✅ Metadata applied")

        print("🚚 Moving restored files into target directory...")
        for item in tmp.iterdir():
            if item.name != "metadata.json":
                dest = target / item.name
                if dest.exists():
                    shutil.rmtree(dest, ignore_errors=True) if dest.is_dir() else dest.unlink()
                shutil.move(item, dest)

    print("\n🎉 Restore completed successfully")
