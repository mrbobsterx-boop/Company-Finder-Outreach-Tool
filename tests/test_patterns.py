from enrichment.patterns import deobfuscate_text, extract_emails, extract_phones


class TestExtractEmails:
    def test_plain_email(self):
        assert extract_emails("Reach us at info@example.com for details.") == [
            "info@example.com"
        ]

    def test_bracket_at_and_dot(self):
        text = "Contact: sales [at] example [dot] com"
        assert extract_emails(text) == ["sales@example.com"]

    def test_paren_at_and_dot(self):
        text = "Email: hello (at) example (dot) de"
        assert extract_emails(text) == ["hello@example.de"]

    def test_word_at_and_dot(self):
        text = "write to john dot doe at example dot com please"
        assert extract_emails(text) == ["john.doe@example.com"]

    def test_spaced_at(self):
        text = "kontakt @ firma.de"
        assert extract_emails(text) == ["kontakt@firma.de"]

    def test_html_entity_at(self):
        text = "info&#64;example.com"
        assert extract_emails(text) == ["info@example.com"]

    def test_multiple_and_dedupe(self):
        text = "info@example.com, sales@example.com, info@example.com"
        assert extract_emails(text) == ["info@example.com", "sales@example.com"]

    def test_ignores_image_filenames(self):
        text = "background: url(logo@2x.png); color: red;"
        assert extract_emails(text) == []

    def test_no_email_present(self):
        assert extract_emails("Just a sentence with no contact info.") == []

    def test_empty_string(self):
        assert extract_emails("") == []

    def test_case_normalized(self):
        assert extract_emails("Info@Example.COM") == ["info@example.com"]


class TestDeobfuscateText:
    def test_multiple_variants_in_one_string(self):
        text = "a[at]b[dot]com or c(at)d(dot)com or e at f dot com"
        result = deobfuscate_text(text)
        assert "a@b.com" in result
        assert "c@d.com" in result
        assert "e@f.com" in result


class TestExtractPhones:
    def test_german_number_with_region_hint(self):
        phones = extract_phones("Call us: 030 12345678", default_region="DE")
        assert phones == ["+493012345678"]

    def test_international_format(self):
        phones = extract_phones("Phone: +49 30 12345678")
        assert phones == ["+493012345678"]

    def test_us_number(self):
        phones = extract_phones("Call (415) 555-2671", default_region="US")
        assert phones == ["+14155552671"]

    def test_no_phone_present(self):
        assert extract_phones("No phone here.", default_region="DE") == []

    def test_empty_string(self):
        assert extract_phones("", default_region="DE") == []
