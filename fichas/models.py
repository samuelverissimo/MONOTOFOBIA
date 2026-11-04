from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from .regras import CAMPOS_EFEITOS_CONDICAO
from .pre_requisitos import validar_pre_requisitos

RESUMO_VALIDATORS = [MaxLengthValidator(500)]


def validar_efeitos_condicao(efeitos):
    if not isinstance(efeitos, dict) or any(
        campo not in CAMPOS_EFEITOS_CONDICAO
        or type(valor) is not int
        or abs(valor) > 10
        for campo, valor in efeitos.items()
    ):
        raise ValidationError('Efeitos de condição devem usar modificadores inteiros conhecidos.')


class CatalogoBase(models.Model):
    nome = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    fonte = models.CharField(max_length=100)
    personalizado = models.BooleanField(default=False)
    resumo = models.TextField(validators=RESUMO_VALIDATORS)

    class Meta:
        abstract = True
        ordering = ('nome',)

    def __str__(self):
        return self.nome


class Pericia(CatalogoBase):
    ATRIBUTOS = [
        ('agilidade', 'Agilidade'),
        ('forca', 'Força'),
        ('intelecto', 'Intelecto'),
        ('presenca', 'Presença'),
        ('vigor', 'Vigor'),
    ]

    atributo = models.CharField(max_length=12, choices=ATRIBUTOS)
    somente_treinada = models.BooleanField(default=False)
    penalidade_carga = models.BooleanField(default=False)
    exige_kit = models.BooleanField(default=False)


class Atributo(CatalogoBase):
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta(CatalogoBase.Meta):
        ordering = ('ordem', 'nome')


class Origem(CatalogoBase):
    pericias_treinadas = models.ManyToManyField(Pericia, related_name='origens', blank=True)
    pericias_especializadas = models.JSONField(default=dict, blank=True)
    escolhas_pericia = models.PositiveSmallIntegerField(default=0)
    poder_nome = models.CharField(max_length=120)
    poder_resumo = models.TextField(validators=RESUMO_VALIDATORS)


class Classe(CatalogoBase):
    PROGRESSOES = [('nex', 'NEX'), ('estagio', 'Estágio')]

    progressao = models.CharField(max_length=10, choices=PROGRESSOES, default='nex')
    pv_base = models.PositiveSmallIntegerField(default=0)
    pv_por_nex = models.PositiveSmallIntegerField(default=0)
    pe_base = models.PositiveSmallIntegerField(default=0)
    pe_por_nex = models.PositiveSmallIntegerField(default=0)
    san_base = models.PositiveSmallIntegerField(default=0)
    san_por_nex = models.PositiveSmallIntegerField(default=0)
    pd_base = models.PositiveSmallIntegerField(default=0)
    pd_por_nex = models.PositiveSmallIntegerField(default=0)
    pericias_obrigatorias = models.JSONField(default=list, blank=True)
    proficiencias = models.JSONField(default=list, blank=True)
    habilidades_por_nex = models.JSONField(default=dict, blank=True)


class Trilha(CatalogoBase):
    classe = models.ForeignKey(Classe, on_delete=models.PROTECT, related_name='trilhas')
    habilidades = models.JSONField(default=list, blank=True)


class Poder(CatalogoBase):
    TIPOS = [
        ('classe', 'Classe'),
        ('origem', 'Origem'),
        ('trilha', 'Trilha'),
        ('geral', 'Geral'),
        ('paranormal', 'Paranormal'),
    ]

    tipo = models.CharField(max_length=12, choices=TIPOS)
    pre_requisitos = models.JSONField(default=dict, blank=True)
    custo = models.CharField(max_length=80, blank=True)

    def clean(self):
        super().clean()
        validar_pre_requisitos(self.pre_requisitos)


class Ritual(CatalogoBase):
    ELEMENTOS = [
        ('sangue', 'Sangue'),
        ('morte', 'Morte'),
        ('conhecimento', 'Conhecimento'),
        ('energia', 'Energia'),
        ('medo', 'Medo'),
    ]

    circulo = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(4)])
    elemento = models.CharField(max_length=16, choices=ELEMENTOS)
    execucao = models.CharField(max_length=100)
    alcance = models.CharField(max_length=100)
    alvo_area = models.CharField(max_length=160)
    duracao = models.CharField(max_length=100)
    resistencia = models.CharField(max_length=120, blank=True)
    custo = models.CharField(max_length=80)


