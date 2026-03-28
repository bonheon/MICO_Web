import requests
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from .models import Category, SubCategory, Detail, Voc, RecipeGroup, AccessLog, SetupHistory
from .forms import CategoryForm, SubCategoryForm, DetailForm, VocForm, VocReplyForm


# ── Setup History 헬퍼 ──────────────────────────────────────────────────────

def _record(user, action, model_type, obj_repr, obj_id=None, changes=None):
    SetupHistory.objects.create(
        action=action, model_type=model_type,
        object_id=obj_id, object_repr=obj_repr,
        user=user, changes=changes or {},
    )

def _cat_fields(obj):
    return {'product': obj.product, 'family': obj.family, 'oper_id': obj.oper_id, 'oper_desc': obj.oper_desc}

def _sub_fields(obj):
    return {'category': str(obj.category), 'fab': obj.fab,
            'device': obj.device, 'recipe_id': obj.recipe_id, 'maker': obj.maker}

def _det_fields(obj):
    return {
        'subcategory': str(obj.subcategory),
        'apc_para': obj.apc_para, 'thk_para': obj.thk_para,
        'target': obj.target, 'pre_target': obj.pre_target,
        'pre_thk_period': obj.pre_thk_period,
        'rr_para': obj.rr_para or '', 'offset_group': obj.offset_group or '',
        'rr_max': obj.rr_max, 'rr_period': obj.rr_period, 'rr_if': obj.rr_if,
        'pre_thk_para_itm': obj.pre_thk_para_itm or '',
        'pre_oper_code': obj.pre_oper_code or '', 'pre_oper_desc': obj.pre_oper_desc or '', 'pre_oper_para': obj.pre_oper_para or '',
        'pre_oper_code2': obj.pre_oper_code2 or '', 'pre_oper_desc2': obj.pre_oper_desc2 or '', 'pre_oper_para2': obj.pre_oper_para2 or '',
        'pre_oper_code3': obj.pre_oper_code3 or '', 'pre_oper_desc3': obj.pre_oper_desc3 or '', 'pre_oper_para3': obj.pre_oper_para3 or '',
        'pre_oper_code4': obj.pre_oper_code4 or '', 'pre_oper_desc4': obj.pre_oper_desc4 or '', 'pre_oper_para4': obj.pre_oper_para4 or '',
        'rr_weight': obj.rr_weight, 'rr_count': obj.rr_count,
    }

def _grp_fields(obj):
    return {
        'name': obj.name, 'category': str(obj.category),
        'subcategories': sorted([s.recipe_id for s in obj.subcategories.all()]),
    }

def _sub_repr(obj):
    """SubCategory 전체 경로: Category > SubCategory"""
    return f'{obj.category} > {obj}'

def _det_repr(obj):
    """Detail 전체 경로: Category > SubCategory > apc_para / thk_para"""
    return f'{obj.subcategory.category} > {obj.subcategory} > {obj.apc_para} / {obj.thk_para}'

def _diff(before, after):
    return {
        k: {'before': before[k], 'after': after[k]}
        for k in before if str(before[k]) != str(after[k])
    }


# ── Auth ──

def _get_user_info_from_workplace(request):
    """
    SK Hynix Workplace SSO 쿠키로 사용자 정보 조회.
    SMOFC 쿠키가 없거나 'LOGOUT' 이거나 API 호출 실패 시 None 반환.
    """
    smofc = request.COOKIES.get('SMOFC', 'LOGOUT')
    lastuser = request.COOKIES.get('LASTUSER', 'LOGOUT')

    if smofc == 'LOGOUT' or lastuser == 'LOGOUT':
        return None

    smsession = request.COOKIES.get('SMSESSION', 'LOGOUT')
    cookies = {
        'SMOFC': smofc,
        'SMSESSION': smsession,
        'LASTUSER': lastuser,
    }

    try:
        url = f'https://workplace.skhynix.com/api/common/v1/account/userInfo/{lastuser}'
        response = requests.get(url, cookies=cookies, timeout=5)
        if not response.ok:
            return None
        data = response.json().get('data', {})
        return {
            'username': lastuser,
            'name': data.get('empNm', ''),       # API 응답 필드명 확인 후 수정
            'email': data.get('email', ''),
            'department': data.get('deptNm', ''),
        }
    except Exception:
        return None


