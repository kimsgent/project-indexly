# Indexly Table Migration Utility

This utility helps you **merge new tables or data** into an existing Indexly database **without re-indexing**, saving time for large datasets.

---

## ⚡ Key Features

- **Path Normalization:** Ensures consistent mapping of files using `normalize_path()`.
- **Schema Checking:** Automatically detects missing columns and adds them.
- **Dry-Run Mode:** Preview changes before applying.
- **Row Validation:** Detects rows with missing critical fields (`path`) and skips them.
- **Logging:** Failed merges are saved in `migrate_db.log`.
- **Conflict Resolution:** Uses `INSERT OR REPLACE` by `path`, not rowid.
- **Interactive & Safe:** Confirms actions before applying when dry-run is off.

---

## ✅ Usage Steps

1. **Download or obtain the migration script:**
    ```bash
    src/indexly/migrate_db.py
    ```

2. **Prepare your databases:**
    - `source_db`: The database with new table or updated data.
    - `target_db`: The existing Indexly database (already indexed).

3. **Preview migration (dry-run mode):**
    ```bash
    python -m indexly.migrate_db \
        --source-db new_data.db \
        --target-db fts_index.db \
        --table file_metadata
    ```
    - No changes are applied.
    - Prints number of rows and missing columns.

4. **Apply migration:**
    ```bash
    python -m indexly.migrate_db \
        --source-db new_data.db \
        --target-db fts_index.db \
        --table file_metadata \
        --dry-run False
    ```
    - Inserts new data.
    - Skips rows with missing `path` or invalid data.
    - Logs any failed merges to `migrate_db.log`.

5. **Check results:**
    - Open Indexly database with your preferred DB viewer.
    - Confirm new columns/data are present.
    - Check `migrate_db.log` for skipped or failed rows.

---

## 🛠 Notes for Users

- **Why use dry-run first:** Prevents accidental overwrites.
- **Avoids re-indexing:** Only merges new rows or missing columns.
- **Logging:** Helps track issues if rows could not be inserted.
- **Required fields:** Every row must have `path`.
- **Flexible:** Can migrate any table (`file_metadata`, `file_tags`, etc.).

---

## 🔑 Keywords

- **Migration**, **Merge**, **Dry-run**, **Validation**, **Logging**, **Safe Update**, **Path Normalization**, **FTS5 Database**

---

### 💡 Tip

If you add a new table to Indexly in future, you can reuse this script to import it **without performing a full re-index**, saving hours on large collections.
