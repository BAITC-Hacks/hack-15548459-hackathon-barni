"""Память.
- Краткосрочная: история каждой сессии (.harness/sessions/<id>.json) — переживает перезапуск.
- Долгосрочная: факты, которые агент сам решил запомнить (.harness/memory.json), поиск по смыслу.
"""
import json
import threading
import time
import uuid

import numpy as np

from . import config, monitor

_lock = threading.Lock()


class SessionStore:
    dir = config.DATA_DIR / "sessions"

    @classmethod
    def _path(cls, session_id):
        safe = "".join(ch for ch in session_id if ch.isalnum() or ch in "-_")[:80] or "default"
        return cls.dir / f"{safe}.json"

    @classmethod
    def load(cls, session_id):
        p = cls._path(session_id)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        return {"messages": [], "summary": ""}

    @classmethod
    def save(cls, session_id, state):
        cls.dir.mkdir(parents=True, exist_ok=True)
        cls._path(session_id).write_text(json.dumps(state, ensure_ascii=False, default=str), encoding="utf-8")

    @classmethod
    def delete(cls, session_id):
        cls._path(session_id).unlink(missing_ok=True)

    @classmethod
    def list(cls):
        return sorted(p.stem for p in cls.dir.glob("*.json")) if cls.dir.exists() else []


class LongTermMemory:
    path = config.DATA_DIR / "memory.json"

    def _load(self):
        return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else []

    def _save(self, items):
        self.path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")

    def add(self, text, tags=""):
        from .router import ROUTER
        try:
            emb = ROUTER.embed([text])[0]
        except Exception as e:
            monitor.log.warning("Память без эмбеддинга: %s", e)
            emb = None
        item = {"id": uuid.uuid4().hex[:8], "text": text, "tags": tags, "ts": time.time(), "emb": emb}
        with _lock:
            items = self._load()
            items.append(item)
            self._save(items)
        return item["id"]

    def search(self, query, k=5):
        items = self._load()
        if not items:
            return []
        scored = []
        with_emb = [it for it in items if it.get("emb")]
        if with_emb:
            try:
                from .router import ROUTER
                q = np.array(ROUTER.embed([query], input_type="query")[0])
                m = np.array([it["emb"] for it in with_emb])
                sims = m @ q / (np.linalg.norm(m, axis=1) * np.linalg.norm(q) + 1e-9)
                scored = [(float(s), it) for s, it in zip(sims, with_emb)]
            except Exception as e:
                monitor.log.warning("Поиск по памяти без эмбеддингов: %s", e)
        if not scored:  # запасной вариант — по словам
            words = set(query.lower().split())
            scored = [(len(words & set(it["text"].lower().split())) / (len(words) or 1), it) for it in items]
        scored.sort(key=lambda x: -x[0])
        return [{"id": it["id"], "text": it["text"], "tags": it["tags"], "score": round(s, 3)}
                for s, it in scored[:k]]

    def all(self):
        return [{k: v for k, v in it.items() if k != "emb"} for it in self._load()]

    def delete(self, item_id):
        with _lock:
            self._save([it for it in self._load() if it["id"] != item_id])


MEMORY = LongTermMemory()
