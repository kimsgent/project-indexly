from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch


# -------------------------------------------------
# Public Dispatcher
# -------------------------------------------------


def export_report(result, fmt: str):

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if fmt == "md":
        filename = f"inference_report_{timestamp}.md"
        export_markdown(result, filename)

    elif fmt == "pdf":
        filename = f"inference_report_{timestamp}.pdf"
        export_pdf(result, filename)

    else:
        raise ValueError("Unsupported export format.")

    print(f"[INFO] Report exported → {filename}")


# -------------------------------------------------
# Markdown Export
# -------------------------------------------------


def export_markdown(result, filename):

    with open(filename, "w") as f:
        f.write("# Inference Report\n\n")
        f.write(f"Generated: {datetime.now()}\n\n")

        f.write("## Core Results\n\n")
        f.write(f"- **Test:** {result.test_name}\n")
        f.write(f"- **Statistic:** {result.statistic}\n")
        f.write(f"- **P-value:** {result.p_value}\n")
        f.write(f"- **Effect size:** {result.effect_size}\n")
        f.write(f"- **Confidence Interval:** ({result.ci_low}, {result.ci_high})\n\n")

        if getattr(result, "bootstrap_used", False):
            f.write("- **Bootstrap CI:** Enabled\n")

        if getattr(result, "correction_method", None):
            f.write(
                f"- **Multiple Comparison Correction:** {result.correction_method}\n"
            )

        if result.additional_table:
            f.write("\n## Additional Results\n\n")
            f.write(f"{result.additional_table}\n\n")

        if result.metadata:
            f.write("\n## Metadata\n\n")
            for key, value in result.metadata.items():
                f.write(f"- {key}: {value}\n")


# -------------------------------------------------
# PDF Export
# -------------------------------------------------


def export_pdf(result, filename):

    doc = SimpleDocTemplate(filename)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("Inference Report", styles["Heading1"]))
    elements.append(Spacer(1, 0.3 * inch))
    elements.append(Paragraph(f"Generated: {datetime.now()}", styles["Normal"]))
    elements.append(Spacer(1, 0.5 * inch))

    elements.append(Paragraph("Core Results", styles["Heading2"]))
    elements.append(Spacer(1, 0.3 * inch))

    elements.append(Paragraph(f"Test: {result.test_name}", styles["Normal"]))
    elements.append(Paragraph(f"Statistic: {result.statistic}", styles["Normal"]))
    elements.append(Paragraph(f"P-value: {result.p_value}", styles["Normal"]))
    elements.append(Paragraph(f"Effect size: {result.effect_size}", styles["Normal"]))
    elements.append(
        Paragraph(
            f"Confidence Interval: ({result.ci_low}, {result.ci_high})",
            styles["Normal"],
        )
    )

    if getattr(result, "bootstrap_used", False):
        elements.append(Paragraph("Bootstrap CI: Enabled", styles["Normal"]))

    if getattr(result, "correction_method", None):
        elements.append(
            Paragraph(
                f"Multiple Comparison Correction: {result.correction_method}",
                styles["Normal"],
            )
        )

    if result.additional_table:
        elements.append(Spacer(1, 0.4 * inch))
        elements.append(Paragraph("Additional Results", styles["Heading2"]))
        elements.append(Spacer(1, 0.2 * inch))
        elements.append(Paragraph(str(result.additional_table), styles["Normal"]))

    if result.metadata:
        elements.append(Spacer(1, 0.4 * inch))
        elements.append(Paragraph("Metadata", styles["Heading2"]))
        elements.append(Spacer(1, 0.2 * inch))

        for key, value in result.metadata.items():
            elements.append(Paragraph(f"{key}: {value}", styles["Normal"]))

    doc.build(elements)
