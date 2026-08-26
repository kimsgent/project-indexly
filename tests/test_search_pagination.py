"""Focused coverage for search-result terminal pagination."""

from __future__ import annotations

import io
from types import SimpleNamespace

import pytest

from indexly import indexly as indexly_app
from indexly import output_utils


class TtyStringIO(io.StringIO):
    def isatty(self) -> bool:
        return True


class InterruptingInput(TtyStringIO):
    def readline(self, *args, **kwargs):
        raise KeyboardInterrupt


class UnavailableInput(TtyStringIO):
    def readline(self, *args, **kwargs):
        raise OSError("input is unavailable")


class NonInteractiveFailingInput(io.StringIO):
    def readline(self, *args, **kwargs):
        raise AssertionError("non-interactive output must not read input")


class FakeRipple:
    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        pass

    def stop(self):
        pass


def _results(count: int) -> list[dict[str, str]]:
    return [
        {
            "path": f"result-{number:02d}.txt",
            "snippet": f"alpha snippet {number}",
            "content": f"alpha regex context {number}",
        }
        for number in range(count)
    ]


def _search_args(**overrides):
    values = {
        "profile": None,
        "context": 25,
        "filetype": None,
        "date_from": None,
        "date_to": None,
        "path_contains": None,
        "filter_tag": None,
        "fuzzy": False,
        "fuzzy_threshold": 80,
        "author": None,
        "camera": None,
        "image_created": None,
        "format": None,
        "no_cache": False,
        "near_distance": None,
        "sort_by": "relevance",
        "db": "test.db",
        "export_format": None,
        "output": None,
        "save_profile": None,
        "pattern": "alpha",
        "folder_or_term": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize("count", [0, 10, 11, 27])
def test_noninteractive_rendering_preserves_all_results_without_paging(
    monkeypatch, count
):
    monkeypatch.setattr(output_utils, "get_tags_for_file", lambda path: [])
    output = io.StringIO()

    output_utils.print_search_results(
        _results(count), "alpha", input_stream=io.StringIO(), output_stream=output
    )

    rendered = output.getvalue()
    assert "Enter: next" not in rendered
    assert "Page " not in rendered
    assert "\x1b" not in rendered
    if count:
        assert f"Found {count} matches:" in rendered
    for number in range(count):
        assert (
            rendered.index(f"result-{number:02d}.txt")
            < rendered.index(f"result-{number + 1:02d}.txt")
            if number + 1 < count
            else True
        )


def test_enter_renders_one_page_at_a_time_with_progress_headers(monkeypatch):
    monkeypatch.setattr(output_utils, "get_tags_for_file", lambda path: [])
    output = TtyStringIO()

    output_utils.print_search_results(
        _results(21), "alpha", input_stream=TtyStringIO("\n\n"), output_stream=output
    )

    rendered = output.getvalue()
    assert "Page 1 of 3 (results 1–10 of 21)" in rendered
    assert "Page 2 of 3 (results 11–20 of 21)" in rendered
    assert "Page 3 of 3 (results 21–21 of 21)" in rendered
    assert rendered.count("Enter: next") == 2
    assert "result-20.txt" in rendered


def test_ten_interactive_results_render_once_without_a_navigation_prompt(monkeypatch):
    monkeypatch.setattr(output_utils, "get_tags_for_file", lambda path: [])
    output = TtyStringIO()

    output_utils.print_search_results(
        _results(10), "alpha", input_stream=TtyStringIO(), output_stream=output
    )

    rendered = output.getvalue()
    assert "Found 10 matches:" in rendered
    assert "Page " not in rendered
    assert "Enter: next" not in rendered
    assert "result-09.txt" in rendered


def test_space_renders_every_remaining_result_without_more_prompts(monkeypatch):
    monkeypatch.setattr(output_utils, "get_tags_for_file", lambda path: [])
    output = TtyStringIO()

    output_utils.print_search_results(
        _results(21), "alpha", input_stream=TtyStringIO(" \n"), output_stream=output
    )

    rendered = output.getvalue()
    assert rendered.count("Enter: next") == 1
    assert "Page 2 of" not in rendered
    assert "result-20.txt" in rendered


@pytest.mark.parametrize("command", ["q", "Q"])
def test_quit_stops_only_later_terminal_rendering(monkeypatch, command):
    monkeypatch.setattr(output_utils, "get_tags_for_file", lambda path: [])
    output = TtyStringIO()

    output_utils.print_search_results(
        _results(21),
        "alpha",
        input_stream=TtyStringIO(f"{command}\n"),
        output_stream=output,
    )

    rendered = output.getvalue()
    assert "result-09.txt" in rendered
    assert "result-10.txt" not in rendered
    assert "Page 2 of" not in rendered


def test_invalid_input_retries_without_rendering_the_page_again(monkeypatch):
    monkeypatch.setattr(output_utils, "get_tags_for_file", lambda path: [])
    output = TtyStringIO()

    output_utils.print_search_results(
        _results(21),
        "alpha",
        input_stream=TtyStringIO("unexpected\n\nq\n"),
        output_stream=output,
    )

    rendered = output.getvalue()
    assert "Use Enter, Space, or q." in rendered
    assert rendered.count("result-00.txt") == 1
    assert rendered.count("Page 1 of 3") == 1
    assert rendered.count("Page 2 of 3") == 1
    assert "result-20.txt" not in rendered


@pytest.mark.parametrize(
    "input_stream", [TtyStringIO(), InterruptingInput(), UnavailableInput()]
)
def test_eof_interrupt_and_unavailable_input_stop_cleanly(monkeypatch, input_stream):
    monkeypatch.setattr(output_utils, "get_tags_for_file", lambda path: [])
    output = TtyStringIO()

    output_utils.print_search_results(
        _results(11), "alpha", input_stream=input_stream, output_stream=output
    )

    rendered = output.getvalue()
    assert "result-09.txt" in rendered
    assert "result-10.txt" not in rendered


def test_noninteractive_output_never_reads_input_even_when_input_is_a_tty(monkeypatch):
    monkeypatch.setattr(output_utils, "get_tags_for_file", lambda path: [])
    output = io.StringIO()

    output_utils.print_search_results(
        _results(11),
        "alpha",
        input_stream=NonInteractiveFailingInput(),
        output_stream=output,
    )

    assert "result-10.txt" in output.getvalue()


def test_fts_output_retains_tags_and_snippet_text_for_paged_results(monkeypatch):
    monkeypatch.setattr(output_utils, "get_tags_for_file", lambda path: ["reviewed"])
    output = TtyStringIO()

    output_utils.print_search_results(
        _results(11), "alpha", input_stream=TtyStringIO(" \n"), output_stream=output
    )

    rendered = output.getvalue()
    assert "[Tags: reviewed]" in rendered
    assert "alpha snippet 0" in rendered
    assert "alpha snippet 10" in rendered


def test_regex_output_keeps_paths_tags_and_highlighted_context(monkeypatch):
    monkeypatch.setattr(output_utils, "get_tags_for_file", lambda path: ["reviewed"])
    output = io.StringIO()

    output_utils.print_regex_results(
        _results(11), "alpha", 8, input_stream=io.StringIO(), output_stream=output
    )

    rendered = output.getvalue()
    assert "result-00.txt" in rendered
    assert "result-10.txt" in rendered
    assert "[Tags: reviewed]" in rendered
    assert "alpha regex" in rendered
    assert "Enter: next" not in rendered


@pytest.mark.parametrize(
    ("count", "navigation", "has_pages"),
    [
        (0, "", False),
        (10, "", False),
        (11, "\n", True),
        (21, "\n\n", True),
    ],
)
def test_regex_pagination_honors_the_result_boundaries(
    monkeypatch, count, navigation, has_pages
):
    monkeypatch.setattr(output_utils, "get_tags_for_file", lambda path: [])
    output = TtyStringIO()

    output_utils.print_regex_results(
        _results(count),
        "alpha",
        8,
        input_stream=TtyStringIO(navigation),
        output_stream=output,
    )

    rendered = output.getvalue()
    assert ("Page 1 of" in rendered) is has_pages
    assert ("Enter: next" in rendered) is has_pages
    if count:
        assert f"result-{count - 1:02d}.txt" in rendered


def test_live_fts_export_and_profile_save_receive_complete_results_after_pager_returns(
    monkeypatch,
):
    results = _results(11)
    exported = []
    saved = []
    monkeypatch.setattr(indexly_app, "Ripple", FakeRipple)
    monkeypatch.setattr(indexly_app, "get_search_term", lambda args: "alpha")
    monkeypatch.setattr(indexly_app, "search_fts5", lambda **kwargs: results)
    monkeypatch.setattr(
        indexly_app, "print_search_results", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        indexly_app,
        "export_results_to_format",
        lambda received, *args: exported.append(received),
    )
    monkeypatch.setattr(
        __import__("indexly.profiles", fromlist=["save_profile"]),
        "save_profile",
        lambda name, args, received: saved.append(received),
    )

    indexly_app.handle_search(
        _search_args(export_format="json", save_profile="pager-quit-profile")
    )

    assert exported == [results]
    assert saved == [results]


def test_saved_profile_fts_export_receives_complete_results_after_pager_returns(
    monkeypatch,
):
    results = _results(11)
    exported = []
    profiles = __import__("indexly.profiles", fromlist=["load_profile"])
    monkeypatch.setattr(
        profiles, "load_profile", lambda name: {"results": results, "term": "alpha"}
    )
    monkeypatch.setattr(
        profiles, "filter_saved_results", lambda received, term: received
    )
    monkeypatch.setattr(
        indexly_app, "sort_search_results", lambda received, sort_by: received
    )
    monkeypatch.setattr(indexly_app, "get_search_term", lambda args: "alpha")
    monkeypatch.setattr(
        indexly_app, "print_search_results", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        indexly_app,
        "export_results_to_format",
        lambda received, *args: exported.append(received),
    )

    indexly_app.handle_search(_search_args(profile="stored", export_format="csv"))

    assert exported == [results]


def test_regex_export_and_profile_save_receive_complete_results_after_pager_returns(
    monkeypatch,
):
    results = _results(11)
    exported = []
    saved = []
    monkeypatch.setattr(indexly_app, "Ripple", FakeRipple)
    monkeypatch.setattr(indexly_app, "search_regex", lambda **kwargs: results)
    monkeypatch.setattr(
        indexly_app, "print_regex_results", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        indexly_app,
        "export_results_to_format",
        lambda received, *args: exported.append(received),
    )
    monkeypatch.setattr(
        __import__("indexly.profiles", fromlist=["save_profile"]),
        "save_profile",
        lambda name, args, received: saved.append(received),
    )

    indexly_app.handle_regex(
        _search_args(export_format="json", save_profile="regex-pager-quit-profile")
    )

    assert exported == [results]
    assert saved == [results]
