"""HTTP API for the tutor MVP."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
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
@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


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
def parse_photo() -> dict:
    raise HTTPException(501, "Photo reading is not connected yet. Type the problems instead.")


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
