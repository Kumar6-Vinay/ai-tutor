"""HTTP API for the tutor MVP."""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .domain.curriculum import SKILLS
from .domain.learner_model import LearnerModel
from .domain.maths_engine import BUG_TEXT, Bug
from .domain.policy import STATE_PLAIN, Session
from .services import intake
from .services.phraser import get_phraser
from .services.safety import check_output
from .store import Store

STATIC = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="Class 1-3 Maths Tutor API", version="0.1.0")
store = Store(os.environ.get("TUTOR_DB", "tutor.db"))
phraser = get_phraser()
vision = intake.get_extractor()


# ---------- access gate and rate limits ----------
# Optional passcode: set TUTOR_ACCESS_CODE and every /api call (except health and unlock) needs the cookie
# that /api/unlock hands out. Unset, the app is open (local use).
def _token(code: str) -> str:
    return hmac.new(code.encode(), b"tutor-access", hashlib.sha256).hexdigest()


def _unlocked(request: Request) -> bool:
    code = os.environ.get("TUTOR_ACCESS_CODE")
    return not code or hmac.compare_digest(request.cookies.get("tutor_access", ""), _token(code))


class Limiter:
    def __init__(self) -> None:
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str, n: int, window: float) -> bool:
        q, now = self.hits[key], time.time()
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= n:
            return False
        q.append(now)
        return True


limiter = Limiter()
PHOTOS_PER_HOUR = int(os.environ.get("TUTOR_PHOTOS_PER_HOUR", "10"))      # per visitor
PHOTOS_PER_HOUR_ALL = int(os.environ.get("TUTOR_PHOTOS_PER_HOUR_ALL", "60"))  # whole app: protects a free quota


