"""144경기 일정 — 라운드로빈(서클 메서드) 9라운드 × 16사이클, 사이클마다 홈/원정 교대."""
from __future__ import annotations


def round_robin(n: int) -> list[list[tuple[int, int]]]:
    arr = list(range(n))
    rounds = []
    for r in range(n - 1):
        games = []
        for i in range(n // 2):
            a, b = arr[i], arr[n - 1 - i]
            games.append((b, a) if r % 2 else (a, b))  # (홈, 원정)
        rounds.append(games)
        arr.insert(1, arr.pop())
    return rounds


def make_schedule(n_teams: int = 10, cycles: int = 16) -> list[list[tuple[int, int]]]:
    """반환: 날짜별 경기 리스트. games[day] = [(home_idx, away_idx), ...] 5경기."""
    base = round_robin(n_teams)
    days = []
    for c in range(cycles):
        for rnd in base:
            days.append([(a, h) if c % 2 else (h, a) for h, a in rnd])
    return days
