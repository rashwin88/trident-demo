import pytest

from ingestion.dspy_programs import _clean_json, _parse_json_list, _parse_json_object


class TestCleanJson:
    def test_plain_json(self):
        assert _clean_json('[{"a": 1}]') == '[{"a": 1}]'

    def test_markdown_fenced(self):
        raw = '```json\n[{"a": 1}]\n```'
        assert _clean_json(raw) == '[{"a": 1}]'

    def test_markdown_fenced_no_lang(self):
        raw = '```\n{"key": "val"}\n```'
        assert _clean_json(raw) == '{"key": "val"}'

    def test_whitespace(self):
        assert _clean_json("  \n  [1, 2]  \n  ") == "[1, 2]"


class TestParseJsonList:
    def test_valid_list(self):
        result = _parse_json_list('[{"label": "BT"}]', "test")
        assert result == [{"label": "BT"}]

    def test_empty_list(self):
        result = _parse_json_list("[]", "test")
        assert result == []

    def test_not_a_list(self):
        result = _parse_json_list('{"a": 1}', "test")
        assert result == []

    def test_invalid_json(self):
        result = _parse_json_list("not json at all", "test")
        assert result == []

    def test_none_input(self):
        result = _parse_json_list(None, "test")  # type: ignore
        assert result == []


class TestParseJsonObject:
    def test_valid_object(self):
        result = _parse_json_object('{"name": "test"}', "test")
        assert result == {"name": "test"}

    def test_not_an_object(self):
        result = _parse_json_object("[1, 2]", "test")
        assert result is None

    def test_invalid_json(self):
        result = _parse_json_object("broken", "test")
        assert result is None
