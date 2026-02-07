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
            shoot_name=profile_args.get("shoot_name"),
            profile=profile_args.get("profile"),
            category=profile_args.get("category"),
            classify_raw=profile_args.get("classify_raw"),
            project_name=profile_args.get("project_name"),
            patient_id=profile_args.get("patient_id"),
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
