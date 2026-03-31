from django.contrib import admin
from .models import Category, SubCategory, Detail, SimulationLink


class SubCategoryInline(admin.TabularInline):
    model = SubCategory
    extra = 1


class DetailInline(admin.TabularInline):
    model = Detail
    extra = 1


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display  = ['family', 'product', 'oper_id', 'oper_desc', 'created_at', 'updated_at']
    list_filter   = ['family', 'product']
    search_fields = ['product', 'oper_id', 'oper_desc']
    inlines = [SubCategoryInline]


@admin.register(SubCategory)
class SubCategoryAdmin(admin.ModelAdmin):
    list_display = ['category', 'fab', 'device', 'recipe_id', 'maker', 'created_at', 'updated_at']
    list_filter = ['category']
    inlines = [DetailInline]


@admin.register(Detail)
class DetailAdmin(admin.ModelAdmin):
    list_display = ['subcategory', 'apc_para', 'thk_para', 'target', 'pre_target', 'pre_thk_period', 'rr_para', 'rr_period', 'rr_if', 'offset_group', 'rr_max', 'created_at', 'updated_at']
    list_filter = ['subcategory__category', 'subcategory']


@admin.register(SimulationLink)
class SimulationLinkAdmin(admin.ModelAdmin):
    list_display  = ['category', 'get_product', 'get_oper_desc', 'url', 'description', 'updated_at']
    list_filter   = ['category__product']
    search_fields = ['category__product', 'category__oper_desc', 'url']
    autocomplete_fields = ['category']

    def get_product(self, obj):
        return obj.category.product
    get_product.short_description = 'Product'
    get_product.admin_order_field = 'category__product'

    def get_oper_desc(self, obj):
        return obj.category.oper_desc
    get_oper_desc.short_description = 'Oper Desc'
    get_oper_desc.admin_order_field = 'category__oper_desc'
