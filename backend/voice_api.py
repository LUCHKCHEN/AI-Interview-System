#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""AI面试系统独立语音问答接口：上传音频 -> 转写 -> RAG -> TTS -> 下载 WAV。"""

import json
import logging
import os
import re
import subprocess
import tempfile
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Optional

import soundfile as sf
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from rag_engine import RagEngine

# funasr 和 fastembed 分别加载不同 OpenMP 运行库，需要显式允许共存。
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

PROJECT_DIR = Path(__file__).resolve().parent
BASE_DIR = PROJECT_DIR.parent
ENV_FILE = BASE_DIR / ".env"
load_dotenv(ENV_FILE, override=True)
VOICE_OUTPUT_DIR = PROJECT_DIR / "voice_output"
DEFAULT_TTS_MODEL_DIR = PROJECT_DIR / "models" / "vits-melo-tts-zh_en"
ASR_MODEL = os.getenv("ASR_MODEL", "").strip() or "paraformer-zh"
ASR_DEVICE = os.getenv("ASR_DEVICE", "").strip() or "cuda:0"
VOICE_HOTWORDS_FILE = Path(
    os.getenv("VOICE_HOTWORDS_FILE", "").strip()
    or str(PROJECT_DIR / "voice_hotwords.txt")
)
TTS_LEXICON_EXTRA_FILE = PROJECT_DIR / "tts_lexicon_extra.txt"
TTS_DYNAMIC_LEXICON_FILE = PROJECT_DIR / "tts_dynamic_lexicon.txt"
VOICE_API_HOST = os.getenv("VOICE_API_HOST", "127.0.0.1").strip() or "127.0.0.1"
VOICE_API_PORT = int(os.getenv("VOICE_API_PORT", "8001").strip() or "8001")
TTS_MODEL_DIR = Path(
    os.getenv("TTS_MODEL_DIR", str(DEFAULT_TTS_MODEL_DIR)).strip()
)
TTS_SPEED = float(os.getenv("TTS_SPEED", "0.85").strip() or "0.85")

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_AUDIO_SECONDS = 5 * 60
ALLOWED_AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".ogg"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

engine = RagEngine()
asr_model = None
tts_model = None
_tts_g2p = None
_known_tts_words = None
_tts_tokens = None
_model_lock = threading.Lock()
_rag_lock = threading.Lock()
_asr_lock = threading.Lock()
_tts_lock = threading.Lock()
_tts_lexicon_lock = threading.RLock()
tasks: Dict[str, Path] = {}


def prepare_runtime_dirs() -> None:
    VOICE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for child in VOICE_OUTPUT_DIR.iterdir():
        if child.is_file():
            child.unlink()
    tasks.clear()


@asynccontextmanager
async def lifespan(_: FastAPI):
    prepare_runtime_dirs()
    yield


app = FastAPI(title="AI面试系统语音问答", version="1.0.0", lifespan=lifespan)


def _ensure_rag() -> None:
    with _rag_lock:
        if engine.vectorstore is None or engine.retriever is None or engine.llm is None:
            engine.prepare()


def _get_asr():
    global asr_model
    if asr_model is None:
        with _model_lock:
            if asr_model is None:
                try:
                    from funasr import AutoModel

                    asr_model = AutoModel(
                        model=ASR_MODEL,
                        vad_model="fsmn-vad",
                        punc_model="ct-punc",
                        device=ASR_DEVICE,
                        disable_update=True,
                    )
                except Exception as exc:
                    raise RuntimeError(
                        f"ASR 模型加载失败，请检查 FunASR 依赖和模型下载：{exc}"
                    ) from exc
    return asr_model


def _load_hotwords() -> list:
    if not VOICE_HOTWORDS_FILE.exists():
        return []
    hotwords = []
    for raw in VOICE_HOTWORDS_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            hotwords.append(line)
    return hotwords



