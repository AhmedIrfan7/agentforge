"""Unit tests for agents/document_analysis.py (roadmap step 095) --
keyword-phrase classification against real text, one case per
category plus the fallback."""

from agents.document_analysis import DocumentAnalysisAgent

agent = DocumentAnalysisAgent()


def test_faq_document_is_classified_as_faq() -> None:
    text = "# Frequently Asked Questions\n\nQ: How do I reset my password?\nA: Click the link."
    result = agent.analyze(text)
    assert result.document_type == "faq"
    assert "frequently asked questions" in result.matched_keywords


def test_manual_document_is_classified_as_manual() -> None:
    text = (
        "# User Manual\n\n## Table of Contents\n\n## Getting Started\n\n"
        "Follow this step-by-step installation guide."
    )
    result = agent.analyze(text)
    assert result.document_type == "manual"


def test_legal_document_is_classified_as_legal() -> None:
    text = (
        "This Agreement is entered into whereas the parties agree to the terms "
        "and conditions herein, hereinafter establishing the governing law. "
        "In witness whereof, neither party shall not be liable for indirect damages."
    )
    result = agent.analyze(text)
    assert result.document_type == "legal"


def test_academic_document_is_classified_as_academic() -> None:
    text = (
        "# Abstract\n\nThis paper presents a novel methodology. "
        "See the literature review for prior work (Smith et al.).\n\n"
        "# References\n\n# Bibliography"
    )
    result = agent.analyze(text)
    assert result.document_type == "academic"


def test_business_document_is_classified_as_business() -> None:
    text = (
        "# Executive Summary\n\nThis quarterly report covers revenue growth "
        "and stakeholder return on investment. See the attached invoice, proposal, "
        "and budget forecast."
    )
    result = agent.analyze(text)
    assert result.document_type == "business"


def test_unrecognizable_content_falls_back_to_general() -> None:
    text = "The cat sat on the mat. It was a sunny day in the park."
    result = agent.analyze(text)
    assert result.document_type == "general"
    assert result.matched_keywords == []


def test_empty_text_falls_back_to_general() -> None:
    result = agent.analyze("")
    assert result.document_type == "general"


def test_classification_is_case_insensitive() -> None:
    result = agent.analyze("FREQUENTLY ASKED QUESTIONS about our product")
    assert result.document_type == "faq"
