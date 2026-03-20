from django.contrib import admin
from .models import Category, SubCategory, Detail


class SubCategoryInline(admin.TabularInline):
    model = SubCategory
    extra = 1


class DetailInline(admin.TabularInline):
    model = Detail
    extra = 1


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['family', 'product', 'oper_id', 'oper_desc', 'created_at', 'updated_at']
    list_filter = ['family', 'product']
    inlines = [SubCategoryInline]


@admin.register(SubCategory)
class SubCategoryAdmin(admin.ModelAdmin):
    list_display = ['category', 'fab', 'device', 'recipe_id', 'maker', 'created_at', 'updated_at']
    list_filter = ['category']
    inlines = [DetailInline]


@admin.register(Detail)
class DetailAdmin(admin.ModelAdmin):
    list_display = ['subcategory', 'apc_para', 'thk_para', 'target', 'pre_target', 'pre_thk_period', 'rr_para', 'rr_period', 'if_rr', 'offset_group', 'rr_max', 'created_at', 'updated_at']
    list_filter = ['subcategory__category', 'subcategory']
