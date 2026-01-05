from pathlib import Path
from .constants import CompareMode


def resolve_paths(arg_a: str, arg_b: str | None) -> tuple[Path, Path, CompareMode]:
    a = Path(arg_a).expanduser().resolve()

    if arg_b:
        b = Path(arg_b).expanduser().resolve()
        return a, b, CompareMode.MANUAL

    if not a.exists():
        raise FileNotFoundError(f"Path not found: {a}")

    cwd = Path.cwd().resolve()
    auto_b = cwd / a.name

    if auto_b.exists():
        return auto_b, a, CompareMode.AUTO

    raise ValueError(
        "Automatic comparison failed. "
        "Please provide both paths explicitly."
    )
