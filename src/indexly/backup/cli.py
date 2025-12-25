# ------------------------------
# src/indexly/backup/cli.py
# ------------------------------
from pathlib import Path
from .executor import run_backup
from .auto import init_auto_backup, disable_auto_backup, auto_enabled
import sys


def _is_interactive() -> bool:
    """True only when a real user can answer prompts."""
    return sys.stdin.isatty()


def handle_backup(args):
    # ------------------------------
    # Init / disable auto mode
    # ------------------------------
    if args.init_auto:
        if not args.folder:
            raise RuntimeError("--init-auto requires a folder path")
        init_auto_backup(Path(args.folder).resolve())
        return

    if args.disable_auto:
        disable_auto_backup(confirm=args.confirm)
        return

    if not args.folder:
        raise RuntimeError("Folder path is required for backup")

    folder = Path(args.folder).resolve()
    auto_active = auto_enabled(folder)
    interactive = _is_interactive()

    # ------------------------------
    # Decide execution mode
    # ------------------------------
    # Manual flag ALWAYS wins
    if args.manual:
        automatic = False
    else:
        automatic = auto_active

    # ------------------------------
    # Manual run while auto is enabled
    # ------------------------------
    if auto_active and args.manual:
        if not interactive:
            print("❌ Auto-backup is enabled and --manual was used in non-interactive mode.")
            print("ℹ️ Disable auto-backup first:")
            print(f'   indexly backup "{folder}" --disable-auto --confirm')
            return

        print("⚠️ Auto-backup is enabled for this folder.")
        print("Choose how to proceed:")
        print("1) Disable auto-backup and continue manually")
        print("2) Keep auto-backup enabled and continue manually")
        print("3) Abort")
        choice = input("Enter 1, 2, or 3: ").strip()

        if choice == "1":
            disable_auto_backup(source=folder, confirm=True)
        elif choice == "2":
            pass
        else:
            print("❌ Aborted safely.")
            return

    # ------------------------------
    # Automatic run safety (scheduler)
    # ------------------------------
    if automatic and not interactive:
        # Never ask questions, ever
        run_backup(
            folder,
            incremental=args.incremental,
            password=args.encrypt,
            automatic=True,
        )
        return

    # ------------------------------
    # Fully manual execution
    # ------------------------------
    run_backup(
        folder,
        incremental=args.incremental,
        password=args.encrypt,
        automatic=False,
    )
