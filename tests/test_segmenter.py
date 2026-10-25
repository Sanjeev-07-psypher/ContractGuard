import importlib.util

import pytest

from contractguard.config import REPO_ROOT
from contractguard.models import Block, Clause, Document
from contractguard.preprocessing.cleaner import clean_document
from contractguard.segmentation.segmenter import SegmentationRules, parse_start, segment

RULES = SegmentationRules.from_config()


def pdf_doc(pages, is_ocr=False):
    """pages: list of lists of block texts."""
    blocks = [
        Block(text=t, page=i + 1, is_ocr=is_ocr) for i, page in enumerate(pages) for t in page
    ]
    return Document(source_path="x.pdf", file_type="pdf", num_pages=len(pages), blocks=blocks)


def run(pages, **kw):
    doc = pdf_doc(pages, **kw)
    return segment(clean_document(doc), doc)


SENT = "The Vendor shall perform this obligation in good faith and on time."

CONTRACT = [
    [
        "SERVICES AGREEMENT\nThis Agreement is made between ACME Ltd and ABC Technologies.",
        f"1. DEFINITIONS\nIn this Agreement, words have the meanings below. {SENT}",
        f"2. Services\n{SENT}\n(a) first item of the services;\n(b) second item.",
    ],
    [
        "3. TERM\n3.1 This Agreement starts on the Effective Date and lasts one year.",
        f"3.2 Either Party may renew it by written notice. {SENT}",
        f"4. Payment\n{SENT}",
        "IN WITNESS WHEREOF the Parties have signed this Agreement.\nBy: ______",
        "SCHEDULE 1 - SERVICE LEVELS\nUptime | 99.5%",
    ],
]


@pytest.fixture(scope="module")
def clauses() -> list[Clause]:
    return run(CONTRACT)


# --------------------------------------------------------------------------- structure


def test_clause_kinds_and_order(clauses):
    assert [c.kind for c in clauses] == [
        "PREAMBLE", "DEFINITIONS", "BODY", "BODY", "BODY", "BODY", "SIGNATURE", "EXHIBIT",
    ]  # fmt: skip
    assert [c.clause_id for c in clauses] == [f"c{i:03d}" for i in range(1, 9)]


def test_numbers_headings_and_paths(clauses):
    got = [(c.number, c.heading, c.section_path) for c in clauses]
    assert got[1] == ("1", "Definitions", "1")
    assert got[2] == ("2", "Services", "2")
    # "3. TERM" is shorter than min_chars, so it merges into 3.1 and gives it its heading
    assert got[3] == ("3.1", "Term", "3 > 3.1")
    assert got[4] == ("3.2", None, "3 > 3.2")
    assert got[6] == (None, None, "SIGNATURE")
    assert got[7][1] == "SCHEDULE 1 - SERVICE LEVELS"


def test_lettered_items_stay_in_parent(clauses):
    services = clauses[2]
    assert "(a) first item" in services.text and "(b) second item." in services.text


def test_signature_block_keeps_by_lines(clauses):
    assert clauses[6].text.endswith("By: ______")


def test_text_matches_offsets_and_pages(clauses):
    cleaned = clean_document(pdf_doc(CONTRACT))
    for c in clauses:
        assert cleaned.text[c.char_start : c.char_end] == c.text
        assert c.text == c.text.strip()
    assert clauses[2].page_start == 1 and clauses[3].page_start == 2
    assert not any(c.is_ocr for c in clauses)


def test_ocr_flag_is_carried(clauses):
    assert all(c.is_ocr for c in run(CONTRACT, is_ocr=True))


# --------------------------------------------------------------------------- start lines


@pytest.mark.parametrize(
    "line, expected",
    [
        ("ARTICLE Ill - CONFIDENTIALITY OBLIGATIONS", ("III", "Confidentiality Obligations")),
        ("ARTICLE | - PURPOSE", ("I", "Purpose")),
        ("ARTICLE Vil - TERM AND RENEWAL", ("VII", "Term and Renewal")),
        ("ARTICLE 4 - Fees", ("4", "Fees")),
        ("SECTION 12: Notices", ("12", "Notices")),
        ("4. Contract Price and Payment", ("4", "Contract Price and Payment")),
        ("10.2 If either Party commits a material breach", ("10.2", None)),
        # a wrapped sentence is short and has no full stop, but it is not Title Case
        ("10.3 On termination, the Contractor shall withdraw its", ("10.3", None)),
        ("5.1 The Client shall pay all Fees.", ("5.1", None)),
    ],
)
def test_parse_start(line, expected):
    assert parse_start(line, RULES) == expected


