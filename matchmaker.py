from __future__ import annotations

import math
import time
import uuid
import unittest
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set

# น้ำหนักการคำนวณคะแนนจับคู่
WEIGHTS = {
    "game": 0.40,
    "time": 0.25,
    "role": 0.20,
    "playstyle": 0.15,
}

TEAM_WEIGHTS = {
    "average_pair_score": 0.70,
    "composition": 0.30,
}

MATCH_THRESHOLD = 0.60
MAX_CANDIDATE_POOL = 200

# [แก้ไข 3] อัปเดตคำศัพท์ Role ให้ตรงกับ Output ที่ GenAI สกัดออกมา
ROLE_COMPATIBILITY: Dict[Tuple[str, str], float] = {
    # FPS
    ("Duelist/Entry", "Controller"): 1.0,
    ("Duelist/Entry", "Initiator"): 1.0,
    ("Controller", "Initiator"): 0.9,
    # MOBA
    ("Carry", "Support/Roam"): 1.0,
    ("Jungle", "Mid Lane"): 0.9,
    ("Offlane", "Jungle"): 0.8,
    # General
    ("Tank", "Healer"): 1.0,
    ("DPS", "Tank"): 0.9,
}

IDEAL_TEAM_COMPOSITIONS: Dict[str, List[str]] = {
    "RoV": ["DSL", "Carry", "Mage", "Roaming", "Jungle"],
    "LoL": ["Top", "AD Carry", "Mid", "Support", "Jungle"],
    "MLBB": ["Roam", "Jungle", "Mid Laner", "Gold Laner", "Exp Laner"],
    "Valorant": ["Duelist", "Controller", "Sentinel", "Initiator", "Flexible"],
    "PUBG": ["IGL", "Attacker", "Attacker", "Support", "Scout"],
    "APEX Legends": ["Skirmisher", "Assault", "Controller", "Support", "Recon"],
}


@dataclass
class Player:
    user_id: str
    display_name: str
    games: List[str]
    available_time: List[str]
    roles: List[str]
    playstyle_vector: List[float]
    region: str = "TH"
    status: str = "offline"
    blocked_users: List[str] = field(default_factory=list)
    queue_time: Optional[int] = None
    rank_score: float = 0.5
    report_rate: float = 0.0
    leave_rate: float = 0.0
    block_rate: float = 0.0
    negative_feedback_rate: float = 0.0


@dataclass
class MatchResult:
    user_id: str
    display_name: str
    base_score: float
    adjusted_score: float
    game_score: float
    time_score: float
    role_score: float
    playstyle_score: float
    toxic_score: float


@dataclass
class MatchSession:
    match_id: str
    users: List[str]
    match_score: float
    created_at: int
    status: str = "matched"


