# mtw_extractor.py
import os
import csv
import struct
import re
import math
from datetime import datetime

from .path_utils import normalize_path
from .extract_utils import store_metadata

try:
    import olefile
    OLE_AVAILABLE = True
except ImportError:
    OLE_AVAILABLE = False


def _stream_suffix(stream_name) -> str:
    name = (
        "_".join(stream_name)
        if isinstance(stream_name, (list, tuple))
        else str(stream_name)
    )
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")
    return name.lower() or "stream"


def _printable_strings(data: bytes, min_len: int = 3):
    strings = re.findall(rb"[ -~]{%d,}" % min_len, data)
    return [s.decode("latin-1", errors="replace").strip() for s in strings]


def _clean_note_text(text: str) -> str:
    text = re.sub(r"[^\x20-\x7E\n\r\t]", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip(" ,;\n\r\t")


def _extract_text_notes(data: bytes):
    skip_values = {"MTB12   WIN", "Arial", "WORK", "ADDR"}
    notes = []

    for item in _printable_strings(data, min_len=4):
        cleaned = _clean_note_text(item)
        if not cleaned:
            continue
        if cleaned in skip_values or cleaned.startswith("MTB12 WIN"):
            continue
        if re.fullmatch(r"[A-Z0-9_.~-]+\.MTW", cleaned, flags=re.IGNORECASE):
            continue
        if cleaned.startswith("CmColumn"):
            continue
        if len(cleaned) >= 24 or " " in cleaned:
            notes.append(cleaned)

    deduped = []
    seen = set()
    for note in notes:
        key = note.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(note)
    return deduped


def _extract_column_names(data: bytes):
    text = "\n".join(_extract_text_notes(data))
    names = re.findall(r"<([^<>]{1,80})>", text)

    if not names:
        for item in _printable_strings(data, min_len=3):
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_ -]{1,40}", item):
                if item in {"Arial", "WIN", "WORK", "ADDR"}:
                    continue
                if item.startswith("CmColumn"):
                    continue
                names.append(item.strip())

    cleaned = []
    seen = set()
    for name in names:
        name = re.sub(r"\s+", "_", name.strip())
        name = re.sub(r"[^A-Za-z0-9_ -]+", "", name).strip("_ -")
        if not name:
            continue
        key = name.lower()
        if key not in seen:
            seen.add(key)
            cleaned.append(name)
    return cleaned


def _is_plausible_double(value: float) -> bool:
    return math.isfinite(value) and abs(value) > 1e-12 and abs(value) < 1_000_000_000


def _extract_numeric_columns(data: bytes, min_values: int = 3):
    candidates = []

    for start in range(0, max(0, len(data) - 7)):
        values = []
        offset = start
        while offset + 8 <= len(data):
            value = struct.unpack_from("<d", data, offset)[0]
            if not _is_plausible_double(value):
                break
            values.append(value)
            offset += 8

        if len(values) >= min_values:
            candidates.append((start, start + (len(values) * 8), values))

    chosen = []
    for start, end, values in sorted(
        candidates, key=lambda item: (-len(item[2]), item[0])
    ):
        overlaps = any(
            not (end <= prev_start or start >= prev_end)
            for prev_start, prev_end, _ in chosen
        )
        if not overlaps:
            chosen.append((start, end, values))

    chosen.sort(key=lambda item: item[0])
    return [values for _, _, values in chosen]


def _format_number(value: float):
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.12g}"


def _worksheet_rows(columns):
    max_len = max((len(col) for col in columns), default=0)
    rows = []
    for index in range(max_len):
        rows.append([
            _format_number(column[index]) if index < len(column) else ""
            for column in columns
        ])
    return rows


def _worksheet_payload(data: bytes):
    columns = _extract_numeric_columns(data)
    names = _extract_column_names(data)

    if len(names) < len(columns):
        names.extend(
            f"column_{idx}" for idx in range(len(names) + 1, len(columns) + 1)
        )
    else:
        names = names[:len(columns)]

    return names, _worksheet_rows(columns), _extract_text_notes(data)