def _login_user_from_workplace(request, user_info):
    """Workplace 사용자 정보로 Django 유저 생성/갱신 후 로그인."""
    employee_id = user_info['username']
    user, created = User.objects.get_or_create(username=employee_id)
    user.first_name = user_info.get('name', '')
    user.email = user_info.get('email', '')
    if created:
        user.set_unusable_password()
    user.save()
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    return user


def login_view(request):
    """
    진입점: Workplace SSO 쿠키(SMOFC)가 있으면 자동 로그인, 없으면 로그인 안내 화면으로 이동.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')

    user_info = _get_user_info_from_workplace(request)
    if user_info:
        _login_user_from_workplace(request, user_info)
        return redirect(request.GET.get('next', 'dashboard'))

    # SSO 쿠키 없음 → Workplace 로그인 안내 화면
    next_url = request.GET.get('next', '')
    return redirect(f'/login/skynet/?next={next_url}' if next_url else '/login/skynet/')


def logout_view(request):
    if request.method == 'POST':
        logout(request)
    return redirect('skynet_login')


def register_view(request):
    # staff 전용: 비로그인 또는 일반 사용자는 접근 불가
    if not request.user.is_authenticated:
        return redirect('login')
    if not request.user.is_staff:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('관리자만 계정을 생성할 수 있습니다.')
    form = UserCreationForm()
    error = None
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('dashboard')
        error = form.errors
    return render(request, 'setup_mico/auth/register.html', {'form': form, 'error': error})


def skynet_login_view(request):
    """
    일반 구성원: Skynet 로그인 안내 화면 (API Key는 Skynet 쿠키에서 자동 수신).
    관리자: ID/PW 로그인 폼 (접힌 상태).
    """
    if request.user.is_authenticated:
        return redirect('dashboard')

    error = None

    if request.method == 'POST' and request.POST.get('login_type') == 'admin':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return redirect(request.GET.get('next', 'dashboard'))
        error = '아이디 또는 비밀번호가 올바르지 않습니다.'

    return render(request, 'setup_mico/auth/skynet_login.html', {'error': error})


@login_required
def learning_values(request):
    """
    Device / Oper Desc / FAB 드롭다운 옵션 제공.
    샘플 데이터 파일에서 가용 컬렉션 목록을 파싱해 cascading 옵션을 생성.
    """
    import json, os

    # ── 샘플 데이터에서 옵션 파싱 ─────────────────────────────────────────
    sample_path = os.path.join(os.path.dirname(__file__), 'sample_data', 'pre_thk_sample.json')
    with open(sample_path, 'r', encoding='utf-8') as f:
        sample_collections = json.load(f)

    # Collection명 → (device, oper_desc, fab) 파싱
    # 형식: MICO_PRE_THK_{device}_{oper_desc}_{fab}_Period
    PREFIX, SUFFIX = 'MICO_PRE_THK_', '_Period'
    options = []
    for col_name in sample_collections:
        inner = col_name[len(PREFIX):-len(SUFFIX)]   # "E2_SN BPSG CMP_M14"
        parts = inner.split('_')                      # ['E2', 'SN BPSG CMP', 'M14']
        if len(parts) < 3:
            continue
        options.append({
            'device'   : parts[0],
            'oper_desc': '_'.join(parts[1:-1]),       # 중간 전체 (언더스코어 포함 복원)
            'fab'      : parts[-1],
        })
    # ─────────────────────────────────────────────────────────────────────

    # ── 사내 MongoDB 사용 시: 위 파싱 대신 MongoDB 컬렉션 목록 조회
    # from pymongo import MongoClient
    # MONGO_URI = 'mongodb://TODO_HOST:TODO_PORT'
    # MONGO_DB  = 'TODO_DB_NAME'
    # client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    # col_names = client[MONGO_DB].list_collection_names()
    # client.close()
    # options = []
    # for col_name in col_names:
    #     if not (col_name.startswith(PREFIX) and col_name.endswith(SUFFIX)):
    #         continue
    #     inner = col_name[len(PREFIX):-len(SUFFIX)]
    #     parts = inner.split('_')
    #     if len(parts) < 3:
    #         continue
    #     options.append({'device': parts[0], 'oper_desc': '_'.join(parts[1:-1]), 'fab': parts[-1]})
    # ─────────────────────────────────────────────────────────────────────

    # Cascading 구조: {device: {oper_desc: [fab, ...]}}
    cascade = {}
    for o in options:
        cascade.setdefault(o['device'], {}).setdefault(o['oper_desc'], []).append(o['fab'])

    return render(request, 'setup_mico/learning_values.html', {
        'cascade_json': json.dumps(cascade, ensure_ascii=False),
    })


@login_required
def learning_values_data(request):
    """
    Pre_Thk 학습값 조회.
    Collection명: MICO_PRE_THK_{device}_{oper_desc}_{fab}_Period

    [현재] 로컬 샘플 파일(sample_data/pre_thk_sample.json) 사용
    [사내] 아래 MongoDB 블록 주석 해제 후 위 샘플 블록 주석 처리
    """
    import os, json

    device    = request.GET.get('device', '').strip()
    oper_desc = request.GET.get('oper_desc', '').strip()
    fab       = request.GET.get('fab', '').strip()

    if not all([device, oper_desc, fab]):
        return JsonResponse({'error': 'device / oper_desc / fab 파라미터가 필요합니다'}, status=400)

    collection_name = f"MICO_PRE_THK_{device}_{oper_desc}_{fab}_Period"

    # ════════════════════════════════════════════════════════════════════
    # [개발] 샘플 데이터 파일 사용
    # ════════════════════════════════════════════════════════════════════
    sample_path = os.path.join(os.path.dirname(__file__), 'sample_data', 'pre_thk_sample.json')
    try:
        with open(sample_path, 'r', encoding='utf-8') as f:
            sample = json.load(f)
        data = sample.get(collection_name, [])
    except FileNotFoundError:
        return JsonResponse({'error': '샘플 데이터 파일을 찾을 수 없습니다'}, status=500)

    return JsonResponse({'collection': collection_name, 'data': data})

    # ════════════════════════════════════════════════════════════════════
    # [사내] MongoDB 연결 시 위 블록 대신 아래 사용 (pip install pymongo)
    # ════════════════════════════════════════════════════════════════════
    # from pymongo import MongoClient
    #
    # MONGO_URI = 'mongodb://TODO_HOST:TODO_PORT'   # ← 실제 접속 정보 입력
    # MONGO_DB  = 'TODO_DB_NAME'                    # ← 실제 DB명 입력
    #
    # try:
    #     client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    #     db  = client[MONGO_DB]
    #     col = db[collection_name]
    #     docs = list(col.find({}, {'_id': 0}).sort('Date', 1))
    #     client.close()
    # except Exception as e:
    #     return JsonResponse({'error': f'DB 연결 오류: {str(e)}'}, status=500)
    #
    # def serialize(doc):
    #     return {k: (v.isoformat() if hasattr(v, 'isoformat') else v) for k, v in doc.items()}
    #
    # return JsonResponse({'collection': collection_name, 'data': [serialize(d) for d in docs]})


@login_required
def learning_rr_data(request):
    """
    Removal Rate 학습값 조회.
    Collection명: MICO_Removal_Rate_{device}_{oper_desc}_{fab}

    [현재] 로컬 샘플 파일(sample_data/rr_sample.json) 사용
    [사내] 아래 MongoDB 블록 주석 해제 후 위 샘플 블록 주석 처리
    """
    import os, json

    device    = request.GET.get('device', '').strip()
    oper_desc = request.GET.get('oper_desc', '').strip()
    fab       = request.GET.get('fab', '').strip()

    if not all([device, oper_desc, fab]):
        return JsonResponse({'error': 'device / oper_desc / fab 파라미터가 필요합니다'}, status=400)

    collection_name = f"MICO_Removal_Rate_{device}_{oper_desc}_{fab}"

    # ════════════════════════════════════════════════════════════════════
    # [개발] 샘플 데이터 파일 사용
    # ════════════════════════════════════════════════════════════════════
    sample_path = os.path.join(os.path.dirname(__file__), 'sample_data', 'rr_sample.json')
    try:
        with open(sample_path, 'r', encoding='utf-8') as f:
            sample = json.load(f)
        data = sample.get(collection_name, [])
    except FileNotFoundError:
        return JsonResponse({'error': '샘플 데이터 파일을 찾을 수 없습니다'}, status=500)

    # Recipe_ID 목록 추출
    recipe_ids = sorted(set(d['Recipe_ID'] for d in data if 'Recipe_ID' in d))

    return JsonResponse({'collection': collection_name, 'data': data, 'recipe_ids': recipe_ids})

    # ════════════════════════════════════════════════════════════════════
    # [사내] MongoDB 연결 시 위 블록 대신 아래 사용 (pip install pymongo)
    # ════════════════════════════════════════════════════════════════════
    # from pymongo import MongoClient
    #
    # MONGO_URI = 'mongodb://TODO_HOST:TODO_PORT'   # ← 실제 접속 정보 입력
    # MONGO_DB  = 'TODO_DB_NAME'                    # ← 실제 DB명 입력
    #
    # try:
    #     client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    #     db  = client[MONGO_DB]
    #     col = db[collection_name]
    #     docs = list(col.find({}, {'_id': 0}).sort('Date', 1))
    #     client.close()
    # except Exception as e:
    #     return JsonResponse({'error': f'DB 연결 오류: {str(e)}'}, status=500)
    #
    # def serialize(doc):
    #     return {k: (v.isoformat() if hasattr(v, 'isoformat') else v) for k, v in doc.items()}
    #
    # recipe_ids = sorted(set(d['Recipe_ID'] for d in docs if 'Recipe_ID' in d))
    # return JsonResponse({'collection': collection_name, 'data': [serialize(d) for d in docs], 'recipe_ids': recipe_ids})


@login_required
def learning_history(request):
    import json

    lot_id  = request.GET.get('lot_id', '').strip()
    wafer_id = request.GET.get('wafer_id', '').strip()
    process  = request.GET.get('process', '').strip()

    queried = any([lot_id, wafer_id, process])

    # ── 외부 DB 연동 시 이 블록을 교체 ──────────────────────────────
    # 실제 조회 결과 rows를 리스트로 반환
    # 예시 row 형식:
    # { 'timestamp': '2026-03-17 14:23', 'lot_id': 'LOT001', 'wafer_id': 'W01',
    #   'oper_id': 'A908740A', 'recipe_id': 'R03_AB', 'apc_para': 'PB_04_TIME',
    #   'thk_para': 'EBARA_ITM_POST_THK1_AVG', 'pre_thk': 3012, 'target': 3000,
    #   'apc_input': 95.2, 'apc_result': 94.8, 'modified': True }
    rows = []
    # ────────────────────────────────────────────────────────────────

    return render(request, 'setup_mico/learning_history.html', {
        'queried':  queried,
        'lot_id':   lot_id,
        'wafer_id': wafer_id,
        'process':  process,
        'rows':     rows,
    })


@login_required
def simulation(request):
    import json
    categories = Category.objects.prefetch_related('subcategories__details').order_by('product', 'oper_id')

    tree = []
    for cat in categories:
        subs = []
        for sub in cat.subcategories.all():
            details = []
            for d in sub.details.all():
                details.append({
                    'pk': d.pk,
                    'label': f'{d.apc_para} / {d.thk_para}',
                    'apc_para': d.apc_para,
                    'thk_para': d.thk_para,
                    'target': d.target,
                    'pre_target': d.pre_target,
                    'pre_thk_period': d.pre_thk_period,
                    'rr_para': d.rr_para or '',
                    'rr_max': d.rr_max,
                    'rr_period': d.rr_period,
                    'rr_if': d.rr_if,
                    'offset_group': d.offset_group or '',
                })
            subs.append({
                'pk': sub.pk,
                'label': f'{sub.fab} / {sub.device} / {sub.recipe_id}',
                'fab': sub.fab,
                'device': sub.device,
                'recipe_id': sub.recipe_id,
                'maker': sub.maker,
                'details': details,
            })
        tree.append({
            'pk': cat.pk,
            'label': f'{cat.product} / {cat.oper_id}',
            'product': cat.product,
            'oper_id': cat.oper_id,
            'subs': subs,
        })

    return render(request, 'setup_mico/simulation.html', {
        'tree_json': json.dumps(tree, ensure_ascii=False),
    })


@login_required
def setup_history(request):
    from django.core.paginator import Paginator

    from django.db.models import Q

    qs = SetupHistory.objects.select_related('user').order_by('-changed_at')

    model_type = request.GET.get('model', '')
    action     = request.GET.get('action', '')
    username   = request.GET.get('user', '')
    date_from  = request.GET.get('date_from', '')
    date_to    = request.GET.get('date_to', '')
    product_q  = request.GET.get('product', '')
    oper_id_q  = request.GET.get('oper_id', '')
    oper_desc_q = request.GET.get('oper_desc', '')

    if model_type:
        qs = qs.filter(model_type=model_type)
    if action:
        qs = qs.filter(action=action)
    if username:
        qs = qs.filter(user__username__icontains=username)
    if date_from:
        qs = qs.filter(changed_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(changed_at__date__lte=date_to)
    if product_q:
        # object_repr에 Category prefix 포함 → 전 계층 검색
        qs = qs.filter(object_repr__icontains=product_q)
    if oper_id_q:
        qs = qs.filter(object_repr__icontains=oper_id_q)
    if oper_desc_q:
        # 현존하는 Category에서 oper_desc 검색 → 하위 계층 이력까지 포함
        matched_cats = Category.objects.filter(oper_desc__icontains=oper_desc_q)
        cat_q = Q()
        for cat in matched_cats:
            cat_prefix = str(cat)  # "product / oper_id / oper_desc"
            cat_q |= Q(object_repr__istartswith=cat_prefix)
        # Category 이력: object_repr에 oper_desc 포함(삭제된 경우 포함) + changes JSONField
        cat_q |= Q(model_type='Category') & Q(object_repr__icontains=oper_desc_q)
        cat_q |= Q(
            model_type='Category'
        ) & (
            Q(changes__oper_desc__icontains=oper_desc_q) |
            Q(changes__oper_desc__before__icontains=oper_desc_q) |
            Q(changes__oper_desc__after__icontains=oper_desc_q)
        )
        qs = qs.filter(cat_q)

    paginator = Paginator(qs, 30)
    page = paginator.get_page(request.GET.get('page', 1))

    users = User.objects.filter(setup_histories__isnull=False).distinct().order_by('username')

    return render(request, 'setup_mico/setup_history.html', {
        'page': page,
        'total': qs.count(),
        'users': users,
        'filter_model':   model_type,
        'filter_action':  action,
        'filter_user':    username,
        'filter_from':    date_from,
        'filter_to':      date_to,
        'filter_product':  product_q,
        'filter_oper_id':  oper_id_q,
        'filter_oper_desc': oper_desc_q,
        'model_choices': SetupHistory.MODEL_CHOICES,
    })


@login_required
def setup_status(request):
    categories = Category.objects.prefetch_related(
        'subcategories__details'
    ).annotate(
        detail_count=Count('subcategories__details')
    ).order_by('product', 'oper_id')
    return render(request, 'setup_mico/setup_status.html', {'categories': categories})


@login_required
def dashboard(request):
    import json

    # 상단 요약 카드
    category_count = Category.objects.count()
    subcategory_count = SubCategory.objects.count()
    detail_count = Detail.objects.count()

    # Product별 공정(Category) 수 + family 정보 → bar chart
    product_counts = (
        Category.objects.values('product', 'family')
        .annotate(count=Count('id'))
        .order_by('family', 'product')
    )
    bar_labels = [r['product'] for r in product_counts]
    bar_data = [r['count'] for r in product_counts]
    bar_families = [r['family'] for r in product_counts]

    # Category별 상세 현황 → 클릭 시 테이블
    # total_equip / applied_equip: 사내 DB 연동 후 채울 예정, 현재 0으로 초기화
    categories = Category.objects.order_by('family', 'product', 'oper_id')
    category_table = []
    for cat in categories:
        total_equip = 0    # TODO: 사내 DB 연동 후 실제 전체 장비 대수로 교체
        applied_equip = 0  # TODO: 사내 DB 연동 후 실제 적용 대수로 교체
        applied_rate = round(applied_equip / total_equip * 100) if total_equip else 0
        category_table.append({
            'product': cat.product,
            'family': cat.family,
            'oper_id': cat.oper_id,
            'oper_desc': cat.oper_desc,
            'total_equip': total_equip,
            'applied_equip': applied_equip,
            'applied_rate': applied_rate,
        })

    context = {
        'category_count': category_count,
        'subcategory_count': subcategory_count,
        'detail_count': detail_count,
        'bar_labels_json': json.dumps(bar_labels, ensure_ascii=False),
        'bar_data_json': json.dumps(bar_data),
        'bar_families_json': json.dumps(bar_families, ensure_ascii=False),
        'category_table_json': json.dumps(category_table, ensure_ascii=False),
    }
    return render(request, 'setup_mico/dashboard.html', context)


# ── Category ──

@login_required
def category_list(request):
    categories = Category.objects.select_related('created_by').order_by('-created_at')
    form = CategoryForm()
    return render(request, 'setup_mico/category_list.html', {
        'categories': categories,
        'form': form,
    })


@login_required
def category_create(request):
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by = request.user
            obj.save()
            _record(request.user, 'create', 'Category', str(obj), obj.pk, _cat_fields(obj))
    return redirect('category_list')


@login_required
def category_update(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if request.method == 'POST':
        old = _cat_fields(category)
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            obj = form.save()
            diff = _diff(old, _cat_fields(obj))
            if diff:
                _record(request.user, 'update', 'Category', str(obj), obj.pk, diff)
    return redirect('category_list')


@login_required
def category_delete(request, pk):
    if request.method == 'POST':
        obj = get_object_or_404(Category, pk=pk)
        _record(request.user, 'delete', 'Category', str(obj))
        obj.delete()
    return redirect('category_list')


@login_required
def category_copy(request, pk):
    if request.method == 'POST':
        original = get_object_or_404(Category, pk=pk)
        fields = _cat_fields(original)
        original.pk = None
        original.created_by = request.user
        original.save()
        fields['copied_from'] = str(pk)
        _record(request.user, 'create', 'Category', str(original), original.pk, fields)
    return redirect('category_list')


# ── SubCategory ──

@login_required
def subcategory_list(request):
    subcategories = SubCategory.objects.select_related('category', 'created_by').order_by('-created_at')
    form = SubCategoryForm()
    return render(request, 'setup_mico/subcategory_list.html', {
        'subcategories': subcategories,
        'form': form,
    })


@login_required
def subcategory_create(request):
    if request.method == 'POST':
        form = SubCategoryForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by = request.user
            obj.save()
            _record(request.user, 'create', 'SubCategory', _sub_repr(obj), obj.pk, _sub_fields(obj))
    return redirect('subcategory_list')


@login_required
def subcategory_update(request, pk):
    subcategory = get_object_or_404(SubCategory, pk=pk)
    if request.method == 'POST':
        old = _sub_fields(subcategory)
        form = SubCategoryForm(request.POST, instance=subcategory)
        if form.is_valid():
            obj = form.save()
            diff = _diff(old, _sub_fields(obj))
            if diff:
                _record(request.user, 'update', 'SubCategory', _sub_repr(obj), obj.pk, diff)
    return redirect('subcategory_list')


@login_required
def subcategory_delete(request, pk):
    if request.method == 'POST':
        obj = get_object_or_404(SubCategory.objects.select_related('category'), pk=pk)
        _record(request.user, 'delete', 'SubCategory', _sub_repr(obj))
        obj.delete()
    return redirect('subcategory_list')


@login_required
def subcategory_copy(request, pk):
    if request.method == 'POST':
        original = get_object_or_404(SubCategory, pk=pk)
        details = list(original.details.all())
        form = SubCategoryForm(request.POST)
        if form.is_valid():
            new_sub = form.save(commit=False)
            new_sub.created_by = request.user
            new_sub.save()
            fields = _sub_fields(new_sub)
            fields['copied_from'] = str(pk)
            if request.POST.get('copy_details') == '1':
                for detail in details:
                    detail.pk = None
                    detail.subcategory = new_sub
                    detail.save()
                fields['detail_count'] = len(details)
            _record(request.user, 'create', 'SubCategory', _sub_repr(new_sub), new_sub.pk, fields)
    return redirect('subcategory_list')


# ── Detail ──

@login_required
def detail_list(request):
    details = Detail.objects.select_related('subcategory__category', 'created_by').order_by('-created_at')
    form = DetailForm()
    return render(request, 'setup_mico/detail_list.html', {
        'details': details,
        'form': form,
    })


@login_required
def detail_create(request):
    if request.method == 'POST':
        form = DetailForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by = request.user
            obj.save()
            _record(request.user, 'create', 'Detail', _det_repr(obj), obj.pk, _det_fields(obj))
    return redirect('detail_list')


@login_required
def detail_update(request, pk):
    detail = get_object_or_404(Detail, pk=pk)
    if request.method == 'POST':
        old = _det_fields(detail)
        form = DetailForm(request.POST, instance=detail)
        if form.is_valid():
            obj = form.save()
            diff = _diff(old, _det_fields(obj))
            if diff:
                _record(request.user, 'update', 'Detail', _det_repr(obj), obj.pk, diff)
    return redirect('detail_list')


@login_required
def detail_delete(request, pk):
    if request.method == 'POST':
        obj = get_object_or_404(Detail.objects.select_related('subcategory__category'), pk=pk)
        _record(request.user, 'delete', 'Detail', _det_repr(obj))
        obj.delete()
    return redirect('detail_list')


@login_required
def detail_copy(request, pk):
    if request.method == 'POST':
        original = get_object_or_404(Detail.objects.select_related('subcategory__category'), pk=pk)
        fields = _det_fields(original)
        fields['copied_from'] = str(pk)
        original.pk = None
        original.created_by = request.user
        original.save()
        _record(request.user, 'create', 'Detail', _det_repr(original), original.pk, fields)
    return redirect('detail_list')


# ── Recipe Grouping ──

@login_required
def recipe_group_list(request):
    import json
    categories = Category.objects.prefetch_related(
        'subcategories',
        'recipe_groups__subcategories'
    ).order_by('product', 'oper_id')

    # 모달용 트리 데이터
    tree = []
    for cat in categories:
        tree.append({
            'pk': cat.pk,
            'label': f'{cat.product} / {cat.oper_id}' + (f' / {cat.oper_desc}' if cat.oper_desc else ''),
            'subs': [
                {'pk': s.pk, 'label': f'{s.recipe_id}  ({s.fab} / {s.device})'}
                for s in cat.subcategories.all()
            ],
        })

    groups = RecipeGroup.objects.select_related('category').prefetch_related('subcategories')
    return render(request, 'setup_mico/recipe_group.html', {
        'categories': categories,
        'groups': groups,
        'tree_json': json.dumps(tree, ensure_ascii=False),
    })


@login_required
def recipe_group_create(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        cat_pk = request.POST.get('category')
        sub_pks = request.POST.getlist('subcategories')
        if name and cat_pk:
            cat = get_object_or_404(Category, pk=cat_pk)
            group = RecipeGroup.objects.create(category=cat, name=name)
            group.subcategories.set(SubCategory.objects.filter(pk__in=sub_pks, category=cat))
            _record(request.user, 'create', 'RecipeGroup', str(group), group.pk, _grp_fields(group))
    return redirect('recipe_group_list')


@login_required
def recipe_group_update(request, pk):
    group = get_object_or_404(RecipeGroup, pk=pk)
    if request.method == 'POST':
        old = _grp_fields(group)
        name = request.POST.get('name', '').strip()
        sub_pks = request.POST.getlist('subcategories')
        if name:
            group.name = name
            group.save()
            group.subcategories.set(
                SubCategory.objects.filter(pk__in=sub_pks, category=group.category)
            )
            diff = _diff(old, _grp_fields(group))
            if diff:
                _record(request.user, 'update', 'RecipeGroup', str(group), group.pk, diff)
    return redirect('recipe_group_list')


@login_required
def recipe_group_delete(request, pk):
    if request.method == 'POST':
        group = get_object_or_404(RecipeGroup, pk=pk)
        _record(request.user, 'delete', 'RecipeGroup', str(group))
        group.delete()
    return redirect('recipe_group_list')


# ── APC 수정건수 ──

@login_required
def apc_history(request):
    import json

    product = request.GET.get('product', '').strip()
    device  = request.GET.get('device', '').strip()
    process = request.GET.get('process', '').strip()

    queried = any([product, device, process])

    # ── 외부 DB 연동 시 이 블록을 교체 ──────────────────────────────
    # dropdown 선택지: DB 연동 후 실제 unique 값 목록으로 교체
    # 예시:
    #   product_list = list(db.execute("SELECT DISTINCT product FROM apc_table").fetchall())
    product_list = []
    device_list  = []
    process_list = []

    # 차트 데이터: DB 연동 후 실제 쿼리 결과로 교체
    # chart_data 형식:
    #   { "labels": ["Jan",...], "datasets": [{"label":"수정건수","data":[12,...]}] }
    chart_data = None
    # ────────────────────────────────────────────────────────────────

    return render(request, 'setup_mico/apc_history.html', {
        'queried':      queried,
        'product':      product,
        'device':       device,
        'process':      process,
        'product_list': product_list,
        'device_list':  device_list,
        'process_list': process_list,
        'chart_json':   json.dumps(chart_data, ensure_ascii=False),
    })


# ── 산포 개선 현황 ──

@login_required
def dispersion(request):
    import json

    product = request.GET.get('product', '').strip()
    device  = request.GET.get('device', '').strip()
    process = request.GET.get('process', '').strip()

    queried = any([product, device, process])

    # ── 외부 DB 연동 시 이 블록을 교체 ──────────────────────────────
    # dropdown 선택지: DB 연동 후 실제 unique 값 목록으로 교체
    product_list = []
    device_list  = []
    process_list = []

    # 차트 데이터: DB 연동 후 실제 쿼리 결과로 교체
    # chart_data 형식:
    #   { "labels": ["공정1",...],
    #     "before": [sigma_before,...],
    #     "after":  [sigma_after,...] }
    chart_data = None
    # ────────────────────────────────────────────────────────────────

    return render(request, 'setup_mico/dispersion.html', {
        'queried':      queried,
        'product':      product,
        'device':       device,
        'process':      process,
        'product_list': product_list,
        'device_list':  device_list,
        'process_list': process_list,
        'chart_json':   json.dumps(chart_data, ensure_ascii=False),
    })


# ── VOC ──

@login_required
def voc_list(request):
    vocs = Voc.objects.select_related('author').all()
    form = VocForm()
    return render(request, 'setup_mico/voc_list.html', {'vocs': vocs, 'form': form})


@login_required
def voc_create(request):
    if request.method == 'POST':
        form = VocForm(request.POST)
        if form.is_valid():
            voc = form.save(commit=False)
            voc.author = request.user
            voc.save()
    return redirect('voc_list')


@login_required
def voc_detail(request, pk):
    voc = get_object_or_404(Voc, pk=pk)
    reply_form = VocReplyForm(instance=voc)
    return render(request, 'setup_mico/voc_detail.html', {'voc': voc, 'reply_form': reply_form})


@login_required
def voc_reply(request, pk):
    if not request.user.is_staff:
        return redirect('voc_detail', pk=pk)
    voc = get_object_or_404(Voc, pk=pk)
    if request.method == 'POST':
        form = VocReplyForm(request.POST, instance=voc)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.replied_by = request.user
            obj.replied_at = timezone.now()
            obj.save()
    return redirect('voc_detail', pk=pk)


@login_required
def voc_delete(request, pk):
    voc = get_object_or_404(Voc, pk=pk)
    if request.method == 'POST':
        if request.user == voc.author or request.user.is_staff:
            voc.delete()
    return redirect('voc_list')


# ── 접속 현황 (superuser only) ──

@login_required
def access_stats(request):
    import json
    if not request.user.is_superuser:
        return redirect('dashboard')

    today = timezone.localdate()
    thirty_days_ago = today - timedelta(days=29)

    # 오늘 접속 횟수
    today_count = AccessLog.objects.filter(
        accessed_at__date=today
    ).count()

    # 오늘 접속자 수 (unique user)
    today_users = AccessLog.objects.filter(
        accessed_at__date=today
    ).values('user').distinct().count()

    # 누적 접속 횟수
    total_count = AccessLog.objects.count()

    # 전체 가입 회원 수
    total_users = User.objects.count()

    # 최근 30일 일별 접속 횟수
    daily_qs = (
        AccessLog.objects
        .filter(accessed_at__date__gte=thirty_days_ago)
        .annotate(date=TruncDate('accessed_at'))
        .values('date')
        .annotate(cnt=Count('id'))
        .order_by('date')
    )
    # 날짜 빈칸 채우기
    daily_map = {row['date']: row['cnt'] for row in daily_qs}
    daily_labels = []
    daily_data = []
    for i in range(30):
        d = thirty_days_ago + timedelta(days=i)
        daily_labels.append(d.strftime('%m/%d'))
        daily_data.append(daily_map.get(d, 0))

    # 사용자별 접속 통계
    user_stats = (
        AccessLog.objects
        .values('user__username')
        .annotate(total=Count('id'))
        .order_by('-total')
    )

    # 최근 접속 로그 50건
    recent_logs = (
        AccessLog.objects
        .select_related('user')
        .order_by('-accessed_at')[:50]
    )

    # 페이지별 인기 Top10
    top_pages = (
        AccessLog.objects
        .values('path')
        .annotate(cnt=Count('id'))
        .order_by('-cnt')[:10]
    )

    return render(request, 'setup_mico/access_stats.html', {
        'today_count': today_count,
        'today_users': today_users,
        'total_count': total_count,
        'total_users': total_users,
        'daily_labels_json': json.dumps(daily_labels),
        'daily_data_json': json.dumps(daily_data),
        'user_stats': user_stats,
        'recent_logs': recent_logs,
        'top_pages': top_pages,
    })



# ── Error handlers ──────────────────────────────────────────────────────────

def error_400(request, exception=None):
    return render(request, 'errors/400.html', status=400)

def error_403(request, exception=None):
    return render(request, 'errors/403.html', status=403)

def error_404(request, exception=None):
    return render(request, 'errors/404.html', status=404)

def error_500(request):
    return render(request, 'errors/500.html', status=500)
