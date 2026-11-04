from django.conf import settings
from django.db import models


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
