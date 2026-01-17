from pathlib import Path

def get_destination(root: Path, file_path: Path, **kwargs) -> Path:
    """
    Default placement: root/unsorted/<filename>
    """
    return root / "unsorted" / file_path.name
