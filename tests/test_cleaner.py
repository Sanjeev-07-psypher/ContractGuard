import pytest

from contractguard.models import Block, Document
from contractguard.preprocessing.cleaner import clean_document
from contractguard.preprocessing.normalizer import normalize_chars


def pdf_doc(pages):
    """pages: list of lists of block texts."""
    blocks = [Block(text=t, page=i + 1) for i, page in enumerate(pages) for t in page]
    return Document(source_path="x.pdf", file_type="pdf", num_pages=len(pages), blocks=blocks)


TOPICS = ["termination", "payment", "liability", "renewal", "confidentiality", "governing law"]


def body(n):
    """Body text that differs in words (not only digits) from page to page."""
    return f"{n}. The {TOPICS[n % len(TOPICS)]} clause has its own body text."


# --------------------------------------------------------------------------- header / footer


def test_repeating_header_and_footer_removed():
    pages = [
        ["ACME Services Agreement | Confidential", body(i), f"Page {i} of 4"] for i in range(1, 5)
    ]
    cleaned = clean_document(pdf_doc(pages))
    assert "ACME Services Agreement" not in cleaned.text
    assert "Page" not in cleaned.text
    assert all(body(i) in cleaned.text for i in range(1, 5))
    assert "ACME Services Agreement | Confidential" in cleaned.removed_lines


def test_header_with_changing_digits_still_matches():
    pages = [[f"Draft v{i} - 2026-10-{10 + i}", body(i)] for i in range(1, 4)]
    assert "Draft" not in clean_document(pdf_doc(pages)).text


def test_header_kept_when_on_fewer_than_half_the_pages():
    pages = [["Schedule header", body(1)], [body(2)], [body(3)], [body(4)]]
    assert "Schedule header" in clean_document(pdf_doc(pages)).text


def test_header_removal_skipped_under_three_pages():
    pages = [["Repeated header line", body(i)] for i in range(1, 3)]
    assert "Repeated header line" in clean_document(pdf_doc(pages)).text


def test_repeated_line_outside_zones_is_kept():
    filler = [f"filler paragraph {c}" for c in "abcdefgh"]
    pages = [["Header", *filler[:4], "Either party may terminate.", *filler[4:], "Footer"]] * 3
    cleaned = clean_document(pdf_doc(pages))
    assert "Header" not in cleaned.text and "Footer" not in cleaned.text
    assert cleaned.text.count("Either party may terminate.") == 3


def test_docx_never_loses_lines_to_header_rule():
    blocks = [Block(text="Same line", para_index=i) for i in range(5)]
    doc = Document(source_path="x.docx", file_type="docx", blocks=blocks)
    assert clean_document(doc).text.count("Same line") == 5


# --------------------------------------------------------------------------- line rules


@pytest.mark.parametrize("line", ["3", "Page 3", "page 3 of 10", "  12 / 40 ", "PAGE 7"])
def test_page_number_lines_removed(line):
    doc = pdf_doc([[f"{line}\n7. Payment terms apply to every invoice."]])
    assert clean_document(doc).text == "7. Payment terms apply to every invoice."


def test_numbers_inside_sentences_are_kept():
    text = "The Company shall pay within 30\ndays of receipt."
    assert "30" in clean_document(pdf_doc([[text]])).text


def test_dehyphenation():
    doc = pdf_doc([["The Vendor shall indem-\nnify the Company."]])
    assert clean_document(doc).text == "The Vendor shall indemnify the Company."


def test_soft_wrapped_lines_joined_but_sentences_and_items_kept_apart():
    raw = (
        "Either Party may terminate this Agreement\nfor convenience.\n"
        "The Vendor shall comply:\n(a) with law."
    )
    doc = pdf_doc([[raw]])
    assert clean_document(doc).text == (
        "Either Party may terminate this Agreement for convenience.\n"
        "The Vendor shall comply:\n(a) with law."
    )


def test_number_alone_on_its_line_joins_next_line():
    doc = pdf_doc([["10.1\nEither Party may terminate this Agreement."]])
    assert clean_document(doc).text == "10.1 Either Party may terminate this Agreement."


# --------------------------------------------------------------------------- characters


def test_quotes_dashes_spaces_normalized():
    raw = "the “Agreement” – Party’s  rights — ok\tend"
    assert normalize_chars(raw) == 'the "Agreement" - Party\'s rights - ok end'


def test_nfkc_ligatures():
    assert normalize_chars("ﬁnal ﬂoor") == "final floor"


def test_case_negations_and_punctuation_preserved():
    raw = "The Licensor shall NOT be liable, unless notwithstanding; except (i) fraud."
    assert normalize_chars(raw) == raw


# --------------------------------------------------------------------------- offset map


def test_offset_map_points_back_to_pages():
    pages = [[body(1)], [body(2), body(3)], [body(4)]]
    cleaned = clean_document(pdf_doc(pages))
    start = cleaned.text.index(body(3))
    assert cleaned.span_at(start).page == 2
    assert cleaned.span_at(start).block_index == 2
    end = cleaned.text.index(body(4)) + 5
    assert cleaned.pages_for(start, end) == (2, 3)
    for span in cleaned.spans:
        assert cleaned.text[span.start : span.end] in [body(i) for i in range(1, 5)]


def test_offset_map_survives_dropped_blocks():
    pages = [["Header", "3"], ["Header", body(2)], ["Header", body(3)]]
    cleaned = clean_document(pdf_doc(pages))
    assert cleaned.text.startswith(body(2))
    assert [s.page for s in cleaned.spans] == [2, 3]


def test_ingestion_report_handles_missing_ocr_results():
    import importlib.util

    from contractguard.config import REPO_ROOT

    spec = importlib.util.spec_from_file_location(
        "eval_ingestion", REPO_ROOT / "evaluation" / "eval_ingestion.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    failed = {"ok": False, "error": "IngestionError: no tesseract"}
    ok = {"ok": True, "blocks": 3, "ocr_pages": [], "warnings": [], "seconds": 0.1}
    report = {
        "files_loaded": 2, "files_total": 3, "ocr_cer_mean": None, "ocr_cer_max": None,
        "ocr_cer_target": 0.05,
        "contracts": [{"contract": "gc01", "docx": ok, "text_pdf": ok, "scanned_pdf": failed}],
    }  # fmt: skip
    md = mod.to_markdown(report)
    assert "n/a" in md and "FAILED: IngestionError" in md
