from pathlib import Path
from .restore import restore_backup


def handle_restore(args):
    restore_backup(
        backup_name=args.backup,
        target=Path(args.target).resolve() if args.target else None,
        password=args.decrypt,
    )
