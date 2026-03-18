class AccessLogMiddleware:
    """인증된 사용자의 페이지 접속을 AccessLog에 기록"""

    SKIP_PREFIXES = ('/static/', '/admin/', '/favicon')
    SKIP_EXTENSIONS = ('.css', '.js', '.png', '.jpg', '.ico', '.woff', '.woff2')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # 정적 파일 / Django admin / 비인증 사용자 스킵
        path = request.path
        if not request.user.is_authenticated:
            return response
        if any(path.startswith(p) for p in self.SKIP_PREFIXES):
            return response
        if any(path.endswith(ext) for ext in self.SKIP_EXTENSIONS):
            return response
        # POST 요청(CRUD 처리) 스킵 — 실질적 페이지 뷰만 기록
        if request.method != 'GET':
            return response
        # 리다이렉트 응답 스킵
        if response.status_code in (301, 302):
            return response

        from .models import AccessLog
        ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() \
             or request.META.get('REMOTE_ADDR')
        AccessLog.objects.create(
            user=request.user,
            path=path,
            ip_address=ip or None,
        )
        return response