class ItemCatalogo(CatalogoBase):
    CATEGORIAS = [('0', '0'), ('I', 'I'), ('II', 'II'), ('III', 'III'), ('IV', 'IV')]
    TIPOS = [('geral', 'Geral'), ('arma', 'Arma'), ('protecao', 'Proteção')]

    categoria = models.CharField(max_length=3, choices=CATEGORIAS)
    espacos = models.PositiveSmallIntegerField(default=1)
    tipo = models.CharField(max_length=10, choices=TIPOS, default='geral')
    proficiencia = models.CharField(max_length=30, blank=True)
    tipo_arma = models.CharField(max_length=30, blank=True)
    empunhadura = models.CharField(max_length=20, blank=True)
    dano = models.CharField(max_length=40, blank=True)
    critico_margem = models.PositiveSmallIntegerField(null=True, blank=True)
    critico_multiplicador = models.PositiveSmallIntegerField(null=True, blank=True)
    alcance = models.CharField(max_length=40, blank=True)
    tipo_dano = models.CharField(max_length=40, blank=True)
    bonus_defesa = models.SmallIntegerField(default=0)
    campos_adicionais = models.JSONField(default=dict, blank=True)


class Condicao(CatalogoBase):
    CATEGORIAS = [
        ('medo', 'Medo'),
        ('mental', 'Mental'),
        ('paralisia', 'Paralisia'),
        ('sentidos', 'Sentidos'),
        ('fadiga', 'Fadiga'),
        ('outra', 'Outra'),
    ]

    categoria = models.CharField(max_length=12, choices=CATEGORIAS, default='outra')
    proxima_escalada = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL, related_name='escalada_de'
    )
    termina_fim_cena = models.BooleanField(default=True)
    efeitos = models.JSONField(default=dict, blank=True, validators=[validar_efeitos_condicao])


class Patente(CatalogoBase):
    pontos_prestigio = models.PositiveIntegerField(default=0)
    credito = models.CharField(max_length=40)
    limites_categoria = models.JSONField(default=dict, blank=True)
    limite_pd = models.PositiveSmallIntegerField(default=1)
    recuperacao = models.PositiveSmallIntegerField(default=1)


class ConfiguracaoMesa(models.Model):
    MODOS_RECURSOS = [('padrao', 'Padrão (PV, PE, SAN)'), ('sem_sanidade', 'Sem Sanidade (PV, PD)')]
    PROGRESSOES = [
        ('nex', 'NEX padrão'),
        ('nivel_nex', 'Nível de Experiência e NEX'),
        ('patentes', 'Evolução por patentes'),
    ]
    COMPARTILHAMENTO = [('nao', 'Não'), ('resumo', 'Somente resumo')]

    modo_recursos = models.CharField(max_length=16, choices=MODOS_RECURSOS, default='padrao')
    sistema_progressao = models.CharField(max_length=16, choices=PROGRESSOES, default='nex')
    ferimentos_debilitantes = models.BooleanField(default=False)
    jogadores_veem_fichas_alheias = models.CharField(
        max_length=8, choices=COMPARTILHAMENTO, default='nao'
    )
    jogador_pode_subir_nex = models.BooleanField(default=False)
    numero_sessao = models.PositiveIntegerField(default=1)
    max_fichas_ativas = models.PositiveSmallIntegerField(
        default=3, validators=[MinValueValidator(1), MaxValueValidator(20)]
    )

    class Meta:
        verbose_name = 'Configuração da mesa'
        verbose_name_plural = 'Configuração da mesa'

    def save(self, *args, **kwargs):
        self.pk = 1
        if self._state.adding and type(self).objects.filter(pk=1).exists():
            self._state.adding = False
            kwargs.pop('force_insert', None)
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('A configuração singleton da mesa não pode ser excluída.')

    def __str__(self):
        return 'Configuração da mesa'


