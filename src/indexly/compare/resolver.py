from pathlib import Path
from .constants import CompareMode


class ComparePathResolutionError(ValueError):
    """Raised when compare paths cannot be resolved into a safe pair."""


def _normalize(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _same_path(a: Path, b: Path) -> bool:
    try:
        return a.samefile(b)
    except OSError:
        return a == b


def resolve_paths(
    arg_a: str | Path,
    arg_b: str | Path | None,
) -> tuple[Path, Path, CompareMode]:
    """Resolve manual or automatic compare arguments into two distinct paths."""
    a = _normalize(arg_a)

    if arg_b is not None:
        b = _normalize(arg_b)
        if not a.exists():
            raise FileNotFoundError(f"Path not found: {a}")
        if not b.exists():
            raise FileNotFoundError(f"Path not found: {b}")
        return a, b, CompareMode.MANUAL

    if not a.exists():
        raise FileNotFoundError(f"Path not found: {a}")

    cwd = Path.cwd().resolve(strict=False)
    auto_b = (cwd / a.name).resolve(strict=False)

    if not auto_b.exists():
        raise ComparePathResolutionError(
            "Automatic comparison needs a same-named file or folder in the "
            f"current directory. Could not find: {auto_b}. Provide both paths "
            "explicitly."
        )

    if _same_path(auto_b, a):
        raise ComparePathResolutionError(
            "Automatic comparison would compare the path to itself. Provide "
            "both paths explicitly."
        )

    return auto_b, a, CompareMode.AUTO
