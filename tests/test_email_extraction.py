from indexly.extract_utils import (
    _clean_email_body,
    _extract_eml_body,
    _normalize_email_party,
)


def test_normalize_email_party_removes_duplicate_address_noise():
    assert (
        _normalize_email_party("'John Doe' <john.doe@example.com>")
        == "John Doe <john.doe@example.com>"
    )
    assert (
        _normalize_email_party("'accounting@example.com' " "<accounting@example.com>")
        == "accounting@example.com"
    )


def test_clean_email_body_trims_signature_and_quoted_reply():
    body = """
Hello Mr. Smith,
it worked, thanks.

Best regards
Jane Smith
Phone: +1 234 567 890

From: John Doe
Sent: Monday, March 23
"""

    cleaned = _clean_email_body(body)

    assert cleaned == "Hello Mr. Smith, it worked, thanks."
    assert "Phone" not in cleaned
    assert "From:" not in cleaned


def test_clean_email_body_trims_configured_disclaimer():
    body = """
Please find the ticket attached.

This email and any attachments are confidential and intended only for the recipient.
Please consider the environment before printing this email.
"""

    assert _clean_email_body(body) == "Please find the ticket attached."


def test_extract_eml_body_handles_parser_body_records():
    parsed = {
        "body": [
            {"content": "Hello team,\n"},
            {"content": "Best regards,\nSupport"},
        ]
    }

    assert _extract_eml_body(parsed) == "Hello team,\n\nBest regards,\nSupport"
