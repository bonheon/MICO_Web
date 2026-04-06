from django import forms
from .models import Category, SubCategory, Detail, Voc


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['family', 'product', 'oper_id', 'oper_desc', 'channel_id']
        widgets = {
            'family':     forms.Select(attrs={'class': 'form-select'}),
            'product':    forms.TextInput(attrs={'class': 'form-control', 'placeholder': '제품명'}),
            'oper_id':    forms.TextInput(attrs={'class': 'form-control', 'placeholder': '공정 ID'}),
            'oper_desc':  forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': '공정 설명'}),
            'channel_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Channel ID'}),
        }
        labels = {
            'family':     'Family',
            'product':    'Product',
            'oper_id':    'Oper ID',
            'oper_desc':  'Oper Desc',
            'channel_id': 'Channel ID',
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
            'rr_para', 'offset_group', 'rr_max', 'rr_period', 'rr_if',
            'pre_thk_para_itm',
            'pre_oper_code', 'pre_oper_desc', 'pre_oper_para',
            'pre_oper_code2', 'pre_oper_desc2', 'pre_oper_para2',
            'pre_oper_code3', 'pre_oper_desc3', 'pre_oper_para3',
            'pre_oper_code4', 'pre_oper_desc4', 'pre_oper_para4',
            'rr_weight', 'rr_count',
            'fb_type', 'rr_alarm_sigma',
        ]
        widgets = {
            'subcategory':      forms.Select(attrs={'class': 'form-select'}),
            'apc_para':         forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'APC Para'}),
            'thk_para':         forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'THK Para'}),
            'target':           forms.NumberInput(attrs={'class': 'form-control'}),
            'pre_target':       forms.NumberInput(attrs={'class': 'form-control'}),
            'pre_thk_period':   forms.NumberInput(attrs={'class': 'form-control'}),
            'rr_para':          forms.Select(attrs={'class': 'form-select'}),
            'offset_group':     forms.Select(attrs={'class': 'form-select'}),
            'rr_max':           forms.NumberInput(attrs={'class': 'form-control'}),
            'rr_period':        forms.NumberInput(attrs={'class': 'form-control'}),
            'rr_if':            forms.NumberInput(attrs={'class': 'form-control'}),
            'pre_thk_para_itm': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Pre THK Para ITM'}),
            'pre_oper_code':    forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Oper Code'}),
            'pre_oper_desc':    forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Oper Desc'}),
            'pre_oper_para':    forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Oper Para'}),
            'pre_oper_code2':   forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Oper Code'}),
            'pre_oper_desc2':   forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Oper Desc'}),
            'pre_oper_para2':   forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Oper Para'}),
            'pre_oper_code3':   forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Oper Code'}),
            'pre_oper_desc3':   forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Oper Desc'}),
            'pre_oper_para3':   forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Oper Para'}),
            'pre_oper_code4':   forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Oper Code'}),
            'pre_oper_desc4':   forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Oper Desc'}),
            'pre_oper_para4':   forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Oper Para'}),
            'rr_weight':        forms.NumberInput(attrs={'class': 'form-control'}),
            'rr_count':         forms.NumberInput(attrs={'class': 'form-control'}),
            'fb_type':          forms.Select(attrs={'class': 'form-select'}),
            'rr_alarm_sigma':   forms.NumberInput(attrs={'class': 'form-control'}),
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