def _who(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    # the last entry is the one our own proxy added; earlier ones can be forged by the visitor
    return fwd.split(",")[-1].strip() or (request.client.host if request.client else "?")


@app.middleware("http")
async def gate(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.url.path not in ("/api/health", "/api/unlock") \
            and not _unlocked(request):
        return JSONResponse({"detail": "Passcode needed"}, status_code=401)
    return await call_next(request)


# ---------- schemas ----------
class ChildIn(BaseModel):
    nickname: str = Field(min_length=1, max_length=16)
    grade: int = Field(ge=1, le=3)
    board: str = "NCERT"
    age_band: Literal["5-7", "8-10"] = "5-7"
    parent_consent: bool

    @field_validator("nickname")
    @classmethod
    def clean_nickname(cls, v: str) -> str:
        v = re.sub(r"[^\w .'-]", "", v, flags=re.UNICODE).strip()
        if not v:
            raise ValueError("Use a short nickname with letters only")
        return v


class Item(BaseModel):
    a: int
    b: int
    op: Literal["+", "-"]


class SessionIn(BaseModel):
    child_id: str
    items: list[Item] = Field(min_length=1, max_length=20)


class ParseIn(BaseModel):
    text: str = Field(max_length=2000)


class InputIn(BaseModel):
    kind: Literal["digit", "regroup", "help", "stuck", "break", "continue", "build", "number"]
    value: Optional[int] = Field(default=None, ge=0, le=99)
    tens: Optional[int] = Field(default=None, ge=0, le=9)
    ones: Optional[int] = Field(default=None, ge=0, le=19)


# ---------- helpers ----------
def _child(cid: str) -> dict:
    c = store.get_child(cid)
    if not c:
        raise HTTPException(404, "Child not found")
    return c


def _load(sid: str) -> tuple[Session, LearnerModel]:
    d = store.get_session(sid)
    if not d:
        raise HTTPException(404, "Session not found")
    return Session.from_dict(d), LearnerModel(store.get_learner(d["child_id"]))


def _save(s: Session, m: LearnerModel) -> None:
    store.save_session(s.to_dict())
    store.save_learner(s.d["child_id"], m.to_dict())


def _say(text: Optional[str], age_band: str) -> Optional[str]:
    if not text:
        return text
    out = phraser.phrase(text, age_band)
    ok, _ = check_output(out)
    return out if ok else text


def _view(s: Session) -> dict:
    v = s.view()
    if "say" in v:
        v["say"] = _say(v["say"], s.d["age_band"])
    return v


# ---------- routes ----------
class UnlockIn(BaseModel):
    code: str = Field(max_length=100)


@app.post("/api/unlock")
def unlock(body: UnlockIn, request: Request, response: Response) -> dict:
    code = os.environ.get("TUTOR_ACCESS_CODE")
    if not code:
        return {"ok": True}
    if not limiter.allow("unlock:" + _who(request), 10, 600):
        raise HTTPException(429, "Too many tries. Wait a few minutes.")
    if not hmac.compare_digest(body.code.encode(), code.encode()):
        raise HTTPException(401, "That passcode is not right")
    response.set_cookie("tutor_access", _token(code), httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30,
                        secure=request.headers.get("x-forwarded-proto") == "https")
    return {"ok": True}


@app.get("/api/health")
def health(request: Request) -> dict:
    return {"ok": True, "photo": getattr(vision, "configured", True), "provider": getattr(vision, "provider", ""),
            "locked": bool(os.environ.get("TUTOR_ACCESS_CODE")), "unlocked": _unlocked(request)}


@app.post("/api/children", status_code=201)
def create_child(body: ChildIn) -> dict:
    if not body.parent_consent:
        raise HTTPException(400, "A parent must give consent before a child profile is created")
    c = store.create_child(body.nickname, body.grade, body.board, body.age_band)
    return {"id": c["id"], "nickname": c["nickname"], "grade": c["grade"], "age_band": c["age_band"]}


@app.delete("/api/children/{cid}", status_code=204, response_class=Response)
def delete_child(cid: str) -> Response:
    _child(cid)
    store.delete_child(cid)
    return Response(status_code=204)


@app.get("/api/children/{cid}/progress")
def progress(cid: str) -> dict:
    c = _child(cid)
    m = LearnerModel(store.get_learner(cid))
    return {
        "nickname": c["nickname"],
        "skills": [{"id": k, "name": SKILLS[k].name, "state": m.state(k).value, "plain": STATE_PLAIN[m.state(k)],
                    "next_review": m.skills[k].next_review} for k in m.skills],
        "noticed": [{"skill": x["skill"], "bug": x["bug"], "text": BUG_TEXT[Bug(x["bug"])],
                     "confirmed": x["confirmed"], "last_seen": x["last_seen"]} for x in m.active_misconceptions()],
    }


@app.delete("/api/children/{cid}/observations/{skill}/{bug}", status_code=204, response_class=Response)
def dismiss(cid: str, skill: str, bug: str) -> Response:
    _child(cid)
    m = LearnerModel(store.get_learner(cid))
    if not m.dismiss_misconception(skill, bug):
        raise HTTPException(404, "No such observation")
    store.save_learner(cid, m.to_dict())
    return Response(status_code=204)


@app.post("/api/worksheets/parse")
def parse_worksheet(body: ParseIn) -> dict:
    items = intake.parse_text(body.text)
    return {"items": items, "needs_confirmation": intake.needs_confirmation(items)}


@app.post("/api/worksheets/photo")
async def parse_photo(request: Request) -> dict:
    """Body is the raw image. The photo is read once and never stored."""
    if not getattr(vision, "configured", True):
        raise HTTPException(501, "Photo reading is not connected yet. Type the problems instead.")
    if not (limiter.allow("photo:" + _who(request), PHOTOS_PER_HOUR, 3600) and limiter.allow("photo:all", PHOTOS_PER_HOUR_ALL, 3600)):
        raise HTTPException(429, "That's a lot of photos for now. Please type the problems, or try again later.")
    data = await request.body()
    if not data:
        raise HTTPException(400, "No photo received")
    if len(data) > intake.MAX_IMAGE_BYTES:
        raise HTTPException(413, "That photo is too big. Try again a bit further away.")
    try:
        raw, not_read = await run_in_threadpool(vision.extract, data)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception:
        raise HTTPException(502, "Could not read the photo. Try again in good light, or type the problems.")
    items = intake.to_items(raw)
    return {"items": items, "needs_confirmation": intake.needs_confirmation(items),
            "not_read": not_read}


@app.post("/api/sessions", status_code=201)
def start_session(body: SessionIn) -> dict:
    child = _child(body.child_id)
    m = LearnerModel(store.get_learner(child["id"]))
    try:
        s = Session.start(child, [i.model_dump() for i in body.items], m)
    except ValueError as e:
        raise HTTPException(422, str(e))
    _save(s, m)
    return {"session_id": s.d["id"], "action": _view(s)}


@app.get("/api/sessions/{sid}")
def get_session(sid: str) -> dict:
    s, _ = _load(sid)
    return {"session_id": sid, "action": _view(s)}


@app.post("/api/sessions/{sid}/input")
def session_input(sid: str, body: InputIn) -> dict:
    s, m = _load(sid)
    if s.d["ended"] and body.kind != "continue":
        raise HTTPException(409, "This session has finished")
    needs = {"digit": "value", "number": "value"}
    if body.kind in needs and body.value is None:
        raise HTTPException(422, "value is required")
    if body.kind == "build" and (body.tens is None or body.ones is None):
        raise HTTPException(422, "tens and ones are required")
    if body.kind == "digit" and body.value > 9:
        raise HTTPException(422, "digit must be 0-9")
    res = s.respond(body.model_dump(exclude_none=True), m)
    _save(s, m)
    fb = res.get("feedback")
    if fb and fb.get("text"):
        fb["text"] = _say(fb["text"], s.d["age_band"])
    return {"feedback": fb, "completed": res.get("completed", False), "action": _view(s)}


@app.get("/api/sessions/{sid}/report")
def report(sid: str) -> dict:
    s, m = _load(sid)
    return s.report(m)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
