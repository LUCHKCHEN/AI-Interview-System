#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""voice_api 接口测试，使用 mock，不调用真实模型和外部 API。"""

import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

import voice_api
from voice_api import VOICE_OUTPUT_DIR, app


class FakeAsr:
    def __init__(self, text="Transformer 是什么？"):
        self.text = text
        self.generate_kwargs = None

    def generate(self, input, **kwargs):
        self.generate_kwargs = kwargs
        return [{"text": self.text}]


class FakeAudio:
    samples = [0.0, 0.1, 0.2]
    sample_rate = 16000


class FakeTts:
    def generate(self, text, generation_config=None):
        self.last_generation_config = generation_config
        return FakeAudio()


class VoiceApiTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()

    def test_health_returns_ok(self):
        with patch.object(voice_api.engine, "prepare", return_value=None):
            response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertTrue(response.json()["rag_ready"])

    def test_voice_ask_success_and_audio_download(self):
        with (
            patch.object(voice_api.engine, "prepare", return_value=None),
            patch.object(
                voice_api.engine,
                "ask",
                return_value={
                    "answer": "Transformer 使用自注意力机制。",
                    "sources": [
                        {"file": "a.md", "excerpt": "Transformer 使用自注意力机制"}
                    ],
                },
            ),
            patch.object(voice_api, "_get_asr", return_value=FakeAsr()),
            patch.object(voice_api, "_get_tts", return_value=FakeTts()),
            patch.object(voice_api, "_get_audio_duration", return_value=1.0),
        ):
            response = self.client.post(
                "/voice/ask",
                files={"audio": ("question.wav", b"fake-wav", "audio/wav")},
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["transcript"], "Transformer 是什么？")
        self.assertIn("自注意力机制", data["answer"])
        self.assertIn("task_id", data)

        audio_response = self.client.get(data["audio_url"])
        self.assertEqual(audio_response.status_code, 200)
        self.assertEqual(audio_response.headers["content-type"], "audio/wav")

    def test_missing_audio_returns_chinese_error(self):
        response = self.client.post("/voice/ask")
        self.assertEqual(response.status_code, 400)
        self.assertIn("上传音频", response.json()["detail"])

    def test_wrong_extension_rejected(self):
        response = self.client.post(
            "/voice/ask",
            files={"audio": ("question.txt", b"text", "text/plain")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("格式不支持", response.json()["detail"])

    def test_oversized_audio_rejected(self):
        with patch.object(voice_api, "MAX_UPLOAD_BYTES", 4):
            response = self.client.post(
                "/voice/ask",
                files={"audio": ("question.wav", b"x" * 10, "audio/wav")},
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("20MB", response.json()["detail"])

    def test_overlong_audio_rejected(self):
        with (
            patch.object(voice_api, "_get_audio_duration", return_value=301.0),
            patch.object(voice_api, "_get_asr", return_value=FakeAsr()),
        ):
            response = self.client.post(
                "/voice/ask",
                files={"audio": ("question.wav", b"fake-wav", "audio/wav")},
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("5 分钟", response.json()["detail"])

    def test_empty_transcript_rejected(self):
        empty_asr = FakeAsr(text="   ")
        with (
            patch.object(voice_api, "_get_asr", return_value=empty_asr),
            patch.object(voice_api, "_get_audio_duration", return_value=1.0),
        ):
            response = self.client.post(
                "/voice/ask",
                files={"audio": ("question.wav", b"fake-wav", "audio/wav")},
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("转写结果为空", response.json()["detail"])

    def test_rag_error_returns_chinese_error(self):
        with (
            patch.object(voice_api.engine, "prepare", return_value=None),
            patch.object(
                voice_api.engine,
                "ask",
                side_effect=ValueError("没有找到与问题相关的资料片段。"),
            ),
            patch.object(voice_api, "_get_asr", return_value=FakeAsr()),
            patch.object(voice_api, "_get_audio_duration", return_value=1.0),
        ):
            response = self.client.post(
                "/voice/ask",
                files={"audio": ("question.wav", b"fake-wav", "audio/wav")},
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("没有找到", response.json()["detail"])

    def test_tts_error_returns_server_error(self):
        with (
            patch.object(voice_api.engine, "prepare", return_value=None),
            patch.object(
                voice_api.engine,
                "ask",
                return_value={"answer": "答案", "sources": []},
            ),
            patch.object(voice_api, "_get_asr", return_value=FakeAsr()),
            patch.object(voice_api, "_get_audio_duration", return_value=1.0),
            patch.object(
                voice_api,
                "_synthesize",
                side_effect=RuntimeError("TTS 生成音频失败，请稍后重试。"),
            ),
        ):
            response = self.client.post(
                "/voice/ask",
                files={"audio": ("question.wav", b"fake-wav", "audio/wav")},
            )
        self.assertEqual(response.status_code, 500)
        self.assertIn("TTS", response.json()["detail"])

    def test_transcribe_uses_hotwords_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hotwords_file = Path(tmpdir) / "voice_hotwords.txt"
            hotwords_file.write_text(
                "自注意力机制\n多头注意力\n", encoding="utf-8"
            )
            fake_asr = FakeAsr()
            with (
                patch.object(voice_api, "_get_asr", return_value=fake_asr),
                patch.object(voice_api, "VOICE_HOTWORDS_FILE", hotwords_file),
            ):
                voice_api._transcribe(Path(tmpdir) / "audio.wav")
            self.assertEqual(
                fake_asr.generate_kwargs["hotword"], "自注意力机制 多头注意力"
            )
            self.assertEqual(
                fake_asr.generate_kwargs["postprocess_hotword_file"],
                str(hotwords_file),
            )

    def test_tts_lexicon_merges_extra_words(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir)
            base_lexicon = model_dir / "lexicon.txt"
            base_lexicon.write_text(
                "hello hh ah l ow 7 8 7 9\n", encoding="utf-8"
            )
            extra_lexicon = model_dir / "extra.txt"
            extra_lexicon.write_text(
                "# comment\nsoftmax s aa f t m ae k s 7 9 7 7 8 7 7 7\n",
                encoding="utf-8",
            )
            with (
                patch.object(voice_api, "TTS_MODEL_DIR", model_dir),
                patch.object(voice_api, "TTS_LEXICON_EXTRA_FILE", extra_lexicon),
                patch.object(
                    voice_api, "TTS_DYNAMIC_LEXICON_FILE", model_dir / "dynamic.txt"
                ),
            ):
                merged = voice_api._get_tts_lexicon()
            text = merged.read_text(encoding="utf-8")
            self.assertIn("hello hh ah l ow", text)
            self.assertIn("softmax s aa f t m ae k s", text)
            self.assertNotIn("# comment", text)

    def test_english_word_re_keeps_contractions(self):
        self.assertEqual(
            voice_api._ENGLISH_WORD_RE.findall(
                "Transformer's state-of-the-art model"
            ),
            ["Transformer's", "state-of-the-art", "model"],
        )

    def test_g2p_to_lexicon_line_maps_arpabet(self):
        with patch.object(
            voice_api,
            "_load_tts_tokens",
            return_value={"z", "ay", "l", "ah", "f", "ow", "n"},
        ):
            line = voice_api._g2p_to_lexicon_line(
                "xylophone",
                ["Z", "AY1", "L", "AH0", "F", "OW2", "N"],
            )
        self.assertEqual(
            line, "xylophone z ay l ah f ow n 7 8 7 7 7 9 7"
        )

    def test_ensure_tts_lexicon_generates_dynamic_entries(self):
        old_known = voice_api._known_tts_words
        old_tts_model = voice_api.tts_model
        voice_api._known_tts_words = None
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                model_dir = Path(tmpdir)
                extra_lexicon = model_dir / "extra.txt"
                extra_lexicon.write_text(
                    "hello hh ah l ow 7 8 7 9\n", encoding="utf-8"
                )
                dynamic_lexicon = model_dir / "dynamic.txt"

                class FakeG2p:
                    def __call__(self, word):
                        if word == "xylophone":
                            return ["Z", "AY1", "L", "AH0", "F", "OW2", "N"]
                        raise AssertionError(f"unexpected word: {word}")

                with (
                    patch.object(voice_api, "TTS_MODEL_DIR", model_dir),
                    patch.object(
                        voice_api, "TTS_LEXICON_EXTRA_FILE", extra_lexicon
                    ),
                    patch.object(
                        voice_api, "TTS_DYNAMIC_LEXICON_FILE", dynamic_lexicon
                    ),
                    patch.object(
                        voice_api, "_get_tts_g2p", return_value=FakeG2p()
                    ),
                    patch.object(
                        voice_api,
                        "_load_tts_tokens",
                        return_value={"z", "ay", "l", "ah", "f", "ow", "n"},
                    ),
                ):
                    changed = voice_api._ensure_tts_lexicon_for_text(
                        "hello xylophone"
                    )
                    changed_again = voice_api._ensure_tts_lexicon_for_text(
                        "xylophone"
                    )
                self.assertTrue(changed)
                self.assertFalse(changed_again)
                self.assertEqual(
                    dynamic_lexicon.read_text(encoding="utf-8").strip(),
                    "xylophone z ay l ah f ow n 7 8 7 7 7 9 7",
                )
        finally:
            voice_api._known_tts_words = old_known
            voice_api.tts_model = old_tts_model

    def test_synthesize_uses_configured_tts_speed(self):
        fake_tts = FakeTts()
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.object(voice_api, "_get_tts", return_value=fake_tts),
            patch.object(voice_api, "VOICE_OUTPUT_DIR", Path(tmpdir)),
        ):
            voice_api._synthesize("你好")
        self.assertLess(fake_tts.last_generation_config.speed, 1.0)
        self.assertAlmostEqual(
            fake_tts.last_generation_config.speed, voice_api.TTS_SPEED, places=6
        )


if __name__ == "__main__":
    unittest.main()