class MatchmakingEngine:
    def __init__(self, threshold: float = MATCH_THRESHOLD):
        self.threshold = threshold
        self.matching_queue: List[Player] = []

    @staticmethod
    def current_timestamp() -> int:
        return int(time.time())

    @staticmethod
    def jaccard_score(items_a: List[str], items_b: List[str]) -> float:
        set_a, set_b = set(items_a), set(items_b)
        union = set_a | set_b
        if not union:
            return 0.0
        return len(set_a & set_b) / len(union)

    def calculate_game_score(self, user_a: Player, user_b: Player) -> float:
        return self.jaccard_score(user_a.games, user_b.games)

    @staticmethod
    def calculate_time_score(user_a: Player, user_b: Player) -> float:
        time_a, time_b = set(user_a.available_time), set(user_b.available_time)
        # [แก้ไขเสริม] ถ้าฝ่ายใดฝ่ายหนึ่งไม่ระบุเวลา (Array ว่าง = เล่นตอนไหนก็ได้) ให้คะแนนเวลาเต็ม 1.0 ไปเลย
        if not time_a or not time_b:
            return 1.0
        return len(time_a & time_b) / len(time_a)

    @staticmethod
    def calculate_role_score(user_a: Player, user_b: Player) -> float:
        best_score = 0.0
        for role_a in user_a.roles:
            for role_b in user_b.roles:
                # [แก้ไข 2] เช็กสลับฝั่ง (Two-way check) เพื่อป้องกันบั๊กหาไม่เจอ
                if (role_a, role_b) in ROLE_COMPATIBILITY:
                    best_score = max(best_score, ROLE_COMPATIBILITY[(role_a, role_b)])
                elif (role_b, role_a) in ROLE_COMPATIBILITY:
                    best_score = max(best_score, ROLE_COMPATIBILITY[(role_b, role_a)])
                elif role_a == role_b:
                    best_score = max(best_score, 0.5)
        return best_score

    @staticmethod
    def cosine_similarity(vector_a: List[float], vector_b: List[float]) -> float:
        if len(vector_a) != len(vector_b) or not vector_a:
            return 0.0
        dot_product = sum(a * b for a, b in zip(vector_a, vector_b))
        magnitude_a = math.sqrt(sum(a * a for a in vector_a))
        magnitude_b = math.sqrt(sum(b * b for b in vector_b))
        if magnitude_a == 0 or magnitude_b == 0:
            return 0.0
        return dot_product / (magnitude_a * magnitude_b)

    @staticmethod
    def calculate_toxic_score(user: Player) -> float:
        score = (
            user.report_rate * 0.40
            + user.leave_rate * 0.30
            + user.block_rate * 0.20
            + user.negative_feedback_rate * 0.10
        )
        return round(min(max(score, 0.0), 1.0), 4)

    def calculate_toxic_penalty(self, user: Player) -> float:
        toxic_score = self.calculate_toxic_score(user)
        if toxic_score <= 0.30:
            return 0.00
        if toxic_score <= 0.60:
            return 0.05
        return 0.15

    def calculate_base_match_score(self, user_a: Player, user_b: Player) -> Tuple[float, Dict[str, float]]:
        game_score = self.calculate_game_score(user_a, user_b)
        time_score = self.calculate_time_score(user_a, user_b)
        role_score = self.calculate_role_score(user_a, user_b)
        playstyle_score = self.cosine_similarity(user_a.playstyle_vector, user_b.playstyle_vector)

        base_score = (
            game_score * WEIGHTS["game"]
            + time_score * WEIGHTS["time"]
            + role_score * WEIGHTS["role"]
            + playstyle_score * WEIGHTS["playstyle"]
        )
        details = {
            "game_score": game_score,
            "time_score": time_score,
            "role_score": role_score,
            "playstyle_score": playstyle_score,
        }
        return round(base_score, 4), details

    @staticmethod
    def waiting_seconds(queue_time: Optional[int]) -> int:
        if queue_time is None:
            return 0
        return max(0, int(time.time()) - queue_time)

    def dynamic_threshold(self, queue_time: Optional[int]) -> float:
        waiting = self.waiting_seconds(queue_time)
        if waiting <= 30:
            return 0.70
        if waiting <= 60:
            return 0.65
        if waiting <= 120:
            return 0.60
        return 0.55

    def waiting_bonus(self, queue_time: Optional[int]) -> float:
        waiting = self.waiting_seconds(queue_time)
        if waiting <= 30:
            return 0.00
        if waiting <= 60:
             return 0.02
        if waiting <= 120:
            return 0.04
        return 0.05

    # ด่านตรวจเช็กกฎพื้นฐานก่อนการคำนวณคะแนน (Rule-based Filtering)
    def pass_rule_layer(self, user_a: Player, user_b: Player, realtime: bool = False) -> bool:
        if user_a.user_id == user_b.user_id:
            return False
        if realtime and user_b.status != "in_queue":
            return False
        if realtime and user_a.region != user_b.region:
            return False
        if not set(user_a.games) & set(user_b.games):
            return False
            
        # [แก้ไข 1] ถ้ามีคนไม่ระบุเวลา (ว่างตลอด) ให้ผ่านได้เลย ไม่ต้องบล็อกทิ้ง
        time_a, time_b = set(user_a.available_time), set(user_b.available_time)
        if time_a and time_b and not (time_a & time_b):
            return False
            
        if user_b.user_id in user_a.blocked_users:
            return False
        if user_a.user_id in user_b.blocked_users:
            return False
            
        # [จุดที่แก้ไขเพิ่ม] ดักจับผู้เล่นที่มีคะแนนความประพฤติแย่ (Toxic Score > 0.60)
        if self.calculate_toxic_score(user_b) > 0.60:
            return False
            
        return True

    def calculate_adjusted_score(self, user_a: Player, user_b: Player) -> MatchResult:
        base_score, details = self.calculate_base_match_score(user_a, user_b)
        toxic_score = self.calculate_toxic_score(user_b)
        toxic_penalty = self.calculate_toxic_penalty(user_b)
        bonus = self.waiting_bonus(user_b.queue_time)
        adjusted_score = max(0.0, min(1.0, base_score + bonus - toxic_penalty))
        return MatchResult(
            user_id=user_b.user_id,
            display_name=user_b.display_name,
            base_score=base_score,
            adjusted_score=round(adjusted_score, 4),
            game_score=round(details["game_score"], 4),
            time_score=round(details["time_score"], 4),
            role_score=round(details["role_score"], 4),
            playstyle_score=round(details["playstyle_score"], 4),
            toxic_score=round(toxic_score, 4),
        )

    def find_matches(self, target_user: Player, candidates: List[Player]) -> List[MatchResult]:
        results: List[MatchResult] = []
        for candidate in candidates[:MAX_CANDIDATE_POOL]:
            if not self.pass_rule_layer(target_user, candidate):
                continue
            result = self.calculate_adjusted_score(target_user, candidate)
            if result.adjusted_score >= self.threshold:
                results.append(result)
        return sorted(results, key=lambda item: item.adjusted_score, reverse=True)

    def add_to_queue(self, user: Player) -> None:
        self.remove_from_queue(user.user_id)
        user.status = "in_queue"
        user.queue_time = self.current_timestamp()
        self.matching_queue.append(user)

    def remove_from_queue(self, user_id: str) -> None:
        self.matching_queue = [user for user in self.matching_queue if user.user_id != user_id]

    def create_match_session(self, user_a: Player, user_b: Player, score: float) -> MatchSession:
        return MatchSession(
            match_id=str(uuid.uuid4()),
            users=[user_a.user_id, user_b.user_id],
            match_score=round(score, 4),
            created_at=self.current_timestamp(),
        )

    def request_realtime_match(self, user: Player):
        self.add_to_queue(user)
        threshold = self.dynamic_threshold(user.queue_time)
        best_candidate: Optional[Player] = None
        best_result: Optional[MatchResult] = None

        for candidate in self.matching_queue[:MAX_CANDIDATE_POOL]:
            if not self.pass_rule_layer(user, candidate, realtime=True):
                continue
            result = self.calculate_adjusted_score(user, candidate)
            if best_result is None or result.adjusted_score > best_result.adjusted_score:
                best_result = result
                best_candidate = candidate

        if best_candidate and best_result and best_result.adjusted_score >= threshold:
            session = self.create_match_session(user, best_candidate, best_result.adjusted_score)
            self.remove_from_queue(user.user_id)
            self.remove_from_queue(best_candidate.user_id)
            user.status = "matched"
            best_candidate.status = "matched"
            return session

        return {"status": "waiting", "message": "No suitable match found yet"}

    @staticmethod
    def team_composition_score(game: str, players: List[Player]) -> float:
        ideal_roles = IDEAL_TEAM_COMPOSITIONS.get(game)
        if not ideal_roles:
            return 0.0
        required: Dict[str, int] = {}
        for role in ideal_roles:
            required[role] = required.get(role, 0) + 1

        selected_roles: Dict[str, int] = {}
        for player in players:
            for role in player.roles:
                if role in required:
                    selected_roles[role] = selected_roles.get(role, 0) + 1
                    break

        matched_slots = 0
        for role, count in required.items():
            matched_slots += min(count, selected_roles.get(role, 0))
        return round(matched_slots / len(ideal_roles), 4)

    def average_pair_score(self, players: List[Player]) -> float:
        if len(players) < 2:
            return 0.0
        scores = []
        for i in range(len(players)):
            for j in range(i + 1, len(players)):
                if self.pass_rule_layer(players[i], players[j]):
                    scores.append(self.calculate_base_match_score(players[i], players[j])[0])
        if not scores:
            return 0.0
        return sum(scores) / len(scores)

    def final_team_score(self, game: str, players: List[Player]) -> float:
        average_pair = self.average_pair_score(players)
        composition = self.team_composition_score(game, players)
        final_score = (
            average_pair * TEAM_WEIGHTS["average_pair_score"]
            + composition * TEAM_WEIGHTS["composition"]
        )
        return round(final_score, 4)

    def build_team(self, target_user: Player, candidates: List[Player], game: str, team_size: int = 5) -> Dict[str, object]:
        team: List[Player] = [target_user]
        remaining = [c for c in candidates if self.pass_rule_layer(target_user, c)]

        while len(team) < team_size and remaining:
            best_candidate = None
            best_team_score = -1.0
            for candidate in remaining:
                trial_team = team + [candidate]
                score = self.final_team_score(game, trial_team)
                if score > best_team_score:
                    best_team_score = score
                    best_candidate = candidate
            if best_candidate is None:
                break
            team.append(best_candidate)
            remaining = [c for c in remaining if c.user_id != best_candidate.user_id]

        return {
            "game": game,
            "team_user_ids": [player.user_id for player in team],
            "team_roles": [player.roles[0] if player.roles else "Unknown" for player in team],
            "composition_score": self.team_composition_score(game, team),
            "team_score": self.final_team_score(game, team),
        }