def _extract_mtw(path: str, output_dir: str = None, extended: bool = False):
    """
    Extracts contents and metadata from Minitab MTW files.

    - Reads OLE property streams (SummaryInformation) to extract basic metadata.
    - Falls back to filesystem timestamps if OLE metadata not present.
    - Processes OLE streams: Worksheets, WorksheetInfo, text, ints, binary fallback.
    - Saves extracted metadata via store_metadata().
    - Returns list of generated artifact file paths.
    """

    # --- Normalize paths ---
    path = normalize_path(path)
    if not output_dir:
        output_dir = os.path.dirname(path)
    output_dir = normalize_path(output_dir)
    base = os.path.join(output_dir, os.path.splitext(os.path.basename(path))[0])

    generated_files = []

    def clean_wsinfo_text(text: str) -> str:
        """Clean WorksheetInfo text into a human-readable sentence."""

        # Remove nulls and non-printable chars
        text = re.sub(r"[^\x20-\x7E\n\r\t]", " ", text)

        # Drop leading junk markers (like G, G,@,@)
        text = re.sub(r"(?:G\s*,?\s*)+|(?:@\s*,?\s*)+", " ", text)

        # Fix spaced-out letters: "D a t a   f r o m" -> "Data from"
        text = re.sub(
            r"(?:[A-Za-z]\s){2,}",
            lambda m: m.group(0).replace(" ", ""),
            text,
        )

        # Fix spaced-out numbers: "1 9 9 9" -> "1999"
        text = re.sub(
            r"(?:\d\s){2,}\d",
            lambda m: m.group(0).replace(" ", ""),
            text,
        )

        # Collapse multiple spaces/commas
        text = re.sub(r"\s{2,}", " ", text)
        text = re.sub(r"\s+,", ",", text)

        # Strip leading/trailing junk
        text = text.strip(" ,.;:-\n\r\t")

        # Try to extract a clean sentence
        match = re.search(r"[A-Z][^.?!]+[.?!]", text)
        if match:
            return match.group(0).strip()

        return text.strip()

    def write_notes(notes_file, notes):
        with open(notes_file, "w", encoding="utf-8") as out:
            out.write("\n\n".join(notes).strip() + "\n")
        generated_files.append(notes_file)

    def process_stream(base, name, raw):
        """Decode Worksheet/WorksheetInfo/Text or fallback to binary."""
        suffix = _stream_suffix(name)
        is_wsinfo = "worksheetinfo" in suffix
        is_worksheet = suffix in {"worksheet", "worksheetdata"} or (
            "worksheet" in suffix and not is_wsinfo
        )

        if is_wsinfo and not extended:
            return

        try:
            # --- Only process WorksheetInfo if extended flag is set ---
            if is_wsinfo:
                text = clean_wsinfo_text("\n".join(_extract_text_notes(raw)))
                if not text:
                    bin_file = normalize_path(f"{base}_{suffix}.bin")
                    with open(bin_file, "wb") as out:
                        out.write(raw)
                    generated_files.append(bin_file)
                    return

                csv_file = normalize_path(f"{base}_{suffix}.csv")
                with open(csv_file, "w", encoding="utf-8") as out:
                    out.write(text + "\n")
                generated_files.append(csv_file)

                # store independent metadata
                ws_metadata = {
                    "path": csv_file,
                    "format": "worksheetinfo",
                    "parent": path,
                    "content": text
                }
                store_metadata(csv_file, ws_metadata)
                print(f"📑 Independent worksheetinfo metadata saved for {csv_file}")

            elif is_worksheet:
                names, rows, notes = _worksheet_payload(raw)
                if rows:
                    csv_file = normalize_path(f"{base}_{suffix}.csv")
                    with open(csv_file, "w", encoding="utf-8", newline="") as fh:
                        writer = csv.writer(fh)
                        writer.writerow(names)
                        writer.writerows(rows)
                    generated_files.append(csv_file)

                if notes:
                    notes_file = normalize_path(f"{base}_{suffix}_notes.txt")
                    write_notes(notes_file, notes)

                if not rows and not notes:
                    bin_file = normalize_path(f"{base}_{suffix}.bin")
                    with open(bin_file, "wb") as out:
                        out.write(raw)
                    generated_files.append(bin_file)

            else:  # generic stream -> txt
                notes = _extract_text_notes(raw)
                if notes:
                    txt_file = normalize_path(f"{base}_{suffix}.txt")
                    write_notes(txt_file, notes)
                elif extended:
                    bin_file = normalize_path(f"{base}_{suffix}.bin")
                    with open(bin_file, "wb") as out:
                        out.write(raw)
                    generated_files.append(bin_file)

        except Exception:
            bin_file = normalize_path(f"{base}_{suffix}.bin")
            with open(bin_file, "wb") as out:
                out.write(raw)
            generated_files.append(bin_file)

    # --- Initialize metadata ---
    metadata = {"format": "mtw"}

    # --- Extract OLE metadata ---
    if OLE_AVAILABLE and olefile.isOleFile(path):
        try:
            with olefile.OleFileIO(path) as ole:
                if ole.exists("\x05SummaryInformation"):
                    smeta = ole.get_metadata()
                    metadata.update({
                        "title": smeta.title,
                        "author": smeta.author,
                        "subject": smeta.subject,
                        "last_modified_by": smeta.last_saved_by,
                        "created": str(smeta.create_time) if smeta.create_time else None,
                        "last_modified": str(smeta.last_saved_time) if smeta.last_saved_time else None,
                    })
        except Exception as e:
            print(f"⚠️ Failed to read OLE metadata: {e}")

    # --- Fallback filesystem timestamps ---
    try:
        stat = os.stat(path)
        metadata.setdefault("created", datetime.fromtimestamp(stat.st_ctime).isoformat())
        metadata.setdefault("last_modified", datetime.fromtimestamp(stat.st_mtime).isoformat())
    except Exception:
        pass

    # --- Process file streams ---
    def is_ole_file(path):
        if not OLE_AVAILABLE:
            return False
        try:
            ole = olefile.OleFileIO(path)
            ole.close()
            return True
        except Exception:
            return False

    if is_ole_file(path):
        with olefile.OleFileIO(path) as ole:
            for stream_name in ole.listdir():
                stream_base = "_".join(stream_name)
                with ole.openstream(stream_name) as s:
                    raw = s.read()
                process_stream(base, stream_base, raw)
    else:
        with open(path, "rb") as f:
            raw = f.read()
        process_stream(base, "Worksheet", raw)

    # --- Store main MTW metadata ---
    print(f"🔎 Extracted metadata for {path}: {metadata}")
    store_metadata(path, metadata)

    print(f"📑 Metadata saved for {path}: {metadata}")
    return generated_files
