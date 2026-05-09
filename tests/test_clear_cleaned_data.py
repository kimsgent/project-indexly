def configure_stats_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


def insert_cleaned_row(file_name, source_path=None):
    from indexly.db_utils import _get_db_connection

    conn = _get_db_connection()
    conn.execute(
        """
        INSERT INTO cleaned_data(file_name, file_type, source_path)
        VALUES (?, ?, ?)
        """,
        (file_name, "csv", source_path),
    )
    conn.commit()
    conn.close()


def cleaned_count():
    from indexly.db_utils import _get_db_connection

    conn = _get_db_connection()
    count = conn.execute("SELECT COUNT(*) FROM cleaned_data").fetchone()[0]
    conn.close()
    return count


def test_clear_cleaned_data_matches_persisted_basename(tmp_path, monkeypatch):
    configure_stats_home(tmp_path, monkeypatch)
    source = tmp_path / "Reports" / "Sample.csv"

    insert_cleaned_row(source.name, str(source))

    from indexly.clean_csv import clear_cleaned_data

    clear_cleaned_data(file_path=str(source))

    assert cleaned_count() == 0


def test_clear_cleaned_data_matches_source_path(tmp_path, monkeypatch):
    configure_stats_home(tmp_path, monkeypatch)
    source = tmp_path / "Reports" / "Sample.csv"

    insert_cleaned_row("Sample.csv", str(source))

    from indexly.clean_csv import clear_cleaned_data

    clear_cleaned_data(file_path=str(source))

    assert cleaned_count() == 0


def test_clear_cleaned_data_matches_normalized_full_path_in_file_name(
    tmp_path, monkeypatch
):
    configure_stats_home(tmp_path, monkeypatch)
    source = tmp_path / "Reports" / "Sample.csv"
    normalized_source = str(source).replace("\\", "/")

    insert_cleaned_row(normalized_source, None)

    from indexly.clean_csv import clear_cleaned_data

    clear_cleaned_data(file_path=str(source))

    assert cleaned_count() == 0
