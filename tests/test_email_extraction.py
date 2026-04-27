from indexly.extract_utils import (
    _clean_email_body,
    _extract_eml_body,
    _normalize_email_party,
)


def test_normalize_email_party_removes_duplicate_address_noise():
    assert (
        _normalize_email_party("'Mario Heidt' <m.heidt@bletec.de>")
        == "Mario Heidt <m.heidt@bletec.de>"
    )
    assert (
        _normalize_email_party(
            "'buchhaltung@bbp-blechbearbeitung.de' "
            "<buchhaltung@bbp-blechbearbeitung.de>"
        )
        == "buchhaltung@bbp-blechbearbeitung.de"
    )


def test_clean_email_body_trims_signature_and_quoted_reply():
    body = """
Hallo Herr Heidt,
hat geklappt, danke.

Mit freundlichen Grüßen
Ulrich Peinemann
Telefon: +49 123

Von: Mario Heidt
Gesendet: Montag, 23. März
"""

    cleaned = _clean_email_body(body)

    assert cleaned == "Hallo Herr Heidt, hat geklappt, danke."
    assert "Telefon" not in cleaned
    assert "Von:" not in cleaned


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