def test_docx_heading_style_starts_a_clause():
    blocks = [
        Block(text="Background to this agreement between the parties named below.", para_index=0),
        Block(text="Confidentiality", para_index=1, style="Heading 1"),
        Block(text=f"{SENT} {SENT}", para_index=2),
        Block(text="1. Term", para_index=3),
        Block(text=SENT, para_index=4),
        Block(text="2. Payment", para_index=5),
        Block(text=SENT, para_index=6),
        Block(text="3. Notices", para_index=7),
        Block(text=SENT, para_index=8),
    ]
    doc = Document(source_path="x.docx", file_type="docx", blocks=blocks)
    clauses = segment(clean_document(doc), doc)
    assert clauses[1].heading == "Confidentiality" and clauses[1].number is None
    assert clauses[1].section_path == "Confidentiality"
    assert all(c.page_start is None for c in clauses)


def test_body_line_starting_with_a_year_is_not_a_heading():
    pages = [[
        "1. Term\nThis Agreement runs from 1 January\n2026 to 31 December 2026 inclusive.",
        f"2. Payment\n{SENT}", f"3. Notices\n{SENT}",
    ]]  # fmt: skip
    clauses = run(pages)
    assert [c.number for c in clauses] == ["1", "2", "3"]


# --------------------------------------------------------------------------- length guards


def test_short_clause_at_the_end_merges_into_previous():
    pages = [[f"1. Term\n{SENT}", f"2. Payment\n{SENT}", f"3. Notices\n{SENT}", "4. Waiver"]]
    clauses = run(pages)
    assert [c.number for c in clauses] == ["1", "2", "3"]
    assert clauses[-1].text.endswith("4. Waiver")


def test_long_clause_is_split_at_sentences():
    long_body = " ".join(f"Sentence number {i} explains one more obligation." for i in range(150))
    pages = [[f"1. Term\n{SENT}", f"2. Services\n{long_body}", f"3. Notices\n{SENT}"]]
    clauses = run(pages)
    parts = [c for c in clauses if c.number == "2"]
    assert [c.clause_id for c in parts][:2] == ["c002a", "c002b"]
    assert all(len(c.text) <= RULES.max_chars for c in parts)
    assert all(c.text.endswith(".") for c in parts)
    assert clauses[-1].clause_id == "c003"


def test_fallback_splits_unnumbered_text_by_paragraph():
    para = "This paragraph describes the obligations of the parties in plain words. " * 3
    pages = [[para, "Short line.", para, para]]
    clauses = run(pages)
    assert len(clauses) == 3  # the short line is merged into the paragraph after it
    assert clauses[1].text.startswith("Short line.")
    assert all(c.kind == "BODY" and c.number is None for c in clauses)


# --------------------------------------------------------------------------- evaluation script


def _eval_module():
    spec = importlib.util.spec_from_file_location(
        "eval_segmentation", REPO_ROOT / "evaluation" / "eval_segmentation.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_eval_matching_tolerates_ocr_slips_and_reports_misses(clauses):
    mod = _eval_module()
    gold = [
        {"first_words": "1. DEFINITIONS In this Agreement, words have the", "number": "1",
         "kind": "DEFINITIONS", "heading": "Definitions"},
        {"first_words": "2. Servlces The Vendor shal1 perform this obligation", "number": "2",
         "kind": "BODY", "heading": "Services"},
        {"first_words": "99. A clause that is not in the contract at all", "number": "99",
         "kind": "BODY", "heading": None},
    ]  # fmt: skip
    s = mod.score(gold, clauses)
    assert s["matched"] == 2 and s["number_ok"] == 2 and s["heading_ok"] == 2
    assert s["missed"] == [gold[2]["first_words"]]
    assert s["precision"] == round(2 / len(clauses), 4)


def test_eval_markdown_shows_failed_files():
    mod = _eval_module()
    summary = {"precision": 0.0, "recall": 0.0, "f1": 0.0, "number_acc": None,
               "kind_acc": None, "heading_acc": None, "failed_files": 1}  # fmt: skip
    report = {
        "f1_target": 0.85,
        "summary": {"docx": summary},
        "contracts": [{"contract": "gc01", "docx": {"ok": False, "error": "IngestionError: x"},
                       "text_pdf": {"ok": False, "error": "e"},
                       "scanned_pdf": {"ok": False, "error": "e"}}],
    }  # fmt: skip
    md = mod.to_markdown(report)
    assert "n/a" in md and "FAILED: IngestionError" in md