class Ficha(models.Model):
    ELEMENTOS_CICATRIZADO = [
        ('sangue', 'Sangue'),
        ('morte', 'Morte'),
        ('conhecimento', 'Conhecimento'),
        ('energia', 'Energia'),
        ('medo', 'Medo'),
    ]
    STATUS = [
        ('ativa', 'Ativa'),
        ('arquivada', 'Arquivada'),
        ('morta', 'Morta'),
        ('aposentada', 'Aposentada'),
    ]

    dono = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='fichas')
    nome = models.CharField(max_length=100)
    jogador = models.CharField(max_length=80, blank=True)
    classe = models.ForeignKey(Classe, null=True, blank=True, on_delete=models.PROTECT)
    origem = models.ForeignKey(Origem, null=True, blank=True, on_delete=models.PROTECT)
    trilha = models.ForeignKey(Trilha, null=True, blank=True, on_delete=models.PROTECT)
    trilha_nome_personalizado = models.CharField(max_length=120, blank=True)
    trilha_resumo_personalizado = models.CharField(max_length=500, blank=True)
    trilha_fonte_personalizada = models.CharField(max_length=100, blank=True)
    nex = models.PositiveSmallIntegerField(default=5, null=True, blank=True)
    estagio = models.PositiveSmallIntegerField(null=True, blank=True)
    patente = models.ForeignKey(Patente, null=True, blank=True, on_delete=models.PROTECT)
    pontos_prestigio = models.IntegerField(default=0)
    nivel_experiencia = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(20)],
    )
    cicatrizado_elemento = models.CharField(
        max_length=16, choices=ELEMENTOS_CICATRIZADO, blank=True,
    )
    cicatrizado_perigo = models.CharField(max_length=120, blank=True)
    cicatrizado_sessao_usada = models.PositiveIntegerField(null=True, blank=True)

    agilidade = models.PositiveSmallIntegerField(default=1, validators=[MaxValueValidator(5)])
    forca = models.PositiveSmallIntegerField(default=1, validators=[MaxValueValidator(5)])
    intelecto = models.PositiveSmallIntegerField(default=1, validators=[MaxValueValidator(5)])
    presenca = models.PositiveSmallIntegerField(default=1, validators=[MaxValueValidator(5)])
    vigor = models.PositiveSmallIntegerField(default=1, validators=[MaxValueValidator(5)])

    pv_atual = models.PositiveIntegerField(default=0)
    pe_atual = models.PositiveIntegerField(default=0)
    san_atual = models.PositiveIntegerField(default=0)
    pd_atual = models.PositiveIntegerField(default=0)
    pv_temporario = models.PositiveIntegerField(default=0)
    ajuste_pv_max = models.SmallIntegerField(default=0)
    ajuste_pe_max = models.SmallIntegerField(default=0)
    ajuste_san_max = models.SmallIntegerField(default=0)
    ajuste_pd_max = models.SmallIntegerField(default=0)
    defesa_bonus = models.SmallIntegerField(default=0)
    deslocamento_bonus = models.SmallIntegerField(default=0)
    limite_pe_bonus = models.SmallIntegerField(default=0)
    credito = models.CharField(max_length=60, blank=True)

    conceito = models.CharField(max_length=240, blank=True)
    aparencia = models.CharField(max_length=1000, blank=True)
    personalidade = models.CharField(max_length=1000, blank=True)
    historia = models.CharField(max_length=4000, blank=True)
    objetivo = models.CharField(max_length=1000, blank=True)
    anotacoes_jogador = models.CharField(max_length=8000, blank=True)
    anotacoes_mestre = models.CharField(max_length=8000, blank=True)
    status = models.CharField(max_length=12, choices=STATUS, default='ativa')
    versao = models.PositiveIntegerField(default=1)
    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('nome', 'pk')
        indexes = [
            models.Index(fields=('dono', 'status'), name='ficha_owner_status_idx'),
            models.Index(fields=('nome',), name='ficha_nome_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(nex__isnull=False, estagio__isnull=True, patente__isnull=True)
                    | Q(nex__isnull=True, estagio__isnull=False, patente__isnull=True)
                    | Q(nex__isnull=True, estagio__isnull=True, patente__isnull=False)
                ),
                name='ficha_uma_progressao',
            ),
            models.CheckConstraint(
                condition=Q(nex__isnull=True) | Q(nex__gte=0, nex__lte=99),
                name='ficha_nex_valido',
            ),
            models.CheckConstraint(
                condition=Q(estagio__isnull=True) | Q(estagio__gte=1, estagio__lte=5),
                name='ficha_estagio_valido',
            ),
        ]

    def clean(self):
        super().clean()
        if self.classe_id and self.classe.slug == 'sobrevivente':
            if self.nex is not None or self.estagio is None or self.patente_id:
                raise ValidationError('Sobreviventes usam estágio, não NEX ou patente.')
        elif self.classe_id and self.nex is None and not self.patente_id:
            raise ValidationError('Esta classe deve usar NEX ou patente.')

    def __str__(self):
        return self.nome


