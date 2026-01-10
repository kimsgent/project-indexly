class IndexlyDBDetector:
    REQUIRED = {
        "file_index",
        "file_index_vocab",
        "file_index_content",
        "file_index_docsize",
        "file_index_idx",
        "file_metadata",
    }

    def __init__(self, raw):
        self.raw = raw or {}

    def is_indexly_db(self) -> bool:
        tables = {t.lower() for t in self.raw.get("tables", [])}
        return self.REQUIRED.issubset(tables)
