from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, validator
from typing import List, Optional, Union
import json
from matchmaker import MatchmakingEngine, Player

app = FastAPI()
engine = MatchmakingEngine()

# ====================================================
# 1. Pydantic Models (อัปเดตใหม่ให้ตรงกับ Botnoi Payload)
# ====================================================

# โมเดลรับข้อมูลผู้ใช้งาน (ใช้เพื่อกรองคน Toxic ใน Week 2)
class UserModel(BaseModel):
    user_id: str
    user_name: str
    platform: str

# โมเดลรับข้อมูลเงื่อนไขจาก AI
class CriteriaModel(BaseModel):
    game: str = ""
    time: Union[List[str], str] = []
    role: Union[List[str], str] = []
    style: Optional[str] = ""

    @validator("time", pre=True)
    def parse_time(cls, v):
        if isinstance(v, str):
            return [v.strip()] if v.strip() else []
        return v

    @validator("role", pre=True)
    def parse_role(cls, v):
        if isinstance(v, str):
            return [v.strip()] if v.strip() else []
        return v

    class Config:
        extra = "allow"

# โมเดลหลักที่รวมทั้ง User และ Criteria เข้าด้วยกัน
class MatchRequestPayload(BaseModel):
    user: UserModel
    criteria: Union[CriteriaModel, str, dict]

    # เผื่อกรณี Botnoi ส่ง JSON ซ้อนมาเป็น String
    @validator("criteria", pre=True)
    def parse_criteria(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return {}
        return v

# ====================================================
# 2. Mock Data (ฐานข้อมูลจำลอง)
# ====================================================
candidates_pool = [
    Player(user_id="U002", display_name="Pro_Gamer", games=["Valorant", "RoV"], available_time=["20:00-22:00", "21:00-23:00"], roles=["Controller"], playstyle_vector=[0.8, 0.2, 0.7, 0.5]),
    Player(user_id="U003", display_name="Chill_Bro", games=["Valorant", "RoV"], available_time=["20:00-22:00", "21:00-23:00"], roles=["Initiator", "Support"], playstyle_vector=[0.5, 0.5, 0.5, 0.5]),
    Player(user_id="U004", display_name="Toxic_Guy", games=["Valorant"], available_time=["20:00-22:00"], roles=["Duelist"], playstyle_vector=[0.9, 0.1, 0.8, 0.5], report_rate=0.9, leave_rate=0.9),
]

# ====================================================
# 3. Main Endpoint
# ====================================================
@app.post("/match")
async def match_players(request: Request):
    try:
        raw_body = await request.json()
        
        # ถอดรหัส Payload ที่ส่งมาจาก Botnoi
        payload = MatchRequestPayload(**raw_body)
        user_info = payload.user
        criteria = payload.criteria

        # ทำให้แน่ใจว่า criteria ถูกแปลงเป็น Object สมบูรณ์
        if isinstance(criteria, dict):
            criteria = CriteriaModel(**criteria)

    except Exception as e:
        return JSONResponse(content={"result": f"ข้อมูลไม่ถูกต้อง: {str(e)}"})

    # 💡 จุดที่ทีมสามารถนำไปเขียน Algorithm คัดกรองคน Toxic ในสัปดาห์ที่ 2
    # print(f"Checking user toxicity for ID: {user_info.user_id}...")

    # ตั้งค่าผู้เล่นที่ทักบอทเข้ามา โดยดึง ID และชื่อจริงของลูกค้ามาใช้เลย!
    target_user = Player(
        user_id=user_info.user_id,           # <--- ใช้ ID จริงจาก LINE/Facebook
        display_name=user_info.user_name,    # <--- ใช้ชื่อจริงจากระบบ
        games=[criteria.game] if criteria.game else [],
        available_time=criteria.time,
        roles=criteria.role,
        playstyle_vector=[0.5, 0.5, 0.5, 0.5],
    )

    # ส่งเข้าเครื่องยนต์จับคู่
    matches = engine.find_matches(target_user, candidates_pool)

    if not matches:
        return JSONResponse(content={"result": f"ตอนนี้ยังไม่มีผู้เล่นเกม {criteria.game} ที่ว่างตรงกันเลยครับ 🎮 รบกวนลองใหม่อีกครั้งนะ!"})

    top = matches[0]
    
    # ตอบกลับแบบรู้ชื่อลูกค้าด้วย (Personalization)
    reply = f"🎯 เจอคู่เล่นแล้วครับคุณ {user_info.user_name}!\n👤 ชื่อ: {top.display_name}\n📊 ความเข้ากัน: {top.adjusted_score * 100:.0f}%\n🎮 เกม: {criteria.game}"
    
    return JSONResponse(content={"result": reply})

@app.get("/health")
async def health():
    return {"status": "ok"}
