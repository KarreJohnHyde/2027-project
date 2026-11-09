"""Whole-slide images: tiled pyramid reading, tissue grid and the upload/view path (generated slides only)."""
import numpy as np
import pytest
import io
from PIL import Image

tifffile = pytest.importorskip("tifffile")

from app.services import wsi_reader  # noqa: E402
from tests.conftest import get_auth_headers  # noqa: E402


def slide(path, compression="jpeg"):
    """A 1536 x 1024 generated slide: white glass with a purple 'tissue' block, two reduced levels."""
    base = np.full((1024, 1536, 3), 240, np.uint8)
    base[200:800, 300:1200] = (150, 60, 140)
    def write(writer, pixels, **options):
        if compression != "jpeg":
            return writer.write(pixels, tile=(256, 256), photometric="rgb", compression=compression, **options)
        def encoded_tiles():
            for y in range(0, pixels.shape[0], 256):
                for x in range(0, pixels.shape[1], 256):
                    tile = np.full((256, 256, 3), 240, np.uint8)
                    region = pixels[y:y + 256, x:x + 256]
                    tile[:region.shape[0], :region.shape[1]] = region
                    buffer = io.BytesIO()
                    Image.fromarray(tile).save(buffer, format="JPEG", subsampling=0)
                    yield buffer.getvalue()
        return writer.write(encoded_tiles(), shape=pixels.shape, dtype=pixels.dtype,
                            tile=(256, 256), photometric="ycbcr", compression="jpeg", subsampling=(1, 1), **options)
    with tifffile.TiffWriter(str(path)) as writer:
        write(writer, base, subifds=2, description="Aperio Image Library v12 |MPP = 0.5|AppMag = 20")
        for factor in (2, 4):
            write(writer, base[::factor, ::factor], subfiletype=1)
    return path, base


def test_describe_reads_the_pyramid_and_scanner_resolution(tmp_path):
    path, _ = slide(tmp_path / "slide.svs")
    info = wsi_reader.describe(path)
    assert info["dimensions"] == [1536, 1024] and [level["downsample"] for level in info["levels"]] == [1.0, 2.0, 4.0]
    assert info["microns_per_pixel"] == 0.5 and info["objective_magnification"] == 20.0


def test_shared_table_jpeg_tiles_match_the_independent_full_jpeg():
    encoded = io.BytesIO()
    Image.new("RGB", (64, 48), (130, 70, 110)).save(encoded, format="JPEG")
    original = encoded.getvalue()
    tables, remaining, offset = [], [], 2
    # Export real JPEG Huffman/quantization tables into TIFF's shared-table form.
    while offset < len(original):
        marker = original[offset + 1]
        if marker == 0xda:  # start of scan: keep entropy-coded bytes intact
            remaining.append(original[offset:])
            break
        length = int.from_bytes(original[offset + 2:offset + 4], "big")
        segment = original[offset:offset + 2 + length]
        (tables if marker in (0xc4, 0xdb) else remaining).append(segment)
        offset += 2 + length
    shared = b"\xff\xd8" + b"".join(tables) + b"\xff\xd9"
    tile = b"\xff\xd8" + b"".join(remaining)
    expected = np.asarray(Image.open(io.BytesIO(original)).convert("RGB"))
    assert np.array_equal(wsi_reader._jpeg_tile(tile, shared, 64, 48), expected)
    with pytest.raises(wsi_reader.WsiError, match="GEOMETRY_MISMATCH"):
        wsi_reader._jpeg_tile(tile, shared, 63, 48)
    with pytest.raises(wsi_reader.WsiError, match="INVALID_JPEG_TABLES"):
        wsi_reader._jpeg_tile(tile, b"invalid tables", 64, 48)
    with pytest.raises(wsi_reader.WsiError, match="TILE_TOO_LARGE"):
        wsi_reader._jpeg_tile(tile, shared, 4097, 4097)


def test_a_region_across_tile_borders_matches_the_source(tmp_path):
    path, base = slide(tmp_path / "slide.tif", compression="zlib")  # lossless, so pixels compare exactly
    region = wsi_reader.read_region(path, 0, 200, 150, 400, 300)
    assert region.shape == (300, 400, 3) and np.array_equal(region, base[150:450, 200:600])
    small = wsi_reader.read_region(path, 2, 0, 0, 384, 256)
    assert np.array_equal(small, base[::4, ::4])


def test_regions_are_bounded_and_inside_the_slide(tmp_path):
    path, _ = slide(tmp_path / "slide.tif", compression="zlib")
    with pytest.raises(wsi_reader.WsiError, match="REGION_TOO_LARGE"):
        wsi_reader.read_region(path, 0, 0, 0, 4096, 10)
    with pytest.raises(wsi_reader.WsiError, match="LEVEL_OUTSIDE_PYRAMID"):
        wsi_reader.read_region(path, 5, 0, 0, 10, 10)


def test_the_tissue_grid_finds_the_stained_block_only(tmp_path):
    path, _ = slide(tmp_path / "slide.tif", compression="zlib")
    grid = wsi_reader.tissue_grid(path, tile=256)
    assert grid["total_tiles"] == 24 and 0 < grid["tissue_tile_count"] < 24
    assert all(300 - 256 < x < 1200 and 200 - 256 < y < 800 for x, y in grid["tissue_tiles"])


def test_a_slide_uploads_and_is_viewed_through_the_api(client, test_users, tmp_path):
    path, _ = slide(tmp_path / "slide.svs")
    headers = get_auth_headers(test_users["clinician_a"])
    case_id = client.post("/api/v1/cases", headers=headers, json={"pseudonymous_id": "SYNTHETIC-WSI"}).json()["id"]
    upload = client.post(f"/api/v1/cases/{case_id}/uploads", headers=headers, data={"deidentified": "true"},
                         files={"file": ("slide.svs", path.read_bytes(), "image/tiff")})
    assert upload.status_code == 201, upload.text
    file_id = upload.json()["id"]
    metadata = client.get(f"/api/v1/uploads/{file_id}/imaging/metadata", headers=headers).json()
    assert metadata["container"] == "WSI" and metadata["wsi"]["levels"][0]["width"] == 1536
    assert client.get(f"/api/v1/uploads/{file_id}/imaging/render", headers=headers).status_code == 200
    region = client.get(f"/api/v1/uploads/{file_id}/wsi/region", headers=headers, params={"level": 0, "x": 256, "y": 256, "width": 256, "height": 256})
    assert region.status_code == 200 and region.headers["content-type"] == "image/png"
    assert client.get(f"/api/v1/uploads/{file_id}/wsi/tissue", headers=headers).json()["tissue_tile_count"] > 0
    assert client.get(f"/api/v1/uploads/{file_id}/wsi/region", headers=get_auth_headers(test_users["clinician_b"]),
                      params={"x": 0, "y": 0}).status_code == 403
    not_tiff = client.post(f"/api/v1/cases/{case_id}/uploads", headers=headers, data={"deidentified": "true"},
                           files={"file": ("fake.svs", b"not a tiff at all", "image/tiff")})
    assert not_tiff.status_code == 415


def test_a_slide_without_a_reduced_level_is_refused_for_preview(tmp_path, monkeypatch):
    path, _ = slide(tmp_path / "slide.tif", compression="zlib")
    monkeypatch.setattr(wsi_reader, "MAX_THUMBNAIL_SOURCE", 200)  # every level of the fixture is then 'too large'
    with pytest.raises(wsi_reader.WsiError, match="WSI_NO_REDUCED_LEVEL"):
        wsi_reader.thumbnail(path)
