"""Near-duplicate receipts: a picture embedding compared with every recent one (cosine).

The exact hash and the perceptual hash miss a receipt that was re-photographed, cropped or
re-rendered. A trained embedding (contrastive or triplet loss, so the same document lands close and
different documents, even from the same template, land apart) catches those. The search is across
organisations, like the hashes, and compares only vectors made by the same model file.

Brute force over the newest `scan_limit` embeddings is exact and needs no extra database extension;
the ceiling is stated in docs/authenticity-detectors.md.
"""

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

import numpy as np
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.detect.base import DetectorResult, skipped
from app.detect.manifest import Entry
from app.detect.onnx_runtime import ModelUnavailable
from app.models import EvidenceEmbedding

MIN_RELATED = 0.5  # below this a neighbour is not worth remembering


class Embedder(Protocol):
    def embed(self, img: Image.Image) -> np.ndarray: ...


@dataclass
class DuplicateSubject:
    image: Image.Image
    session: Session
    org_id: uuid.UUID
    claim_id: uuid.UUID
    evidence_id: uuid.UUID


def top_matches(
    matrix: np.ndarray, ids: list[uuid.UUID], vec: np.ndarray, k: int = 10
) -> list[tuple[uuid.UUID, float]]:
    """The k most similar rows by cosine similarity (rows and vec are L2-normalised)."""
    if matrix.size == 0:
        return []
    sims = matrix @ vec
    order = np.argsort(-sims)[:k]
    return [(ids[i], float(sims[i])) for i in order if sims[i] >= MIN_RELATED]


class NearDuplicateDetector:
    kind = "duplicate"

    def __init__(
        self,
        *,
        name: str,
        version: str,
        sha256: str,
        embedder: Embedder,
        default_threshold: float | None = None,
        uncertain_band: tuple[float, float] | None = None,
        scan_limit: int = 20000,
        days: int = 180,
    ):
        self.name = name
        self.version = version
        self.sha256 = sha256
        self.default_threshold = default_threshold
        self._embedder = embedder
        self._band = uncertain_band
        self._limit = scan_limit
        self._days = days

    @classmethod
    def from_entry(cls, entry: Entry, embedder: Embedder, scan_limit: int, days: int):
        return cls(
            name=entry.name,
            version=entry.version,
            sha256=entry.sha256,
            embedder=embedder,
            default_threshold=entry.threshold,
            uncertain_band=entry.uncertain_band,
            scan_limit=scan_limit,
            days=days,
        )

    def score(self, subject: DuplicateSubject) -> DetectorResult:
        started = time.perf_counter()
        try:
            vec = self._embedder.embed(subject.image)
        except ModelUnavailable as exc:
            return skipped(self.kind, self.name, str(exc))
        self._store(subject, vec)
        cutoff = datetime.now(UTC) - timedelta(days=self._days)
        rows = subject.session.execute(
            select(EvidenceEmbedding.claim_id, EvidenceEmbedding.vector)
            .where(
                EvidenceEmbedding.model_sha256 == self.sha256,
                EvidenceEmbedding.claim_id != subject.claim_id,
                EvidenceEmbedding.created_at >= cutoff,
            )
            .order_by(EvidenceEmbedding.created_at.desc())
            .limit(self._limit)
        ).all()
        rows = [r for r in rows if len(r.vector) == vec.size * 2]
        if rows:
            matrix = np.vstack([np.frombuffer(r.vector, dtype=np.float16) for r in rows])
            matches = top_matches(matrix.astype(np.float32), [r.claim_id for r in rows], vec)
        else:
            matches = []
        best = matches[0][1] if matches else 0.0
        band = self._band
        return DetectorResult(
            kind=self.kind,
            detector=self.name,
            model_version=self.version,
            model_sha256=self.sha256,
            score=min(1.0, max(0.0, best)),
            label="near_duplicate",
            uncertain=band is not None and band[0] <= best < band[1],
            latency_ms=(time.perf_counter() - started) * 1000,
            signals=[f"compared:{len(rows)}"],
            related=tuple(matches),
        )

    def _store(self, subject: DuplicateSubject, vec: np.ndarray) -> None:
        """Keep this file's embedding so later receipts can be compared with it."""
        payload = vec.astype(np.float16).tobytes()
        row = subject.session.get(EvidenceEmbedding, subject.evidence_id)
        if row is None:
            subject.session.add(
                EvidenceEmbedding(
                    evidence_id=subject.evidence_id,
                    org_id=subject.org_id,
                    claim_id=subject.claim_id,
                    model_sha256=self.sha256,
                    dim=int(vec.size),
                    vector=payload,
                )
            )
        else:  # a reprocessed claim, possibly under a newer model
            row.model_sha256, row.dim, row.vector = self.sha256, int(vec.size), payload
        subject.session.flush()
