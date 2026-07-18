"""Side-effect-free constants shared by rename command implementations."""

SUPPORTED_DATE_FORMATS = [
    "%Y%m%d",
    "%Y-%m-%d",
    "%y%m%d",
    "%d-%m-%Y",
    "%d%m%Y",
]

DEFAULT_PATTERN = "{date}-{title}"
