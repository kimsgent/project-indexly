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

    plan: List[Dict[str, str]] = []
    profile = profile.lower()

    resolver: Callable = base_destination

    if profile != "health":
        rule = PROFILE_RULES.get(profile)
        if callable(rule):
            resolver = rule

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
                "rule": resolver.__name__,
            }
        )

    return plan
