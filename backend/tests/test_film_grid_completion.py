"""Montage cells the contour pass misses are recovered from the panel lattice (synthetic films only)."""
import io

from PIL import Image, ImageDraw

from app.services import film_processing


def montage(columns: int, rows: int, faint: set[tuple[int, int]], empty: set[tuple[int, int]] = frozenset()) -> Image.Image:
    """Skull-like ellipses on black film; 'faint' cells have no bright outline (the contour pass cannot see them)."""
    image = Image.new("RGB", (columns * 200, rows * 240), "black")
    draw = ImageDraw.Draw(image)
    for row in range(rows):
        for col in range(columns):
            if (row, col) in empty:
                continue
            x, y = col * 200 + 15, row * 240 + 10
            if (row, col) in faint:
                draw.ellipse((x, y, x + 170, y + 215), fill=(60, 100, 115))
            else:
                draw.ellipse((x, y, x + 170, y + 215), fill=(55, 95, 110), outline="white", width=12)
    return image


def assess(image: Image.Image) -> dict:
    data = io.BytesIO()
    image.save(data, "PNG")
    data.seek(0)
    return film_processing.assess_raster(Image.open(data))


def test_faint_cells_of_a_regular_montage_are_recovered_and_marked():
    faint = {(0, 1), (1, 3), (1, 4), (0, 4)}
    result = assess(montage(5, 2, faint))
    assert len(result["panels"]) == 10
    inferred = [(panel["row"], panel["column"]) for panel in result["panels"] if panel["detection"] == "GRID_COMPLETION"]
    assert sorted(inferred) == sorted(faint)
    assert result["source_type"] == "FILM_MONTAGE_CANDIDATE"


def test_empty_cells_are_not_turned_into_panels():
    result = assess(montage(4, 2, faint=set(), empty={(1, 2), (1, 3)}))
    assert len(result["panels"]) == 6 and all(panel["detection"] == "CONTOUR" for panel in result["panels"])


def test_a_complete_montage_needs_no_completion():
    result = assess(montage(5, 2, faint=set()))
    assert len(result["panels"]) == 10 and all(panel["detection"] == "CONTOUR" for panel in result["panels"])
