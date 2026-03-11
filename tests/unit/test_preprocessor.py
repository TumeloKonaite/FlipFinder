from src.agents.EnsembleAgent.preprocessor import FIELD_ORDER, Preprocessor


def test_extract_and_normalize_response_keeps_expected_field_order():
    preprocessor = Preprocessor.__new__(Preprocessor)
    raw = """
    Category: Electronics
    Title: Apple iPhone 13 Pro Max 256GB
    Brand: Apple
    Description: Flagship smartphone with premium camera system.
    Details: 256GB storage, unlocked, excellent battery health.
    """

    fields = preprocessor._extract_fields(raw)
    normalized = preprocessor._normalize_response(fields)

    lines = normalized.splitlines()
    assert len(lines) == len(FIELD_ORDER)
    assert lines[0].startswith("Title: ")
    assert lines[1].startswith("Category: ")
    assert lines[2].startswith("Brand: ")
    assert lines[3].startswith("Description: ")
    assert lines[4].startswith("Details: ")


def test_validation_errors_flags_missing_fields_and_bad_title():
    preprocessor = Preprocessor.__new__(Preprocessor)
    fields = {
        "Title": "Invalid title:",
        "Category": "",
        "Brand": "BrandX",
        "Description": "Useful description.",
        "Details": "",
    }

    errors = preprocessor._validation_errors(fields)

    assert errors == ["Category", "Details", "Title"]


def test_fallback_response_includes_all_required_fields():
    preprocessor = Preprocessor.__new__(Preprocessor)

    fallback = preprocessor._fallback_response("  Vintage camera body only   ")

    for field in FIELD_ORDER:
        assert f"{field}:" in fallback
    assert "Vintage camera body only" in fallback
