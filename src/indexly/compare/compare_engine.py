from pathlib import Path
from .file_compare import compare_files
from .folder_compare import compare_folders
from .models import FileCompareResult, FolderCompareResult


def run_compare(
    path_a: str | Path,
    path_b: str | Path,
    *,
    threshold: float | None = None,
    extensions: str | None = None,
    ignore: str | None = None,
    context: int = 3,  # New argument for foldable diff lines
) -> tuple[FileCompareResult | FolderCompareResult, int]:

    a = Path(path_a)
    b = Path(path_b)

    ext_set = (
        {e.lower() for e in (extensions or "").split(",") if e} if extensions else None
    )
    ignore_set = (
        {i.lower() for i in (ignore or "").split(",") if i} if ignore else set()
    )

    # Folder comparison
    if a.is_dir() and b.is_dir():
        result = compare_folders(
            a, b, threshold=threshold, extensions=ext_set, ignore=ignore_set
        )
        exit_code = 0 if result.summary.identical == len(result.files) else 1
        return result, exit_code

    # File comparison
    if a.is_file() and b.is_file():
        result = compare_files(a, b, threshold=threshold)
        exit_code = 0 if result.identical else 1
        return result, exit_code

    # Mismatched types
    from .models import FileCompareResult

    return (
        FileCompareResult(
            path_a=a,
            path_b=b,
            tier=None,
            identical=False,
            similarity=None,
            diffs=[
                type(
                    "Diff",
                    (),
                    {
                        "sign": "!",
                        "text": f"Cannot compare: {a} and {b} are different types",
                    },
                )()
            ],
        ),
        2,
    )
