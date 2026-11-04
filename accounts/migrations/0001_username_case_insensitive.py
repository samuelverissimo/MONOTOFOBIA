from django.db import migrations, models
from django.db.models import Count
from django.db.models.functions import Lower


CONSTRAINT_NAME = 'accounts_user_username_ci_uniq'


def adicionar_indice_case_insensitive(apps, schema_editor):
    usuario = apps.get_model('auth', 'User')
    if not schema_editor.connection.features.supports_expression_indexes:
        raise RuntimeError(
            'O banco configurado precisa suportar índices funcionais para '
            'garantir usernames sem distinção entre maiúsculas e minúsculas.'
        )

    duplicados = (
        usuario.objects.annotate(username_minusculo=Lower('username'))
        .values('username_minusculo')
        .annotate(total=Count('id'))
        .filter(total__gt=1)
    )
    if duplicados.exists():
        raise RuntimeError(
            'Existem usernames duplicados sem distinção de caixa; corrija-os '
            'antes de aplicar esta migração.'
        )

    schema_editor.add_constraint(
        usuario,
        models.UniqueConstraint(Lower('username'), name=CONSTRAINT_NAME),
    )


def remover_indice_case_insensitive(apps, schema_editor):
    usuario = apps.get_model('auth', 'User')
    schema_editor.remove_constraint(
        usuario,
        models.UniqueConstraint(Lower('username'), name=CONSTRAINT_NAME),
    )


class Migration(migrations.Migration):
    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(
            adicionar_indice_case_insensitive,
            remover_indice_case_insensitive,
        ),
    ]