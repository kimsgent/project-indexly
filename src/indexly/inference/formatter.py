import json
from textwrap import indent
from rich.table import Table
from rich.console import Console
from .models import InferenceResult

console = Console()

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

def display_inference_result(result: InferenceResult):
    table = Table(title=result.test_name, show_lines=True)

    table.add_column("Statistic", justify="right")
    table.add_column("Value", justify="left")

    if result.statistic is not None:
        table.add_row("statistic", f"{result.statistic:.4f}")
    if result.ci_low is not None and result.ci_high is not None:
        table.add_row("95% CI", f"[{result.ci_low:.2f}, {result.ci_high:.2f}]")
    if result.p_value is not None:
        table.add_row("p-value", f"{result.p_value:.4f}")
    if result.effect_size is not None:
        table.add_row("effect_size", f"{result.effect_size:.4f}")

    # Optional metadata
    for key, value in result.metadata.items():
        table.add_row(str(key), str(value))

    if result.additional_table is not None:
        console.print("\nAdditional Table:")
        console.print(result.additional_table)

    console.print(table)
