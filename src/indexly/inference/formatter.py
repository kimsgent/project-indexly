import json
from textwrap import indent


def format_result(result):
    """
    Professional console formatter for InferenceResult
    """

    data = result.to_dict()

    lines = []
    lines.append("=" * 60)
    lines.append(f"TEST: {data['test_name']}")
    lines.append("-" * 60)
    lines.append(f"Statistic : {data['statistic']:.6f}")
    lines.append(f"P-value   : {data['p_value']:.6f}")

    if data.get("effect_size") is not None:
        lines.append(f"Effect Size : {data['effect_size']:.6f}")

    if data.get("ci_low") is not None:
        lines.append(f"95% CI : [{data['ci_low']:.6f}, {data['ci_high']:.6f}]")

    lines.append("-" * 60)
    lines.append("Interpretation:")
    lines.append(indent(data["interpretation"], "  "))
    lines.append("=" * 60)

    if data.get("additional_table"):
        lines.append("\nAdditional Table:")
        lines.append(indent(json.dumps(data["additional_table"], indent=2), "  "))

    return "\n".join(lines)
