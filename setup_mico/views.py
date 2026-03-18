from django.shortcuts import render, redirect, get_object_or_404
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
    return {'product': obj.product, 'oper_id': obj.oper_id, 'oper_desc': obj.oper_desc}

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
        'rr_max': obj.rr_max, 'rr_period': obj.rr_period, 'if_rr': obj.if_rr,
    }

def _grp_fields(obj):
    return {
        'name': obj.name, 'category': str(obj.category),
        'subcategories': sorted([s.recipe_id for s in obj.subcategories.all()]),
    }

def _diff(before, after):
    return {
        k: {'before': before[k], 'after': after[k]}
        for k in before if str(before[k]) != str(after[k])
    }


# ── Auth ──

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    error = None
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return redirect(request.GET.get('next', 'dashboard'))
        error = '아이디 또는 비밀번호가 올바르지 않습니다.'
    return render(request, 'setup_mico/auth/login.html', {'error': error})


def logout_view(request):
    if request.method == 'POST':
        logout(request)
    return redirect('login')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = UserCreationForm()
    error = None
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard')
        error = form.errors
    return render(request, 'setup_mico/auth/register.html', {'form': form, 'error': error})


@login_required
def learning_values(request):
    import json
    categories = Category.objects.prefetch_related('subcategories__details').order_by('product', 'oper_id')

    # JS용 계층 데이터
    tree = []
    for cat in categories:
        subs = []
        for sub in cat.subcategories.all():
            details = []
            for d in sub.details.all():
                details.append({'pk': d.pk, 'label': f'{d.apc_para} / {d.thk_para}'})
            subs.append({
                'pk': sub.pk,
                'label': f'{sub.fab} / {sub.device} / {sub.recipe_id}',
                'details': details,
            })
        tree.append({
            'pk': cat.pk,
            'label': f'{cat.product} / {cat.oper_id}',
            'subs': subs,
        })

    return render(request, 'setup_mico/learning_values.html', {
        'tree_json': json.dumps(tree, ensure_ascii=False),
    })


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
                    'if_rr': d.if_rr,
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

    qs = SetupHistory.objects.select_related('user').order_by('-changed_at')

    model_type = request.GET.get('model', '')
    action     = request.GET.get('action', '')
    username   = request.GET.get('user', '')
    date_from  = request.GET.get('date_from', '')
    date_to    = request.GET.get('date_to', '')

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

    paginator = Paginator(qs, 30)
    page = paginator.get_page(request.GET.get('page', 1))

    users = User.objects.filter(setup_histories__isnull=False).distinct().order_by('username')

    return render(request, 'setup_mico/setup_history.html', {
        'page': page,
        'total': qs.count(),
        'users': users,
        'filter_model':  model_type,
        'filter_action': action,
        'filter_user':   username,
        'filter_from':   date_from,
        'filter_to':     date_to,
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
    context = {
        'category_count': Category.objects.count(),
        'subcategory_count': SubCategory.objects.count(),
        'detail_count': Detail.objects.count(),
    }
    return render(request, 'setup_mico/dashboard.html', context)


# ── Category ──

@login_required
def category_list(request):
    categories = Category.objects.all().order_by('-created_at')
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
            obj = form.save()
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
        original.save()
        fields['copied_from'] = str(pk)
        _record(request.user, 'create', 'Category', str(original), original.pk, fields)
    return redirect('category_list')


# ── SubCategory ──

@login_required
def subcategory_list(request):
    subcategories = SubCategory.objects.select_related('category').order_by('-created_at')
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
            obj = form.save()
            _record(request.user, 'create', 'SubCategory', str(obj), obj.pk, _sub_fields(obj))
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
                _record(request.user, 'update', 'SubCategory', str(obj), obj.pk, diff)
    return redirect('subcategory_list')


@login_required
def subcategory_delete(request, pk):
    if request.method == 'POST':
        obj = get_object_or_404(SubCategory, pk=pk)
        _record(request.user, 'delete', 'SubCategory', str(obj))
        obj.delete()
    return redirect('subcategory_list')


@login_required
def subcategory_copy(request, pk):
    if request.method == 'POST':
        original = get_object_or_404(SubCategory, pk=pk)
        details = list(original.details.all())
        form = SubCategoryForm(request.POST)
        if form.is_valid():
            new_sub = form.save()
            fields = _sub_fields(new_sub)
            fields['copied_from'] = str(pk)
            if request.POST.get('copy_details') == '1':
                for detail in details:
                    detail.pk = None
                    detail.subcategory = new_sub
                    detail.save()
                fields['detail_count'] = len(details)
            _record(request.user, 'create', 'SubCategory', str(new_sub), new_sub.pk, fields)
    return redirect('subcategory_list')


# ── Detail ──

@login_required
def detail_list(request):
    details = Detail.objects.select_related('subcategory__category').order_by('-created_at')
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
            obj = form.save()
            _record(request.user, 'create', 'Detail', str(obj), obj.pk, _det_fields(obj))
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
                _record(request.user, 'update', 'Detail', str(obj), obj.pk, diff)
    return redirect('detail_list')


@login_required
def detail_delete(request, pk):
    if request.method == 'POST':
        obj = get_object_or_404(Detail, pk=pk)
        _record(request.user, 'delete', 'Detail', str(obj))
        obj.delete()
    return redirect('detail_list')


@login_required
def detail_copy(request, pk):
    if request.method == 'POST':
        original = get_object_or_404(Detail, pk=pk)
        fields = _det_fields(original)
        fields['copied_from'] = str(pk)
        original.pk = None
        original.save()
        _record(request.user, 'create', 'Detail', str(original), original.pk, fields)
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
            'label': f'{cat.product} / {cat.oper_id}',
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
