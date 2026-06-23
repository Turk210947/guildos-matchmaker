from fastapi import FastAPI
from pydantic import BaseModel, validator
from typing import List, Union, Optional

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
        if v == "" or v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v

    @validator("role", pre=True)
    def parse_role(cls, v):
        if v is None:
            return ""
        return v

class MatchRequestPayload(BaseModel):
    user: UserModel
    criteria: Union[CriteriaModel, str]  # รองรับกรณี Botnoi ส่งมาเป็น String

    @validator("criteria", pre=True)
    def parse_criteria(cls, v):
        import json
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return {}
        return v

# --- Endpoint ---

@app.post("/match")
async def match_players(payload: MatchRequestPayload):  # ✅ ใส่ Pydantic Model ตรงๆ
    try:
        user_id = payload.user.user_id
        criteria = payload.criteria

        # โยนเข้า Algorithm
        from matchmaker import MatchmakingEngine
        engine = MatchmakingEngine()
        results = engine.find_matches(user_id, criteria.dict())

        return {"result": results}

    except Exception as e:
        return {"result": f"เกิดข้อผิดพลาด: {str(e)}"}
