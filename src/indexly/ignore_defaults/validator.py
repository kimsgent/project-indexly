from __future__ import annotations

REQUIRED_RULES = {
    ".indexly/",
    "fts_index.db*",
}

def validate_template(template: str) -> tuple[bool, list[str]]:
    warnings: list[str] = []

    if not template.strip():
        return False, ["Template is empty"]

    rules = [
        line.strip()
        for line in template.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    if not rules:
        return False, ["Template contains no active rules"]

    missing = REQUIRED_RULES - set(rules)
    if missing:
        warnings.append(
            f"Missing recommended rules: {', '.join(sorted(missing))}"
        )

    return True, warnings
