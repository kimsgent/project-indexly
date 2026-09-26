"""Regression coverage for generated Hugo release URLs."""

from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from generate_releases import _release_url


def test_release_urls_use_the_canonical_english_hugo_routes():
    assert _release_url("2.1.7") == "/en/releases/v2.1.7/"
    assert _release_url("2.1.1", archived=True) == "/en/releases/archive/v2.1.1/"
