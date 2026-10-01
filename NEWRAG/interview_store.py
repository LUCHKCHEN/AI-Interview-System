#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""面试会话与弱项标签的本地 JSON 持久化。"""

import json
import os
import re
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_DIR = Path(__file__).resolve().parent
BASE_DIR = PROJECT_DIR.parent
RECORDS_DIR = Path(
    os.getenv("INTERVIEW_RECORDS_DIR", "").strip()
    or str(BASE_DIR / "interview_records")
)
SESSION_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class InterviewStore:
    """读写面试记录；每个会话保存为独立目录，便于导出和清理。"""

    def __init__(self, root: Path = RECORDS_DIR) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def session_dir(self, session_id: str) -> Path:
        if not SESSION_ID_RE.fullmatch(session_id or ""):
            raise ValueError("会话编号无效。")
        return self.root / session_id

    def _weak_tags_file(self) -> Path:
        return self.root / "weak_tags.json"

    def save(self, session: dict) -> None:
        session_id = session.get("session_id", "")
        directory = self.session_dir(session_id)
        directory.mkdir(parents=True, exist_ok=True)
        session["updated_at"] = datetime.now().isoformat(timespec="seconds")
        target = directory / "session.json"
        with self._lock:
            temp = directory / "session.json.tmp"
            temp.write_text(
                json.dumps(session, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temp.replace(target)

    def load(self, session_id: str) -> Optional[dict]:
        path = self.session_dir(session_id) / "session.json"
        with self._lock:
            if not path.exists():
                return None
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None

    def update(self, session_id: str, patch: Dict) -> Optional[dict]:
        with self._lock:
            session = self.load(session_id)
            if session is None:
                return None
            session.update(patch)
            self.save(session)
            return session

    def list_sessions(self, limit: int = 20, offset: int = 0) -> List[dict]:
        sessions = []
        with self._lock:
            for path in self.root.glob("*/session.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                sessions.append(data)
        sessions.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return sessions[offset : offset + limit]

    def delete(self, session_id: str) -> bool:
        directory = self.session_dir(session_id)
        with self._lock:
            if not directory.exists():
                return False
            shutil.rmtree(directory)
            return True

    def load_weak_tags(self) -> dict:
        path = self._weak_tags_file()
        with self._lock:
            if not path.exists():
                return {"tags": []}
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return {"tags": []}

    def save_weak_tags(self, payload: dict) -> None:
        path = self._weak_tags_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".json.tmp")
        with self._lock:
            temp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temp.replace(path)

    def update_weak_tags(self, tags: List[str]) -> dict:
        with self._lock:
            payload = self.load_weak_tags()
            existing = {
                item["tag"]: item
                for item in payload.get("tags", [])
                if isinstance(item, dict) and item.get("tag")
            }
            now = datetime.now().isoformat(timespec="seconds")
            for raw_tag in tags:
                tag = str(raw_tag).strip()
                if not tag:
                    continue
                item = existing.get(tag, {"tag": tag, "count": 0})
                item["count"] = int(item.get("count", 0)) + 1
                item["last_seen_at"] = now
                existing[tag] = item
            payload["tags"] = sorted(
                existing.values(),
                key=lambda item: (-int(item.get("count", 0)), item.get("tag", "")),
            )
            self.save_weak_tags(payload)
            return payload


store = InterviewStore()
