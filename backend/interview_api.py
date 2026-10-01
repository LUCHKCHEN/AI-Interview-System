#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""AI面试系统 FastAPI 接口。"""

import asyncio
import hashlib
import json
import logging
import os
import re
import threading
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    Form,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

import speech_service
from interview_service import (
    InterviewError,
    contains_transition_keyword,
    knowledge_catalog,
    knowledge_state,
    public_session,
    service,
    set_knowledge_state,
    trim_answer_command,
)
from interview_store import store

PROJECT_DIR = Path(__file__).resolve().parent
BASE_DIR = PROJECT_DIR.parent
DATA_DIR = BASE_DIR / "data"
INTERVIEW_API_HOST = os.getenv("INTERVIEW_API_HOST", "127.0.0.1").strip()
INTERVIEW_API_PORT = int(os.getenv("INTERVIEW_API_PORT", "8002").strip() or "8002")
MAX_RESUME_BYTES = 10 * 1024 * 1024
MAX_TURN_SECONDS = 180
SILENCE_WARNING_SECONDS = 8
SILENCE_FINALIZE_SECONDS = 6
PCM_BYTES_PER_SECOND = 16000 * 2
COMPLETION_MESSAGE = "技术面试结束，接下来进入评分环节。"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="AI面试系统", version="2.0.0")


@app.exception_handler(InterviewError)
async def interview_error_handler(_: Request, exc: InterviewError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": exc.error_code, "message": exc.message},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, __: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error_code": "INVALID_REQUEST",
            "message": "提交内容不完整，请检查简历、岗位描述和公司信息。",
        },
    )


def _report_summary(session: dict) -> dict:
    report = session.get("report") or {}
    return {
        "session_id": session.get("session_id"),
        "created_at": session.get("created_at"),
        "company": session.get("company", ""),
        "role": session.get("role", ""),
        "mode": session.get("mode"),
        "status": session.get("status"),
        "score": report.get("total_score"),
        "level": report.get("level", "尚未生成报告"),
        "weak_tags": report.get("weak_tags", session.get("weak_tags", [])),
        "questions": len(session.get("questions", [])),
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "interview",
        "knowledge": knowledge_state["status"],
    }


@app.post("/api/interview/sessions", status_code=201)
async def create_session(
    resume_pdf: Optional[UploadFile] = File(None),
    resume_text: str = Form(""),
    jd: str = Form(...),
    company: str = Form(""),
    role: str = Form(""),
):
    pdf_bytes = b""
    pdf_name = ""
    if resume_pdf is not None:
        pdf_name = resume_pdf.filename or "resume.pdf"
        pdf_bytes = await resume_pdf.read(MAX_RESUME_BYTES + 1)
        if len(pdf_bytes) > MAX_RESUME_BYTES:
            raise InterviewError("PDF_TOO_LARGE", "简历 PDF 不能超过 10MB。")
    session = await asyncio.to_thread(
        service.create_session,
        resume_pdf=pdf_bytes,
        resume_pdf_name=pdf_name,
        resume_text=resume_text,
        jd=jd,
        company=company,
        role=role,
    )
    return public_session(session)


@app.get("/api/interview/sessions/{session_id}")
def get_session(session_id: str):
    return public_session(service.get_session(session_id))


@app.get("/api/interview/sessions/{session_id}/turns/{turn_no}/question-audio")
async def question_audio(session_id: str, turn_no: int):
    session = service.get_session(session_id)
    questions = session.get("questions", [])
    if turn_no < 1 or turn_no > len(questions):
        raise InterviewError("INVALID_TURN", "题号无效。", 404)
    directory = store.session_dir(session_id)
    output_path = directory / f"question-{turn_no}.wav"
    if not output_path.exists():
        try:
            generated = await asyncio.to_thread(
                speech_service.synthesize_question,
                questions[turn_no - 1].get("title", ""),
            )
            generated.replace(output_path)
        except Exception as exc:
            raise InterviewError(
                "TTS_FAILED",
                "题目语音暂时不可用，可继续阅读屏幕文字作答。",
                503,
            ) from exc
    return FileResponse(
        str(output_path),
        media_type="audio/wav",
        filename=f"question-{turn_no}.wav",
    )


