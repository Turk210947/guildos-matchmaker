from fastapi import FastAPI
from pydantic import BaseModel, validator
from typing import List, Union, Optional
import json
from matchmaker import MatchmakingEngine, Player

app = FastAPI()

# --- Pydantic Models ---

class UserModel(BaseModel):
    user_id: str
    user_name: str
    platform: str

class CriteriaModel(BaseModel):
    game: str = ""
    time: Union[List[str], str] = []
    role: Union[List[str], str] = ""
    style: str = ""

    @validator("time", pre=True)
    def parse_time(cls, v):
        if not v:
            return []
        if isinstance(v, str):
            return [v] if v else []
        return v

    @validator("role", pre=True)
    def parse_role(cls, v):
        if not v:
            return ""
        return v

class MatchRequestPayload(BaseModel):
    user: UserModel
    criteria: Union[CriteriaModel, str]

    @validator("criteria", pre=True)
    def parse_criteria(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return {}
        return v

# --- Helper: แปลง style string → playstyle_vector ---
def style_to_vector(style: str) -> List[float]:
    style_map = {
        "Competitive": [0.9, 0.2, 0.8, 0.9],
        "Casual":      [0.3, 0.8, 0.3, 0.4],
        "Aggressive":  [1.0, 0.1, 0.9, 0.5],
        "Teamwork":    [0.7, 0.5, 0.6, 1.0],
    }
    return style_map.get(style, [0.5, 0.5, 0.5, 0.5])

# --- Helper: ดึง Candidates จาก Supabase (หรือ Mock ก่อน) ---
def get_candidates_from_db(game: str) -> List[Player]:
    # TODO Week 2: เปลี่ยนเป็น Supabase query จริง
    # ตอนนี้ใช้ Mock Data ก่อน เพื่อให้ระบบทำงานได้
    mock_players = [
        Player(
            user_id="mock_001",
            display_name="MockPlayer_Sentinel",
            games=["CS2"],
            available_time=["20:00-21:00"],
            roles=["Sentinel"],
            playstyle_vector=[0.8, 0.2, 0.7, 0.8],
            region="TH",
            status="in_queue",
        ),
        Player(
            user_id="mock_002",
            display_name="MockPlayer_Controller",
            games=["CS2", "Valorant"],
            available_time=["19:00-21:00", "20:00-21:00"],
            roles=["Controller"],
            playstyle_vector=[0.7, 0.3, 0.8, 0.6],
            region="TH",
            status="in_queue",
        ),
        Player(
            user_id="mock_003",
            display_name="MockPlayer_RoV",
            games=["RoV"],
            available_time=["20:00-22:00"],
            roles=["Carry"],
            playstyle_vector=[0.8, 0.2, 0.7, 0.5],
            region="TH",
            status="in_queue",
        ),
    ]
    # Filter เฉพาะเกมที่ตรงกัน
    if game:
        return [p for p in mock_players if game in p.games]
    return mock_players

# --- Endpoint ---

@app.post("/match")
async def match_players(payload: MatchRequestPayload):
    try:
        user = payload.user
        criteria = payload.criteria

        # แปลง role เป็น List
        roles = []
        if isinstance(criteria.role, list):
            roles = criteria.role
        elif criteria.role:
            roles = [criteria.role]

        # แปลง time เป็น List
        times = criteria.time if isinstance(criteria.time, list) else []

        # สร้าง Target Player จาก criteria ที่ได้จาก Botnoi
        target_player = Player(
            user_id=user.user_id,
            display_name=user.user_name,
            games=[criteria.game] if criteria.game else [],
            available_time=times,
            roles=roles,
            playstyle_vector=style_to_vector(criteria.style),
            region="TH",
            status="in_queue",
        )

        # ดึง Candidates จาก DB (หรือ Mock)
        candidates = get_candidates_from_db(criteria.game)

        # รัน Matchmaking Algorithm
        engine = MatchmakingEngine()
        results = engine.find_matches(target_player, candidates)

        # Format Response
        if not results:
            return {
                "result": f"ขณะนี้ยังไม่มีผู้เล่น {criteria.game} ที่ว่างตรงกันเลยครับ 🎮 ลองใหม่อีกครั้งนะ!"
            }

        top = results[0]
        return {
            "result": (
                f"เจอตี้แล้ว! 🎯 {top.display_name} "
                f"(คะแนนความเข้ากัน: {int(top.adjusted_score * 100)}%) "
                f"เกม: {criteria.game} | Role: {top.display_name}"
            ),
            "matches": [
                {
                    "user_id": r.user_id,
                    "display_name": r.display_name,
                    "score": r.adjusted_score,
                    "game_score": r.game_score,
                    "time_score": r.time_score,
                    "role_score": r.role_score,
                }
                for r in results
            ]
        }

    except Exception as e:
        return {"result": f"เกิดข้อผิดพลาด: {str(e)}"}
