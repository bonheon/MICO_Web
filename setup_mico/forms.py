from django import forms
from .models import Category, SubCategory, Detail, Voc


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['family', 'product', 'oper_id', 'oper_desc']
        widgets = {
            'family':    forms.Select(attrs={'class': 'form-select'}),
            'product':   forms.TextInput(attrs={'class': 'form-control', 'placeholder': '제품명'}),
            'oper_id':   forms.TextInput(attrs={'class': 'form-control', 'placeholder': '공정 ID'}),
            'oper_desc': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': '공정 설명'}),
        }
        labels = {
            'family':    'Family',
            'product':   'Product',
            'oper_id':   'Oper ID',
            'oper_desc': 'Oper Desc',
        }


class SubCategoryForm(forms.ModelForm):
    class Meta:
        model = SubCategory
        fields = ['category', 'fab', 'device', 'recipe_id', 'maker']
        widgets = {
            'category':  forms.Select(attrs={'class': 'form-select'}),
            'fab':       forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'FAB'}),
            'device':    forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Device'}),
            'recipe_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Recipe ID'}),
            'maker':     forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Maker'}),
        }
        labels = {
            'category':  'Category',
            'fab':       'FAB',
            'device':    'Device',
            'recipe_id': 'Recipe ID',
            'maker':     'Maker',
        }


class DetailForm(forms.ModelForm):
    class Meta:
        model = Detail
        fields = [
            'subcategory', 'apc_para', 'thk_para',
            'target', 'pre_target', 'pre_thk_period',
            'rr_para', 'offset_group', 'rr_max', 'rr_period', 'if_rr',
        ]
        widgets = {
            'subcategory':    forms.Select(attrs={'class': 'form-select'}),
            'apc_para':       forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'APC Para'}),
            'thk_para':       forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'THK Para'}),
            'target':         forms.NumberInput(attrs={'class': 'form-control'}),
            'pre_target':     forms.NumberInput(attrs={'class': 'form-control'}),
            'pre_thk_period': forms.NumberInput(attrs={'class': 'form-control'}),
            'rr_para':        forms.Select(attrs={'class': 'form-select'}),
            'offset_group':   forms.Select(attrs={'class': 'form-select'}),
            'rr_max':         forms.NumberInput(attrs={'class': 'form-control'}),
            'rr_period':      forms.NumberInput(attrs={'class': 'form-control'}),
            'if_rr':          forms.NumberInput(attrs={'class': 'form-control'}),
        }


class VocForm(forms.ModelForm):
    class Meta:
        model = Voc
        fields = ['title', 'content']
        widgets = {
            'title':   forms.TextInput(attrs={'class': 'form-control', 'placeholder': '제목을 입력하세요'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 6, 'placeholder': '불편한 점이나 문제점을 자세히 적어주세요'}),
        }


class VocReplyForm(forms.ModelForm):
    class Meta:
        model = Voc
        fields = ['reply']
        widgets = {
            'reply': forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': '답변 내용을 입력하세요'}),
        }