class FichaPericia(models.Model):
    GRAUS = [('destreinado', 'Destreinado'), ('treinado', 'Treinado'), ('veterano', 'Veterano'), ('expert', 'Expert')]

    ficha = models.ForeignKey(Ficha, on_delete=models.CASCADE, related_name='pericias')
    pericia = models.ForeignKey(Pericia, on_delete=models.PROTECT, related_name='fichas')
    grau = models.CharField(max_length=12, choices=GRAUS, default='destreinado')
    especializacao = models.CharField(max_length=80, blank=True)
    bonus_extra = models.SmallIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('ficha', 'pericia'), name='ficha_pericia_unica')]


class FichaPoder(models.Model):
    ficha = models.ForeignKey(Ficha, on_delete=models.CASCADE, related_name='poderes')
    poder = models.ForeignKey(Poder, null=True, blank=True, on_delete=models.PROTECT)
    nome_personalizado = models.CharField(max_length=120, blank=True)
    resumo_personalizado = models.CharField(max_length=500, blank=True)
    fonte = models.CharField(max_length=100, default='Personalizado')


class FichaRitual(models.Model):
    ficha = models.ForeignKey(Ficha, on_delete=models.CASCADE, related_name='rituais')
    ritual = models.ForeignKey(Ritual, null=True, blank=True, on_delete=models.PROTECT)
    nome_personalizado = models.CharField(max_length=120, blank=True)
    resumo_personalizado = models.CharField(max_length=500, blank=True)
    fonte = models.CharField(max_length=100, default='Personalizado')


class FichaCondicao(models.Model):
    ficha = models.ForeignKey(Ficha, on_delete=models.CASCADE, related_name='condicoes')
    condicao = models.ForeignKey(Condicao, on_delete=models.PROTECT)
    desde = models.DateTimeField(auto_now_add=True)
    anotacao = models.CharField(max_length=300, blank=True)
    turnos_morrendo = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('ficha', 'condicao'), name='ficha_condicao_unica')]


class FerimentoDebilitante(models.Model):
    ATRIBUTOS = [
        ('agilidade', 'Agilidade'),
        ('forca', 'Força'),
        ('intelecto', 'Intelecto'),
        ('presenca', 'Presença'),
        ('vigor', 'Vigor'),
        ('superficial', 'Superficial (sem atributo afetado)'),
    ]

    ficha = models.ForeignKey(Ficha, on_delete=models.CASCADE, related_name='ferimentos')
    atributo = models.CharField(max_length=16, choices=ATRIBUTOS)
    tratamento_aprovado_em = models.DateTimeField(null=True, blank=True)
    curado_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('criado_em', 'pk')


class ItemInventario(models.Model):
    ESTADOS = [('guardado', 'Guardado'), ('vestido', 'Vestido'), ('empunhado', 'Empunhado'), ('equipado', 'Equipado')]

    ficha = models.ForeignKey(Ficha, on_delete=models.CASCADE, related_name='inventario')
    item_catalogo = models.ForeignKey(ItemCatalogo, null=True, blank=True, on_delete=models.PROTECT)
    nome = models.CharField(max_length=120)
    fonte = models.CharField(max_length=100, default='Personalizado')
    categoria = models.CharField(max_length=3, choices=ItemCatalogo.CATEGORIAS, default='0')
    espacos = models.PositiveSmallIntegerField(default=1)
    quantidade = models.PositiveSmallIntegerField(default=1)
    estado = models.CharField(max_length=12, choices=ESTADOS, default='guardado')
    notas = models.CharField(max_length=500, blank=True)
    campos_arma_protecao = models.JSONField(default=dict, blank=True)


