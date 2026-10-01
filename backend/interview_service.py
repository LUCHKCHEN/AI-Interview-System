#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""动态模拟面试的解析、出题、切题与评分逻辑。"""

import io
import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from openai import OpenAI
from pypdf import PdfReader

from interview_store import InterviewStore, store

PROJECT_DIR = Path(__file__).resolve().parent
BASE_DIR = PROJECT_DIR.parent
DATA_DIR = BASE_DIR / "data"
ENV_FILE = BASE_DIR / ".env"
load_dotenv(ENV_FILE, override=True)

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"
TRANSITION_KEYWORDS = (
    "以上就是我的回答",
    "我的回答完毕",
    "回答完毕",
    "答题完毕",
    "这道题回答完了",
    "我说完了",
)
TECH_TERMS = (
    "Java", "JVM", "Spring Boot", "Spring Cloud", "Spring", "MyBatis",
    "MySQL", "Redis", "Kafka", "RabbitMQ", "Elasticsearch", "Linux",
    "Docker", "Kubernetes", "K8s", "并发", "多线程", "JUC", "分布式",
    "微服务", "数据库", "索引", "缓存", "消息队列", "计算机网络",
    "操作系统", "算法", "数据结构", "设计模式", "Redis 持久化",
    "Python", "FastAPI", "LangChain", "FAISS", "RAG", "Transformer",
    "Attention", "Embedding", "向量检索", "重排", "大模型", "LLM",
    "Prompt", "Agent", "机器学习", "深度学习", "PyTorch", "TensorFlow",
    "React", "TypeScript", "JavaScript", "Node.js", "Vue", "WebSocket",
)
ROLE_HINTS = ("工程师", "开发", "算法", "数据", "产品", "测试", "运维")
logger = logging.getLogger(__name__)


