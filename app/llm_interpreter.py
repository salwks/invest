"""
LLM-based news interpreter using Anthropic Claude.
Analyzes news headlines and classifies them into structured EventCards.
"""

import json
from typing import Optional
from anthropic import Anthropic
from pydantic import ValidationError

from app.schemas import EventCard, RSSFeedItem
from app.config import get_settings
from app.utils import (
    generate_event_id, get_market_session,
    get_utc_now, setup_logger, extract_tickers_from_text
)

logger = setup_logger(__name__)


# System prompt for Claude
SYSTEM_PROMPT = """You are a financial news classification system. Your task is to analyze news headlines and extract structured information.

CRITICAL RULES:
1. Output ONLY valid JSON matching the exact schema provided
2. Do NOT guess or speculate - if uncertain, set reliability < 0.6
3. sentiment: -1.0 (very negative) to 1.0 (very positive)
4. reliability: 0.0 (uncertain) to 1.0 (highly confident)
5. For rumors or unconfirmed news: set category="rumor" and reliability < 0.5
6. Extract only factual key_facts - no opinions or speculation

Categories:
- earnings: Quarterly/annual earnings reports
- FDA: FDA approvals, rejections, or regulatory decisions
- M&A: Mergers, acquisitions, takeovers
- guidance: Company guidance updates
- partnership: Business partnerships, collaborations
- regulatory: Regulatory actions (non-FDA)
- rumor: Unconfirmed reports, speculation
- other: Everything else

Be conservative with sentiment and reliability scores."""


# JSON schema for Claude
EVENT_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {
            "type": "string",
            "enum": ["earnings", "FDA", "M&A", "guidance", "partnership", "regulatory", "rumor", "other"]
        },
        "sentiment": {
            "type": "number",
            "minimum": -1.0,
            "maximum": 1.0
        },
        "reliability": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0
        },
        "key_facts": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 5
        }
    },
    "required": ["category", "sentiment", "reliability", "key_facts"]
}


class LLMInterpreter:
    """
    Interprets RSS feed items using Claude LLM.
    """

    def __init__(self):
        self.settings = get_settings()
        self.client = Anthropic(api_key=self.settings.anthropic_api_key)
        self.model = self.settings.anthropic_model
        self.whitelist = self.settings.tickers

    async def interpret(self, item: RSSFeedItem, max_retries: int = 2) -> Optional[EventCard]:
        """
        Interpret RSS item into EventCard using LLM.

        Args:
            item: RSS feed item
            max_retries: Maximum retry attempts on validation failure

        Returns:
            EventCard if successful, None if failed
        """
        for attempt in range(max_retries):
            try:
                # Build user prompt
                user_prompt = self._build_user_prompt(item)

                # Call Claude
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=500,
                    temperature=0.3,  # Lower temperature for more consistent output
                    system=SYSTEM_PROMPT,
                    messages=[
                        {"role": "user", "content": user_prompt}
                    ]
                )

                # Extract JSON from response
                content = response.content[0].text.strip()
                llm_output = self._extract_json(content)

                # Create EventCard
                event_card = self._build_event_card(item, llm_output)

                logger.debug(f"Successfully interpreted: {item.headline[:50]}... "
                           f"(category={event_card.category}, sentiment={event_card.sentiment:.2f})")
                return event_card

            except ValidationError as e:
                logger.warning(f"Validation failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    logger.error(f"Failed to interpret after {max_retries} attempts: {item.headline}")
                    return None

            except Exception as e:
                logger.error(f"LLM interpretation error: {e}")
                return None

        return None

    def _build_user_prompt(self, item: RSSFeedItem) -> str:
        """Build user prompt for Claude."""
        prompt = f"""Analyze this financial news item and return ONLY a JSON object:

Headline: {item.headline}
Source: {item.source}
Published: {item.published_at.isoformat()}"""

        if item.snippet:
            prompt += f"\nSnippet: {item.snippet[:300]}"

        prompt += f"""

Return JSON matching this schema:
{json.dumps(EVENT_SCHEMA, indent=2)}

Remember: Be conservative with scores. Use category="other" and low reliability if uncertain."""

        return prompt

    def _extract_json(self, content: str) -> dict:
        """Extract JSON from Claude's response."""
        # Try to parse directly
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try to find JSON in code blocks
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            content = content[start:end].strip()
        elif "```" in content:
            start = content.find("```") + 3
            end = content.find("```", start)
            content = content[start:end].strip()

        # Try parsing again
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to extract valid JSON: {e}")

    def _build_event_card(self, item: RSSFeedItem, llm_output: dict) -> EventCard:
        """Build EventCard from RSS item and LLM output."""
        # Extract tickers from headline
        tickers = extract_tickers_from_text(item.headline + " " + (item.snippet or ""), self.whitelist)

        # Determine session
        session = get_market_session(item.published_at)

        # Generate event ID
        event_id = generate_event_id(item.source, item.headline, item.published_at)

        # Build EventCard
        return EventCard(
            event_id=event_id,
            tickers=tickers,
            headline=item.headline,
            published_at=item.published_at,
            category=llm_output["category"],
            sentiment=float(llm_output["sentiment"]),
            reliability=float(llm_output["reliability"]),
            key_facts=llm_output.get("key_facts", []),
            session=session,
            cluster_id=item.cluster_id,
            source=item.source,
            url=item.url
        )


async def main():
    """Test LLM interpreter."""
    from datetime import datetime, timezone

    # Create test RSS item
    test_item = RSSFeedItem(
        source="Test",
        headline="Apple announces record Q4 earnings, beats estimates by 15%",
        url="https://example.com",
        published_at=datetime.now(timezone.utc),
        snippet="Apple Inc. reported quarterly earnings that exceeded analyst expectations...",
        cluster_id="test123"
    )

    interpreter = LLMInterpreter()
    event = await interpreter.interpret(test_item)

    if event:
        print("\n=== Event Card ===")
        print(f"Category: {event.category}")
        print(f"Sentiment: {event.sentiment}")
        print(f"Reliability: {event.reliability}")
        print(f"Tickers: {event.tickers}")
        print(f"Key Facts: {event.key_facts}")
    else:
        print("Failed to interpret event")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
