"""RAG: поиск по документам из рабочей папки.
Индекс строится один раз и обновляется только для изменённых файлов."""
import hashlib
import json
import threading

import numpy as np

from . import config, monitor
from .textio import DOC_SUFFIXES, chunk_text, extract_text

_lock = threading.Lock()


class DocIndex:
    def __init__(self):
        self.dir = config.DATA_DIR / "index"
        self.meta_path = self.dir / "meta.json"
        self.vec_path = self.dir / "vectors.npy"

    def _load(self):
        if self.meta_path.exists() and self.vec_path.exists():
            return json.loads(self.meta_path.read_text(encoding="utf-8")), np.load(self.vec_path)
        return {"model": None, "files": {}, "chunks": []}, np.zeros((0, 0))

    def _files(self):
        return sorted(p for p in config.WORKSPACE.rglob("*")
                      if p.is_file() and p.suffix.lower() in DOC_SUFFIXES and not p.name.startswith("."))

    def build(self, force=False):
        from .router import ROUTER
        with _lock:
            meta, vecs = self._load()
            if force or meta["model"] != config.ROLES["embed"]:
                meta, vecs = {"model": config.ROLES["embed"], "files": {}, "chunks": []}, np.zeros((0, 0))

            current = {}
            for p in self._files():
                rel = str(p.relative_to(config.WORKSPACE))
                current[rel] = hashlib.md5(p.read_bytes()).hexdigest()

            keep = [i for i, c in enumerate(meta["chunks"]) if current.get(c["file"]) == meta["files"].get(c["file"])]
            chunks = [meta["chunks"][i] for i in keep]
            vecs = vecs[keep] if len(keep) and vecs.size else np.zeros((0, 0))

            changed = [f for f, h in current.items() if meta["files"].get(f) != h]
            new_chunks, errors = [], []
            for rel in changed:
                try:
                    text = extract_text(config.WORKSPACE / rel)
                    new_chunks += [{"file": rel, "text": t} for t in chunk_text(text)]
                except Exception as e:
                    errors.append(f"{rel}: {e}")
            if new_chunks:
                new_vecs = np.array(ROUTER.embed([c["text"] for c in new_chunks]), dtype=np.float32)
                vecs = new_vecs if not vecs.size else np.vstack([vecs, new_vecs])
                chunks += new_chunks

            meta = {"model": config.ROLES["embed"], "files": current, "chunks": chunks}
            self.dir.mkdir(parents=True, exist_ok=True)
            self.meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
            np.save(self.vec_path, vecs if vecs.size else np.zeros((0, 0)))

        monitor.trace("rag_index", files=len(current), updated=len(changed), chunks=len(chunks))
        report = f"Файлов: {len(current)}, обновлено: {len(changed)}, фрагментов в индексе: {len(chunks)}"
        return report + (f"\nОшибки: {'; '.join(errors)}" if errors else "")

    def search(self, query, k=5):
        from .router import ROUTER
        meta, vecs = self._load()
        stale = not meta["chunks"] or any(
            meta["files"].get(str(p.relative_to(config.WORKSPACE))) is None for p in self._files())
        if stale:
            self.build()
            meta, vecs = self._load()
        if not meta["chunks"]:
            return []
        q = np.array(ROUTER.embed([query], input_type="query")[0], dtype=np.float32)
        sims = vecs @ q / (np.linalg.norm(vecs, axis=1) * np.linalg.norm(q) + 1e-9)
        top = np.argsort(-sims)[:k]
        return [{"file": meta["chunks"][i]["file"], "score": round(float(sims[i]), 3),
                 "text": meta["chunks"][i]["text"]} for i in top]


INDEX = DocIndex()
