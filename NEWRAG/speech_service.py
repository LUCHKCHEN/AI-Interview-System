#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""面试接口复用的 ASR/TTS 适配层。"""

import tempfile
import wave
from pathlib import Path

import voice_api


def write_pcm16_wav(path: Path, pcm: bytes, sample_rate: int = 16000) -> None:
    """把 16-bit 单声道 PCM 写入 WAV 文件。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)


def transcribe_pcm(pcm: bytes, sample_rate: int = 16000) -> str:
    """把浏览器发送的 16kHz/16-bit 单声道 PCM 转成临时 WAV 后识别。"""

    if not pcm:
        return ""
    handle = tempfile.NamedTemporaryFile(
        prefix="interview_turn_",
        suffix=".wav",
        delete=False,
    )
    path = Path(handle.name)
    handle.close()
    try:
        write_pcm16_wav(path, pcm, sample_rate)
        return voice_api._transcribe(path)
    finally:
        path.unlink(missing_ok=True)


def synthesize_question(text: str) -> Path:
    return voice_api._synthesize(text)
