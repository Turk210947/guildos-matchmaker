from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
from matchmaker import MatchmakingEngine, Player

app = FastAPI()
engine = MatchmakingEngine()

# โครงสร้าง JSON ที่ Botnoi จะส่งมา
class MatchRequest(BaseModel):
    game: str
    time: List[str]
    role: str
    style: str

# จำลองฐานข้อมูลผู้เล่นในระบบ (Mock Candidates)
candidates_pool = [
    Player(user_id="U002", display_name="Pro_Gamer", games=["Valorant"], available_time=["20:00-22:00"], roles=["Controller"], playstyle_vector=[0.8, 0.2, 0.7, 0.5]),
    Player(user_id="U003", display_name="Chill_Bro", games=["Valorant"], available_time=["20:00-22:00"], roles=["Initiator"], playstyle_vector=[0.5, 0.5, 0.5, 0.5]),
    # คนนี้โดนรีพอร์ตเยอะ (report_rate=0.9) ระบบต้องทำการปัดตก ไม่เอามาจับคู่
    Player(
        user_id="U004", display_name="Toxic_Guy", games=["Valorant"], available_time=["20:00-22:00"], roles=["Duelist"], playstyle_vector=[0.9, 0.1, 0.8, 0.5], report_rate=0.9, leave_rate=0.9 # เพิ่มการออกเกมกลางคันเข้าไป
    )
]

@app.post("/match")
async def match_players(data: MatchRequest):
    # 1. แปลงคำสั่งที่ได้จาก Botnoi ให้กลายเป็น Player Object
    target_user = Player(
        user_id="U001",
        display_name="Botnoi_User",
        games=[data.game],
        available_time=data.time,
        roles=[data.role],
        playstyle_vector=[0.5, 0.5, 0.5, 0.5] # ตอนนี้ใส่ค่ากลางๆ ไว้ก่อน
    )

    # 2. ส่งเข้า Algorithm จับคู่
    matches = engine.find_matches(target_user, candidates_pool)

    # 3. จัดฟอร์แมตข้อมูลส่งกลับไปให้หน้าเว็บ
    results = []
    for match in matches:
        results.append({
            "user_id": match.user_id,
            "name": match.display_name,
            "match_score": f"{match.adjusted_score * 100:.2f}%"
        })

    return {
        "status": "success",
        "top_matches": results
    }