@app.get("/api/interview/sessions/{session_id}/turns/{turn_no}/answer-audio")
def answer_audio(session_id: str, turn_no: int):
    service.get_session(session_id)
    path = store.session_dir(session_id) / f"turn-{turn_no}.wav"
    if not path.exists():
        raise InterviewError("AUDIO_NOT_FOUND", "这道题的录音不存在。", 404)
    return FileResponse(
        str(path),
        media_type="audio/wav",
        filename=f"turn-{turn_no}.wav",
    )


@app.get("/api/interview/sessions/{session_id}/completion-audio")
async def completion_audio(session_id: str):
    service.get_session(session_id)
    output_path = store.session_dir(session_id) / "completion.wav"
    if not output_path.exists():
        try:
            generated = await asyncio.to_thread(
                speech_service.synthesize_question,
                COMPLETION_MESSAGE,
            )
            generated.replace(output_path)
        except Exception as exc:
            raise InterviewError(
                "TTS_FAILED",
                "结束语语音暂时不可用，评分流程仍会继续。",
                503,
            ) from exc
    return FileResponse(
        str(output_path),
        media_type="audio/wav",
        filename="completion.wav",
    )


@app.post("/api/interview/sessions/{session_id}/finish")
def finish_session(session_id: str, background_tasks: BackgroundTasks):
    session = service.get_session(session_id)
    session["status"] = "scoring"
    session["error_code"] = ""
    session["message"] = ""
    store.save(session)
    background_tasks.add_task(_score_and_evolve, session_id)
    return {
        "session_id": session_id,
        "status": "scoring",
        "message": COMPLETION_MESSAGE,
    }


@app.get("/api/interview/sessions/{session_id}/report")
def get_report(session_id: str):
    session = service.get_session(session_id)
    report = session.get("report")
    if report:
        return {"status": "ready", "report": report}
    if session.get("status") == "scoring":
        return {"status": "processing", "report": None}
    if session.get("status") == "failed":
        return {
            "status": "failed",
            "report": None,
            "error_code": session.get("error_code", "SCORING_FAILED"),
            "message": session.get("message", "评分暂时不可用。"),
        }
    return {"status": "idle", "report": None}


@app.get("/api/history")
def history(limit: int = 20, offset: int = 0):
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    sessions = store.list_sessions(limit=limit, offset=offset)
    return {
        "items": [_report_summary(session) for session in sessions],
        "weak_tags": store.load_weak_tags().get("tags", []),
    }


@app.get("/api/history/{session_id}")
def history_detail(session_id: str):
    return public_session(service.get_session(session_id))


@app.delete("/api/history/{session_id}")
def delete_history(session_id: str):
    if not store.delete(session_id):
        raise InterviewError("SESSION_NOT_FOUND", "没有找到这条历史记录。", 404)
    return {"message": "历史记录已删除。"}


@app.get("/api/history/{session_id}/export")
def export_history(session_id: str):
    session = service.get_session(session_id)
    content = json.dumps(session, ensure_ascii=False, indent=2).encode("utf-8")
    return JSONResponse(
        content=json.loads(content.decode("utf-8")),
        headers={
            "Content-Disposition": (
                f'attachment; filename="interview-{session_id}.json"'
            )
        },
    )


@app.get("/api/knowledge/status")
def get_knowledge_status():
    return knowledge_state


@app.get("/api/knowledge/catalog")
def get_knowledge_catalog():
    return {"items": knowledge_catalog()}


async def _send(websocket: WebSocket, payload: dict) -> None:
    try:
        await websocket.send_json(payload)
    except Exception:
        pass


