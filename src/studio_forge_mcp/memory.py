"""sqlite-vec semantic memory store for studio-forge-mcp."""

from __future__ import annotations

import hashlib
import math
import sqlite3
import struct
from pathlib import Path

import sqlite_vec  # type: ignore[import-untyped]

from studio_forge_mcp.schemas import ForgeMemoryHit

EMBEDDING_DIM = 64


def compute_embedding(text: str) -> list[float]:
    """Deterministic 64-d normalized character-trigram embedding."""
    vec = [0.0] * EMBEDDING_DIM
    normalized = " ".join((text or "").lower().split())
    if not normalized:
        return vec
    padded = f"  {normalized}  "
    for i in range(len(padded) - 2):
        trigram = padded[i : i + 3]
        digest = hashlib.blake2b(trigram.encode("utf-8"), digest_size=4).digest()
        idx = int.from_bytes(digest, "little") % EMBEDDING_DIM
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _pack_f32(vec: list[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)


class ForgeVectorMemory:
    """SQLite + sqlite-vec (vec0) store for edited artifacts and recipes."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS forge_memory_meta (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                ref_id TEXT NOT NULL,
                summary TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(kind, ref_id)
            );
            """
        )
        conn.execute(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS forge_memory_vec USING vec0(
                embedding float[{EMBEDDING_DIM}]
            );
            """
        )
        conn.commit()
        return conn

    def vec_version(self) -> str:
        conn = self._connect()
        try:
            row = conn.execute("SELECT vec_version()").fetchone()
            return str(row[0])
        finally:
            conn.close()

    def index(self, kind: str, ref_id: str, text: str) -> int:
        vec = compute_embedding(text)
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO forge_memory_meta (kind, ref_id, summary, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(kind, ref_id) DO UPDATE SET
                    summary = excluded.summary,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (kind, ref_id, text[:300]),
            )
            rowid = int(
                conn.execute(
                    "SELECT id FROM forge_memory_meta WHERE kind = ? AND ref_id = ?",
                    (kind, ref_id),
                ).fetchone()["id"]
            )
            conn.execute("DELETE FROM forge_memory_vec WHERE rowid = ?", (rowid,))
            conn.execute(
                "INSERT INTO forge_memory_vec(rowid, embedding) VALUES (?, ?)",
                (rowid, _pack_f32(vec)),
            )
            conn.commit()
            return rowid
        finally:
            conn.close()

    def search(
        self, query: str, *, kind: str | None = None, limit: int = 5
    ) -> list[ForgeMemoryHit]:
        vec = compute_embedding(query)
        conn = self._connect()
        try:
            sql = """
                SELECT m.kind, m.ref_id, m.summary, v.distance
                FROM forge_memory_vec v
                JOIN forge_memory_meta m ON m.id = v.rowid
                WHERE v.embedding MATCH ? AND k = ?
            """
            params: list[object] = [_pack_f32(vec), max(limit * 3, 15)]
            rows = conn.execute(sql, params).fetchall()
            hits: list[ForgeMemoryHit] = []
            for r in rows:
                if kind and r["kind"] != kind:
                    continue
                hits.append(
                    ForgeMemoryHit(
                        kind=str(r["kind"]),
                        ref_id=str(r["ref_id"]),
                        summary=str(r["summary"]),
                        distance=round(float(r["distance"]), 4),
                    )
                )
                if len(hits) >= limit:
                    break
            return hits
        finally:
            conn.close()
