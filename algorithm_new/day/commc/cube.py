# [TEST 삭제] 이 파일 전체 삭제 대상 — day/ 패키지 전체 삭제.

class Cube_Connector:
    """Cube 메시징 시스템 커넥터 Mock."""

    def __init__(self, bot_id, bot_token):
        self._bot_id = bot_id

    def sendMsg(self, *args, **kwargs):
        if args and len(args) >= 3:
            print(f'  [Cube] {args[2]}')
