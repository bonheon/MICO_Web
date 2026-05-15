# [TEST 삭제] 이 파일 전체 삭제 대상 — day/ 패키지 전체(day/__init__.py, day/auth/, day/commc/) 삭제.
# 회사 실서버에는 실제 day.auth.sdk 패키지가 설치되어 있으므로 이 Mock 디렉터리 불필요.

def logon(*args, **kwargs):
    """Cube/Day SSO 로그인 Mock."""
    return True
