from pathlib import Path
from typing import List, Dict, Callable

from indexly.organize.profiles import PROFILE_RULES
from indexly.organize.profiles.base_rules import get_destination as base_destination


from pathlib import Path
from typing import List, Dict, Callable

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
    NO existence validation.
    """

    plan: List[Dict[str, str]] = []

    # 🔒 IMPORTANT:
    # The planner must NEVER call health_rules.get_destination
    # because it enforces patient existence.
    # Destination resolution happens during execution.
    resolver: Callable = base_destination

    for path in files:
        if not path.is_file():
            continue

        # Logical / placeholder destination only
        dest = resolver(
            root=destination_root,
            file_path=path,
        )

        plan.append(
            {
                "source": str(path),
                "destination": str(dest),  # may be overridden during execution
                "profile": profile,
                "rule": "planner",
            }
        )

    return plan