_G2P_PHONE_MAP = {
    "AA": "aa", "AE": "ae", "AH": "ah", "AO": "ao", "AW": "aw",
    "AY": "ay", "B": "b", "CH": "ch", "D": "d", "DH": "dh",
    "EH": "eh", "ER": "er", "EY": "ey", "F": "f", "G": "g",
    "HH": "hh", "IH": "ih", "IY": "iy", "JH": "jh", "K": "k",
    "L": "l", "M": "m", "N": "n", "NG": "ng", "OW": "ow",
    "OY": "oy", "P": "p", "R": "r", "S": "s", "SH": "sh",
    "T": "t", "TH": "th", "UH": "uh", "UW": "uw", "V": "v",
    "W": "w", "Y": "y", "Z": "z", "ZH": "zh",
}
_G2P_TONE_MAP = {"0": 7, "1": 8, "2": 9}
_ENGLISH_WORD_RE = re.compile(r"[A-Za-z]+(?:['-][A-Za-z]+)*")


def _load_tts_tokens() -> set:
    global _tts_tokens
    if _tts_tokens is None:
        with _tts_lexicon_lock:
            if _tts_tokens is None:
                tokens_file = TTS_MODEL_DIR / "tokens.txt"
                if tokens_file.exists():
                    _tts_tokens = {
                        line.split()[0]
                        for line in tokens_file.read_text(encoding="utf-8").splitlines()
                        if line.strip()
                    }
                else:
                    _tts_tokens = set()
    return _tts_tokens


def _load_known_tts_words() -> set:
    global _known_tts_words
    if _known_tts_words is None:
        with _tts_lexicon_lock:
            if _known_tts_words is None:
                known = set()
                for path in (
                    TTS_MODEL_DIR / "lexicon.txt",
                    TTS_LEXICON_EXTRA_FILE,
                    TTS_DYNAMIC_LEXICON_FILE,
                ):
                    if path.exists():
                        for raw in path.read_text(encoding="utf-8").splitlines():
                            line = raw.strip()
                            if line and not line.startswith("#"):
                                known.add(line.split()[0].lower())
                _known_tts_words = known
    return _known_tts_words


def _get_tts_g2p():
    global _tts_g2p
    if _tts_g2p is None:
        with _tts_lexicon_lock:
            if _tts_g2p is None:
                import nltk
                nltk.data.find = lambda *args, **kwargs: True
                import g2p_en.g2p as g2p_module
                g2p_module.pos_tag = lambda words: [(word, "NN") for word in words]
                import cmudict as cmudict_package
                g2p_module.cmudict = type(
                    "CMUDict", (), {"dict": staticmethod(cmudict_package.dict)}
                )()
                from g2p_en import G2p
                _tts_g2p = G2p()
    return _tts_g2p


def _g2p_to_lexicon_line(word: str, pron: list) -> Optional[str]:
    tokens = _load_tts_tokens()
    phones = []
    tones = []
    for item in pron:
        matched = re.fullmatch(r"([A-Z]+)([012]?)", item)
        if matched is None:
            return None
        phone = _G2P_PHONE_MAP.get(matched.group(1))
        if phone is None or phone not in tokens:
            return None
        phones.append(phone)
        tones.append(_G2P_TONE_MAP.get(matched.group(2), 7))
    if not phones:
        return None
    return f"{word.lower()} {' '.join(phones)} {' '.join(map(str, tones))}"


def _ensure_tts_lexicon_for_text(text: str) -> bool:
    global tts_model
    words = {word.lower() for word in _ENGLISH_WORD_RE.findall(text)}
    if not words:
        return False
    with _tts_lexicon_lock:
        known = _load_known_tts_words()
        missing = sorted(word for word in words if word not in known)
        if not missing:
            return False
        try:
            g2p = _get_tts_g2p()
        except Exception:
            logger.warning("英文音标模型加载失败，跳过自动补充 TTS 词典。", exc_info=True)
            return False
        lines = []
        added_words = set()
        for word in missing:
            try:
                line = _g2p_to_lexicon_line(word, g2p(word))
            except Exception:
                logger.warning("无法为英文单词生成音标，继续使用原 TTS 逻辑：%s", word, exc_info=True)
                continue
            if line:
                lines.append(line)
                added_words.add(word)
        if not lines:
            return False
        TTS_DYNAMIC_LEXICON_FILE.parent.mkdir(parents=True, exist_ok=True)
        with TTS_DYNAMIC_LEXICON_FILE.open("a", encoding="utf-8") as dst:
            dst.write("\n".join(lines) + "\n")
        known.update(added_words)
        tts_model = None
        return True


