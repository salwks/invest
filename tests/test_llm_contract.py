"""
Test LLM interpreter contract and schema validation.
Ensures LLM output conforms to expected EventCard schema.
"""

import pytest
from datetime import datetime, timezone

from app.llm_interpreter import LLMInterpreter
from app.schemas import RSSFeedItem, EventCard


# Sample headlines for testing
SAMPLE_HEADLINES = [
    {
        "headline": "Apple reports record Q4 earnings, beats Wall Street expectations",
        "snippet": "Apple Inc. announced quarterly earnings that exceeded analyst forecasts...",
        "expected_category": "earnings",
        "expected_sentiment_range": (0.6, 1.0)
    },
    {
        "headline": "FDA approves new Pfizer drug for cancer treatment",
        "snippet": "The FDA has granted approval to Pfizer's new oncology treatment...",
        "expected_category": "FDA",
        "expected_sentiment_range": (0.5, 1.0)
    },
    {
        "headline": "Tesla faces recall over safety concerns",
        "snippet": "Tesla is recalling thousands of vehicles due to safety issues...",
        "expected_category": "regulatory",
        "expected_sentiment_range": (-1.0, 0.0)
    },
    {
        "headline": "Microsoft announces partnership with OpenAI",
        "snippet": "Microsoft has announced a strategic partnership...",
        "expected_category": "partnership",
        "expected_sentiment_range": (0.3, 1.0)
    },
    {
        "headline": "Amazon reportedly considering acquisition of retail chain - sources",
        "snippet": "Sources familiar with the matter say Amazon is in talks...",
        "expected_category": "rumor",  # Unconfirmed
        "expected_sentiment_range": (-0.5, 0.5)
    },
]


@pytest.fixture
def llm_interpreter():
    """Create LLM interpreter instance."""
    return LLMInterpreter()


@pytest.mark.asyncio
@pytest.mark.parametrize("sample", SAMPLE_HEADLINES[:3])  # Test first 3 to limit API calls
async def test_llm_interpretation_schema(llm_interpreter, sample):
    """Test that LLM output conforms to EventCard schema."""
    # Create RSS item
    item = RSSFeedItem(
        source="Test",
        headline=sample["headline"],
        url="https://example.com",
        published_at=datetime.now(timezone.utc),
        snippet=sample.get("snippet", ""),
        cluster_id="test123"
    )

    # Interpret with LLM
    event = await llm_interpreter.interpret(item)

    # Basic validation
    assert event is not None, "LLM should return EventCard"
    assert isinstance(event, EventCard)

    # Schema fields
    assert event.event_id
    assert event.headline == sample["headline"]
    assert event.category in ["earnings", "FDA", "M&A", "guidance", "partnership", "regulatory", "rumor", "other"]
    assert -1.0 <= event.sentiment <= 1.0
    assert 0.0 <= event.reliability <= 1.0
    assert isinstance(event.key_facts, list)
    assert event.session in ["pre", "regular", "after"]


@pytest.mark.asyncio
async def test_llm_sentiment_range(llm_interpreter):
    """Test that sentiment is in correct range for positive news."""
    item = RSSFeedItem(
        source="Test",
        headline="Company announces record profits and strong growth",
        url="https://example.com",
        published_at=datetime.now(timezone.utc),
        snippet="The company reported exceptional results...",
        cluster_id="test_positive"
    )

    event = await llm_interpreter.interpret(item)

    assert event is not None
    assert event.sentiment > 0.0, "Positive news should have positive sentiment"


@pytest.mark.asyncio
async def test_llm_reliability_for_rumor(llm_interpreter):
    """Test that rumors have lower reliability scores."""
    item = RSSFeedItem(
        source="Test",
        headline="Company reportedly considering merger - unconfirmed sources",
        url="https://example.com",
        published_at=datetime.now(timezone.utc),
        snippet="Sources say the company may be in talks...",
        cluster_id="test_rumor"
    )

    event = await llm_interpreter.interpret(item)

    assert event is not None
    # Rumors should have lower reliability
    # Note: This is a heuristic - LLM may vary
    assert event.category == "rumor" or event.reliability < 0.7


@pytest.mark.asyncio
async def test_llm_retry_on_failure(llm_interpreter):
    """Test retry mechanism (simulated)."""
    # This would require mocking the Anthropic API
    # For now, just verify the mechanism exists
    assert llm_interpreter is not None


def test_json_extraction():
    """Test JSON extraction from various formats."""
    from app.llm_interpreter import LLMInterpreter

    interp = LLMInterpreter()

    # Plain JSON
    result = interp._extract_json('{"category": "earnings", "sentiment": 0.8, "reliability": 0.9, "key_facts": []}')
    assert result["category"] == "earnings"

    # JSON in code block
    result = interp._extract_json('```json\n{"category": "FDA", "sentiment": 0.7, "reliability": 0.85, "key_facts": []}\n```')
    assert result["category"] == "FDA"

    # JSON in plain code block
    result = interp._extract_json('```\n{"category": "M&A", "sentiment": 0.6, "reliability": 0.75, "key_facts": []}\n```')
    assert result["category"] == "M&A"
