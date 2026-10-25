from datetime import date

import pytest

from contractguard.classification.contract_type import detect_contract_type
from contractguard.extraction.dates import (
    effective_date,
    end_of_term,
    explicit_expiry,
    find_term,
    parse_date,
)
from contractguard.extraction.document import extract_meta
from contractguard.extraction.durations import parse_duration
from contractguard.extraction.facts import (
    counterparty_unilateral,
    extract_facts,
    governing_law,
    liability,
    normalize_jurisdiction,
    payment_due,
    renewal,
    termination_notice,
)
from contractguard.extraction.parties import extract_parties
from contractguard.extraction.sentences import split_sentences
from contractguard.models import Clause, Party

OUR_ORG = "ABC Technologies Pvt. Ltd."
PARTIES = [
    Party(name=OUR_ORG, alias="Company", role="OUR_ORG"),
    Party(name="Sharma Infotech Pvt. Ltd.", alias="Vendor", role="COUNTERPARTY"),
]


def clause(text, *categories, cid="c001", kind="BODY"):
    return Clause(
        clause_id=cid, number=None, heading=None, text=text, page_start=1, page_end=1,
        section_path="1", char_start=0, char_end=len(text), kind=kind,
        categories=list(categories),
    )  # fmt: skip


def lia(text):
    has_cap, uncapped = liability([clause(text, "LIABILITY")])
    return has_cap.value, uncapped.value


# --------------------------------------------------------------------------- liability


@pytest.mark.parametrize(
    "text, expected",
    [
        ("The aggregate liability of either Party shall not exceed the Fees paid.", (True, False)),
        ("Each Party's total liability is limited to INR 10,00,000.", (True, False)),
        ("In no event shall the liability of the Vendor exceed the fees paid.", (True, False)),
        ("The maximum aggregate liability of the Vendor is the annual fee.", (True, False)),
        ("The Vendor shall have unlimited liability for breach.", (False, True)),
        ("Each Party shall be liable for any and all losses arising from breach.", (False, True)),
        ("The Licensee shall be liable for all damages caused.", (False, True)),
        ("Liability is without any limitation as to the amount.", (False, True)),
        # negation within 8 tokens before the match
        ("The Licensor shall not be liable for any and all damages arising from misuse.",
         (False, False)),
        ("Neither Party is liable for any and all losses of profit.", (False, False)),
        # "including but not limited to" is neither a cap nor an uncapped clause
        ("Neither Party is liable for indirect loss, including but not limited to loss of profit.",
         (False, False)),
        ("Damages, including, without limitation, lost revenue, are excluded.", (False, False)),
        # a cap present wins over uncapped wording
        ("The Vendor is liable for any and all losses, but liability shall not exceed INR 5 lakh.",
         (True, False)),
    ],
)  # fmt: skip
def test_liability_patterns(text, expected):
    assert lia(text) == expected


def test_liability_carve_out_noted_without_flipping_cap():
    has_cap, _ = liability([
        clause("Total liability shall not exceed the Fees.", "LIABILITY", cid="c001"),
        clause("The limitation in Clause 11.1 shall not apply to fraud.", "LIABILITY", cid="c002"),
    ])  # fmt: skip
    assert has_cap.value is True and has_cap.note == "cap has carve-outs"
    assert has_cap.clause_ids == ["c001"]


def test_liability_none_without_liability_clauses():
    has_cap, uncapped = liability([clause("Some text.", "OTHER")])
    assert has_cap.value is None and uncapped.value is None


# --------------------------------------------------------------------------- termination


TERMINATION = (
    "The Vendor may terminate this Agreement for convenience at any time by giving the Company "
    "seven (7) days' prior written notice.\n"
    "Either Party may terminate this Agreement by written notice if the other Party fails to cure "
    "a material breach within thirty (30) days of receiving notice of the breach."
)


def test_notice_prefers_convenience_and_skips_cure_periods():
    fact = termination_notice([clause(TERMINATION, "TERMINATION", cid="c010")])
    assert fact.value == 7 and fact.unit == "days" and fact.clause_ids == ["c010"]
    assert fact.evidence_text.startswith("The Vendor may terminate")
    assert fact.evidence_text in TERMINATION


def test_notice_takes_minimum_of_convenience_rights():
    text = (
        "The Vendor may terminate for convenience by giving fifteen (15) days' prior written "
        "notice.\nThe Company may terminate for convenience by giving thirty (30) days' notice."
    )
    fact = termination_notice([clause(text, "TERMINATION")])
    assert fact.value == 15 and not fact.ambiguous and "minimum" in fact.note