def _get_tts_lexicon() -> Path:
    base_lexicon = TTS_MODEL_DIR / "lexicon.txt"
    extra_files = [TTS_LEXICON_EXTRA_FILE, TTS_DYNAMIC_LEXICON_FILE]
    if not any(path.exists() for path in extra_files):
        return base_lexicon

    merged_lexicon = TTS_MODEL_DIR / "lexicon_with_extra.txt"
    try:
        latest_mtime = base_lexicon.stat().st_mtime
        for path in extra_files:
            if path.exists():
                latest_mtime = max(latest_mtime, path.stat().st_mtime)
        if merged_lexicon.exists() and merged_lexicon.stat().st_mtime >= latest_mtime:
            return merged_lexicon
    except OSError:
        pass

    extra_words = set()
    extra_lines = []
    for extra_lexicon in extra_files:
        if not extra_lexicon.exists():
            continue
        for raw in extra_lexicon.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#"):
                extra_lines.append(line)
                extra_words.add(line.split()[0].lower())

    with base_lexicon.open("r", encoding="utf-8") as src, merged_lexicon.open(
        "w", encoding="utf-8"
    ) as dst:
        for line in src:
            if not line.strip():
                dst.write(line)
                continue
            if line.split()[0].lower() not in extra_words:
                dst.write(line)
        dst.write("\n")
        for line in extra_lines:
            dst.write(line + "\n")
    return merged_lexicon


def _get_tts():
    global tts_model
    if tts_model is None:
        with _model_lock:
            if tts_model is None:
                try:
                    import sherpa_onnx

                    model_file = TTS_MODEL_DIR / "model.onnx"
                    with _tts_lexicon_lock:
                        lexicon_file = _get_tts_lexicon()
                    tokens_file = TTS_MODEL_DIR / "tokens.txt"
                    if not (
                        model_file.exists()
                        and lexicon_file.exists()
                        and tokens_file.exists()
                    ):
                        raise RuntimeError(
                            f"TTS 模型文件不完整，请检查 {TTS_MODEL_DIR}"
                        )

                    rule_fsts = ",".join(
                        str(path) for path in sorted(TTS_MODEL_DIR.glob("*.fst"))
                    )
                    tts_config = sherpa_onnx.OfflineTtsConfig(
                        model=sherpa_onnx.OfflineTtsModelConfig(
                            vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                                model=str(model_file),
                                lexicon=str(lexicon_file),
                                tokens=str(tokens_file),
                            ),
                            provider="cpu",
                            debug=False,
                            num_threads=2,
                        ),
                        rule_fsts=rule_fsts,
                        max_num_sentences=1,
                    )
                    if not tts_config.validate():
                        raise RuntimeError("TTS 配置校验失败，请检查模型目录。")
                    tts_model = sherpa_onnx.OfflineTts(tts_config)
                except RuntimeError:
                    raise
                except Exception as exc:
                    raise RuntimeError(f"TTS 模型加载失败：{exc}") from exc
    return tts_model


def _get_audio_duration(path: Path) -> float:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise ValueError(result.stderr.strip())
        data = json.loads(result.stdout or "{}")
        return float(data["format"]["duration"])
    except Exception as exc:
        raise ValueError(
            "无法读取音频时长，请确认 ffmpeg/ffprobe 已安装且音频文件有效。"
        ) from exc


