# OCR engine comparison

`benchmarks/ocr_benchmark.py` renders seeded synthetic report pages (invented values; 14 laboratory
rows and, on half the pages, four impression sentences) in six system fonts, degrades them as a clean
scan, a phone photograph and a low-resolution fax, and reads every page with each available engine.
Results are written to `benchmarks/results/ocr-benchmark-*.json` and charted in Research Analytics.

Scores: character and word error rate against the rendered text (order-sensitive), laboratory values
recovered end to end through MedTwin's extractor (relative to what it extracts from the rendered text),
negated statements kept, and seconds per page. Real hand-transcribed pages can be scored privately
with `--gold-dir` and `--private-out` (outside the repository).

## Run of 2026-10-29 (12 pages, 16-core CPU)

| Engine | Lab values read (clean / photo / low-res) | CER clean | s/page |
| --- | --- | --- | --- |
| RapidOCR as MedTwin runs it (no angle classifier, box threshold 0.3) | 96% / 93% / 94% | 2.6% | 2.1-2.5 |
| RapidOCR with the per-box angle classifier | 64% / 76% / 62% | 7.3% | 2.0-3.3 |
| RapidOCR, default box threshold 0.5 | 96% / 93% / 94% | 2.6% | 2.1-2.2 |
| Windows OCR (word boxes grouped into rows by MedTwin) | 74% / 54% / 58% | 2.9% | 0.2-0.3 |

Tesseract was not installed and was not compared. Every engine kept all negations.

Reading: the angle classifier costs a third of the laboratory values, which supports reading without
it. Windows OCR is about ten times faster and makes fewer word errors, but loses more values. The
default box threshold matches 0.3 on these clean synthetic pages; 0.3 was chosen for faint lines on
real photographs, which synthetic pages do not have. Synthetic pages in system fonts are easier than
real photographed reports; the scores rank engines for this pipeline and are not an accuracy claim.
