"""기록 모델 — 원시 카운트만 저장하고 지표(AVG/OPS/ERA 등)는 파생 프로퍼티로 계산한다.

경기 박스스코어와 시즌 누계가 같은 클래스를 쓰므로 (경기 종료 시 add로 합산)
두 기록이 어긋날 수 없다.
"""
from __future__ import annotations
from dataclasses import dataclass, fields


@dataclass
class BattingLine:
    pa: int = 0    # 타석
    ab: int = 0    # 타수
    h: int = 0     # 안타
    b2: int = 0    # 2루타
    b3: int = 0    # 3루타
    hr: int = 0    # 홈런
    bb: int = 0    # 볼넷
    hbp: int = 0   # 사구
    so: int = 0    # 삼진
    gdp: int = 0   # 병살타
    sf: int = 0    # 희생플라이
    sb: int = 0    # 도루
    cs: int = 0    # 도루자
    r: int = 0     # 득점
    rbi: int = 0   # 타점
    e: int = 0     # 실책 (수비 기록 — 편의상 타자 라인에 저장)

    def add(self, other: "BattingLine") -> None:
        for f in fields(self):
            setattr(self, f.name, getattr(self, f.name) + getattr(other, f.name))

    @property
    def singles(self) -> int:
        return self.h - self.b2 - self.b3 - self.hr

    @property
    def tb(self) -> int:  # 루타
        return self.singles + 2 * self.b2 + 3 * self.b3 + 4 * self.hr

    @property
    def avg(self) -> float:
        return self.h / self.ab if self.ab else 0.0

    @property
    def obp(self) -> float:
        d = self.ab + self.bb + self.hbp + self.sf
        return (self.h + self.bb + self.hbp) / d if d else 0.0

    @property
    def slg(self) -> float:
        return self.tb / self.ab if self.ab else 0.0

    @property
    def ops(self) -> float:
        return self.obp + self.slg


@dataclass
class PitchingLine:
    g: int = 0      # 등판
    gs: int = 0     # 선발
    w: int = 0
    l: int = 0
    sv: int = 0
    hld: int = 0
    outs: int = 0   # 아웃카운트 (IP*3)
    h: int = 0      # 피안타
    hr: int = 0     # 피홈런
    bb: int = 0
    hbp: int = 0
    so: int = 0
    r: int = 0      # 실점
    er: int = 0     # 자책 (실책 출루 주자·2사 후 실책 연장 이닝의 득점은 비자책)
    pitches: int = 0

    def add(self, other: "PitchingLine") -> None:
        for f in fields(self):
            setattr(self, f.name, getattr(self, f.name) + getattr(other, f.name))

    @property
    def ip(self) -> float:
        return self.outs / 3.0

    @property
    def ip_str(self) -> str:
        return f"{self.outs // 3}.{self.outs % 3}"

    @property
    def era(self) -> float:
        return self.er * 27.0 / self.outs if self.outs else 99.99

    @property
    def whip(self) -> float:
        return (self.h + self.bb) / self.ip if self.outs else 99.99

    @property
    def k9(self) -> float:
        return self.so * 27.0 / self.outs if self.outs else 0.0

    @property
    def bb9(self) -> float:
        return self.bb * 27.0 / self.outs if self.outs else 0.0
