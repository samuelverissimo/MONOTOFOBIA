from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = 'Promove explicitamente um usuário existente a mestre (staff e superusuário).'

    def add_arguments(self, parser):
        parser.add_argument('usuario', help='Username exato do usuário existente.')

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        try:
            usuario = User.objects.get(username=options['usuario'])
        except User.DoesNotExist as erro:
            raise CommandError('Usuário não encontrado; nenhum usuário foi promovido.') from erro

        ja_mestre = usuario.is_staff and usuario.is_superuser
        if not ja_mestre:
            usuario.is_staff = True
            usuario.is_superuser = True
            usuario.save(update_fields=('is_staff', 'is_superuser'))

        if ja_mestre:
            self.stdout.write(self.style.WARNING(f'{usuario.username} já é mestre.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'{usuario.username} foi promovido a mestre.'))