import pytest

from stores.graph import EDGE_VOCABULARY, EDGE_VOCABULARY_LIST, GraphStore
from stores.knowledge import KnowledgeStore
from stores.procedural import ProceduralStore


# ── Edge vocabulary tests ─────────────────────────────


class TestEdgeVocabulary:
    def test_has_20_types(self):
        assert len(EDGE_VOCABULARY) == 20

    def test_sorted_list_matches_set(self):
        assert set(EDGE_VOCABULARY_LIST) == EDGE_VOCABULARY
        assert EDGE_VOCABULARY_LIST == sorted(EDGE_VOCABULARY_LIST)

    def test_all_uppercase(self):
        for edge in EDGE_VOCABULARY:
            assert edge == edge.upper(), f"{edge} is not uppercase"

    def test_expected_types_present(self):
        expected = [
            "CONTAINS",
            "MENTIONS",
            "DEFINES",
            "ASSERTS",
            "RELATED_TO",
            "INSTANCE_OF",
            "SOURCED_FROM",
            "IMPLEMENTED_BY",
        ]
        for e in expected:
            assert e in EDGE_VOCABULARY


# ── GraphStore unit tests (no Neo4j required) ─────────


class TestGraphStoreInit:
    def test_not_connected_by_default(self):
        store = GraphStore()
        assert store._driver is None

    def test_driver_property_asserts_on_no_connection(self):
        store = GraphStore()
        with pytest.raises(AssertionError, match="not connected"):
            _ = store.driver


# ── KnowledgeStore unit tests (no Milvus required) ────


class TestKnowledgeStoreCollectionNaming:
    def test_simple_name(self):
        assert KnowledgeStore._collection_name("test") == "ks_test"

    def test_hyphenated_name(self):
        assert (
            KnowledgeStore._collection_name("circuit-intelligence")
            == "ks_circuit_intelligence"
        )

    def test_already_underscored(self):
        assert (
            KnowledgeStore._collection_name("carrier_contracts")
            == "ks_carrier_contracts"
        )


# ── ProceduralStore unit tests (no Milvus required) ───


class TestProceduralStoreCollectionNaming:
    def test_simple_name(self):
        assert ProceduralStore._collection_name("test") == "ps_test"

    def test_hyphenated_name(self):
        assert (
            ProceduralStore._collection_name("circuit-intelligence")
            == "ps_circuit_intelligence"
        )

    def test_already_underscored(self):
        assert (
            ProceduralStore._collection_name("carrier_contracts")
            == "ps_carrier_contracts"
        )


class TestProceduralStoreInit:
    def test_not_connected_by_default(self):
        store = ProceduralStore()
        assert store._connected is False


class TestKnowledgeStoreInit:
    def test_not_connected_by_default(self):
        store = KnowledgeStore()
        assert store._connected is False
