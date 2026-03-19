from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path('login/', views.login_view, name='login'),
    path('login/skynet/', views.skynet_login_view, name='skynet_login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),

    path('', views.dashboard, name='dashboard'),
    path('learning/', views.learning_values, name='learning_values'),
    path('learning/history/', views.learning_history, name='learning_history'),
    path('simulation/', views.simulation, name='simulation'),
    path('apc/history/', views.apc_history, name='apc_history'),
    path('improvement/dispersion/', views.dispersion, name='dispersion'),
    path('setup/status/', views.setup_status, name='setup_status'),
    path('setup/history/', views.setup_history, name='setup_history'),

    # Category CRUD
    path('setup/category/', views.category_list, name='category_list'),
    path('setup/category/create/', views.category_create, name='category_create'),
    path('setup/category/<int:pk>/update/', views.category_update, name='category_update'),
    path('setup/category/<int:pk>/delete/', views.category_delete, name='category_delete'),
    path('setup/category/<int:pk>/copy/', views.category_copy, name='category_copy'),

    # SubCategory CRUD
    path('setup/subcategory/', views.subcategory_list, name='subcategory_list'),
    path('setup/subcategory/create/', views.subcategory_create, name='subcategory_create'),
    path('setup/subcategory/<int:pk>/update/', views.subcategory_update, name='subcategory_update'),
    path('setup/subcategory/<int:pk>/delete/', views.subcategory_delete, name='subcategory_delete'),
    path('setup/subcategory/<int:pk>/copy/', views.subcategory_copy, name='subcategory_copy'),

    # Recipe Grouping
    path('setup/recipe-group/', views.recipe_group_list, name='recipe_group_list'),
    path('setup/recipe-group/create/', views.recipe_group_create, name='recipe_group_create'),
    path('setup/recipe-group/<int:pk>/update/', views.recipe_group_update, name='recipe_group_update'),
    path('setup/recipe-group/<int:pk>/delete/', views.recipe_group_delete, name='recipe_group_delete'),

    # Detail CRUD
    path('setup/detail/', views.detail_list, name='detail_list'),
    path('setup/detail/create/', views.detail_create, name='detail_create'),
    path('setup/detail/<int:pk>/update/', views.detail_update, name='detail_update'),
    path('setup/detail/<int:pk>/delete/', views.detail_delete, name='detail_delete'),
    path('setup/detail/<int:pk>/copy/', views.detail_copy, name='detail_copy'),

    # 접속 현황 (superuser only)
    path('admin-stats/', views.access_stats, name='access_stats'),

    # VOC
    path('voc/', views.voc_list, name='voc_list'),
    path('voc/create/', views.voc_create, name='voc_create'),
    path('voc/<int:pk>/', views.voc_detail, name='voc_detail'),
    path('voc/<int:pk>/reply/', views.voc_reply, name='voc_reply'),
    path('voc/<int:pk>/delete/', views.voc_delete, name='voc_delete'),
]
