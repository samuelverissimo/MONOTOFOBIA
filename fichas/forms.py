from django import forms
from django.core.exceptions import ValidationError

from fichas.models import Classe, ConfiguracaoMesa, Ficha, ItemCatalogo, ItemInventario, Origem, Pericia
from fichas.regras import ATRIBUTOS, NEX_VALIDOS, pericias_treinadas_disponiveis, validar_atributos_iniciais


class ConceitoFichaForm(forms.Form):
    nome = forms.CharField(label='Nome do personagem', max_length=100)
    conceito = forms.CharField(label='Conceito em uma frase', max_length=240)
    aparencia = forms.CharField(label='Aparência', max_length=1000, widget=forms.Textarea(attrs={'rows': 3}))
    personalidade = forms.CharField(label='Personalidade', max_length=1000, widget=forms.Textarea(attrs={'rows': 3}))
    historia = forms.CharField(label='História', max_length=4000, widget=forms.Textarea(attrs={'rows': 5}))
    objetivo = forms.CharField(label='Objetivo', max_length=1000, widget=forms.Textarea(attrs={'rows': 3}))

    def __init__(self, *args, livre=False, **kwargs):
        super().__init__(*args, **kwargs)
        if livre:
            for campo in self.fields.values():
                campo.required = False


class AtributosFichaForm(forms.Form):
    agilidade = forms.IntegerField(label='Agilidade', min_value=0, max_value=5, initial=1)
    forca = forms.IntegerField(label='Força', min_value=0, max_value=5, initial=1)
    intelecto = forms.IntegerField(label='Intelecto', min_value=0, max_value=5, initial=1)
    presenca = forms.IntegerField(label='Presença', min_value=0, max_value=5, initial=1)
    vigor = forms.IntegerField(label='Vigor', min_value=0, max_value=5, initial=1)

    def __init__(self, *args, classe=None, livre=False, **kwargs):
        self.classe = classe
        self.livre = livre
        super().__init__(*args, **kwargs)
        if not livre:
            for nome in ATRIBUTOS:
                self.fields[nome].max_value = 3

    def clean(self):
        dados = super().clean()
        if any(nome not in dados for nome in ATRIBUTOS):
            return dados

        if self.livre:
            try:
                validar_atributos_iniciais(dados, livre=True)
            except ValueError as erro:
                raise ValidationError(str(erro)) from erro
            return dados

        if self.classe:
            classe_slug = self.classe.slug if isinstance(self.classe, Classe) else str(self.classe)
            try:
                validar_atributos_iniciais(dados, classe_slug)
            except ValueError as erro:
                raise ValidationError(str(erro)) from erro
            return dados

        # A classe vem depois no assistente; aceita ambos os orçamentos iniciais
        # e confere o orçamento exato assim que o jogador escolher a classe.
        valido = False
        for classe_slug in ('combatente', 'sobrevivente'):
            try:
                validar_atributos_iniciais(dados, classe_slug)
                valido = True
                break
            except ValueError:
                continue
        if not valido:
            raise ValidationError('Distribua os pontos conforme uma das classes disponíveis.')
        return dados