async def _save_upload(audio: UploadFile) -> Path:
    if not audio.filename:
        raise HTTPException(status_code=400, detail="上传文件没有文件名。")
    suffix = Path(audio.filename).suffix.lower()
    if suffix not in ALLOWED_AUDIO_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail="音频格式不支持，仅支持 mp3、wav、m4a、ogg。",
        )
    content = await audio.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="音频文件不能超过 20MB。")
    VOICE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        prefix="voice_upload_",
        suffix=suffix,
        delete=False,
        dir=str(VOICE_OUTPUT_DIR),
    )
    handle.write(content)
    handle.close()
    return Path(handle.name)


def _transcribe(path: Path) -> str:
    model = _get_asr()
    hotwords = _load_hotwords()
    generate_kwargs = {"input": str(path), "batch_size": 1}
    if hotwords:
        generate_kwargs["hotword"] = " ".join(hotwords)
        generate_kwargs["postprocess_hotword_file"] = str(VOICE_HOTWORDS_FILE)
    with _asr_lock:
        results = model.generate(**generate_kwargs)
    text = results[0].get("text", "").strip() if results else ""
    if not text:
        raise ValueError("语音转写结果为空，请重新录制后上传。")
    return text


def _synthesize(text: str) -> Path:
    import sherpa_onnx

    VOICE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with _tts_lock:
        _ensure_tts_lexicon_for_text(text)
        model = _get_tts()
        generation_config = sherpa_onnx.GenerationConfig()
        generation_config.sid = 0
        generation_config.speed = TTS_SPEED
        audio = model.generate(text, generation_config)
        if len(audio.samples) == 0:
            raise RuntimeError("TTS 生成音频失败，请稍后重试。")
        task_id = uuid.uuid4().hex
        output_path = VOICE_OUTPUT_DIR / f"{task_id}.wav"
        sf.write(
            str(output_path),
            audio.samples,
            samplerate=audio.sample_rate,
            subtype="PCM_16",
        )
    return output_path


def process_audio_file(audio_path: Path) -> dict:
    """处理本地音频文件并生成语音回答，FastAPI 与后续 UI 共用。"""
    duration = _get_audio_duration(audio_path)
    if duration > MAX_AUDIO_SECONDS:
        raise ValueError("音频时长不能超过 5 分钟。")
    question = _transcribe(audio_path)
    _ensure_rag()
    result = engine.ask(question)
    output_path = _synthesize(result["answer"])
    task_id = uuid.uuid4().hex
    tasks[task_id] = output_path
    return {
        "task_id": task_id,
        "transcript": question,
        "answer": result["answer"],
        "sources": result["sources"],
        "audio_url": f"/audio/{task_id}",
        "audio_path": str(output_path),
    }


@app.get("/health")
def health():
    rag_ready = False
    rag_error = ""
    try:
        _ensure_rag()
        rag_ready = True
    except Exception as exc:
        rag_error = str(exc)
    return {
        "status": "ok",
        "rag_ready": rag_ready,
        "rag_error": rag_error,
        "asr_loaded": asr_model is not None,
        "tts_loaded": tts_model is not None,
        "asr_model": ASR_MODEL,
        "tts_model": "vits-melo-tts-zh_en",
    }


@app.post("/voice/ask")
async def voice_ask(audio: Optional[UploadFile] = File(None)):
    if audio is None:
        raise HTTPException(status_code=400, detail="请上传音频文件。")
    temp_path = None
    try:
        temp_path = await _save_upload(audio)
        result = process_audio_file(temp_path)
        return {
            "task_id": result["task_id"],
            "transcript": result["transcript"],
            "answer": result["answer"],
            "sources": result["sources"],
            "audio_url": result["audio_url"],
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("语音问答处理失败")
        raise HTTPException(status_code=500, detail=f"语音问答处理失败：{exc}") from exc
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


@app.get("/audio/{task_id}")
def download_audio(task_id: str):
    audio_path = tasks.get(task_id)
    if audio_path is None or not audio_path.exists():
        raise HTTPException(status_code=404, detail="音频不存在或已过期。")
    return FileResponse(
        str(audio_path),
        media_type="audio/wav",
        filename=f"{task_id}.wav",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=VOICE_API_HOST, port=VOICE_API_PORT)
