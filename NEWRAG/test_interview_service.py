#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""面试领域逻辑测试，不调用真实模型。"""

import tempfile
import unittest
from pathlib import Path

from interview_service import (
    DeepSeekJsonClient,
    InterviewService,
    count_chinese,
    detect_mode,
    trim_answer_command,
)
from interview_store import InterviewStore


class InterviewServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = InterviewStore(Path(self.temp_dir.name))
        self.llm = DeepSeekJsonClient()
        self.llm.api_key = ""
        self.service = InterviewService(self.store, self.llm)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_transition_keyword_truncates_answer(self):
        transcript, keyword = trim_answer_command(
            "我先说明方案，然后给出验证结果。回答完毕。"
        )
        self.assertEqual(transcript, "我先说明方案，然后给出验证结果。")
        self.assertEqual(keyword, "回答完毕")

    def test_mode_thresholds(self):
        self.assertEqual(detect_mode(["Java", "MySQL", "Redis"], ["Java"]), "broad")
        self.assertEqual(
            detect_mode(
                ["Java", "MySQL", "Redis", "Kafka", "JVM"],
                ["Java", "MySQL"],
            ),
            "precise",
        )
        self.assertEqual(
            detect_mode(
                ["Java", "MySQL", "Redis", "Kafka"],
                ["Java", "MySQL"],
            ),
            "precise",
        )

    def test_create_session_builds_three_questions(self):
        session = self.service.create_session(
            resume_text="本科计算机专业，负责 RAG 检索项目，熟悉 Java、MySQL、Redis。",
            jd="需要 Java、JVM、MySQL、Redis、Kafka，负责高并发服务。",
            company="示例公司",
            role="Java 后端工程师",
        )
        self.assertEqual(session["mode"], "precise")
        self.assertEqual(len(session["questions"]), 3)
        self.assertEqual(session["status"], "ready")
        self.assertIn("Java", session["jd_keywords"])

    def test_short_answer_penalty_and_fallback_score(self):
        session = self.service.create_session(
            resume_text="熟悉 Java、MySQL。",
            jd="需要 Java、MySQL、Redis。",
        )
        self.service.finalize_turn(
            session["session_id"],
            1,
            "我做过项目。",
            1000,
        )
        report = self.service.score_session(session["session_id"])
        self.assertTrue(report["short_answer_penalty"])
        self.assertLessEqual(report["total_score"], 60)
        self.assertTrue(report["estimated"])
        self.assertEqual(count_chinese(report["qa"][0]["transcript"]), 5)

    def test_weak_tags_are_scoped_to_store_root(self):
        payload = self.store.update_weak_tags(["RAG"])
        self.assertEqual(payload["tags"][0]["tag"], "RAG")
        self.assertTrue((Path(self.temp_dir.name) / "weak_tags.json").exists())


if __name__ == "__main__":
    unittest.main()
