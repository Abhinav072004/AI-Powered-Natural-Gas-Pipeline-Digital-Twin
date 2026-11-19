import pytest

from fastapi.testclient import TestClient

from pipeline_twin.api import app
from pipeline_twin.copilot import KnowledgeIndex, answer, passages


@pytest.fixture(scope="module")
def index():
    return KnowledgeIndex(passages())


def test_cited_answer_and_unrelated_query(index, monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    result = answer(index, "What is linepack and why does it matter?", "Simulated inventory: 6.46 million kg")
    assert result["mode"] == "excerpts"
    assert "linepack" in result["answer"].lower()
    assert "[1]" in result["answer"]
    assert result["sources"] and result["simulated_context"].startswith("Simulated")
    assert answer(index, "Xylophonic aardvarks purplish astrophysics", None)["sources"] == []


def test_copilot_context_comes_from_selected_scenario():
    client = TestClient(app)
    response = client.post("/api/copilot", json={"question": "Why does a pressure drop happen?", "scenario": "pressure_drop"})
    assert response.status_code == 200
    assert "demo-pressure_drop" in response.json()["simulated_context"]
    assert response.json()["sources"]


def test_registered_pdf_preserves_page_reference(tmp_path):
    import json
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    pdf = PdfWriter()
    page = pdf.add_blank_page(width=200, height=200)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                             NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
    })
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 12 Tf 10 20 Td (Test technical reference) Tj ET")
    page[NameObject("/Contents")] = content
    pdf.write(tmp_path / "reference.pdf")
    (tmp_path / "manifest.json").write_text(json.dumps([{
        "file": "reference.pdf", "title": "Test reference", "reference": "https://example.test/reference",
    }]))
    result = passages(tmp_path)[-1]
    assert result.excerpt == "Test technical reference"
    assert result.page == 1
    assert result.reference == "https://example.test/reference"
