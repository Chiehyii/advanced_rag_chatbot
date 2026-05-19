from extraction_schema import normalize_extracted_scholarship


def test_normalize_extracted_scholarship_limits_and_fallbacks():
    normalized = normalize_extracted_scholarship(
        {
            "scholarship_code": "bad code!",
            "title": " Example Scholarship ",
            "link": "javascript:alert(1)",
            "tags": ["alpha", "alpha", {"bad": "shape"}],
            "description": {"unexpected": "object"},
            "markdown_content": "",
            "unknown_field": "ignored",
        },
        fallback_code="sch-safe",
        fallback_url="https://example.edu/apply",
    )

    assert normalized["scholarship_code"] == "sch-safe"
    assert normalized["title"] == "Example Scholarship"
    assert normalized["link"] == "https://example.edu/apply"
    assert normalized["tags"] == ["alpha", "{'bad': 'shape'}"]
    assert "unknown_field" not in normalized
    assert normalized["markdown_content"]


def test_normalize_extracted_scholarship_rejects_unsafe_fallback_url():
    normalized = normalize_extracted_scholarship(
        {"title": "Only Title"},
        fallback_url="file:///etc/passwd",
    )

    assert normalized["link"] == ""
    assert normalized["markdown_content"] == "Only Title"
