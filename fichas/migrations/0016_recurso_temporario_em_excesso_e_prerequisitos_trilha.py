from django.db import migrations, models
from django.db.models import F


def mover_pv_temporarios_para_total(apps, schema_editor):
    Ficha = apps.get_model('fichas', 'Ficha')
    Ficha.objects.update(pv_atual=F('pv_atual') + F('pv_temporario'))


class Migration(migrations.Migration):

    dependencies = [
        ('fichas', '0015_habilidadeficha'),
    ]

    operations = [
        migrations.RunPython(
            mover_pv_temporarios_para_total,
            migrations.RunPython.noop,
        ),
        migrations.AddField(
            model_name='trilha',
            name='pre_requisitos',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.RemoveField(
            model_name='ficha',
            name='pv_temporario',
        ),
    ]