async def _finalize_websocket_turn(
    websocket: WebSocket,
    session_id: str,
    turn_no: int,
    pcm: bytes,
    duration_ms: int,
    interim_text: str = "",
    text_answer: str = "",
) -> bool:
    transcript = (text_answer or "").strip()
    audio_path = ""
    if not transcript and pcm:
        try:
            transcript = await asyncio.to_thread(
                speech_service.transcribe_pcm,
                pcm,
                16000,
            )
        except Exception:
            transcript = interim_text.strip()
            if not transcript:
                await _send(
                    websocket,
                    {
                        "type": "error",
                        "error_code": "ASR_FAILED",
                        "message": "语音转写失败，可切到文本补充后继续。",
                    },
                )
                return False
    if not transcript and interim_text:
        transcript = interim_text
    if not transcript:
        await _send(
            websocket,
            {
                "type": "error",
                "error_code": "EMPTY_ANSWER",
                "message": "没有听到有效回答，请重录本题。",
            },
        )
        return False

    cleaned, matched_keyword = trim_answer_command(transcript)
    if not cleaned:
        await _send(
            websocket,
            {
                "type": "error",
                "error_code": "EMPTY_ANSWER",
                "message": "没有识别到有效回答，请重录本题。",
            },
        )
        return False

    if pcm:
        audio_path = str(store.session_dir(session_id) / f"turn-{turn_no}.wav")
        await asyncio.to_thread(
            speech_service.write_pcm16_wav,
            Path(audio_path),
            pcm,
        )
    session = await asyncio.to_thread(
        service.finalize_turn,
        session_id,
        turn_no,
        cleaned,
        duration_ms,
        audio_path,
    )
    if matched_keyword:
        await _send(
            websocket,
            {
                "type": "transition",
                "matched_keyword": matched_keyword,
                "message": "好的，了解了",
            },
        )
    await _send(
        websocket,
        {
            "type": "finalized",
            "transcript": cleaned,
            "turn_no": turn_no,
            "next_turn_no": session.get("current_turn_no", turn_no),
            "chars": len(re.findall(r"[\u4e00-\u9fff]", cleaned)),
        },
    )
    if turn_no >= len(session.get("questions", [])):
        await _send(
            websocket,
            {
                "type": "status",
                "state": "finished",
                "message": COMPLETION_MESSAGE,
            },
        )
    return True


@app.websocket("/api/interview/sessions/{session_id}/turns/{turn_no}/answers")
async def answers_websocket(websocket: WebSocket, session_id: str, turn_no: int):
    try:
        session = service.get_session(session_id)
    except InterviewError as exc:
        await websocket.accept()
        await _send(
            websocket,
            {"type": "error", "error_code": exc.error_code, "message": exc.message},
        )
        await websocket.close()
        return
    questions = session.get("questions", [])
    if turn_no < 1 or turn_no > len(questions):
        await websocket.accept()
        await _send(
            websocket,
            {
                "type": "error",
                "error_code": "INVALID_TURN",
                "message": "题号无效。",
            },
        )
        await websocket.close()
        return

    await websocket.accept()
    await _send(
        websocket,
        {
            "type": "status",
            "state": "ready",
            "turn_no": turn_no,
            "message": "可以开始回答。",
        },
    )
    pcm = bytearray()
    duration_ms = 0
    interim_text = ""
    last_interim_at = 0.0
    loop = asyncio.get_running_loop()
    silence_warned = False
    timeout = float(SILENCE_WARNING_SECONDS)

    try:
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=timeout)
            except asyncio.TimeoutError:
                if not silence_warned:
                    silence_warned = True
                    timeout = float(SILENCE_FINALIZE_SECONDS)
                    await _send(
                        websocket,
                        {
                            "type": "warning",
                            "code": "SILENCE_TIMEOUT",
                            "message": "长时间未听到回答，可继续说或手动结束本题。",
                        },
                    )
                    continue
                finished = await _finalize_websocket_turn(
                    websocket,
                    session_id,
                    turn_no,
                    bytes(pcm),
                    duration_ms,
                    interim_text,
                )
                if finished:
                    await websocket.close()
                return

            if message.get("type") == "websocket.disconnect":
                return
            if message.get("bytes") is not None:
                chunk = message["bytes"]
                pcm.extend(chunk)
                silence_warned = False
                timeout = float(SILENCE_WARNING_SECONDS)
                duration_ms = int(len(pcm) / PCM_BYTES_PER_SECOND * 1000)
                if duration_ms >= MAX_TURN_SECONDS * 1000:
                    finished = await _finalize_websocket_turn(
                        websocket,
                        session_id,
                        turn_no,
                        bytes(pcm),
                        duration_ms,
                        interim_text,
                    )
                    if finished:
                        await websocket.close()
                    return
                now = loop.time()
                if now - last_interim_at >= 4 and duration_ms >= 4000:
                    last_interim_at = now
                    try:
                        interim_text = await asyncio.to_thread(
                            speech_service.transcribe_pcm,
                            bytes(pcm),
                            16000,
                        )
                    except Exception:
                        interim_text = ""
                    await _send(
                        websocket,
                        {
                            "type": "status",
                            "interim_text": interim_text,
                            "chars": len(
                                re.findall(r"[\u4e00-\u9fff]", interim_text)
                            ),
                            "elapsed_ms": duration_ms,
                        },
                    )
                    if contains_transition_keyword(interim_text):
                        finished = await _finalize_websocket_turn(
                            websocket,
                            session_id,
                            turn_no,
                            bytes(pcm),
                            duration_ms,
                            interim_text,
                        )
                        if finished:
                            await websocket.close()
                        return
                continue

            raw_text = message.get("text") or ""
            if not raw_text:
                continue
            try:
                payload = json.loads(raw_text)
            except json.JSONDecodeError:
                await _send(
                    websocket,
                    {
                        "type": "error",
                        "error_code": "INVALID_MESSAGE",
                        "message": "录音消息格式无效。",
                    },
                )
                continue
            message_type = payload.get("type")
            if message_type == "finish":
                finished = await _finalize_websocket_turn(
                    websocket,
                    session_id,
                    turn_no,
                    bytes(pcm),
                    duration_ms,
                    interim_text,
                    str(payload.get("transcript", "")),
                )
                if finished:
                    await websocket.close()
                return
            if message_type == "text_answer":
                finished = await _finalize_websocket_turn(
                    websocket,
                    session_id,
                    turn_no,
                    bytes(pcm),
                    duration_ms,
                    interim_text,
                    str(payload.get("transcript", "")),
                )
                if finished:
                    await websocket.close()
                return
            if message_type == "start":
                silence_warned = False
                timeout = float(SILENCE_WARNING_SECONDS)
                continue
            await _send(
                websocket,
                {
                    "type": "error",
                    "error_code": "INVALID_MESSAGE",
                    "message": "不支持的消息类型。",
                },
            )
    except WebSocketDisconnect:
        return
    except Exception:
        logger.exception("面试录音 WebSocket 处理失败")
        await _send(
            websocket,
            {
                "type": "error",
                "error_code": "WS_FAILED",
                "message": "录音链路暂时中断，请重录本题或改用文本补充。",
            },
        )


