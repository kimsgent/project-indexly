# mtw_extractor.py
import os
import struct
import re
from datetime import datetime
import pandas as pd

from .path_utils import normalize_path
from .extract_utils import store_metadata

try:
    import olefile
    OLE_AVAILABLE = True
except ImportError:
    OLE_AVAILABLE = False


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

    # --- Helpers ---
    def extract_integers(data):
        return [
            struct.unpack("<i", data[i: i + 4])[0]
            for i in range(0, len(data) - 4, 4)
            if 0 <= struct.unpack("<i", data[i: i + 4])[0] < 10000
        ]

    def clean_wsinfo_text(text: str) -> str:
        """Clean WorksheetInfo text into a human-readable sentence."""

        # Remove nulls and non-printable chars
        text = re.sub(r"[^\x20-\x7E\n\r\t]", " ", text)

        # Drop leading junk markers (like G, G,@,@)
        text = re.sub(r"(?:G\s*,?\s*)+|(?:@\s*,?\s*)+", " ", text)

        # Fix spaced-out letters: "D a t a   f r o m" -> "Data from"
        text = re.sub(r"(?:[A-Za-z]\s){2,}", 
                    lambda m: m.group(0).replace(" ", ""), 
                    text)

        # Fix spaced-out numbers: "1 9 9 9" -> "1999"
        text = re.sub(r"(?:\d\s){2,}\d", 
                    lambda m: m.group(0).replace(" ", ""), 
                    text)

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

    def process_stream(base, name, raw):
        """Decode Worksheet/WorksheetInfo/Text or fallback to binary."""
        try:
            text = raw.decode("utf-8", errors="replace")

            # --- Only process WorksheetInfo if extended flag is set ---
            if extended and "WorksheetInfo" in name:
                text = clean_wsinfo_text(text)

                csv_file = normalize_path(f"{base}_{name}.csv")
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

            elif "Worksheet" in name:  # normal worksheet
                csv_file = normalize_path(f"{base}_{name}.csv")
                with open(csv_file, "w", encoding="utf-8") as out:
                    out.write(text)
                generated_files.append(csv_file)

                ints = extract_integers(raw)
                if ints:
                    df = pd.DataFrame({"value": ints})
                    data_csv = normalize_path(f"{base}_{name}_data.csv")
                    df.to_csv(data_csv, index=False)
                    generated_files.append(data_csv)

            else:  # generic stream -> txt
                txt_file = normalize_path(f"{base}_{name}.txt")
                with open(txt_file, "w", encoding="utf-8") as out:
                    out.write(text)
                generated_files.append(txt_file)

        except Exception:
            bin_file = normalize_path(f"{base}_{name}.bin")
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
