from pathlib import Path
from typing import List, Dict, Callable

from indexly.organize.profiles import PROFILE_RULES
from indexly.organize.profiles.base_rules import get_destination as base_destination


def build_placement_plan(
    *,
    source_root: Path,
    destination_root: Path,
    files: List[Path | tuple[Path, Path]],
    profile: str,
    **profile_args,
) -> List[Dict[str, str]]:

    plan: List[Dict[str, str]] = []
    profile = profile.lower()

    resolver: Callable = base_destination

    rule = PROFILE_RULES.get(profile)
    if callable(rule):
        resolver = rule

    for item in files:
        if isinstance(item, tuple):
            source_path, rule_path = item
        else:
            source_path = item
            rule_path = item

        if not source_path.is_file():
            continue

        dest = resolver(
            root=destination_root,
            file_path=rule_path,
            shoot_name=profile_args.get("shoot_name"),
            profile=profile,
            category=profile_args.get("category"),
            classify_raw=profile_args.get("classify_raw"),
            project_name=profile_args.get("project_name"),
            patient_id=profile_args.get("patient_id"),
            ensure_patient_folder_exists=profile_args.get("ensure_patient_folder_exists", False),
        )

        plan.append(
            {
                "source": str(source_path),
                "destination": str(dest),
                "profile": profile,
                "rule": resolver.__name__,
            }
        )

    return plan
