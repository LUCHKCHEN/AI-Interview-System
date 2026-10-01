#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""面试 HTTP/WebSocket 接口测试，不调用真实 ASR/TTS/LLM。"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import interview_api
from interview_service import DeepSeekJsonClient, InterviewService
from interview_store import InterviewStore


class InterviewApiTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = InterviewStore(Path(self.temp_dir.name))
        self.llm = DeepSeekJsonClient()
        self.llm.api_key = ""
        self.service = InterviewService(self.store, self.llm)
        interview_api.service = self.service
        interview_api.store = self.store
        self.client = TestClient(interview_api.app)
        self.env_patch = patch.dict(os.environ, {"INTERVIEW_AUTO_REBUILD": "0"})
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.client.close()
        self.temp_dir.cleanup()

    def _create_session(self):
        response = self.client.post(
            "/api/interview/sessions",
            data={
                "resume_text": "本科计算机专业，负责 RAG 检索项目，熟悉 Java 和 MySQL。",
                "jd": "需要 Java、JVM、MySQL、Redis、Kafka，参与高并发服务。",
                "company": "示例公司",
                "role": "Java 后端工程师",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_create_and_get_session(self):
        created = self._create_session()
        detail = self.client.get(
            f"/api/interview/sessions/{created['session_id']}"
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["mode"], "precise")
        self.assertEqual(len(detail.json()["questions"]), 3)
        self.assertNotIn("ideal_answer", detail.json()["questions"][0])

    def test_scanned_pdf_returns_text_fallback_code(self):
        with patch("interview_service.extract_pdf_text", return_value=""):
            response = self.client.post(
                "/api/interview/sessions",
                data={"jd": "Java MySQL Redis"},
                files={
                    "resume_pdf": (
                        "scan.pdf",
                        b"%PDF-fake",
                        "application/pdf",
                    )
                },
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error_code"], "SCANNED_PDF")

    def test_question_audio_uses_cached_wav(self):
        created = self._create_session()
        with patch.object(
            interview_api.speech_service,
            "synthesize_question",
            return_value=Path(self.temp_dir.name) / "generated.wav",
        ) as synthesize:
            generated = Path(self.temp_dir.name) / "generated.wav"
            generated.write_bytes(b"RIFFdemo")
            response = self.client.get(
                f"/api/interview/sessions/{created['session_id']}/turns/1/question-audio"
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "audio/wav")
        synthesize.assert_called_once()

    def test_completion_audio_uses_cached_wav(self):
        created = self._create_session()
        with patch.object(
            interview_api.speech_service,
            "synthesize_question",
            return_value=Path(self.temp_dir.name) / "generated.wav",
        ) as synthesize:
            generated = Path(self.temp_dir.name) / "generated.wav"
            generated.write_bytes(b"RIFFdemo")
            response = self.client.get(
                f"/api/interview/sessions/{created['session_id']}/completion-audio"
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "audio/wav")
        synthesize.assert_called_once()

    def test_websocket_finalizes_turn_and_report(self):
        created = self._create_session()
        session_id = created["session_id"]
        path = f"/api/interview/sessions/{session_id}/turns/1/answers"
        with patch.object(
            interview_api.speech_service,
            "transcribe_pcm",
            return_value="我先分析问题，再说明方案和结果。回答完毕。",
        ):
            with self.client.websocket_connect(path) as websocket:
                self.assertEqual(websocket.receive_json()["type"], "status")
                websocket.send_bytes(b"\x00\x00" * 16000)
                websocket.send_json({"type": "finish"})
                events = []
                while True:
                    try:
                        event = websocket.receive_json()
                    except WebSocketDisconnect:
                        break
                    events.append(event)
                    if event.get("type") == "finalized":
                        break
        self.assertTrue(any(item.get("type") == "transition" for item in events))
        finalized = next(item for item in events if item.get("type") == "finalized")
        self.assertEqual(finalized["transcript"], "我先分析问题，再说明方案和结果。")

        with patch.object(interview_api, "_write_reinforcement_docs"):
            finish = self.client.post(
                f"/api/interview/sessions/{session_id}/finish"
            )
            self.assertEqual(finish.status_code, 200)
            report = self.client.get(
                f"/api/interview/sessions/{session_id}/report"
            )
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.json()["status"], "ready")
        self.assertIn("total_score", report.json()["report"])

    def test_history_list_export_and_delete(self):
        created = self._create_session()
        session_id = created["session_id"]
        listing = self.client.get("/api/history")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["items"][0]["session_id"], session_id)

        exported = self.client.get(f"/api/history/{session_id}/export")
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(exported.json()["session_id"], session_id)

        deleted = self.client.delete(f"/api/history/{session_id}")
        self.assertEqual(deleted.status_code, 200)
        missing = self.client.get(f"/api/history/{session_id}")
        self.assertEqual(missing.status_code, 404)


if __name__ == "__main__":
    unittest.main()
