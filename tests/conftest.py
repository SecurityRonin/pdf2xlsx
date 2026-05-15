import pytest
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def annual_report():
    return FIXTURES / "annual_report.pdf"


@pytest.fixture
def esg_report():
    return FIXTURES / "esg_report.pdf"


@pytest.fixture
def academic_paper():
    return FIXTURES / "academic_paper.pdf"


@pytest.fixture
def esg_disclosure():
    return FIXTURES / "esg_disclosure.pdf"


@pytest.fixture
def term_sheet():
    return FIXTURES / "term_sheet.pdf"


@pytest.fixture
def general_ledger():
    return FIXTURES / "general_ledger.pdf"
