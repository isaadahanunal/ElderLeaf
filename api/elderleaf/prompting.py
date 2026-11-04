"""Try SAM prompts in ranked order and keep the first confident answer.

Shared by the app (pipeline.py) and the eval (eval/run_agent.py), so the comparison measures
exactly what users get. Each round sends the next candidate of every unfinished chain in parallel
(e.g. crop try 2 and weed try 2 together); a chain stops at its first confident answer.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field

from .sam import PRICE_PER_IMAGE_USD, Segmentation, scores_from_text

MIN_MEAN_CONFIDENCE = 0.5


def is_confident(scores: list[float], threshold: float) -> bool:
    """A usable answer: at least one mask above the threshold and a decent mean confidence."""
    if not any(s >= threshold for s in scores):
        return False
    return statistics.fmean(scores) >= MIN_MEAN_CONFIDENCE


def _scores(seg: Segmentation) -> list[float]:
    """Scores of an answer; reads them from the raw text when masks were not decoded."""
    if seg.instances:
        return [i.score_or_one for i in seg.instances]
    return [1.0 if s is None else s for s in scores_from_text(seg.raw_text)]


@dataclass
class Attempt:
    target: str
    prompt: str
    rank: int | str  # 1, 2, 3 = agent's order; "fallback" = fixed phrase
    round: int
    masks: int = 0
    kept: int = 0
    mean_confidence: float | None = None
    latency_s: float | None = None
    cached: bool = False
    ok: bool = False
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Chain:
    target: str
    candidates: list[tuple[str, int | str]]
    attempts: list[Attempt] = field(default_factory=list)
    segs: dict[str, Segmentation] = field(default_factory=dict)
    chosen: Attempt | None = None
    _next: int = 0

    @property
    def finished(self) -> bool:
        return (self.chosen is not None and self.chosen.ok) or self._next >= len(self.candidates)

    def next_candidate(self) -> tuple[str, int | str]:
        candidate = self.candidates[self._next]
        self._next += 1
        return candidate

    def record(self, attempt: Attempt, seg: Segmentation | None) -> None:
        self.attempts.append(attempt)
        if seg is not None:
            self.segs[attempt.prompt] = seg
        if attempt.ok and (self.chosen is None or not self.chosen.ok):
            self.chosen = attempt

    def finalize(self) -> None:
        """No confident answer at all: keep the attempt with the most kept masks (then confidence)."""
        if self.chosen is None:
            usable = [a for a in self.attempts if a.prompt in self.segs]
            if usable:
                self.chosen = max(usable, key=lambda a: (a.kept, a.mean_confidence or 0.0))

    @property
    def chosen_seg(self) -> Segmentation | None:
        return self.segs.get(self.chosen.prompt) if self.chosen else None


def build_candidates(proposed: list[str], fallback: list[str], limit: int = 3) -> list[tuple[str, int | str]]:
    out: list[tuple[str, int | str]] = []
    seen: set[str] = set()
    for rank, prompt in enumerate(proposed[:limit], start=1):
        if prompt not in seen:
            out.append((prompt, rank))
            seen.add(prompt)
    for prompt in fallback:
        if prompt not in seen:
            out.append((prompt, "fallback"))
            seen.add(prompt)
    return out


def run_chains(
    sam,
    image,
    chains: list[Chain],
    threshold: float,
    *,
    on_start: Callable[[Chain, str, int | str], object] | None = None,
    on_done: Callable[[object, Chain, Attempt], None] | None = None,
    max_workers: int = 4,
    decode_chosen: bool = True,
) -> None:
    """Callbacks run in the calling thread (safe for DB writes).

    Attempts are judged on confidence scores only (no mask decoding, which is slow); with
    decode_chosen the masks of each chain's chosen answer are decoded at the end (cache hit)."""
    round_no = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        while active := [c for c in chains if not c.finished]:
            round_no += 1
            futures = {}
            for chain in active:
                prompt, rank = chain.next_candidate()
                token = on_start(chain, prompt, rank) if on_start else None
                futures[pool.submit(sam.segment, image, prompt, parse=False)] = (chain, prompt, rank, token)
            for future in as_completed(futures):
                chain, prompt, rank, token = futures[future]
                attempt = Attempt(target=chain.target, prompt=prompt, rank=rank, round=round_no)
                seg = None
                try:
                    seg = future.result()
                    scores = _scores(seg)
                    attempt.masks = len(scores)
                    attempt.kept = sum(s >= threshold for s in scores)
                    attempt.mean_confidence = round(statistics.fmean(scores), 3) if scores else None
                    attempt.latency_s = seg.meta.get("latency_s")
                    attempt.cached = bool(seg.meta.get("cached"))
                    attempt.ok = is_confident(scores, threshold)
                except Exception as exc:  # a failed call is a failed attempt; the chain moves on
                    attempt.error = f"{type(exc).__name__}: {exc}"
                chain.record(attempt, seg)
                if on_done:
                    on_done(token, chain, attempt)
    for chain in chains:
        chain.finalize()
        if decode_chosen and chain.chosen is not None and chain.chosen.prompt in chain.segs:
            chain.segs[chain.chosen.prompt] = sam.segment(image, chain.chosen.prompt)


def sam_latency(attempts: list[Attempt]) -> float:
    """Time spent waiting for SAM: calls of a round run in parallel, rounds run one after another."""
    rounds: dict[int, float] = {}
    for a in attempts:
        rounds[a.round] = max(rounds.get(a.round, 0.0), a.latency_s or 0.0)
    return round(sum(rounds.values()), 3)


def sam_cost(n_calls: int) -> float:
    return round(n_calls * PRICE_PER_IMAGE_USD, 6)