# โครงสร้างสำหรับรัน Unit Test ทดสอบระบบ
class TestMatchmakingEngine(unittest.TestCase):
    def setUp(self):
        self.engine = MatchmakingEngine()
        self.user_a = Player(
            user_id="U001",
            display_name="Player 1",
            games=["RoV", "Valorant"],
            available_time=["20:00-22:00", "22:00-24:00"],
            roles=["Carry"],
            playstyle_vector=[0.8, 0.2, 0.7, 0.5],
            region="TH",
        )
        self.user_b = Player(
            user_id="U002",
            display_name="Player 2",
            games=["RoV"],
            available_time=["22:00-24:00"],
            roles=["Support/Roam"],
            playstyle_vector=[0.7, 0.3, 0.8, 0.4],
            region="TH",
        )

    def test_game_score(self):
        self.assertAlmostEqual(self.engine.calculate_game_score(self.user_a, self.user_b), 0.5)

    def test_time_score(self):
        self.assertAlmostEqual(self.engine.calculate_time_score(self.user_a, self.user_b), 0.5)

    def test_role_score(self):
        self.assertEqual(self.engine.calculate_role_score(self.user_a, self.user_b), 1.0)

    def test_cosine_similarity(self):
        self.assertAlmostEqual(self.engine.cosine_similarity([1, 0], [1, 0]), 1.0)

    def test_rule_layer_valid(self):
        self.assertTrue(self.engine.pass_rule_layer(self.user_a, self.user_b))

    def test_blocked_user_invalid(self):
        self.user_a.blocked_users = ["U002"]
        self.assertFalse(self.engine.pass_rule_layer(self.user_a, self.user_b))

    def test_toxic_score(self):
        toxic_user = Player(
            user_id="T001",
            display_name="Toxic",
            games=["RoV"],
            available_time=["20:00-22:00"],
            roles=["Support/Roam"],
            playstyle_vector=[0.1, 0.1, 0.1, 0.1],
            report_rate=1.0,
            leave_rate=1.0,
            block_rate=1.0,
            negative_feedback_rate=1.0,
        )
        self.assertEqual(self.engine.calculate_toxic_score(toxic_user), 1.0)
        self.assertEqual(self.engine.calculate_toxic_penalty(toxic_user), 0.15)


def demo():
    engine = MatchmakingEngine()
    target = Player(
        user_id="U001",
        display_name="Mock Player 1",
        games=["RoV", "Valorant"],
        available_time=["20:00-22:00", "22:00-24:00"],
        roles=["Carry"],
        playstyle_vector=[0.8, 0.2, 0.7, 0.5],
        region="TH",
    )
    candidates = [
        Player("U002", "Mock Player 2", ["RoV"], ["22:00-24:00"], ["Support/Roam"], [0.7, 0.3, 0.8, 0.4], "TH"),
        Player("U003", "Mock Player 3", ["RoV"], ["20:00-22:00"], ["Jungle"], [0.6, 0.2, 0.7, 0.6], "TH", report_rate=0.8, leave_rate=0.5),
        Player("U004", "Mock Player 4", ["Valorant"], ["22:00-24:00"], ["Controller"], [0.9, 0.1, 0.8, 0.5], "TH"),
    ]

    matches = engine.find_matches(target, candidates)
    print("Top Matches:")
    for match in matches:
        print(match)


if __name__ == "__main__":
    demo()
