from __future__ import annotations

import asyncio
import hashlib
import math
import re
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Optional, Sequence

from app.core.logging import get_logger
from app.core.settings import Settings, settings
from app.db.models import TargetTeam

logger = get_logger(__name__)

EMBEDDING_DIM = 256
BIGRAM_WEIGHT = 0.5
MIN_SIMILARITY = 0.2
MAX_RESOLUTION_SUMMARY_CHARS = 400
MAX_INDEXED_TICKET_CHARS = 1000

_STOPWORDS = frozenset(
    {
        "a", "an", "the", "is", "are", "am", "was", "were", "be", "to", "of", "in", "on", "at",
        "for", "with", "my", "me", "i", "it", "its", "and", "or", "do", "does", "how", "can",
        "could", "would", "should", "please", "when", "every", "keeps", "get", "gets", "this",
        "that", "we", "our", "you", "your", "m", "s", "t", "from", "by", "as", "but", "so",
    }
)


@dataclass(frozen=True)
class KnowledgeEntry:
    """One resolved historical ticket stored in the knowledge base."""

    entry_id: str
    ticket_text: str
    team: TargetTeam
    resolution: str


DEFAULT_KNOWLEDGE_BASE: tuple[KnowledgeEntry, ...] = (
    KnowledgeEntry(
        "KB-0001",
        "VPN keeps dropping every few minutes when connected over home Wi-Fi",
        TargetTeam.NETWORK,
        "Moved to the 5 GHz band or a wired connection, flushed the DNS cache, disabled other VPN or proxy software, and restarted the GlobalProtect agent.",
    ),
    KnowledgeEntry(
        "KB-0002",
        "GlobalProtect VPN fails to connect on macOS after an update",
        TargetTeam.NETWORK,
        "Allowed the blocked system extension in Privacy & Security, restarted the Mac, and signed in to GlobalProtect again.",
    ),
    KnowledgeEntry(
        "KB-0003",
        "Wi-Fi is very slow and web pages time out on my laptop",
        TargetTeam.NETWORK,
        "Forgot and rejoined the Wi-Fi network, restarted the router, tested on a hotspot to isolate the network, and flushed the DNS cache.",
    ),
    KnowledgeEntry(
        "KB-0004",
        "How do I export Jira filter results to Excel",
        TargetTeam.SOFTWARE,
        "Opened the filter in issue search, used Export Excel CSV, then imported the file in Excel with Data > From Text/CSV.",
    ),
    KnowledgeEntry(
        "KB-0005",
        "How do I build a pivot table in Excel to summarize data by status",
        TargetTeam.SOFTWARE,
        "Selected the data range, chose Insert > PivotTable, then dragged status to Rows and a count field to Values.",
    ),
    KnowledgeEntry(
        "KB-0006",
        "Outlook is not syncing new emails",
        TargetTeam.SOFTWARE,
        "Confirmed Work Offline was off, restarted Outlook, and repaired the account from File > Account Settings.",
    ),
    KnowledgeEntry(
        "KB-0007",
        "Microphone not detected in Teams meetings",
        TargetTeam.SOFTWARE,
        "Enabled microphone permission for Teams in the operating system, selected the correct device in Teams settings, and restarted Teams.",
    ),
    KnowledgeEntry(
        "KB-0008",
        "External monitor flickers after connecting to the docking station",
        TargetTeam.HARDWARE,
        "Swapped the video cable, updated display drivers, lowered the refresh rate, and reseated the dock connection.",
    ),
    KnowledgeEntry(
        "KB-0009",
        "USB headset is not detected by my laptop",
        TargetTeam.HARDWARE,
        "Tried a different USB port, selected the headset as the default sound device, and updated audio drivers.",
    ),
    KnowledgeEntry(
        "KB-0010",
        "CI pipeline fails at the dependency install step",
        TargetTeam.INFRA,
        "Checked for recent lockfile changes, cleared the build cache, and re-ran the pipeline from a clean workspace.",
    ),
)


@dataclass(frozen=True)
class RAGResult:
    """Knowledge-base lookup outcome: prompt-ready snippets and their source ids."""

    snippets: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        if token in _STOPWORDS:
            continue
        if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]
        tokens.append(token)
    return tokens


@lru_cache(maxsize=8192)
def _bucket(feature: str) -> tuple[int, float]:
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    return value % EMBEDDING_DIM, 1.0 if (value >> 40) & 1 else -1.0


def embed_text(text: str) -> Optional[list[float]]:
    """Deterministic signed-hashing embedding of unigrams and bigrams; None when no usable tokens exist."""
    tokens = _tokens(text)
    if not tokens:
        return None
    vector = [0.0] * EMBEDDING_DIM
    for token in tokens:
        index, sign = _bucket(token)
        vector[index] += sign
    for first, second in zip(tokens, tokens[1:]):
        index, sign = _bucket(f"{first} {second}")
        vector[index] += BIGRAM_WEIGHT * sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return None
    return [value / norm for value in vector]


def _collapse(text: str, limit: int) -> str:
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _format_snippet(ticket_text: str, resolution: str) -> str:
    return f"Ticket: {ticket_text} | Resolution: {resolution}"