def test_notice_business_days_and_no_convenience_wording():
    text = "Either Party may terminate this Agreement by giving thirty (30) business days' notice."
    assert termination_notice([clause(text, "TERMINATION")]).value == 42


def test_notice_none_when_no_period():
    fact = termination_notice([clause("Either Party may terminate immediately.", "TERMINATION")])
    assert fact.value is None and fact.note == "no notice period found"


@pytest.mark.parametrize(
    "text, expected",
    [
        (TERMINATION, True),
        ("Either Party may terminate for convenience on sixty (60) days' notice.", False),
        ("The Company may terminate for convenience on thirty (30) days' notice.", False),
        ("The Vendor may terminate for convenience on 15 days' notice.\n"
         "The Company may terminate for convenience on 30 days' notice.", False),
    ],
)  # fmt: skip
def test_counterparty_unilateral(text, expected):
    assert counterparty_unilateral([clause(text, "TERMINATION")], PARTIES).value is expected


def test_counterparty_unilateral_unknown_roles():
    unknown = [p.model_copy(update={"role": "UNKNOWN"}) for p in PARTIES]
    fact = counterparty_unilateral([clause(TERMINATION, "TERMINATION")], unknown)
    assert fact.value is None and fact.note == "party roles unknown"


# --------------------------------------------------------------------------- renewal, payment, law


@pytest.mark.parametrize(
    "text, expected, ambiguous",
    [
        ("This Agreement shall automatically renew for successive one-year terms.", True, False),
        ("It renews unless either Party gives notice of non-renewal.", True, False),
        ("This Agreement may be renewed by mutual written agreement.", False, False),
        ("The term is one year.", None, False),
        ("It shall automatically renew. It may be renewed by mutual agreement.", None, True),
    ],
)
def test_renewal(text, expected, ambiguous):
    fact = renewal([clause(text, "RENEWAL")])
    assert fact.value is expected and fact.ambiguous is ambiguous


@pytest.mark.parametrize(
    "text, expected",
    [
        ("The Company shall pay each invoice within fifteen (15) days of receipt.", 15),
        ("Payment terms are Net 30 from the date of invoice.", 30),
        ("Payment is due no later than 45 days after the invoice date.", 45),
        ("The internet service fee is payable monthly.", None),
        ("The Vendor shall invoice by the fifth (5th) day of each month.", None),
    ],
)
def test_payment_due(text, expected):
    assert payment_due([clause(text, "PAYMENT")]).value == expected


def test_payment_conflicting_values_are_ambiguous():
    text = "Pay each invoice within 15 days.\nPay each other invoice within 30 days."
    fact = payment_due([clause(text, "PAYMENT")])
    assert fact.value is None and fact.ambiguous and "15, 30" in fact.note


@pytest.mark.parametrize(
    "text, expected",
    [
        ("This Agreement is governed by the laws of India.", "India"),
        ("governed by the laws of the State of New York, without regard to", "USA (New York)"),
        ("governed by the laws of England and Wales, and the courts", "UK (England and Wales)"),
        ("governed by the laws of Karnataka.", "India (Karnataka)"),
        ("governed by the laws of Ruritania.", "Ruritania"),
    ],
)
def test_governing_law(text, expected):
    assert governing_law([clause(text, "GOVERNING_LAW")]).value == expected


def test_normalize_jurisdiction_is_case_insensitive():
    assert normalize_jurisdiction("republic of india") == "India"


def test_extract_facts_returns_every_key():
    facts = extract_facts([clause(TERMINATION, "TERMINATION")], PARTIES)
    assert list(facts) == [
        "termination.notice_days", "termination.counterparty_unilateral", "liability.has_cap",
        "liability.is_uncapped", "renewal.is_automatic", "payment.due_days",
        "governing_law.jurisdiction",
    ]  # fmt: skip
    assert facts["payment.due_days"].value is None and facts["payment.due_days"].clause_ids == []


# --------------------------------------------------------------------------- sentences, dates


def test_sentences_do_not_split_after_company_abbreviations():
    text = "ABC Technologies Pvt. Ltd. shall pay Rs. 500. The Vendor agrees."
    assert split_sentences(text) == [
        "ABC Technologies Pvt. Ltd. shall pay Rs. 500.",
        "The Vendor agrees.",
    ]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("1st day of April, 2026", date(2026, 4, 1)),
        ("15/05/2026", date(2026, 5, 15)),
        ("3rd August 2026", date(2026, 8, 3)),
        ("April 1, 2026", date(2026, 4, 1)),
    ],
)
def test_parse_date_dmy(text, expected):
    assert parse_date(text, "DMY") == expected


