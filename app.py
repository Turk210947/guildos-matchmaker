from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, validator
from typing import List, Optional, Union
import json
from matchmaker import MatchmakingEngine, Player

app = FastAPI()
engine = MatchmakingEngine()

class MatchRequest(BaseModel):
    game: str
    time: Union[List[str], str]
    role: Union[List[str], str]
    style: Optional[str] = None

    @validator("time", pre=True)
    def parse_time(cls, v):
        if isinstance(v, str):
            return [v.strip()]
        return v

    @validator("role", pre=True)
    def parse_role(cls, v):
        if isinstance(v, str):
            return [v.strip()]
        return v

    class Config:
        extra = "allow"

candidates_pool = [
    Player(user_id="U002", display_name="Pro_Gamer", games=["Valorant", "RoV"], available_time=["20:00-22:00", "21:00-23:00"], roles=["Controller"], playstyle_vector=[0.8, 0.2, 0.7, 0.5]),
    Player(user_id="U003", display_name="Chill_Bro", games=["Valorant", "RoV"], available_time=["20:00-22:00", "21:00-23:00"], roles=["Initiator", "Support"], playstyle_vector=[0.5, 0.5, 0.5, 0.5]),
    Player(user_id="U004", display_name="Toxic_Guy", games=["Valorant"], available_time=["20:00-22:00"], roles=["Duelist"], playstyle_vector=[0.9, 0.1, 0.8, 0.5], report_rate=0.9, leave_rate=0.9),
]

@app.post("/match")
async def match_players(request: Request):
    try:
        raw_body = await request.json()

        # รองรับกรณี Botnoi ส่งมาแบบ {"user_input": {...}}
        if "user_input" in raw_body:
            inner = raw_body["user_input"]
            if isinstance(inner, str):
                inner = json.loads(inner)
            raw_body = inner

        data = MatchRequest(**raw_body)
    except Exception as e:
        return PlainTextResponse(f"ข้อมูลไม่ถูกต้อง: {str(e)}")

    target_user = Player(
        user_id="U001",
        display_name="Botnoi_User",
        games=[data.game],
        available_time=data.time,
        roles=data.role,
        playstyle_vector=[0.5, 0.5, 0.5, 0.5],
    )

    matches = engine.find_matches(target_user, candidates_pool)

    if not matches:
        return PlainTextResponse(f"ตอนนี้ยังไม่มีผู้เล่น {data.game} ที่ว่างตรงกันครับ 🎮")

    top = matches[0]
    reply = f"🎯 เจอคู่เล่นแล้ว!\n👤 ชื่อ: {top.display_name}\n📊 ความเข้ากัน: {top.adjusted_score * 100:.0f}%\n🎮 เกม: {data.game}"
    return PlainTextResponse(reply)

@app.get("/health")
async def health():
    return {"status": "ok"}
