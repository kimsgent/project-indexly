from PIL import Image

from indexly.extract_utils import extract_image_metadata


def test_extract_image_metadata_handles_bmp_without_exif_warning(tmp_path, capsys):
    image_path = tmp_path / "sample.bmp"
    Image.new("RGB", (2, 3), color="white").save(image_path)

    metadata = extract_image_metadata(str(image_path))

    assert metadata["dimensions"] == "2x3"
    assert metadata["format"] == "BMP"
    assert "created" in metadata
    assert "last_modified" in metadata
    assert "Failed to extract image metadata" not in capsys.readouterr().out
