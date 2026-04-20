"""Tile feedback collection and aggregation."""
import time
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum

class Sentiment(Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"

@dataclass
class FeedbackEntry:
    tile_id: str
    rating: int  # 1-5
    comment: str = ""
    sentiment: Sentiment = Sentiment.NEUTRAL
    agent: str = ""
    timestamp: float = field(default_factory=time.time)
    tags: list[str] = field(default_factory=list)

@dataclass
class FeedbackAggregate:
    tile_id: str
    avg_rating: float
    count: int
    sentiment_dist: dict = field(default_factory=dict)
    top_tags: list[tuple[str, int]] = field(default_factory=list)

class TileFeedback:
    def __init__(self):
        self._feedback: dict[str, list[FeedbackEntry]] = defaultdict(list)
        self._all: list[FeedbackEntry] = []

    def add(self, tile_id: str, rating: int, comment: str = "",
            agent: str = "", tags: list[str] = None) -> FeedbackEntry:
        if not 1 <= rating <= 5:
            raise ValueError("Rating must be 1-5")
        sentiment = Sentiment.POSITIVE if rating >= 4 else Sentiment.NEGATIVE if rating <= 2 else Sentiment.NEUTRAL
        entry = FeedbackEntry(tile_id=tile_id, rating=rating, comment=comment,
                            sentiment=sentiment, agent=agent, tags=tags or [])
        self._feedback[tile_id].append(entry)
        self._all.append(entry)
        return entry

    def aggregate(self, tile_id: str) -> FeedbackAggregate:
        entries = self._feedback.get(tile_id, [])
        if not entries:
            return FeedbackAggregate(tile_id=tile_id, avg_rating=0, count=0)
        avg = sum(e.rating for e in entries) / len(entries)
        dist = defaultdict(int)
        tag_counts = defaultdict(int)
        for e in entries:
            dist[e.sentiment.value] += 1
            for t in e.tags:
                tag_counts[t] += 1
        top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        return FeedbackAggregate(tile_id=tile_id, avg_rating=round(avg, 2),
                               count=len(entries), sentiment_dist=dict(dist),
                               top_tags=top_tags)

    def top_rated(self, n: int = 10, min_reviews: int = 1) -> list[FeedbackAggregate]:
        aggregates = []
        for tid in self._feedback:
            agg = self.aggregate(tid)
            if agg.count >= min_reviews:
                aggregates.append(agg)
        aggregates.sort(key=lambda a: a.avg_rating, reverse=True)
        return aggregates[:n]

    def needs_attention(self, max_rating: float = 2.0, min_reviews: int = 2) -> list[FeedbackAggregate]:
        return [a for a in self.top_rated(100, min_reviews) if a.avg_rating <= max_rating]

    def by_agent(self, agent: str) -> list[FeedbackEntry]:
        return [e for e in self._all if e.agent == agent]

    @property
    def stats(self) -> dict:
        return {"tiles_reviewed": len(self._feedback),
                "total_reviews": len(self._all),
                "avg_rating": round(sum(e.rating for e in self._all) / len(self._all), 2) if self._all else 0}
