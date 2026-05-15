class Cube_Connector:

    def __init__(self, bot_id, bot_token):
        self._bot_id = bot_id

    def sendMsg(self, *args, **kwargs):
        if args:
            print(f'  [Cube sendMsg] {args}')
