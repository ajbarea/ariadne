"""WorldSpeech (`disco-eth/WorldSpeech`) as an AUDIO dataset adapter.

Proves the audio modality on the canonical seam. Per ADR-0008 (multimodal via
agentic-to-text), audio is reasoned over as text; WorldSpeech ships a
human-provided transcript per utterance, so the deterministic mapping uses that
transcript directly — no live ASR. ``map_utterances`` is a pure transform
(fabricated rows in tests); the adapter class streams the real corpus.

Rows are 24 kHz parliamentary / broadcaster / institutional speech utterances:
``human_transcript`` + ``source`` (the institution) + ``source_url`` +
``session_date`` + ``language`` + ``country`` + ``segment_id``.

Known issue (env-specific, cosmetic): ``ariadne index --dataset worldspeech`` exits 134
on some envs (e.g. Python 3.12 + WSL2). ``datasets`` imports torch to handle the
audio-schema column at load time, and torch's *core* threading segfaults at interpreter
finalization (``PyGILState_Release`` — a PEP 788 C-API-finalization class), independent
of CUDA (CPU-only torch crashes identically) and unfixable by column selection (torch
loads regardless). The 500 transcript documents index correctly; only the process exit
code is affected. Verified 2026-06 across datasets ``select_columns``/``columns=``,
``CUDA_VISIBLE_DEVICES=``, and a CPU-only torch build.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Literal

from ariadne.datasets.base import register
from ariadne.datasets.canonical import Canonical, Document, Entity

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from ariadne.evaluation.needle import NeedleFixture


def _org_id(source: str) -> str:
    return f"org:{source}"


def map_utterances(rows: Iterable[dict]) -> Iterator[Canonical]:
    """Map speech utterances to canonical records (source orgs + transcript documents).

    Each utterance with a non-empty transcript becomes a ``speech_transcript``
    Document linked to its ``source`` institution (one deduped org Entity per
    distinct source).
    """
    orgs: dict[str, Entity] = {}
    documents: list[Document] = []

    for row in rows:
        transcript = str(row.get("human_transcript") or "").strip()
        if not transcript:
            continue
        source = str(row.get("source") or "").strip()
        source_ids: tuple[str, ...] = ()
        if source:
            oid = _org_id(source)
            orgs.setdefault(oid, Entity(id=oid, type="org", name=source))
            source_ids = (oid,)
        documents.append(
            Document(
                id=f"utterance:{row.get('segment_id', '')}",
                text=transcript,
                source_entity_ids=source_ids,
                metadata={
                    "source": source,
                    "source_url": str(row.get("source_url") or ""),
                    "session_date": str(row.get("session_date") or ""),
                    "language": str(row.get("language") or ""),
                    "country": str(row.get("country") or ""),
                    "duration": str(row.get("duration") or ""),
                },
                modality="speech_transcript",
            )
        )

    yield from orgs.values()
    yield from documents


_DATASET = "disco-eth/WorldSpeech"
_DEFAULT_CONFIG = "en_us"  # one language-region config; streaming bounds the volume
_DEFAULT_LIMIT = 500


class WorldSpeechAdapter:
    """Streams one ``disco-eth/WorldSpeech`` language-region config to canonical.

    ``config`` selects a language-region (e.g. ``en_us``, ``en_pk``); ``limit``
    bounds rows so we never pull the multi-TB whole. License is CC-BY-NC-4.0
    (research/demo use).
    """

    name: str = "worldspeech"
    entity_type: str = "org"
    access: Literal["public", "restricted"] = "public"

    def __init__(self, config: str = _DEFAULT_CONFIG, limit: int = _DEFAULT_LIMIT) -> None:
        self.config = config
        self.limit = limit

    def _stream(self):
        # Lazy import via importlib so the static checker stays stable whether or
        # not the optional `data` extra is installed (mirrors enron.py).
        import importlib

        datasets = importlib.import_module("datasets")
        ds = datasets.load_dataset(_DATASET, name=self.config, split="train", streaming=True)
        # Don't decode the raw audio column: we map the provided transcript
        # (ADR-0008, audio-as-text); decoding would require torchcodec we don't
        # need. cast to Audio(decode=False) so iteration skips the decoder.
        with contextlib.suppress(ValueError, KeyError):
            ds = ds.cast_column("audio", datasets.Audio(decode=False))
        return ds

    def _rows(self):
        for taken, row in enumerate(self._stream()):
            yield row
            if taken + 1 >= self.limit:
                break

    def load(self):
        return map_utterances(self._rows())

    def eval_fixtures(self) -> list[NeedleFixture]:
        # Real speech content is not known a priori, so no planted needle; this
        # connector proves audio-modality ingestion, not needle grounding.
        return []


register(WorldSpeechAdapter())