class InterviewError(Exception):
    """带机器码和 HTTP 状态的业务异常。"""

    def __init__(self, error_code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.status_code = status_code


class DeepSeekJsonClient:
    """只封装面试服务需要的 JSON 生成，失败时调用方自动降级。"""

    def __init__(self) -> None:
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        self.base_url = os.getenv("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL).strip()
        self.model = os.getenv("DEEPSEEK_CHAT_MODEL", DEEPSEEK_MODEL).strip()
        self._client = None

    @property
    def available(self) -> bool:
        return bool(self.api_key) and not self.api_key.startswith("在这里填写你的")

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=60,
                max_retries=1,
            )
        return self._client

    def complete_json(self, system_prompt: str, user_prompt: str) -> Optional[dict]:
        if not self.available:
            return None
        try:
            response = self._get_client().chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=1800,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or ""
            return _json_object(content)
        except Exception:
            logger.warning("DeepSeek JSON 调用失败，使用本地降级逻辑。", exc_info=True)
            return None


def _json_object(text: str) -> Optional[dict]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        matched = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not matched:
            return None
        try:
            value = json.loads(matched.group(0))
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


def extract_pdf_text(content: bytes) -> str:
    """提取文字型 PDF；扫描件会返回空字符串，由调用方提供文本通道。"""

    try:
        reader = PdfReader(io.BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise InterviewError(
            "INVALID_PDF",
            "PDF 无法解析，请确认文件未损坏，或改用文本粘贴。",
        ) from exc
    return "\n".join(pages).strip()


def count_chinese(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", text or ""))


def trim_answer_command(transcript: str) -> tuple[str, Optional[str]]:
    text = (transcript or "").strip()
    matched_keyword = None
    matched_at = None
    for keyword in TRANSITION_KEYWORDS:
        position = text.find(keyword)
        if position >= 0 and (matched_at is None or position < matched_at):
            matched_at = position
            matched_keyword = keyword
    if matched_at is None:
        return text, None
    cleaned = text[:matched_at].strip()
    cleaned = re.sub(r"[，,；;]\s*$", "", cleaned)
    return cleaned, matched_keyword


def contains_transition_keyword(text: str) -> Optional[str]:
    _, keyword = trim_answer_command(text)
    return keyword


def extract_keywords(text: str) -> List[str]:
    source = text or ""
    lowered = source.lower()
    found = []
    for term in TECH_TERMS:
        if term.lower() in lowered:
            found.append(term)
    for token in re.findall(r"\b[A-Za-z][A-Za-z0-9+#.\-]{1,24}\b", source):
        if token.lower() in {"and", "with", "from", "the", "for", "using"}:
            continue
        if token not in found:
            found.append(token)
    return found[:18]


def detect_mode(jd_keywords: List[str], resume_skills: List[str]) -> str:
    count = len(jd_keywords)
    if count >= 5:
        return "precise"
    if count <= 2:
        return "broad"
    covered = len(set(jd_keywords) & set(resume_skills))
    return "precise" if covered >= 2 else "broad"


def _resume_summary(resume_text: str) -> dict:
    skills = extract_keywords(resume_text)
    lines = [line.strip(" -•\t") for line in resume_text.splitlines() if line.strip()]
    projects = [
        line[:160]
        for line in lines
        if any(marker in line for marker in ("项目", "系统", "平台", "负责"))
    ][:4]
    education = next(
        (
            line[:120]
            for line in lines
            if any(marker in line for marker in ("大学", "学院", "本科", "硕士", "学历"))
        ),
        "",
    )
    return {
        "skills": skills,
        "projects": projects,
        "education": education,
    }


def _fallback_questions(context: dict) -> List[dict]:
    role = context.get("role") or "目标岗位"
    company = context.get("company") or "目标公司"
    primary = context.get("jd_keywords", ["核心技术"])[0]
    second = context.get("jd_keywords", ["系统设计"])[-1]
    return [
        {
            "title": f"请用两分钟介绍一段最能证明你胜任{role}的项目经历，并说明你的个人贡献。",
            "intent": "考察项目事实、个人贡献和口头表达结构。",
            "hint": "采用背景、目标、行动、结果的顺序，先用一句话给出结论。",
            "dimension": "逻辑表达",
            "ideal_answer": "应包含项目背景、个人职责、关键技术选择、量化结果和复盘。",
        },
        {
            "title": f"结合{company}的岗位要求，讲讲你如何设计或优化{primary}相关的方案。",
            "intent": f"考察对 {primary} 的技术深度与岗位核心能力匹配度。",
            "hint": "先说明约束和指标，再解释方案取舍、失败模式与验证方式。",
            "dimension": "技术深度",
            "ideal_answer": f"围绕 {primary} 给出原理、设计权衡、指标和实际案例。",
        },
        {
            "title": f"如果线上系统在引入{second}后出现性能波动，你会如何定位、止损并长期修复？",
            "intent": "考察压力场景下的排查路径、应变能力和工程边界意识。",
            "hint": "按影响面、监控证据、短期止损、根因验证、长期治理展开。",
            "dimension": "应变潜力",
            "ideal_answer": "应体现分层排查、数据驱动、快速止损、根因修复和复盘闭环。",
        },
    ]


def _valid_questions(payload: Optional[dict]) -> Optional[List[dict]]:
    if not payload:
        return None
    questions = payload.get("questions")
    if not isinstance(questions, list) or len(questions) != 3:
        return None
    normalized = []
    for index, item in enumerate(questions, start=1):
        if not isinstance(item, dict) or not str(item.get("title", "")).strip():
            return None
        normalized.append(
            {
                "id": f"q{index}",
                "number": index,
                "title": str(item["title"]).strip(),
                "intent": str(item.get("intent", "")).strip(),
                "hint": str(item.get("hint", "")).strip(),
                "dimension": str(item.get("dimension", "")).strip() or "综合能力",
                "ideal_answer": str(item.get("ideal_answer", "")).strip(),
            }
        )
    return normalized


class InterviewService:
    def __init__(
        self,
        record_store: InterviewStore = store,
        llm: Optional[DeepSeekJsonClient] = None,
    ) -> None:
        self.store = record_store
        self.llm = llm or DeepSeekJsonClient()

    def company_style(self, company: str) -> str:
        if not company:
            return ""
        root = DATA_DIR / "04_公司风格库"
        if not root.exists():
            return ""
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".md", ".txt"}:
                continue
            if company.lower() not in path.stem.lower():
                continue
            try:
                text = path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            lines = [
                line.strip(" #\t")
                for line in text.splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            ]
            return lines[0][:160] if lines else ""
        return ""

    def generate_questions(self, context: dict) -> List[dict]:
        if self.llm.available:
            prompt = {
                "company": context.get("company", ""),
                "role": context.get("role", ""),
                "mode": context.get("mode"),
                "resume_summary": context.get("resume_summary"),
                "jd_keywords": context.get("jd_keywords"),
                "weak_tags": context.get("weak_tags", []),
            }
            payload = self.llm.complete_json(
                "你是技术实习生的模拟面试官，只输出合法 JSON。",
                (
                    "请生成严格递进的三道中文面试题，分别覆盖项目破冰、核心技术深挖、"
                    "压力或能力差集场景。每题的 title 只包含要朗读的问题，intent 是屏幕"
                    "上的考察理由，hint 是回答结构，ideal_answer 是评分骨架。返回格式："
                    '{"questions":[{"title":"","intent":"","hint":"","dimension":"",'
                    '"ideal_answer":""}]}。上下文：'
                    + str(prompt)
                ),
            )
            questions = _valid_questions(payload)
            if questions:
                return questions
        return _valid_questions({"questions": _fallback_questions(context)}) or []

    def create_session(
        self,
        *,
        resume_pdf: bytes = b"",
        resume_pdf_name: str = "",
        resume_text: str = "",
        jd: str,
        company: str = "",
        role: str = "",
    ) -> dict:
        jd = (jd or "").strip()
        if not jd:
            raise InterviewError("EMPTY_JD", "岗位描述不能为空。")
        extracted_resume = extract_pdf_text(resume_pdf) if resume_pdf else ""
        resume = extracted_resume or (resume_text or "").strip()
        if not resume:
            if resume_pdf:
                raise InterviewError(
                    "SCANNED_PDF",
                    "这份 PDF 没有可提取文字，请改用文本粘贴通道。",
                )
            raise InterviewError("EMPTY_RESUME", "请上传文字型 PDF 或粘贴简历文本。")

        jd_keywords = extract_keywords(jd)
        resume_summary = _resume_summary(resume)
        mode = detect_mode(jd_keywords, resume_summary["skills"])
        weak_payload = self.store.load_weak_tags()
        weak_tags = [
            item.get("tag", "")
            for item in weak_payload.get("tags", [])
            if item.get("tag")
        ][:8]
        context = {
            "company": (company or "").strip(),
            "role": (role or "").strip() or "目标岗位",
            "mode": mode,
            "resume_summary": resume_summary,
            "jd_keywords": jd_keywords,
            "weak_tags": weak_tags,
        }
        questions = self.generate_questions(context)
        now = datetime.now().isoformat(timespec="seconds")
        session = {
            "session_id": uuid.uuid4().hex,
            "created_at": now,
            "updated_at": now,
            "status": "ready",
            "mode": mode,
            "company": context["company"],
            "role": context["role"],
            "company_style": self.company_style(context["company"]),
            "resume_name": resume_pdf_name or "粘贴文本",
            "resume_text": resume[:12000],
            "resume_summary": resume_summary,
            "jd": jd[:6000],
            "jd_keywords": jd_keywords,
            "weak_tags": weak_tags,
            "questions": questions,
            "current_turn_no": 1,
            "turns": [],
            "report": None,
            "error_code": "",
            "message": "",
        }
        self.store.save(session)
        return session

    def get_session(self, session_id: str) -> dict:
        session = self.store.load(session_id)
        if session is None:
            raise InterviewError("SESSION_NOT_FOUND", "没有找到这轮面试。", 404)
        return session

    def finalize_turn(
        self,
        session_id: str,
        turn_no: int,
        transcript: str,
        duration_ms: int,
        audio_path: Optional[str] = None,
    ) -> dict:
        session = self.get_session(session_id)
        if turn_no < 1 or turn_no > len(session.get("questions", [])):
            raise InterviewError("INVALID_TURN", "题号无效。")
        cleaned, matched_keyword = trim_answer_command(transcript)
        if not cleaned:
            raise InterviewError("EMPTY_ANSWER", "没有识别到有效回答，请重录本题。")
        turn = {
            "turn_no": turn_no,
            "question": session["questions"][turn_no - 1]["title"],
            "transcript": cleaned,
            "char_count": count_chinese(cleaned),
            "duration_ms": max(0, int(duration_ms)),
            "audio_path": audio_path or "",
            "matched_keyword": matched_keyword or "",
            "finalized_at": datetime.now().isoformat(timespec="seconds"),
        }
        turns = [
            item for item in session.get("turns", []) if item.get("turn_no") != turn_no
        ]
        turns.append(turn)
        turns.sort(key=lambda item: item.get("turn_no", 0))
        next_turn = min(turn_no + 1, len(session["questions"]))
        session.update(
            {
                "turns": turns,
                "current_turn_no": next_turn,
                "status": "interviewing",
            }
        )
        directory = self.store.session_dir(session_id)
        turn_file = directory / f"turn-{turn_no}.json"
        turn_file.write_text(
            json.dumps(turn, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.store.save(session)
        return session

    def score_session(self, session_id: str) -> dict:
        session = self.get_session(session_id)
        turns = session.get("turns", [])
        if not turns:
            report = self._build_report(
                session,
                self._fallback_score(session, []),
                estimated=True,
            )
        else:
            answers = [
                {
                    "turn_no": turn.get("turn_no"),
                    "question": turn.get("question", ""),
                    "transcript": turn.get("transcript", ""),
                    "char_count": turn.get("char_count", 0),
                    "duration_ms": turn.get("duration_ms", 0),
                }
                for turn in turns
            ]
            payload = None
            if self.llm.available:
                scoring_context = {
                    "company": session.get("company"),
                    "role": session.get("role"),
                    "jd_keywords": session.get("jd_keywords"),
                    "ideal_answers": [
                        question.get("ideal_answer", "")
                        for question in session.get("questions", [])
                    ],
                    "answers": answers,
                }
                payload = self.llm.complete_json(
                    "你是严格、诚实的技术面试评分员，只输出合法 JSON。",
                    (
                        "按 technical_accuracy 40%、logic_expression 25%、"
                        "adaptability_learning 20%、job_match 15% 评分。每个维度返回"
                        '{"score":0-100,"reason":"中文理由"}，并返回 strengths、'
                        "weak_tags、suggestions 三个字符串数组。答案少于 50 个有效汉字"
                        "必须扣分，少于 20 个汉字时总分不得超过 60。上下文："
                        + str(scoring_context)
                    ),
                )
            if payload and self._valid_score_payload(payload):
                score_payload = self._normalize_score_payload(session, payload)
                estimated = False
            else:
                score_payload = self._fallback_score(session, answers)
                estimated = True
            report = self._build_report(session, score_payload, estimated)
        session["report"] = report
        session["status"] = "ready_report"
        session["error_code"] = ""
        session["message"] = ""
        self.store.save(session)
        if report.get("weak_tags"):
            self.store.update_weak_tags(report["weak_tags"])
        return report

    def _valid_score_payload(self, payload: dict) -> bool:
        keys = (
            "technical_accuracy",
            "logic_expression",
            "adaptability_learning",
            "job_match",
        )
        return all(
            isinstance(payload.get(key), dict)
            and payload[key].get("score") is not None
            for key in keys
        )

    def _normalize_score_payload(self, session: dict, payload: dict) -> dict:
        weights = {
            "technical_accuracy": 0.4,
            "logic_expression": 0.25,
            "adaptability_learning": 0.2,
            "job_match": 0.15,
        }
        dimensions = {}
        total = 0.0
        for key, weight in weights.items():
            raw = payload.get(key) or {}
            score = max(0, min(100, int(round(float(raw.get("score", 0))))))
            dimensions[key] = {
                "score": score,
                "weight": weight,
                "reason": str(raw.get("reason", "")).strip() or "暂无评分说明。",
            }
            total += score * weight
        answers = session.get("turns", [])
        total_chars = sum(int(item.get("char_count", 0)) for item in answers)
        short_penalty = bool(answers) and total_chars < 50 * len(answers)
        if answers and any(int(item.get("char_count", 0)) < 20 for item in answers):
            total = min(total, 60)
        return {
            "total_score": max(0, min(100, int(round(total)))),
            "dimensions": dimensions,
            "strengths": _string_list(payload.get("strengths"))[:3],
            "weak_tags": _string_list(payload.get("weak_tags"))[:6],
            "suggestions": _string_list(payload.get("suggestions"))[:3],
            "short_answer_penalty": short_penalty,
            "estimated": False,
        }

    def _fallback_score(self, session: dict, answers: List[dict]) -> dict:
        if not answers:
            answers = [
                {
                    "transcript": item.get("transcript", ""),
                    "char_count": item.get("char_count", 0),
                }
                for item in session.get("turns", [])
            ]
        joined = "\n".join(item.get("transcript", "") for item in answers)
        keywords = session.get("jd_keywords", [])
        covered = [keyword for keyword in keywords if keyword.lower() in joined.lower()]
        coverage = len(covered) / max(1, len(keywords))
        counts = [int(item.get("char_count", 0)) for item in answers]
        average_chars = sum(counts) / max(1, len(counts))
        structure_hits = sum(
            joined.count(word)
            for word in ("首先", "其次", "最后", "因为", "所以", "结果", "复盘")
        )
        logic = min(100, 42 + min(average_chars, 180) * 0.22 + structure_hits * 3)
        technical = min(100, 35 + coverage * 48 + min(average_chars, 180) * 0.08)
        adaptability = min(100, 40 + min(average_chars, 200) * 0.18 + structure_hits * 2)
        match = min(100, 38 + coverage * 52)
        short_penalty = any(count < 50 for count in counts)
        if any(count < 20 for count in counts):
            cap = 60
        else:
            cap = 100
        dimensions = {
            "technical_accuracy": {
                "score": round(technical),
                "weight": 0.4,
                "reason": f"回答覆盖了 {len(covered)} 个岗位关键词，按本地规则估算。",
            },
            "logic_expression": {
                "score": round(logic),
                "weight": 0.25,
                "reason": "根据回答长度和连接词使用情况估算，缺少模型评分时仅供参考。",
            },
            "adaptability_learning": {
                "score": round(adaptability),
                "weight": 0.2,
                "reason": "根据回答展开程度和问题响应情况估算。",
            },
            "job_match": {
                "score": round(match),
                "weight": 0.15,
                "reason": "根据 JD 关键词覆盖度估算。",
            },
        }
        total = sum(item["score"] * item["weight"] for item in dimensions.values())
        total = min(cap, round(total))
        weak_tags = keywords[:3] if coverage < 0.6 else []
        if short_penalty:
            weak_tags.append("回答完整度")
        suggestions = [
            "先用一句话给结论，再补充约束、方案和结果。",
            "每个技术选择都说明指标、取舍和失败边界。",
            "回答结束前用一句话复盘，主动说出下一次改进点。",
        ]
        return {
            "total_score": int(total),
            "dimensions": dimensions,
            "strengths": ["能够围绕问题持续作答"] if joined else [],
            "weak_tags": list(dict.fromkeys(weak_tags))[:6],
            "suggestions": suggestions,
            "short_answer_penalty": short_penalty,
            "estimated": True,
        }

    def _build_report(self, session: dict, score_payload: dict, estimated: bool) -> dict:
        total = int(score_payload["total_score"])
        if total >= 85:
            level = "建议进入下一轮"
        elif total >= 70:
            level = "建议补充关键细节"
        else:
            level = "建议补一轮基础练习"
        turns = session.get("turns", [])
        qa = []
        for question in session.get("questions", []):
            turn = next(
                (
                    item
                    for item in turns
                    if item.get("turn_no") == question.get("number")
                ),
                None,
            )
            qa.append(
                {
                    "question": question.get("title", ""),
                    "transcript": turn.get("transcript", "") if turn else "",
                    "audio_url": (
                        f"/api/interview/sessions/{session['session_id']}/turns/"
                        f"{question.get('number')}/answer-audio"
                        if turn and turn.get("audio_path")
                        else ""
                    ),
                    "score": round(total),
                }
            )
        weak_tags = list(dict.fromkeys(score_payload.get("weak_tags", [])))[:6]
        return {
            "session_id": session["session_id"],
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "total_score": total,
            "level": level,
            "estimated": estimated or bool(score_payload.get("estimated")),
            "dimensions": score_payload["dimensions"],
            "strengths": score_payload.get("strengths") or [],
            "weaknesses": weak_tags,
            "weak_tags": weak_tags,
            "suggestions": score_payload.get("suggestions") or [],
            "short_answer_penalty": bool(score_payload.get("short_answer_penalty")),
            "qa": qa,
        }


def _string_list(value) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


service = InterviewService()
knowledge_state = {
    "status": "idle",
    "updated_at": "",
    "message": "",
}
_knowledge_lock = threading.Lock()


def public_session(session: dict) -> dict:
    questions = [
        {
            "id": item.get("id", f"q{index}"),
            "number": item.get("number", index),
            "title": item.get("title", ""),
            "intent": item.get("intent", ""),
            "hint": item.get("hint", ""),
            "dimension": item.get("dimension", ""),
        }
        for index, item in enumerate(session.get("questions", []), start=1)
    ]
    turns = [
        {
            "turn_no": item.get("turn_no"),
            "question": item.get("question", ""),
            "transcript": item.get("transcript", ""),
            "char_count": item.get("char_count", 0),
            "duration_ms": item.get("duration_ms", 0),
            "matched_keyword": item.get("matched_keyword", ""),
        }
        for item in session.get("turns", [])
    ]
    return {
        "session_id": session.get("session_id"),
        "created_at": session.get("created_at"),
        "status": session.get("status"),
        "mode": session.get("mode"),
        "company": session.get("company", ""),
        "role": session.get("role", ""),
        "company_style": session.get("company_style", ""),
        "resume_name": session.get("resume_name", ""),
        "resume_summary": session.get("resume_summary", {}),
        "jd_keywords": session.get("jd_keywords", []),
        "weak_tags": session.get("weak_tags", []),
        "questions": questions,
        "turns": turns,
        "current_turn_no": session.get("current_turn_no", 1),
        "error_code": session.get("error_code", ""),
        "message": session.get("message", ""),
    }


def knowledge_catalog() -> List[dict]:
    catalog = []
    directories = sorted(DATA_DIR.iterdir()) if DATA_DIR.exists() else []
    for directory in directories:
        if not directory.is_dir():
            continue
        files = [
            path
            for path in directory.rglob("*")
            if path.is_file() and path.suffix.lower() in {".md", ".txt"}
        ]
        catalog.append(
            {
                "name": directory.name,
                "files": len(files),
                "size": sum(path.stat().st_size for path in files),
            }
        )
    return catalog


def set_knowledge_state(status: str, message: str = "") -> None:
    with _knowledge_lock:
        knowledge_state.update(
            {
                "status": status,
                "message": message,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