class OrigemFichaForm(forms.Form):
    origem = forms.ModelChoiceField(queryset=Origem.objects.order_by('nome'), label='Origem', empty_label='Escolha uma origem', required=False)

    def __init__(self, *args, livre=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['origem'].required = not livre


class ClasseFichaForm(forms.Form):
    classe = forms.ModelChoiceField(queryset=Classe.objects.order_by('nome'), label='Classe', empty_label='Escolha uma classe', required=False)

    def __init__(self, *args, livre=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['classe'].required = not livre


class PericiasFichaForm(forms.Form):
    def __init__(self, *args, classe, origem, intelecto, livre=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.classe = classe
        self.origem = origem
        self.intelecto = intelecto
        self.livre = livre
        if livre:
            self.quantidade_escolhas = 0
            self.fields['pericias_escolhidas'] = forms.ModelMultipleChoiceField(
                queryset=Pericia.objects.order_by('nome'),
                label='Perícias (opcional)',
                required=False,
                widget=forms.CheckboxSelectMultiple,
            )
            return

        if classe is None or origem is None:
            raise ValueError('Classe e origem são necessárias para validar perícias.')
        origem_slugs = set(origem.pericias_treinadas.values_list('slug', flat=True))
        todas = Pericia.objects.order_by('nome')
        obrigatorias = classe.pericias_obrigatorias or []

        for indice, alternativas in enumerate(obrigatorias):
            disponiveis = todas.filter(slug__in=alternativas).exclude(slug__in=origem_slugs)
            if not disponiveis.exists():
                disponiveis = todas.exclude(slug__in=origem_slugs)
            self.fields[f'pericia_obrigatoria_{indice}'] = forms.ModelChoiceField(
                queryset=disponiveis,
                label='Escolha uma perícia obrigatória da classe',
                empty_label='Escolha uma perícia',
            )

        self.quantidade_escolhas = (
            pericias_treinadas_disponiveis(classe.slug, intelecto) + origem.escolhas_pericia
        )
        self.fields['pericias_escolhidas'] = forms.ModelMultipleChoiceField(
            queryset=todas.exclude(slug__in=origem_slugs),
            label=f'Escolha {self.quantidade_escolhas} perícias adicionais',
            required=self.quantidade_escolhas > 0,
            widget=forms.CheckboxSelectMultiple,
            help_text='Não repita perícias fornecidas pela origem ou pelos requisitos da classe.',
        )

    def clean(self):
        dados = super().clean()
        if self.livre:
            return dados
        obrigatorias = [
            dados[f'pericia_obrigatoria_{indice}']
            for indice in range(len(self.classe.pericias_obrigatorias or []))
            if dados.get(f'pericia_obrigatoria_{indice}')
        ]
        escolhidas = list(dados.get('pericias_escolhidas', []))
        slugs = [pericia.slug for pericia in obrigatorias + escolhidas]
        if len(slugs) != len(set(slugs)):
            self.add_error('pericias_escolhidas', 'Não escolha a mesma perícia mais de uma vez.')
        if len(escolhidas) != self.quantidade_escolhas:
            self.add_error(
                'pericias_escolhidas',
                f'Escolha exatamente {self.quantidade_escolhas} perícias adicionais.',
            )
        return dados


class RevisaoFichaForm(forms.Form):
    confirmar = forms.BooleanField(label='Confirmo os dados da ficha', required=True)

    def __init__(self, *args, livre=False, **kwargs):
        super().__init__(*args, **kwargs)
        if livre:
            self.fields['confirmar'].required = False


class FichaEdicaoForm(forms.Form):
    nome = forms.CharField(label='Nome do personagem', max_length=100)
    jogador = forms.CharField(label='Jogador (opcional)', max_length=80, required=False)
    conceito = forms.CharField(label='Conceito', max_length=240, required=False)
    aparencia = forms.CharField(label='Aparência', max_length=1000, required=False, widget=forms.Textarea(attrs={'rows': 3}))
    personalidade = forms.CharField(label='Personalidade', max_length=1000, required=False, widget=forms.Textarea(attrs={'rows': 3}))
    historia = forms.CharField(label='História', max_length=4000, required=False, widget=forms.Textarea(attrs={'rows': 5}))
    objetivo = forms.CharField(label='Objetivo', max_length=1000, required=False, widget=forms.Textarea(attrs={'rows': 3}))
    anotacoes_jogador = forms.CharField(label='Anotações privadas', max_length=8000, required=False, widget=forms.Textarea(attrs={'rows': 5}))
    anotacoes_mestre = forms.CharField(label='Anotações do mestre', max_length=8000, required=False, widget=forms.Textarea(attrs={'rows': 5}))
    versao = forms.IntegerField(widget=forms.HiddenInput)

    def __init__(self, *args, mestre=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not mestre:
            self.fields.pop('anotacoes_mestre')


class AvancoNexForm(forms.Form):
    nex_novo = forms.ChoiceField(label='Novo NEX')
    versao = forms.IntegerField(widget=forms.HiddenInput)

    def __init__(self, *args, nex_atual, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['nex_novo'].choices = [
            (nex, f'{nex}%') for nex in NEX_VALIDOS if nex > nex_atual
        ]


class ItemInventarioForm(forms.Form):
    nome = forms.CharField(label='Item', max_length=120)
    categoria = forms.ChoiceField(label='Categoria', choices=ItemCatalogo.CATEGORIAS)
    espacos = forms.IntegerField(label='Espaços por unidade', min_value=0, max_value=100)
    quantidade = forms.IntegerField(label='Quantidade', min_value=1, max_value=999)
    estado = forms.ChoiceField(label='Estado', choices=ItemInventario.ESTADOS)
    notas = forms.CharField(label='Notas', max_length=500, required=False)


class ItemInventarioAjusteForm(forms.Form):
    quantidade = forms.IntegerField(min_value=1, max_value=999)
    estado = forms.ChoiceField(choices=ItemInventario.ESTADOS)


class ConfiguracaoMesaForm(forms.Form):
    modo_recursos = forms.ChoiceField(label='Modo de recursos', choices=ConfiguracaoMesa.MODOS_RECURSOS)
    jogador_pode_subir_nex = forms.BooleanField(label='Jogadores podem avançar NEX', required=False)
    max_fichas_ativas = forms.IntegerField(label='Máximo de fichas ativas', min_value=1, max_value=20)


class FichaStatusForm(forms.Form):
    status = forms.ChoiceField(
        choices=[(valor, rotulo) for valor, rotulo in Ficha.STATUS if valor in ('ativa', 'arquivada')],
    )
    versao = forms.IntegerField(widget=forms.HiddenInput)