def test_parse_date_mdy_order():
    assert parse_date("05/06/2026", "MDY") == date(2026, 5, 6)


def test_effective_date_uses_the_cue_sentence():
    text = (
        "Signed on 2 January 2026.\n"
        'This Agreement is entered into with effect from 1 July 2026 (the "Effective Date").'
    )
    assert effective_date(text, "DMY").value == date(2026, 7, 1)


@pytest.mark.parametrize(
    "start, duration, end",
    [
        (date(2026, 4, 1), "one (1) year", date(2027, 3, 31)),
        (date(2026, 5, 15), "three (3) years", date(2029, 5, 14)),
        (date(2028, 2, 29), "1 year", date(2029, 2, 28)),
        (date(2026, 1, 31), "1 month", date(2026, 2, 28)),
        (date(2026, 1, 1), "30 days", date(2026, 1, 30)),
    ],
)
def test_end_of_term_legal_reading(start, duration, end):
    assert end_of_term(start, parse_duration(duration)) == end


def test_term_anchor_and_explicit_expiry():
    anchored = find_term("The initial term of one (1) year starts on the Effective Date.")
    assert anchored.text == "initial term of one (1) year" and anchored.from_effective_date
    loose = find_term("The Rental Period is twelve (12) months from the date of delivery.")
    assert loose and not loose.from_effective_date
    assert explicit_expiry("This Agreement shall expire on 31 March 2027.", "DMY").value == date(
        2027, 3, 31
    )


# --------------------------------------------------------------------------- parties, type, meta


PREAMBLE = (
    'SERVICES AGREEMENT\nThis Agreement is dated 1 April 2026 (the "Effective Date") between '
    "Sharma Infotech Pvt. Ltd., a company incorporated under the Companies Act, 2013 "
    '(hereinafter the "Vendor"), and ABC Technologies Pvt. Ltd., having its registered office '
    'at Bengaluru (the "Company").'
)


def test_parties_resolved_by_our_org_name():
    parties = extract_parties(PREAMBLE, OUR_ORG)
    assert [(p.name, p.alias, p.role) for p in parties] == [
        ("Sharma Infotech Pvt. Ltd.", "Vendor", "COUNTERPARTY"),
        ("ABC Technologies Pvt. Ltd.", "Company", "OUR_ORG"),
    ]


def test_parties_fall_back_to_aliases_then_unknown():
    assert [p.role for p in extract_parties(PREAMBLE, None)] == ["COUNTERPARTY", "OUR_ORG"]
    nda = PREAMBLE.replace("Vendor", "Discloser").replace("Company", "Recipient")
    assert [p.role for p in extract_parties(nda, None)] == ["UNKNOWN", "UNKNOWN"]


def test_alias_survives_lost_opening_quote():
    ocr = PREAMBLE.replace('(the "Company")', '(the Company")')
    assert extract_parties(ocr, OUR_ORG)[1].alias == "Company"


@pytest.mark.parametrize(
    "title, expected",
    [
        ("MUTUAL NON-DISCLOSURE AGREEMENT", "NDA"),
        ("SOFTWARE AS A SERVICE SUBSCRIPTION AGREEMENT", "SAAS_LICENSE"),
        ("MASTER SERVICES AGREEMENT", "VENDOR_SERVICE"),
        ("EQUIPMENT RENTAL AGREEMENT", "OTHER"),
    ],
)
def test_contract_type(title, expected):
    assert detect_contract_type(f"{title}\nThis agreement is made.").contract_type == expected


def test_user_contract_type_overrides():
    result = detect_contract_type("MUTUAL NON-DISCLOSURE AGREEMENT", user_type="VENDOR_SERVICE")
    assert (result.contract_type, result.source) == ("VENDOR_SERVICE", "user")


def test_extract_meta_end_to_end():
    clauses = [
        clause(PREAMBLE, kind="PREAMBLE", cid="c001"),
        clause("This Agreement commences on the Effective Date for an initial term of one (1) "
               "year.", "OTHER", cid="c002"),
        clause("This Agreement is governed by the laws of India.", "GOVERNING_LAW", cid="c003"),
    ]  # fmt: skip
    meta = extract_meta(clauses, OUR_ORG, date_order="DMY")
    assert meta.title == "SERVICES AGREEMENT"
    assert meta.contract_type == "VENDOR_SERVICE" and meta.contract_type_source == "auto"
    assert meta.effective_date == date(2026, 4, 1)
    assert meta.expiry_date == date(2027, 3, 31)
    assert meta.governing_law == "India"
    assert [p.role for p in meta.parties] == ["COUNTERPARTY", "OUR_ORG"]
