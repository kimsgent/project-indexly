from pathlib import Path
from typing import List, Dict, Callable

from indexly.organize.profiles import PROFILE_RULES
from indexly.organize.profiles.base_rules import get_destination as base_destination


def build_placement_plan(
    *,
    source_root: Path,
    destination_root: Path,
    files: List[Path],
    profile: str,
    **profile_args,
) -> List[Dict[str, str]]:
    """
    Build a safe placement plan.
    NO filesystem writes.
    """

    resolver: Callable = PROFILE_RULES.get(profile, base_destination)

    plan: List[Dict[str, str]] = []

    for path in files:
        if not path.is_file():
            continue

        dest = resolver(
            root=destination_root,
            file_path=path,
            **profile_args,
        )

        plan.append(
            {
                "source": str(path),
                "destination": str(dest),
                "profile": profile,
                "rule": resolver.__module__.split(".")[-1],
            }
        )

    return plan
