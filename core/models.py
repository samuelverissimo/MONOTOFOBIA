from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils.crypto import get_random_string


class Mesa(models.Model):
    mestre = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='mesas_criadas',
    )
    nome = models.CharField(max_length=100)
    publica = models.BooleanField(default=False)
    codigo_acesso = models.CharField(
        max_length=8,
        unique=True,
        null=True,
        blank=True,
        validators=[RegexValidator(r'^[0-9]{8}$', 'O código deve conter exatamente 8 dígitos.')],
    )
    criada_em = models.DateTimeField(auto_now_add=True)
    fichas = models.ManyToManyField(
        'fichas.Ficha', through='InscricaoMesa', related_name='mesas',
    )

    class Meta:
        ordering = ('nome', 'pk')
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(publica=True, codigo_acesso__isnull=True)
                    | models.Q(publica=False, codigo_acesso__isnull=False)
                ),
                name='mesa_codigo_compativel_visibilidade',
            ),
        ]

    def save(self, *args, **kwargs):
        if self.publica:
            self.codigo_acesso = None
        elif not self.codigo_acesso:
            while True:
                codigo = get_random_string(8, allowed_chars='0123456789')
                if not type(self).objects.filter(codigo_acesso=codigo).exists():
                    self.codigo_acesso = codigo
                    break
        elif len(self.codigo_acesso) != 8 or not self.codigo_acesso.isascii() or not self.codigo_acesso.isdigit():
            raise ValidationError('O código privado deve conter exatamente 8 dígitos.')
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.nome


class InscricaoMesa(models.Model):
    mesa = models.ForeignKey(Mesa, on_delete=models.CASCADE, related_name='inscricoes')
    ficha = models.ForeignKey(
        'fichas.Ficha', on_delete=models.CASCADE, related_name='inscricoes_mesa',
    )
    inscrita_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('inscrita_em', 'pk')
        constraints = [
            models.UniqueConstraint(fields=('mesa', 'ficha'), name='mesa_ficha_inscricao_unica'),
        ]


class CenaMesa(models.Model):
    TIPOS = [
        ('investigacao', 'Investigação'),
        ('interludio', 'Interlúdio'),
        ('medo', 'Medo'),
        ('furtividade', 'Furtividade'),
        ('perseguicao', 'Perseguição'),
    ]

    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='cenas_mesa_criadas',
    )
    nome = models.CharField(max_length=100)
    tipo = models.CharField(max_length=16, choices=TIPOS, default='investigacao')
    descricao_jogadores = models.CharField(max_length=2000, blank=True)
    anotacoes_mestre = models.CharField(max_length=4000, blank=True)
    ativa = models.BooleanField(default=False)
    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-ativa', '-atualizada_em', '-pk')


class PistaCena(models.Model):
    ESTADOS = [
        ('oculta', 'Oculta'),
        ('revelada', 'Revelada'),
        ('anotada', 'Anotada pelo grupo'),
    ]

    cena = models.ForeignKey(CenaMesa, on_delete=models.CASCADE, related_name='pistas')
    titulo = models.CharField(max_length=120)
    conteudo = models.CharField(max_length=2000)
    estado = models.CharField(max_length=12, choices=ESTADOS, default='oculta')
    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('criada_em', 'pk')


class RegistroCena(models.Model):
    cena = models.ForeignKey(CenaMesa, on_delete=models.CASCADE, related_name='registros')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    acao = models.CharField(max_length=40)
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-criada_em', '-pk')


class AmeacaMesa(models.Model):
    CATEGORIAS = [
        ('humano', 'Humano'),
        ('criatura', 'Criatura'),
        ('anomalia', 'Anomalia'),
        ('outro', 'Outro'),
    ]

    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='ameacas_mesa_criadas',
    )
    nome = models.CharField(max_length=120)
    categoria = models.CharField(max_length=12, choices=CATEGORIAS, default='outro')
    defesa = models.PositiveSmallIntegerField(null=True, blank=True)
    pv = models.PositiveSmallIntegerField(null=True, blank=True)
    deslocamento = models.CharField(max_length=100, blank=True)
    resistencias = models.CharField(max_length=500, blank=True)
    vulnerabilidades = models.CharField(max_length=500, blank=True)
    imunidades = models.CharField(max_length=500, blank=True)
    acoes = models.CharField(max_length=2000, blank=True)
    anotacoes_mestre = models.CharField(max_length=4000, blank=True)
    ativa = models.BooleanField(default=True)
    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-ativa', 'nome', 'pk')


class RegistroAmeaca(models.Model):
    ameaca = models.ForeignKey(AmeacaMesa, on_delete=models.CASCADE, related_name='registros')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    acao = models.CharField(max_length=12, choices=[('criada', 'Criada'), ('editada', 'Editada')])
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-criada_em', '-pk')
