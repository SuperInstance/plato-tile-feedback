"""Tile feedback — user feedback loops with sentiment scoring, action tracking, and aggregation."""
import time
import re
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict
from enum import Enum

class FeedbackType(Enum):
    UPVOTE = "upvote"
    DOWNVOTE = "downvote"
    CORRECTION = "correction"
    COMMENT = "comment"
    FLAG = "flag"
    RATING = "rating"

class FeedbackAction(Enum):
    BOOST = "boost"
    DEMOTE = "demote"
    CORRECT = "correct"
    FLAG_REVIEW = "flag_review"
    NO_ACTION = "no_action"

@dataclass
class Feedback:
    id: str
    tile_id: str
    feedback_type: FeedbackType
    value: float = 0.0       # -1 to 1 for votes, 1-5 for ratings
    comment: str = ""
    user_id: str = ""
    sentiment: float = 0.0   # -1 (negative) to 1 (positive)
    action: FeedbackAction = FeedbackAction.NO_ACTION
    created_at: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)

@dataclass
class TileFeedbackSummary:
    tile_id: str
    total_feedback: int = 0
    upvotes: int = 0
    downvotes: int = 0
    avg_rating: float = 0.0
    avg_sentiment: float = 0.0
    corrections: int = 0
    flags: int = 0
    net_score: float = 0.0
    trend: str = "neutral"

class TileFeedback:
    def __init__(self, auto_action: bool = True):
        self.auto_action = auto_action
        self._feedback: dict[str, list[Feedback]] = defaultdict(list)
        self._user_feedback: dict[str, set[str]] = defaultdict(set)  # user → tile_ids
        self._action_log: list[dict] = []

    def add(self, tile_id: str, feedback_type: str, value: float = 0.0,
            comment: str = "", user_id: str = "", metadata: dict = None) -> Feedback:
        fb_id = f"fb-{tile_id}-{int(time.time()*1000)}"
        ft = FeedbackType(feedback_type)
        sentiment = self._compute_sentiment(ft, value, comment)
        action = self._determine_action(ft, value, sentiment) if self.auto_action else FeedbackAction.NO_ACTION
        fb = Feedback(id=fb_id, tile_id=tile_id, feedback_type=ft, value=value,
                     comment=comment, user_id=user_id, sentiment=sentiment,
                     action=action, metadata=metadata or {})
        self._feedback[tile_id].append(fb)
        if user_id:
            self._user_feedback[user_id].add(tile_id)
        if action != FeedbackAction.NO_ACTION:
            self._action_log.append({"action": action.value, "tile_id": tile_id,
                                    "feedback_id": fb_id, "timestamp": time.time()})
        return fb

    def summary(self, tile_id: str) -> TileFeedbackSummary:
        items = self._feedback.get(tile_id, [])
        if not items:
            return TileFeedbackSummary(tile_id=tile_id)
        upvotes = sum(1 for f in items if f.feedback_type == FeedbackType.UPVOTE)
        downvotes = sum(1 for f in items if f.feedback_type == FeedbackType.DOWNVOTE)
        ratings = [f.value for f in items if f.feedback_type == FeedbackType.RATING]
        sentiments = [f.sentiment for f in items]
        corrections = sum(1 for f in items if f.feedback_type == FeedbackType.CORRECTION)
        flags = sum(1 for f in items if f.feedback_type == FeedbackType.FLAG)
        avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0.0
        avg_rating = sum(ratings) / len(ratings) if ratings else 0.0
        net_score = upvotes - downvotes + avg_sentiment * 10
        # Trend: compare recent vs older feedback
        midpoint = len(items) // 2
        recent = items[midpoint:]
        older = items[:midpoint] if midpoint > 0 else items
        recent_sent = sum(f.sentiment for f in recent) / max(len(recent), 1)
        older_sent = sum(f.sentiment for f in older) / max(len(older), 1)
        trend = "improving" if recent_sent > older_sent + 0.1 else (
            "declining" if recent_sent < older_sent - 0.1 else "neutral")
        return TileFeedbackSummary(
            tile_id=tile_id, total_feedback=len(items),
            upvotes=upvotes, downvotes=downvotes, avg_rating=round(avg_rating, 2),
            avg_sentiment=round(avg_sentiment, 3), corrections=corrections, flags=flags,
            net_score=round(net_score, 2), trend=trend
        )

    def top_tiles(self, n: int = 10, metric: str = "net_score") -> list[TileFeedbackSummary]:
        summaries = [self.summary(tid) for tid in self._feedback]
        summaries.sort(key=lambda s: getattr(s, metric, 0), reverse=True)
        return summaries[:n]

    def flagged_tiles(self, threshold: int = 3) -> list[str]:
        return [tid for tid in self._feedback
                if sum(1 for f in self._feedback[tid] if f.feedback_type == FeedbackType.FLAG) >= threshold]

    def user_history(self, user_id: str) -> list[Feedback]:
        result = []
        for tile_id in self._user_feedback.get(user_id, set()):
            result.extend(f for f in self._feedback.get(tile_id, []) if f.user_id == user_id)
        result.sort(key=lambda f: f.created_at, reverse=True)
        return result

    def by_type(self, feedback_type: str) -> list[Feedback]:
        ft = FeedbackType(feedback_type)
        return [f for items in self._feedback.values() for f in items if f.feedback_type == ft]

    def recent(self, n: int = 20) -> list[Feedback]:
        all_fb = [f for items in self._feedback.values() for f in items]
        all_fb.sort(key=lambda f: f.created_at, reverse=True)
        return all_fb[:n]

    def _compute_sentiment(self, ft: FeedbackType, value: float, comment: str) -> float:
        base = 0.0
        if ft == FeedbackType.UPVOTE:
            base = 0.8
        elif ft == FeedbackType.DOWNVOTE:
            base = -0.8
        elif ft == FeedbackType.RATING:
            base = (value - 3.0) / 2.0  # normalize 1-5 to -1..1
        elif ft == FeedbackType.FLAG:
            base = -0.9
        elif ft == FeedbackType.CORRECTION:
            base = -0.3
        # Adjust by comment keywords
        if comment:
            positive_words = {"great", "good", "helpful", "correct", "thanks", "love", "excellent"}
            negative_words = {"wrong", "bad", "broken", "error", "fix", "incorrect", "misleading"}
            words = set(re.findall(r'\b\w+\b', comment.lower()))
            pos_count = len(words & positive_words)
            neg_count = len(words & negative_words)
            if pos_count + neg_count > 0:
                base = base * 0.7 + (pos_count - neg_count) / (pos_count + neg_count) * 0.3
        return max(-1.0, min(1.0, base))

    def _determine_action(self, ft: FeedbackType, value: float, sentiment: float) -> FeedbackAction:
        if ft == FeedbackType.FLAG and value >= 3:
            return FeedbackAction.FLAG_REVIEW
        if ft == FeedbackType.CORRECTION:
            return FeedbackAction.CORRECT
        if sentiment > 0.5:
            return FeedbackAction.BOOST
        if sentiment < -0.5:
            return FeedbackAction.DEMOTE
        return FeedbackAction.NO_ACTION

    @property
    def stats(self) -> dict:
        total = sum(len(items) for items in self._feedback.values())
        tiles = len(self._feedback)
        users = len(self._user_feedback)
        return {"tiles": tiles, "total_feedback": total, "users": users,
                "actions_taken": len(self._action_log),
                "avg_per_tile": round(total / tiles, 1) if tiles > 0 else 0}