class RAGService:
    """ChromaDB-backed past-ticket knowledge base used to ground Gemini resolutions."""

    def __init__(self, cfg: Settings = settings) -> None:
        self._cfg = cfg
        self._lock = threading.Lock()
        self._attempted = False
        self._ready = False
        self._collection: Optional[Any] = None

    @property
    def is_ready(self) -> bool:
        """True once the ChromaDB collection has been opened and seeded successfully."""
        return self._ready

    def _initialise(self) -> bool:
        with self._lock:
            if self._attempted:
                return self._ready
            self._attempted = True
            try:
                import chromadb
                from chromadb.config import Settings as ChromaSettings

                client = chromadb.PersistentClient(
                    path=self._cfg.CHROMA_PERSIST_DIR,
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
                collection = client.get_or_create_collection(
                    name=self._cfg.CHROMA_COLLECTION,
                    metadata={"hnsw:space": "cosine"},
                    embedding_function=None,
                )
                self._seed(collection)
                self._collection = collection
                self._ready = True
                logger.info(
                    "RAG knowledge base ready",
                    extra={"collection": self._cfg.CHROMA_COLLECTION, "documents": collection.count()},
                )
            except Exception:  # noqa: BLE001 - RAG is optional grounding and must never block the pipeline
                logger.exception("RAG knowledge base unavailable; Gemini will run without grounding")
                self._collection = None
                self._ready = False
            return self._ready

    @staticmethod
    def _seed(collection: Any) -> None:
        ids: list[str] = []
        embeddings: list[list[float]] = []
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []
        for entry in DEFAULT_KNOWLEDGE_BASE:
            embedding = embed_text(entry.ticket_text)
            if embedding is None:
                continue
            ids.append(entry.entry_id)
            embeddings.append(embedding)
            documents.append(entry.ticket_text)
            metadatas.append({"target_team": entry.team.value, "resolution": entry.resolution, "origin": "seed"})
        if ids:
            collection.upsert(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)

    def _retrieve_sync(self, raw_text: str) -> RAGResult:
        if not self._initialise() or self._collection is None:
            return RAGResult()
        embedding = embed_text(raw_text)
        if embedding is None:
            return RAGResult()
        total = self._collection.count()
        if total == 0:
            return RAGResult()
        response = self._collection.query(
            query_embeddings=[embedding],
            n_results=min(self._cfg.RAG_TOP_K, total),
            include=["documents", "metadatas", "distances"],
        )
        ids = (response.get("ids") or [[]])[0]
        documents = (response.get("documents") or [[]])[0]
        metadatas = (response.get("metadatas") or [[]])[0]
        distances = (response.get("distances") or [[]])[0]

        snippets: list[str] = []
        source_ids: list[str] = []
        for entry_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
            similarity = 1.0 - float(distance)
            if similarity < MIN_SIMILARITY:
                continue
            resolution = str((metadata or {}).get("resolution", "")).strip()
            if not document or not resolution:
                continue
            snippets.append(_format_snippet(str(document), resolution))
            source_ids.append(str(entry_id))
        return RAGResult(snippets=snippets, source_ids=source_ids)

    def _index_sync(self, ticket_id: str, raw_text: str, team: TargetTeam, resolution_text: str) -> bool:
        if not self._initialise() or self._collection is None:
            return False
        ticket_text = _collapse(raw_text, MAX_INDEXED_TICKET_CHARS)
        embedding = embed_text(ticket_text)
        if embedding is None:
            return False
        self._collection.upsert(
            ids=[f"TICKET-{ticket_id}"],
            embeddings=[embedding],
            documents=[ticket_text],
            metadatas=[
                {
                    "target_team": team.value,
                    "resolution": _collapse(resolution_text, MAX_RESOLUTION_SUMMARY_CHARS),
                    "origin": "resolved_ticket",
                }
            ],
        )
        return True

    async def initialize(self) -> bool:
        """Opens and seeds the knowledge base off the event loop; returns whether RAG is available."""
        return await asyncio.to_thread(self._initialise)

    async def retrieve(self, raw_text: str) -> RAGResult:
        """Returns similar resolved tickets for the given text; empty when RAG is unavailable or nothing is similar."""
        try:
            return await asyncio.to_thread(self._retrieve_sync, raw_text)
        except Exception:  # noqa: BLE001 - grounding failures must not fail ticket processing
            logger.exception("RAG retrieval failed; continuing without grounding")
            return RAGResult()

    async def index_resolved_ticket(
        self,
        ticket_id: str,
        raw_text: str,
        team: TargetTeam,
        resolution_text: str,
    ) -> bool:
        """Adds a resolved ticket to the knowledge base; returns False instead of raising on any failure."""
        try:
            return await asyncio.to_thread(self._index_sync, ticket_id, raw_text, team, resolution_text)
        except Exception:  # noqa: BLE001 - indexing is best-effort
            logger.exception("Failed to index resolved ticket", extra={"ticket_id": ticket_id})
            return False


_rag_service: Optional[RAGService] = None


def get_rag_service() -> RAGService:
    """Returns the process-wide RAG service so the ChromaDB client is opened once."""
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service
