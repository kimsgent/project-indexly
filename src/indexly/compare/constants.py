from enum import Enum, IntEnum

THRESHOLD_SEMANTICS = (
    "threshold is a similarity tolerance: 0.0 requires exact text and 1.0 "
    "accepts any extracted text as similar."
)


class CompareMode(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"


class CompareTier(str, Enum):
    TEXT = "text"
    EXTRACTED_TEXT = "extracted-text"
    BINARY = "binary"
    INCOMPATIBLE = "incompatible"


class CompareTarget(str, Enum):
    FILE = "file"
    FOLDER = "folder"


class ExitCode(IntEnum):
    IDENTICAL = 0
    DIFFERENT = 1
    ERROR = 2


TEXT_EXTENSIONS = {
    ".txt", ".md", ".rst", ".log",
    ".csv", ".tsv",
    ".json", ".yaml", ".yml",
    ".ini", ".cfg",
    ".xml", ".html",
    ".py", ".js", ".ts", ".java", ".c", ".cpp", ".sh",
}

EXTRACTED_TEXT_EXTENSIONS = {
    ".docx", ".odt", ".pptx", ".pdf", ".epub", ".xlsx",
}
