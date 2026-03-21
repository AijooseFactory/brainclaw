"""
Simple test to verify the testing harness imports and basic functionality works.
"""

def test_imports():
    """Test that we can import the public testing harness."""
    from openclaw_memory.testing import (
        generate_synthetic_documents,
        generate_contradictory_documents,
        generate_entity_rich_documents,
        SyntheticDataConfig,
    )
    
    # If we get here, imports succeeded
    assert True


def test_generate_synthetic_documents():
    """Test generating a few synthetic documents."""
    from openclaw_memory.testing import generate_synthetic_documents
    
    docs = generate_synthetic_documents(2, seed=123)
    assert len(docs) == 2
    assert "content" in docs[0]
    assert "id" in docs[0]
    assert isinstance(docs[0]["content"], str)
    assert len(docs[0]["content"]) > 0


def test_generate_contradictory_documents():
    """Test generating contradictory documents."""
    from openclaw_memory.testing import generate_contradictory_documents
    
    docs = generate_contradictory_documents(1, seed=456)
    assert len(docs) == 2  # One pair = two documents
    assert "contradiction_group" in docs[0]
    assert "contradiction_position" in docs[0]


def test_generate_entity_rich_documents():
    """Test generating entity-rich documents."""
    from openclaw_memory.testing import generate_entity_rich_documents
    
    docs = generate_entity_rich_documents(1, seed=789)
    assert len(docs) == 1
    assert "entities" in docs[0]
    assert "relationships" in docs[0]


if __name__ == "__main__":
    test_imports()
    test_generate_synthetic_documents()
    test_generate_contradictory_documents()
    test_generate_entity_rich_documents()
    print("All tests passed!")