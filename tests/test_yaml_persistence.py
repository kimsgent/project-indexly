import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from indexly.analysis_orchestrator import _persist_analysis
from indexly.yaml_pipeline import run_yaml_pipeline


def test_nested_yaml_persistence_stores_json_safe_metadata_and_artifact(
    tmp_path, monkeypatch
):
    analysis_db = tmp_path / "state" / "indexly.db"
    monkeypatch.setenv("INDEXLY_ANALYSIS_DB", str(analysis_db))

    source = tmp_path / "config.yaml"
    source.write_text(
        """
app:
  name: MyApplication
  version: 1.0.0
  debug: true
database:
  host: localhost
  port: 5432
  username: admin
  password: secret123
  options:
    pool_size: 10
    timeout: 30
features:
  - authentication
  - logging
  - analytics
users:
  - name: Alice
    role: admin
    active: true
  - name: Bob
    role: user
    active: false
logging:
  level: INFO
  file: /var/log/myapp.log
  rotation:
    enabled: true
    max_size_mb: 50
    backups: 5
""".strip(),
        encoding="utf-8",
    )
    raw = {
        "app": {"name": "MyApplication", "version": "1.0.0", "debug": True},
        "database": {
            "host": "localhost",
            "port": 5432,
            "username": "admin",
            "password": "secret123",
            "options": {"pool_size": 10, "timeout": 30},
        },
        "features": ["authentication", "logging", "analytics"],
        "users": [
            {"name": "Alice", "role": "admin", "active": True},
            {"name": "Bob", "role": "user", "active": False},
        ],
        "logging": {
            "level": "INFO",
            "file": "/var/log/myapp.log",
            "rotation": {"enabled": True, "max_size_mb": 50, "backups": 5},
        },
    }

    df, df_stats, table_output = run_yaml_pipeline(
        raw=raw,
        args=SimpleNamespace(treeview=True, file_path=str(source)),
    )

    assert df.attrs["_df_stats"].equals(df_stats)
    assert df.attrs["_raw_yaml"] == raw

    persisted = _persist_analysis(
        df,
        None,
        source,
        "yaml",
        table_output,
        args=SimpleNamespace(no_persist=False, keep_artifact_history=False),
        verbose=False,
    )

    assert persisted is True

    conn = sqlite3.connect(analysis_db)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT summary_json, metadata_json, cleaned_data_json FROM cleaned_data WHERE file_name = ?",
        (source.name,),
    ).fetchone()
    conn.close()

    assert row is not None
    summary = json.loads(row["summary_json"])
    metadata = json.loads(row["metadata_json"])
    cleaned_data = json.loads(row["cleaned_data_json"])

    assert "count" in summary
    assert cleaned_data

    yaml_table_output = metadata["yaml_table_output"]
    assert isinstance(yaml_table_output["vertical_summary"], list)
    assert any(
        item["Field"] == "database.password"
        for item in yaml_table_output["vertical_summary"]
    )

    artifact_path = Path(metadata["analysis_artifact_path"])
    assert metadata["analysis_artifact_schema"] == "indexly.yaml.analysis.v1"
    assert artifact_path.exists()

    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["schema"] == "indexly.yaml.analysis.v1"
    assert artifact["raw_yaml"]["database"]["options"]["pool_size"] == 10
    assert isinstance(artifact["table_output"]["vertical_summary"], list)
