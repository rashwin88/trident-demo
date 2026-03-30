import pytest

from ingestion.extractor import (
    _build_entities,
    _build_concepts,
    _build_relationships,
    _build_propositions,
    _build_procedure,
    _build_table_semantic,
)


class TestBuildEntities:
    def test_valid(self):
        raw = [{"label": "BT", "entity_type": "Carrier", "description": "British Telecom"}]
        result = _build_entities(raw)
        assert len(result) == 1
        assert result[0].label == "BT"

    def test_missing_label(self):
        raw = [{"entity_type": "Carrier"}]
        result = _build_entities(raw)
        assert result == []

    def test_missing_optional_fields(self):
        raw = [{"label": "X"}]
        result = _build_entities(raw)
        assert len(result) == 1
        assert result[0].entity_type == "Unknown"
        assert result[0].description is None


class TestBuildConcepts:
    def test_valid(self):
        raw = [{"name": "MRC", "definition": "Monthly charge", "aliases": ["Monthly Recurring Charge"]}]
        result = _build_concepts(raw)
        assert len(result) == 1
        assert "Monthly Recurring Charge" in result[0].aliases

    def test_missing_name(self):
        raw = [{"definition": "Something"}]
        result = _build_concepts(raw)
        assert result == []


class TestBuildRelationships:
    def test_valid(self):
        raw = [{"source_label": "A", "edge_type": "RELATED_TO", "target_label": "B"}]
        result = _build_relationships(raw)
        assert len(result) == 1
        assert result[0].confidence == 1.0

    def test_with_confidence(self):
        raw = [{"source_label": "A", "edge_type": "PART_OF", "target_label": "B", "confidence": 0.8}]
        result = _build_relationships(raw)
        assert result[0].confidence == 0.8


class TestBuildPropositions:
    def test_valid(self):
        raw = [{"subject": "CID-1", "predicate": "has", "object": "100Mbps"}]
        result = _build_propositions(raw, "chunk-1")
        assert len(result) == 1
        assert result[0].chunk_id == "chunk-1"


class TestBuildProcedure:
    def test_valid(self):
        raw = {
            "name": "Decom",
            "intent": "Decommission a circuit",
            "steps": [
                {"step_number": 1, "description": "Notify carrier"},
                {"step_number": 2, "description": "Remove config", "prerequisites": [1]},
            ],
        }
        result = _build_procedure(raw, "chunk-1")
        assert result is not None
        assert result.name == "Decom"
        assert len(result.steps) == 2
        assert result.steps[1].prerequisites == [1]

    def test_none_input(self):
        assert _build_procedure(None, "chunk-1") is None


class TestBuildTableSemantic:
    def test_valid(self):
        raw = {
            "table_name": "circuits",
            "description": "Circuit inventory",
            "columns": [
                {"column_name": "id", "description": "Primary key", "is_key": True},
                {"column_name": "bandwidth", "description": "Bandwidth in Mbps"},
            ],
        }
        result = _build_table_semantic(raw)
        assert result is not None
        assert result.columns[0].is_key is True
        assert result.columns[1].is_key is False

    def test_none_input(self):
        assert _build_table_semantic(None) is None
