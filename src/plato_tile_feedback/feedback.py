"""Tile feedback — ratings, reactions, comments, and reputation signals."""
import time
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
from collections import defaultdict

class ReactionType(Enum):
    UPVOTE = "upvote"
    DOWNVOTE = "downvote"
    SHRUG = "shrug"
    FLAG = "flag"
    BOOKMARK = "bookmark"

class FeedbackType(Enum):
    RATING = "rating"
    REACTION = "reaction"
    COMMENT = "comment"
    CORRECTION = "correction"

@dataclass
class Feedback:
    tile_id: str
    agent: str
    type: FeedbackType
    value: str = ""  # rating 1-5, reaction name, comment text
    created_at: float = field(default_factory=time.time)

@dataclass
class TileFeedbackSummary:
    tile_id: str
    rating_avg: float = 0.0
    rating_count: int = 0
    upvotes: int = 0
    downvotes: int = 0
    flags: int = 0
    bookmarks: int = 0
    comment_count: int = 0
    top_comments: list[dict] = field(default_factory=list)

class TileFeedback:
    def __init__(self):
        self._feedback: list[Feedback] = []
        self._agent_history: dict[str, list[Feedback]] = defaultdict(list)

    def rate(self, tile_id: str, agent: str, rating: int) -> Feedback:
        if not 1 <= rating <= 5:
            raise ValueError("Rating must be 1-5")
        fb = Feedback(tile_id=tile_id, agent=agent, type=FeedbackType.RATING, value=str(rating))
        self._add(fb)
        return fb

    def react(self, tile_id: str, agent: str, reaction: str) -> Feedback:
        fb = Feedback(tile_id=tile_id, agent=agent, type=FeedbackType.REACTION, value=reaction.lower())
        self._add(fb)
        return fb

    def comment(self, tile_id: str, agent: str, text: str) -> Feedback:
        fb = Feedback(tile_id=tile_id, agent=agent, type=FeedbackType.COMMENT, value=text)
        self._add(fb)
        return fb

    def correct(self, tile_id: str, agent: str, correction: str) -> Feedback:
        fb = Feedback(tile_id=tile_id, agent=agent, type=FeedbackType.CORRECTION, value=correction)
        self._add(fb)
        return fb

    def _add(self, fb: Feedback):
        self._feedback.append(fb)
        self._agent_history[fb.agent].append(fb)
        if len(self._feedback) > 10000:
            self._feedback = self._feedback[-10000:]

    def summary(self, tile_id: str) -> TileFeedbackSummary:
        tile_fb = [f for f in self._feedback if f.tile_id == tile_id]
        ratings = [int(f.value) for f in tile_fb if f.type == FeedbackType.RATING]
        reactions = [f.value for f in tile_fb if f.type == FeedbackType.REACTION]
        comments = [f for f in tile_fb if f.type == FeedbackType.COMMENT]
        avg = sum(ratings) / len(ratings) if ratings else 0.0
        top = sorted(comments, key=lambda c: c.created_at, reverse=True)[:5]
        return TileFeedbackSummary(
            tile_id=tile_id, rating_avg=round(avg, 2), rating_count=len(ratings),
            upvotes=reactions.count("upvote"), downvotes=reactions.count("downvote"),
            flags=reactions.count("flag"), bookmarks=reactions.count("bookmark"),
            comment_count=len(comments),
            top_comments=[{"agent": c.agent, "text": c.value[:200],
                          "ago_s": round(time.time() - c.created_at)} for c in top])

    def agent_feedback(self, agent: str, limit: int = 50) -> list[Feedback]:
        return self._agent_history.get(agent, [])[-limit:]

    def controversial(self, n: int = 10) -> list[TileFeedbackSummary]:
        """Tiles with most polarized feedback."""
        tile_ids = set(f.tile_id for f in self._feedback)
        summaries = [(self.summary(tid), abs(self.summary(tid).upvotes - self.summary(tid).downvotes))
                    for tid in tile_ids]
        summaries.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in summaries[:n]]

    def flagged(self, n: int = 10) -> list[TileFeedbackSummary]:
        summaries = []
        seen = set()
        for f in self._feedback:
            if f.tile_id not in seen and f.type == FeedbackType.REACTION and f.value == "flag":
                seen.add(f.tile_id)
                summaries.append(self.summary(f.tile_id))
        return summaries[:n]

    def top_rated(self, n: int = 10) -> list[TileFeedbackSummary]:
        tile_ids = set(f.tile_id for f in self._feedback)
        summaries = [self.summary(tid) for tid in tile_ids if self.summary(tid).rating_count > 0]
        summaries.sort(key=lambda s: s.rating_avg, reverse=True)
        return summaries[:n]

    def corrections_for(self, tile_id: str) -> list[Feedback]:
        return [f for f in self._feedback if f.tile_id == tile_id and f.type == FeedbackType.CORRECTION]

    @property
    def stats(self) -> dict:
        return {"total_feedback": len(self._feedback),
                "unique_tiles": len(set(f.tile_id for f in self._feedback)),
                "unique_agents": len(set(f.agent for f in self._feedback)),
                "by_type": {t.value: sum(1 for f in self._feedback if f.type == t) for t in FeedbackType}}