class Pendencia(models.Model):
    ficha = models.ForeignKey(Ficha, on_delete=models.CASCADE, related_name='pendencias')
    tipo = models.CharField(max_length=40)
    descricao = models.CharField(max_length=240)
    fonte = models.CharField(max_length=100)
    quantidade = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(99)])
    resolvida = models.BooleanField(default=False)
    criada_em = models.DateTimeField(auto_now_add=True)


class RegistroPrestigio(models.Model):
    EVENTOS = [
        ('solucao', 'Solução do caso (+10)'),
        ('pista', 'Pista adicional encontrada (+2)'),
        ('inocente', 'Morte de inocente (-2)'),
        ('membro', 'Morte de membro do grupo (-5)'),
    ]

    ficha = models.ForeignKey(Ficha, on_delete=models.CASCADE, related_name='registros_prestigio')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    numero_sessao = models.PositiveIntegerField()
    evento = models.CharField(max_length=12, choices=EVENTOS)
    quantidade = models.PositiveSmallIntegerField(default=1)
    delta = models.SmallIntegerField()
    criada_em = models.DateTimeField(auto_now_add=True)


class Rolagem(models.Model):
    TIPOS = [('pericia', 'Perícia'), ('atributo', 'Atributo'), ('ataque', 'Ataque'), ('dano', 'Dano'), ('livre', 'Dado livre')]

    ficha = models.ForeignKey(Ficha, on_delete=models.CASCADE, related_name='rolagens')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='rolagens')
    tipo = models.CharField(max_length=12, choices=TIPOS)
    descricao = models.CharField(max_length=120)
    dados = models.JSONField(default=list)
    dado_escolhido = models.IntegerField(null=True, blank=True)
    bonus = models.IntegerField(default=0)
    total = models.IntegerField()
    secreta = models.BooleanField(default=False)
    criada_em = models.DateTimeField(auto_now_add=True)


class EncontroCombate(models.Model):
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    nome = models.CharField(max_length=100)
    rodada = models.PositiveIntegerField(default=1)
    indice_turno = models.SmallIntegerField(default=-1)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-ativo', '-criado_em', '-pk')


class ParticipanteCombate(models.Model):
    encontro = models.ForeignKey(EncontroCombate, on_delete=models.CASCADE, related_name='participantes')
    ficha = models.ForeignKey(
        Ficha, null=True, blank=True, on_delete=models.PROTECT, related_name='participacoes_combate',
    )
    ameaca = models.ForeignKey(
        'core.AmeacaMesa', null=True, blank=True, on_delete=models.PROTECT,
        related_name='participacoes_combate',
    )
    nome = models.CharField(max_length=120)
    iniciativa = models.SmallIntegerField()
    surpreendido = models.BooleanField(default=False)
    acao_padrao_usada = models.BooleanField(default=False)
    acoes_movimento_usadas = models.PositiveSmallIntegerField(default=0)
    acao_completa_usada = models.BooleanField(default=False)
    reacao_defensiva_usada = models.BooleanField(default=False)
    pe_gasto_turno = models.PositiveSmallIntegerField(default=0)
    pd_gasto_turno = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ('-iniciativa', 'pk')
        constraints = [
            models.UniqueConstraint(
                fields=('encontro', 'ficha'), condition=models.Q(ficha__isnull=False),
                name='combate_ficha_unica',
            ),
        ]


class LogAlteracao(models.Model):
    ficha = models.ForeignKey(Ficha, on_delete=models.CASCADE, related_name='historico')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    e_mestre = models.BooleanField(default=False)
    campo = models.CharField(max_length=80)
    valor_antigo = models.CharField(max_length=500, blank=True)
    valor_novo = models.CharField(max_length=500, blank=True)
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-criada_em',)

    def clean(self):
        super().clean()
        if self.campo in {'anotacoes_jogador', 'anotacoes_mestre', 'historia'}:
            raise ValidationError('Conteúdo privado de texto não pode ser copiado para o histórico.')