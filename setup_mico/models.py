from django.db import models
from django.contrib.auth.models import User


class Category(models.Model):
    FAMILY_CHOICES = [('NAND', 'NAND'), ('DRAM', 'DRAM')]

    product = models.CharField(max_length=100, verbose_name='제품명', default='')
    family = models.CharField(max_length=10, choices=FAMILY_CHOICES, verbose_name='Family', default='')
    oper_id = models.CharField(max_length=100, verbose_name='공정 ID', default='')
    oper_desc = models.CharField(max_length=100, verbose_name='공정 설명', default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Category'
        verbose_name_plural = 'Categories'

    def __str__(self):
        if self.oper_desc:
            return f'{self.product} / {self.oper_id} / {self.oper_desc}'
        return f'{self.product} / {self.oper_id}'


class SubCategory(models.Model):
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name='subcategories',
        verbose_name='카테고리'
    )
    fab = models.CharField(max_length=100, verbose_name='FAB', default='')
    device = models.CharField(max_length=100, verbose_name='Device', default='')
    recipe_id = models.CharField(max_length=100, verbose_name='Recipe ID', default='')
    maker = models.CharField(max_length=100, verbose_name='Maker', default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'SubCategory'
        verbose_name_plural = 'SubCategories'

    def __str__(self):
        return f'{self.fab} / {self.device} / {self.recipe_id}'


class Detail(models.Model):
    RR_PARA_CHOICES = [
        ('pad', 'Pad'),
        ('disk', 'Disk'),
        ('head', 'Head'),
    ]
    OFFSET_GROUP_CHOICES = [
        ('Y', 'Y'),
        ('N', 'N'),
    ]

    subcategory = models.ForeignKey(
        SubCategory,
        on_delete=models.CASCADE,
        related_name='details',
        verbose_name='서브카테고리'
    )
    apc_para = models.CharField(max_length=100, verbose_name='APC Para')
    thk_para = models.CharField(max_length=100, verbose_name='THK Para')
    target = models.IntegerField(verbose_name='Target')
    pre_target = models.IntegerField(verbose_name='Pre Target')
    pre_thk_period = models.IntegerField(verbose_name='Pre THK Period')
    rr_para = models.CharField(max_length=10, choices=RR_PARA_CHOICES, verbose_name='RR Para', blank=True, default='')
    offset_group = models.CharField(max_length=1, choices=OFFSET_GROUP_CHOICES, verbose_name='Offset Group', blank=True, default='')
    rr_max = models.IntegerField(verbose_name='RR Max', null=True, blank=True)
    rr_period = models.IntegerField(verbose_name='RR Period', null=True, blank=True)
    if_rr = models.IntegerField(verbose_name='IF RR', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Detail'
        verbose_name_plural = 'Details'

    def __str__(self):
        return f'{self.subcategory} > {self.apc_para}'


class RecipeGroup(models.Model):
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE,
        related_name='recipe_groups', verbose_name='카테고리'
    )
    name = models.CharField(max_length=100, verbose_name='그룹명')
    subcategories = models.ManyToManyField(
        SubCategory, related_name='recipe_groups',
        blank=True, verbose_name='레시피'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Recipe Group'
        verbose_name_plural = 'Recipe Groups'
        ordering = ['category__product', 'category__oper_id', 'name']

    def __str__(self):
        return f'{self.category} > {self.name}'


class SetupHistory(models.Model):
    ACTION_CHOICES = [
        ('create', '생성'),
        ('update', '수정'),
        ('delete', '삭제'),
    ]
    MODEL_CHOICES = [
        ('Category', 'Category'),
        ('SubCategory', 'SubCategory'),
        ('Detail', 'Detail'),
        ('RecipeGroup', 'Recipe Group'),
    ]

    action = models.CharField(max_length=10, choices=ACTION_CHOICES, verbose_name='작업')
    model_type = models.CharField(max_length=20, choices=MODEL_CHOICES, verbose_name='구분')
    object_id = models.IntegerField(null=True, blank=True, verbose_name='대상 ID')
    object_repr = models.CharField(max_length=500, verbose_name='대상')
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='setup_histories', verbose_name='작업자'
    )
    changed_at = models.DateTimeField(auto_now_add=True, verbose_name='작업 일시')
    changes = models.JSONField(default=dict, blank=True, verbose_name='변경 내용')

    class Meta:
        verbose_name = 'Setup History'
        verbose_name_plural = 'Setup Histories'
        ordering = ['-changed_at']

    def __str__(self):
        return f'[{self.action}] {self.model_type} {self.object_repr}'


class AccessLog(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='access_logs', verbose_name='사용자'
    )
    path = models.CharField(max_length=500, verbose_name='경로')
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name='IP 주소')
    accessed_at = models.DateTimeField(auto_now_add=True, verbose_name='접속 일시')

    class Meta:
        verbose_name = 'Access Log'
        verbose_name_plural = 'Access Logs'
        ordering = ['-accessed_at']

    def __str__(self):
        return f'{self.user} | {self.path} | {self.accessed_at}'


class Voc(models.Model):
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='vocs', verbose_name='작성자')
    title = models.CharField(max_length=200, verbose_name='제목')
    content = models.TextField(verbose_name='내용')
    reply = models.TextField(verbose_name='답변', blank=True, default='')
    replied_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='voc_replies', verbose_name='답변자'
    )
    replied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'VOC'
        verbose_name_plural = 'VOCs'
        ordering = ['-created_at']

    @property
    def is_answered(self):
        return bool(self.reply)

    def __str__(self):
        return self.title
