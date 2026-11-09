"""A brain-CT finding read by OCR without spaces must still be extracted with its site.

Synthetic report text in the glued form photographed bold print produces (one OCR slip that merges
"parietal lobe"); no patient report is used."""

from app.services import ocr_text
from app.services.nlp_processor import extract_clinical_statements


def test_a_glued_sentence_with_one_short_ocr_slip_is_split():
    normalised, index = ocr_text.normalise("RighthighparietalobeHemorrhagiccontusionwithmildperilesionaledema.")
    assert normalised.startswith("Right high parietal obe Hemorrhagic contusion with mild perilesional edema")
    assert index is not None and index[-1] == len("RighthighparietalobeHemorrhagiccontusionwithmildperilesionaledema.")


def test_short_unknown_words_are_still_left_alone():
    assert ocr_text._segment("spondylotic") is None
    assert ocr_text._segment("Sitagliptinmetformin") is None, "a 20-letter run with two unknown pieces is not split"


def test_contusion_and_oedema_are_extracted_with_the_parietal_lobe():
    text = ("FINDINGS:\nRighthighparietalobeHemorrhagiccontusionwithmildperilesionaledema.\nNo midline shift.\n"
            "IMPRESSION:\nRIGHTHIGH PARIETALLOBEHEMORRHAGICCONTUSION.\n")
    statements = extract_clinical_statements(text)
    contusions = [item for item in statements if item["entity"] == "Cerebral contusion"]
    assert len(contusions) == 2 and all(item["negation"] == "AFFIRMED" for item in contusions)
    assert all(item["atlas_structure_id"] == "nervous.parietal_lobe" for item in contusions)
    assert any(item["entity"] == "Cerebral oedema" and item["negation"] == "AFFIRMED" for item in statements)
    assert any(item["entity"] == "Midline shift" and item["negation"] == "NEGATED" for item in statements)
    for item in contusions:  # spans quote the text exactly as read
        assert text[item["source_span_start"]:item["source_span_end"]] == item["source_span"]
    from app.services.terminology import atlas_structure_name
    # The atlas name lets models whose parts carry their own ids (the lobe-labelled brain) light up the lobe.
    assert atlas_structure_name("nervous.parietal_lobe") == "Parietal lobe"