def _score_and_evolve(session_id: str) -> None:
    try:
        report = service.score_session(session_id)
    except Exception as exc:
        logger.exception("面试评分失败")
        session = store.load(session_id)
        if session is not None:
            session["status"] = "failed"
            session["error_code"] = "SCORING_FAILED"
            session["message"] = "评分暂时不可用，请稍后重试。"
            store.save(session)
        return
    try:
        _write_reinforcement_docs(report)
    except Exception:
        logger.warning("补强文档生成失败，评分报告仍可用。", exc_info=True)
    if os.getenv("INTERVIEW_AUTO_REBUILD", "1").strip() != "0":
        threading.Thread(
            target=_rebuild_index,
            name=f"rebuild-{session_id}",
            daemon=True,
        ).start()


def _write_reinforcement_docs(report: dict) -> None:
    tags = report.get("weak_tags") or []
    if not tags:
        return
    root = DATA_DIR / "05_自动补强"
    root.mkdir(parents=True, exist_ok=True)
    for tag in tags[:3]:
        digest = hashlib.sha1(str(tag).encode("utf-8")).hexdigest()[:10]
        path = root / f"{digest}.md"
        if path.exists():
            continue
        safe_tag = str(tag).replace("\n", " ").strip()
        path.write_text(
            (
                f"# 自动补强：{safe_tag}\n\n"
                f"Publish_Date: {date.today().isoformat()}\n\n"
                "## 复习目标\n\n"
                f"围绕“{safe_tag}”补充概念、常见追问、工程取舍和可量化案例。\n\n"
                "## 回答检查清单\n\n"
                "- 能否先说明业务目标和约束？\n"
                "- 能否解释关键技术方案及取舍？\n"
                "- 能否给出指标、失败模式和复盘结论？\n"
            ),
            encoding="utf-8",
        )


def _rebuild_index() -> None:
    set_knowledge_state("rebuilding", "正在重建知识库索引。")
    try:
        from rag_engine import RagEngine

        engine = RagEngine()
        engine.prepare()
        set_knowledge_state("ready", "知识库索引已更新。")
    except Exception as exc:
        logger.warning("知识库自动重建失败：%s", exc)
        set_knowledge_state("idle", "知识库索引将在下次提问时自动更新。")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=INTERVIEW_API_HOST, port=INTERVIEW_API_PORT)
