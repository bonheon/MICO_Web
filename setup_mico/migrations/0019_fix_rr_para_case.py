"""
데이터 마이그레이션: rr_para 대문자 값(PAD, DISK, HEAD)을
모델 choices의 소문자 값(pad, disk, head)으로 변환
"""
from django.db import migrations


def normalize_rr_para(apps, schema_editor):
    Detail = apps.get_model('setup_mico', 'Detail')
    mapping = {'PAD': 'pad', 'DISK': 'disk', 'HEAD': 'head'}
    for old, new in mapping.items():
        Detail.objects.filter(rr_para=old).update(rr_para=new)


def reverse_normalize_rr_para(apps, schema_editor):
    Detail = apps.get_model('setup_mico', 'Detail')
    mapping = {'pad': 'PAD', 'disk': 'DISK', 'head': 'HEAD'}
    for old, new in mapping.items():
        Detail.objects.filter(rr_para=old).update(rr_para=new)


class Migration(migrations.Migration):

    dependencies = [
        ('setup_mico', '0018_add_channel_id_fb_type_rr_alarm_sigma'),
    ]

    operations = [
        migrations.RunPython(normalize_rr_para, reverse_normalize_rr_para),
    ]
