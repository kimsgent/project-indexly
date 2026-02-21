from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate
from reportlab.platypus import Paragraph
from reportlab.platypus import Spacer


def export_markdown(result, filename="report.md"):
    with open(filename, "w") as f:
        f.write(f"# Inference Report\n\n")
        f.write(f"**Test:** {result.test_name}\n\n")
        f.write(f"Statistic: {result.statistic}\n\n")
        f.write(f"P-value: {result.p_value}\n\n")
        f.write(f"Effect size: {result.effect_size}\n\n")
        f.write(f"CI: ({result.ci_low}, {result.ci_high})\n\n")

        if result.additional_table:
            f.write("\n## Additional Results\n\n")
            f.write(f"{result.additional_table}\n\n")

        f.write(f"\nMetadata:\n{result.metadata}\n")


def export_pdf(result, filename="report.pdf"):
    doc = SimpleDocTemplate(filename)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("Inference Report", styles["Heading1"]))
    elements.append(Spacer(1, 0.5 * inch))

    elements.append(Paragraph(f"Test: {result.test_name}", styles["Normal"]))
    elements.append(Paragraph(f"Statistic: {result.statistic}", styles["Normal"]))
    elements.append(Paragraph(f"P-value: {result.p_value}", styles["Normal"]))
    elements.append(Paragraph(f"Effect size: {result.effect_size}", styles["Normal"]))
    elements.append(
        Paragraph(f"CI: {result.ci_low}, {result.ci_high}", styles["Normal"])
    )
    if result.additional_table:
        elements.append(Spacer(1, 0.3 * inch))
        elements.append(Paragraph("Additional Results:", styles["Heading2"]))
        elements.append(Spacer(1, 0.2 * inch))
        elements.append(Paragraph(str(result.additional_table), styles["Normal"]))
    doc.build(elements)
