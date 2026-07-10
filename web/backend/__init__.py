"""웹 백엔드 초기화.

웹 실시간 경기에서만 경기 중 야수 교체 확장을 활성화한다. 콘솔·검증 하네스의
기본 GameSimulator 자동 진행 경로는 원본 클래스를 그대로 사용할 수 있다.
"""
from kbo.engine.substitution_patch import apply_substitution_patch

apply_substitution_patch()
