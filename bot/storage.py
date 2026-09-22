"""Storage persistente del bot (SQLite, un file su disco: nessuna dipendenza
esterna, nessun servizio da pagare). Tiene traccia di chi si e' iscritto
all'intervista settimanale, di chi e' gia' stato estratto, e delle risposte
raccolte durante ogni intervista.

Lo schema e' pensato per essere interrogato in seguito da chi comporra'
l'inserto settimanale, senza doverlo ridisegnare.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

_SCHEMA = """
CREATE TABLE IF NOT EXISTS candidati (
    user_id INTEGER PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    username TEXT,
    registrato_il TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS estrazioni (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    settimana TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    invitato_il TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS interviste (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    settimana TEXT NOT NULL,
    nome TEXT NOT NULL DEFAULT '',
    stato TEXT NOT NULL DEFAULT 'invitato',
    pubblicata INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS risposte (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    intervista_id INTEGER NOT NULL REFERENCES interviste(id),
    indice_domanda INTEGER NOT NULL,
    domanda TEXT NOT NULL,
    risposta TEXT NOT NULL,
    creato_il TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS domande (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    intervista_id INTEGER NOT NULL REFERENCES interviste(id),
    indice INTEGER NOT NULL,
    testo TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Storage:
    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            # Un database creato prima che una colonna esistesse non la
            # riceve da CREATE TABLE IF NOT EXISTS (non tocca le tabelle
            # gia' esistenti): senza questo, ogni nuova colonna avrebbe
            # richiesto di cancellare a mano il file per ripartire puliti.
            self._assicura_colonna(conn, "interviste", "nome", "TEXT NOT NULL DEFAULT ''")
            self._assicura_colonna(conn, "interviste", "pubblicata", "INTEGER NOT NULL DEFAULT 0")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _assicura_colonna(
        conn: sqlite3.Connection, tabella: str, colonna: str, definizione: str
    ) -> None:
        colonne = {riga[1] for riga in conn.execute(f"PRAGMA table_info({tabella})")}
        if colonna not in colonne:
            conn.execute(f"ALTER TABLE {tabella} ADD COLUMN {colonna} {definizione}")

    def registra_candidato(self, user_id: int, chat_id: int, username: str | None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO candidati (user_id, chat_id, username, registrato_il)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    chat_id = excluded.chat_id,
                    username = excluded.username
                """,
                (user_id, chat_id, username, _now()),
            )

    def candidati_disponibili(self, esclusi: set[int]) -> list[tuple[int, int, str | None]]:
        with self._connect() as conn:
            righe = conn.execute(
                "SELECT user_id, chat_id, username FROM candidati"
            ).fetchall()
        return [riga for riga in righe if riga[0] not in esclusi]

    def gia_estratti_recentemente(self, ultime_settimane: int = 8) -> set[int]:
        with self._connect() as conn:
            righe = conn.execute(
                "SELECT user_id FROM estrazioni ORDER BY id DESC LIMIT ?",
                (ultime_settimane,),
            ).fetchall()
        return {riga[0] for riga in righe}

    def registra_estrazione(self, settimana: str, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO estrazioni (settimana, user_id, invitato_il) VALUES (?, ?, ?)",
                (settimana, user_id, _now()),
            )

    def apri_intervista(self, user_id: int, settimana: str, nome: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO interviste (user_id, settimana, nome, stato) VALUES (?, ?, ?, 'invitato')",
                (user_id, settimana, nome),
            )
            return int(cur.lastrowid)

    def intervista_aperta_per(self, user_id: int) -> tuple[int, str, str] | None:
        with self._connect() as conn:
            riga = conn.execute(
                """
                SELECT id, stato, nome FROM interviste
                WHERE user_id = ? AND stato != 'completata'
                ORDER BY id DESC LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        return tuple(riga) if riga else None

    def aggiorna_stato_intervista(self, intervista_id: int, stato: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE interviste SET stato = ? WHERE id = ?", (stato, intervista_id)
            )

    def salva_risposta(
        self, intervista_id: int, indice_domanda: int, domanda: str, risposta: str
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO risposte (intervista_id, indice_domanda, domanda, risposta, creato_il)
                VALUES (?, ?, ?, ?, ?)
                """,
                (intervista_id, indice_domanda, domanda, risposta, _now()),
            )

    def salva_domande(self, intervista_id: int, domande: list[str]) -> None:
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO domande (intervista_id, indice, testo) VALUES (?, ?, ?)",
                [(intervista_id, indice, testo) for indice, testo in enumerate(domande)],
            )

    def carica_domande(self, intervista_id: int) -> list[str]:
        with self._connect() as conn:
            righe = conn.execute(
                "SELECT testo FROM domande WHERE intervista_id = ? ORDER BY indice",
                (intervista_id,),
            ).fetchall()
        return [riga[0] for riga in righe]

    def carica_risposte(self, intervista_id: int) -> list[tuple[str, str]]:
        with self._connect() as conn:
            righe = conn.execute(
                """
                SELECT domanda, risposta FROM risposte
                WHERE intervista_id = ? ORDER BY indice_domanda
                """,
                (intervista_id,),
            ).fetchall()
        return [tuple(riga) for riga in righe]

    def prossima_intervista_da_pubblicare(self) -> tuple[int, int, str] | None:
        """La piu' vecchia intervista completata e non ancora pubblicata
        (id, user_id, nome). FIFO: se una settimana salta, la prossima
        pubblicazione recupera quella rimasta indietro invece di saltarla."""
        with self._connect() as conn:
            riga = conn.execute(
                """
                SELECT id, user_id, nome FROM interviste
                WHERE stato = 'completata' AND pubblicata = 0
                ORDER BY id ASC LIMIT 1
                """
            ).fetchone()
        return tuple(riga) if riga else None

    def segna_pubblicata(self, intervista_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE interviste SET pubblicata = 1 WHERE id = ?", (intervista_id,)
            )
