"""Whole-slide images (tiled, pyramidal TIFF: Aperio SVS, Hamamatsu NDPI, generic tiled TIFF) read tile by tile.

Only the tiles a requested region touches are decoded, so a slide never has to fit in memory. Microns per pixel and
the scanning magnification are read from the scanner's ImageDescription where present. A tissue grid marks tiles with
stained tissue by a fixed brightness/saturation rule; it is a viewing and sampling aid, not a model. No pathology model is
registered: slide-level labels are needed to train or evaluate one.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

WSI_SUFFIXES = {".svs", ".tif", ".tiff", ".ndpi"}
MAX_REGION = 2048
THUMBNAIL_MAX = 2048
MAX_THUMBNAIL_SOURCE = 16384  # the smallest level is read region by region; larger means the slide has no usable pyramid
MAX_UNTILED_PIXELS = 8192 * 8192
MAX_TILE_PIXELS = 4096 * 4096
MAX_TILE_BYTES = 64 * 1024**2
TISSUE_RULE = "a pixel is tissue when it is darker than 220/255 (grey) and its saturation is at least 0.07; a tile is tissue when 40% or more of it is"


class WsiError(ValueError):
    """The file is not a readable tiled, pyramidal whole-slide image."""


def _jpeg_tile(data: bytes, tables: bytes | None, width: int, height: int) -> np.ndarray:
    """Decode bounded baseline JPEG with Pillow's codec, independently of imagecodecs.

    TIFF may store shared JPEG tables outside each tile. JPEG SOI/EOI markers
    are removed only at the join; the original slide is never modified.
    """
    if width * height > MAX_TILE_PIXELS or len(data) + len(tables or b"") > MAX_TILE_BYTES:
        raise WsiError("WSI_TILE_TOO_LARGE: compressed tile or decoded dimensions exceed the viewing budget.")
    if tables:
        if not (tables.startswith(b"\xff\xd8") and tables.endswith(b"\xff\xd9") and data.startswith(b"\xff\xd8")):
            raise WsiError("WSI_INVALID_JPEG_TABLES: shared JPEG tables or tile markers are invalid.")
        data = tables[:-2] + data[2:]
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format != "JPEG" or image.size != (width, height):
                raise WsiError("WSI_JPEG_GEOMETRY_MISMATCH: decoded tile dimensions differ from the TIFF grid.")
            return np.array(image.convert("RGB"))
    except WsiError:
        raise
    except Exception as exc:
        raise WsiError(f"WSI_JPEG_UNREADABLE: {type(exc).__name__}") from exc


def _levels(tif) -> list[Any]:
    series = tif.series[0]
    levels = [level.pages[0] for level in series.levels]
    if not levels or levels[0].ndim < 2:
        raise WsiError("WSI_UNREADABLE: no image pyramid was found.")
    return levels


def _mpp(description: str) -> tuple[float | None, float | None]:
    mpp = re.search(r"MPP\s*=\s*([0-9.]+)", description or "")
    magnification = re.search(r"AppMag\s*=\s*([0-9.]+)", description or "")
    return (float(mpp.group(1)) if mpp else None), (float(magnification.group(1)) if magnification else None)


def describe(path: Path) -> dict[str, Any]:
    import tifffile

    try:
        with tifffile.TiffFile(str(path)) as tif:
            levels = _levels(tif)
            base = levels[0]
            if not base.is_tiled:
                raise WsiError("WSI_NOT_TILED: the TIFF is not tiled; whole-slide images are read one tile at a time.")
            mpp, magnification = _mpp(tif.pages[0].description)
            if mpp is None and base.tags.get("XResolution") is not None and base.tags.get("ResolutionUnit") is not None:
                unit = base.tags["ResolutionUnit"].value
                numerator, denominator = base.tags["XResolution"].value
                if int(unit) == 3 and numerator:  # pixels per centimetre
                    mpp = round(1e4 * denominator / numerator, 4)
            height, width = base.shape[:2]
            return {
                "format": "NDPI" if tif.is_ndpi else "SVS" if tif.is_svs else "TIFF",
                "dimensions": [int(width), int(height)],
                "levels": [{"level": index, "width": int(page.shape[1]), "height": int(page.shape[0]),
                            "downsample": round(width / page.shape[1], 3), "tiled": bool(page.is_tiled),
                            "tile": [int(page.tilewidth), int(page.tilelength)] if page.is_tiled else None}
                           for index, page in enumerate(levels)],
                "microns_per_pixel": mpp, "objective_magnification": magnification,
                "samples_per_pixel": int(base.samplesperpixel), "compression": str(base.compression.name) if hasattr(base.compression, "name") else str(base.compression),
            }
    except WsiError:
        raise
    except Exception as exc:  # tifffile raises many types for corrupt or non-TIFF content
        raise WsiError(f"WSI_UNREADABLE: {type(exc).__name__}") from exc


def read_region(path: Path, level: int, x: int, y: int, width: int, height: int) -> np.ndarray:
    """RGB pixels of [x, x + width) x [y, y + height) at one pyramid level, decoding only the tiles it touches."""
    import tifffile

    if not (0 < width <= MAX_REGION and 0 < height <= MAX_REGION):
        raise WsiError(f"REGION_TOO_LARGE: at most {MAX_REGION} x {MAX_REGION} pixels per request.")
    with tifffile.TiffFile(str(path)) as tif:
        levels = _levels(tif)
        if not 0 <= level < len(levels):
            raise WsiError(f"LEVEL_OUTSIDE_PYRAMID: levels are 0-{len(levels) - 1}.")
        page = levels[level]
        page_height, page_width = page.shape[:2]
        if x < 0 or y < 0 or x >= page_width or y >= page_height:
            raise WsiError("REGION_OUTSIDE_SLIDE: the region starts outside this level.")
        width, height = min(width, page_width - x), min(height, page_height - y)
        out = np.full((height, width, 3), 255, dtype=np.uint8)
        if not page.is_tiled:
            if page_width * page_height > MAX_UNTILED_PIXELS:
                raise WsiError("UNTILED_LEVEL_TOO_LARGE: this pyramid level is not tiled and too large to read whole.")
            data = page.asarray()
            region = data[y:y + height, x:x + width]
            out[:region.shape[0], :region.shape[1]] = region[..., :3] if region.ndim == 3 else region[..., None]
            return out
        tile_width, tile_height = page.tilewidth, page.tilelength
        if tile_width * tile_height > MAX_TILE_PIXELS or int(page.planarconfig) != 1:
            raise WsiError("WSI_TILE_LAYOUT_UNSUPPORTED: tiles must be bounded and use contiguous colour samples.")
        across = -(-page_width // tile_width)
        handle = tif.filehandle
        # Build the decoder before seeking: creating it can move the shared file position.
        jpeg = int(page.compression) == 7
        if jpeg and (page.bitspersample != 8 or page.samplesperpixel not in (1, 3) or int(page.photometric) not in (1, 2, 6)):
            raise WsiError("WSI_JPEG_LAYOUT_UNSUPPORTED: only 8-bit grey, RGB or YCbCr baseline JPEG tiles are supported.")
        decode, jpegtables = (None if jpeg else page.decode), page.jpegtables
        for row in range(y // tile_height, (y + height - 1) // tile_height + 1):
            for column in range(x // tile_width, (x + width - 1) // tile_width + 1):
                index = row * across + column
                if index >= len(page.dataoffsets) or not page.databytecounts[index]:
                    continue
                if page.databytecounts[index] > MAX_TILE_BYTES:
                    raise WsiError("WSI_TILE_TOO_LARGE: compressed tile exceeds the viewing budget.")
                handle.seek(page.dataoffsets[index])
                data = handle.read(page.databytecounts[index])
                segment = _jpeg_tile(data, jpegtables, tile_width, tile_height) if jpeg else decode(data, index, jpegtables=jpegtables)[0]
                if segment is None:
                    continue
                tile = np.asarray(segment).reshape(tile_height, tile_width, -1)
                tile = tile[..., :3] if tile.shape[-1] >= 3 else np.repeat(tile[..., :1], 3, axis=-1)
                top, left = row * tile_height, column * tile_width
                y0, x0 = max(y, top), max(x, left)
                y1, x1 = min(y + height, top + tile_height), min(x + width, left + tile_width)
                out[y0 - y:y1 - y, x0 - x:x1 - x] = tile[y0 - top:y1 - top, x0 - left:x1 - left]
        return out


def thumbnail(path: Path) -> tuple[np.ndarray, dict[str, Any]]:
    """The smallest pyramid level, scaled to at most THUMBNAIL_MAX on its long side, built one region at a time so
    memory stays bounded by the thumbnail. A slide whose smallest level is far larger is refused."""
    info = describe(path)
    level = next((item for item in reversed(info["levels"]) if max(item["width"], item["height"]) <= THUMBNAIL_MAX), info["levels"][-1])
    long_side = max(level["width"], level["height"])
    if long_side > MAX_THUMBNAIL_SOURCE:
        raise WsiError(f"WSI_NO_REDUCED_LEVEL: the smallest pyramid level is {level['width']} x {level['height']} px; a slide needs a level of at most "
                       f"{MAX_THUMBNAIL_SOURCE} px on its long side to be previewed.")
    scale = min(1.0, THUMBNAIL_MAX / long_side)
    canvas = Image.new("RGB", (max(1, round(level["width"] * scale)), max(1, round(level["height"] * scale))), (255, 255, 255))
    for y in range(0, level["height"], MAX_REGION):
        for x in range(0, level["width"], MAX_REGION):
            region = read_region(path, level["level"], x, y, min(MAX_REGION, level["width"] - x), min(MAX_REGION, level["height"] - y))
            piece = Image.fromarray(region)
            if scale < 1.0:
                piece = piece.resize((max(1, round(region.shape[1] * scale)), max(1, round(region.shape[0] * scale))))
            canvas.paste(piece, (round(x * scale), round(y * scale)))
    image = np.asarray(canvas)
    return image, {"level": level["level"], "downsample_from_level0": round(level["downsample"] / scale, 3), "width": image.shape[1], "height": image.shape[0]}


def tissue_grid(path: Path, tile: int = 256) -> dict[str, Any]:
    """Level-0 tiles of ``tile`` pixels that contain tissue, estimated on the thumbnail."""
    image, thumb = thumbnail(path)
    rgb = image.astype(np.float32) / 255.0
    grey = rgb.mean(axis=2)
    saturation = (rgb.max(axis=2) - rgb.min(axis=2)) / np.maximum(rgb.max(axis=2), 1e-6)
    tissue = (grey < 220 / 255) & (saturation >= 0.07)
    factor = thumb["downsample_from_level0"]
    info = describe(path)
    width, height = info["dimensions"]
    cells = []
    for y in range(0, height, tile):
        for x in range(0, width, tile):
            region = tissue[int(y / factor):max(int(y / factor) + 1, int((y + tile) / factor)), int(x / factor):max(int(x / factor) + 1, int((x + tile) / factor))]
            if region.size and float(region.mean()) >= 0.4:
                cells.append([x, y])
    total = (-(-width // tile)) * (-(-height // tile))
    return {"tile_size_px": tile, "level": 0, "tissue_tiles": cells, "tissue_tile_count": len(cells), "total_tiles": total,
            "tissue_fraction_of_thumbnail": round(float(tissue.mean()), 4), "rule": TISSUE_RULE,
            "semantics": "A fixed colour rule for viewing and tile sampling; not a model and not evaluated against annotated slides."}


def png(array: np.ndarray) -> bytes:
    data = io.BytesIO()
    Image.fromarray(array).save(data, format="PNG")
    return data.getvalue()
