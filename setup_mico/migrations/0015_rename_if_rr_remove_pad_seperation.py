from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('setup_mico', '0014_detail_new_fields'),
    ]

    operations = [
        migrations.RenameField(
            model_name='detail',
            old_name='if_rr',
            new_name='rr_if',
        ),
        migrations.RemoveField(
            model_name='detail',
            name='pad_seperation',
        ),
    ]
