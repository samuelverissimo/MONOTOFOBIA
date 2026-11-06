from collections import Counter
import json

from django import forms
from django.core.exceptions import ValidationError

from core.models import AmeacaMesa
from fichas.models import (
    Classe,
    ConfiguracaoMesa,
    EncontroCombate,
    Ficha,
    FichaPericia,
    FerimentoDebilitante,
    HabilidadeFicha,
    ItemCatalogo,
    ItemInventario,
    ParticipanteCombate,
    Origem,
    Patente,
    RegistroPrestigio,
    Pericia,
    Poder,
    Ritual,
    Trilha,
)
from fichas.pre_requisitos import (
    nex_efetivo,
    poder_atende_pre_requisitos,
    trilha_atende_pre_requisitos,
)
from fichas.regras import (
    ATRIBUTOS,
    NEX_VALIDOS,
    nex_equivalente_por_nivel,
    pericias_treinadas_disponiveis,
    validar_atributos_iniciais,
)


class ConceitoFichaForm(forms.Form):
    nome = forms.CharField(label='Nome do personagem', max_length=100)
    conceito = forms.CharField(label='Conceito em uma frase', max_length=240)

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
        if livre:
            self.fields['agilidade'].help_text = (
                'Criação livre: distribua valores de 0 a 5 entre os cinco atributos.'
            )
        else:
            for nome in ATRIBUTOS:
                self.fields[nome].max_value = 3
            classe_slug = classe.slug if isinstance(classe, Classe) else str(classe or 'combatente')
            total = 8 if classe_slug == 'sobrevivente' else 9
            self.fields['agilidade'].help_text = (
                f'Distribua {total} pontos entre os cinco atributos; no máximo um '
                'pode ser 0 e nenhum pode passar de 3.'
            )

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
        campo_origem = self.fields['origem']
        campo_origem.widget = OrigemSelect(choices=campo_origem.choices)
        self.fields['origem'].required = not livre


class SlugSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        instance = getattr(value, 'instance', None)
        if instance and hasattr(instance, 'slug'):
            option['attrs']['data-slug'] = instance.slug
        if isinstance(instance, Classe):
            try:
                option['attrs']['data-pericias-base'] = pericias_treinadas_disponiveis(
                    instance.slug, 0,
                ) + len(instance.pericias_obrigatorias or [])
            except ValueError:
                option['attrs']['data-pericias-base'] = len(instance.pericias_obrigatorias or [])
        return option


class PoderSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        instance = getattr(value, 'instance', None)
        if isinstance(instance, Poder):
            option['attrs']['data-power-name'] = instance.nome
            option['attrs']['data-power-description'] = instance.resumo or ''
        return option


class RitualSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        instance = getattr(value, 'instance', None)
        if isinstance(instance, Ritual):
            option['attrs']['data-ritual-name'] = instance.nome
            option['attrs']['data-ritual-description'] = instance.resumo or ''
        return option


class TrilhaSelect(SlugSelect):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        instance = getattr(value, 'instance', None)
        if instance:
            option['attrs']['data-classe'] = instance.classe.slug
        return option


class ClasseFichaForm(forms.Form):
    classe = forms.ModelChoiceField(
        queryset=Classe.objects.order_by('nome'), label='Classe',
        empty_label='Escolha uma classe', required=False, widget=SlugSelect,
    )

    def __init__(self, *args, livre=False, mesa=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['classe'].required = not livre
        if mesa and mesa.sistema_progressao == 'patentes':
            self.fields['classe'].queryset = self.fields['classe'].queryset.exclude(
                slug='sobrevivente',
            )


class OrigemSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        instance = getattr(value, 'instance', None)
        if isinstance(instance, Origem):
            option['attrs']['data-origin-pericias'] = ','.join(
                str(pk) for pk in instance.pericias_treinadas.values_list('pk', flat=True)
            )
            option['attrs']['data-origin-escolhas'] = instance.escolhas_pericia
        return option


class PericiaCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        instance = getattr(value, 'instance', None)
        if isinstance(instance, Pericia):
            option['attrs']['data-pericia-id'] = instance.pk
            option['attrs']['data-slug'] = instance.slug
        return option


class PericiasFichaForm(forms.Form):
    def __init__(self, *args, classe, origem, intelecto, livre=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.classe = classe
        self.origem = origem
        self.intelecto = intelecto
        self.livre = livre
        if livre or classe is None or origem is None:
            self.quantidade_escolhas = 0
            self.fields['pericias_escolhidas'] = forms.ModelMultipleChoiceField(
                queryset=Pericia.objects.order_by('nome'),
                label='Perícias treinadas',
                required=False,
                widget=PericiaCheckboxSelectMultiple(
                    attrs={'class': 'checklist', 'data-additional-skills': ''},
                ),
                help_text='Escolha classe e origem para calcular quantas perícias selecionar.',
            )
            return
        origem_slugs = set(origem.pericias_treinadas.values_list('slug', flat=True))
        todas = Pericia.objects.order_by('nome')
        self.quantidade_escolhas = (
            pericias_treinadas_disponiveis(classe.slug, intelecto)
            + len(classe.pericias_obrigatorias or [])
            + origem.escolhas_pericia
        )
        self.fields['pericias_escolhidas'] = forms.ModelMultipleChoiceField(
            queryset=todas.exclude(slug__in=origem_slugs),
            label='Perícias treinadas',
            required=self.quantidade_escolhas > 0,
            widget=PericiaCheckboxSelectMultiple(
                attrs={'class': 'checklist', 'data-additional-skills': ''},
            ),
            help_text=(
                f'Selecione exatamente {self.quantidade_escolhas} perícias. '
                'As perícias da origem já contam e não aparecem nesta lista; todas '
                'as escolhas começam Treinadas.'
            ),
        )

    def clean(self):
        dados = super().clean()
        if self.livre or self.classe is None or self.origem is None:
            return dados
        escolhidas = list(dados.get('pericias_escolhidas', []))
        if len(escolhidas) != self.quantidade_escolhas:
            self.add_error(
                'pericias_escolhidas',
                f'Escolha exatamente {self.quantidade_escolhas} perícias treinadas.',
            )
        return dados


class ProgressaoInicialForm(forms.Form):
    nex_inicial = forms.ChoiceField(label='NEX inicial')
    nivel_inicial = forms.ChoiceField(label='Nível de experiência inicial')
    nex_paranormal = forms.ChoiceField(label='NEX paranormal inicial')
    patente_inicial = forms.ModelChoiceField(
        queryset=Patente.objects.none(),
        label='Patente inicial',
        empty_label=None,
        required=False,
    )

    def __init__(self, *args, mesa, classe=None, **kwargs):
        super().__init__(*args, **kwargs)
        if classe and classe.slug == 'sobrevivente':
            self.fields.clear()
            return
        if mesa.sistema_progressao == 'nivel_nex':
            self.fields.pop('nex_inicial')
            self.fields.pop('patente_inicial')
            self.fields['nivel_inicial'].choices = [
                (str(nivel), f'Nível {nivel}') for nivel in range(1, 21)
            ]
            self.fields['nivel_inicial'].initial = '1'
            self.fields['nex_paranormal'].choices = [
                (str(nex), f'{nex}%') for nex in range(100)
            ]
            self.fields['nex_paranormal'].initial = '0'
            self.fields['nex_paranormal'].help_text = (
                'Exposição paranormal é separada do nível de experiência.'
            )
        elif mesa.sistema_progressao == 'patentes':
            self.fields.pop('nex_inicial')
            self.fields.pop('nivel_inicial')
            self.fields.pop('nex_paranormal')
            self.fields['patente_inicial'].queryset = Patente.objects.order_by(
                'limite_pd', 'pontos_prestigio', 'nome',
            )
            self.fields['patente_inicial'].required = True
            recruta = Patente.objects.filter(slug='recruta').first()
            if recruta:
                self.fields['patente_inicial'].initial = recruta.pk
        else:
            self.fields.pop('nivel_inicial')
            self.fields.pop('nex_paranormal')
            self.fields.pop('patente_inicial')
            self.fields['nex_inicial'].choices = [
                (str(nex), f'{nex}%') for nex in NEX_VALIDOS
            ]
            self.fields['nex_inicial'].initial = '5'


class TrilhaInicialForm(forms.Form):
    trilha = forms.ModelChoiceField(
        queryset=Trilha.objects.none(),
        label='Trilha',
        empty_label='Sem trilha por enquanto',
        required=False,
        widget=TrilhaSelect,
    )
    estagio_inicial = forms.ChoiceField(label='Estágio inicial')
    cicatrizado_elemento = forms.ChoiceField(
        label='Elemento de Cicatrizado',
        choices=(('', 'Escolha o elemento'), *Ficha.ELEMENTOS_CICATRIZADO),
        required=False,
    )
    cicatrizado_perigo = forms.CharField(
        label='Perigo específico de Cicatrizado',
        max_length=120,
        required=False,
    )

    def __init__(self, *args, classe, initial=None, **kwargs):
        self.classe = classe
        super().__init__(*args, initial=initial, **kwargs)
        trilhas = Trilha.objects.order_by('nome')
        if classe:
            trilhas = trilhas.filter(classe_id=classe.pk)
        elif self.is_bound:
            trilhas = trilhas.none()
        self.fields['trilha'].queryset = trilhas
        self.fields['estagio_inicial'].choices = [
            (str(estagio), f'Estágio {estagio}') for estagio in range(1, 6)
        ]
        if classe and classe.slug == 'sobrevivente':
            self.fields['estagio_inicial'].required = True
            self.fields['cicatrizado_elemento'].help_text = (
                'Opcional no estágio 5; pode ser registrado mais tarde na ficha.'
            )
        else:
            self.fields['estagio_inicial'].required = False

    def clean(self):
        dados = super().clean()
        if not self.classe or self.classe.slug != 'sobrevivente':
            dados['estagio_inicial'] = ''
            dados['cicatrizado_elemento'] = ''
            dados['cicatrizado_perigo'] = ''
        if dados.get('cicatrizado_elemento') and not dados.get('cicatrizado_perigo'):
            self.add_error('cicatrizado_perigo', 'Informe o perigo paranormal enfrentado.')
        if dados.get('cicatrizado_perigo') and not dados.get('cicatrizado_elemento'):
            self.add_error('cicatrizado_elemento', 'Escolha o elemento do perigo.')
        return dados


class CriacaoInicialForm(forms.Form):
    confirmar = forms.BooleanField(label='Confirmo os dados iniciais da ficha')
    trilha = forms.ModelChoiceField(
        queryset=Trilha.objects.none(),
        label='Trilha (opcional)',
        empty_label='Sem trilha por enquanto',
        required=False,
    )
    nex_inicial = forms.ChoiceField(label='NEX inicial')
    nivel_inicial = forms.ChoiceField(label='Nível inicial')
    nex_paranormal = forms.ChoiceField(label='NEX paranormal inicial')
    estagio_inicial = forms.ChoiceField(label='Estágio inicial')
    patente_inicial = forms.ModelChoiceField(
        queryset=Patente.objects.none(),
        label='Patente inicial',
        empty_label=None,
        required=False,
    )
    cicatrizado_elemento = forms.ChoiceField(
        label='Elemento de Cicatrizado',
        choices=(('', 'Escolha o elemento'), *Ficha.ELEMENTOS_CICATRIZADO),
        required=False,
    )
    cicatrizado_perigo = forms.CharField(
        label='Perigo específico de Cicatrizado',
        max_length=120,
        required=False,
    )

    GRAUS_TREINAMENTO = (
        ('treinado', 'Treinado'),
        ('veterano', 'Veterano'),
        ('expert', 'Expert'),
    )

    def __init__(
        self, *args, mesa, classe, origem, atributos, pericia_ids, livre=False,
        progressao=None, trilha_inicial=None, estagio_inicial_inicial=None,
        cicatrizado_elemento_inicial='', cicatrizado_perigo_inicial='',
        incluir_trilha=True, incluir_cicatrizado=True,
        incluir_confirmacao=True, incluir_treinamento=True, **kwargs,
    ):
        self.mesa = mesa
        self.classe = classe
        self.origem = origem
        self.atributos = atributos
        self.livre = livre
        self.progressao = progressao
        self.trilha_inicial = trilha_inicial
        self.estagio_inicial_inicial = estagio_inicial_inicial
        self.cicatrizado_elemento_inicial = cicatrizado_elemento_inicial
        self.cicatrizado_perigo_inicial = cicatrizado_perigo_inicial
        self.incluir_treinamento = incluir_treinamento
        super().__init__(*args, **kwargs)
        if not incluir_confirmacao:
            self.fields.pop('confirmar')
        if livre:
            if 'confirmar' in self.fields:
                self.fields['confirmar'].required = False

        pericias = Pericia.objects.in_bulk(pericia_ids)
        self.pericias = pericias
        if classe:
            self.fields['trilha'].queryset = Trilha.objects.filter(
                classe_id=classe.pk,
            ).order_by('nome')
        self.fields['patente_inicial'].queryset = Patente.objects.order_by(
            'limite_pd', 'pontos_prestigio', 'nome',
        )

        sobrevivente = bool(classe and classe.slug == 'sobrevivente')
        progressao = mesa.sistema_progressao
        if not classe:
            self.fields.pop('trilha')
        if sobrevivente:
            for campo in (
                'nex_inicial', 'nivel_inicial', 'nex_paranormal', 'patente_inicial',
            ):
                self.fields.pop(campo)
            self.fields['estagio_inicial'].choices = [
                (str(estagio), f'Estágio {estagio}') for estagio in range(1, 6)
            ]
            self.fields['estagio_inicial'].initial = '1'
            self.fields['cicatrizado_elemento'].help_text = (
                'Opcional no estágio 5; pode ser escolhido mais tarde pela ficha.'
            )
        elif not classe:
            self.fields.pop('nex_inicial')
            self.fields.pop('nivel_inicial')
            self.fields.pop('nex_paranormal')
            self.fields.pop('estagio_inicial')
            if progressao != 'patentes':
                self.fields.pop('patente_inicial')
            self.fields.pop('cicatrizado_elemento')
            self.fields.pop('cicatrizado_perigo')
        elif progressao == 'nex':
            self.fields.pop('nivel_inicial')
            self.fields.pop('nex_paranormal')
            self.fields.pop('estagio_inicial')
            self.fields.pop('patente_inicial')
            self.fields.pop('cicatrizado_elemento')
            self.fields.pop('cicatrizado_perigo')
            self.fields['nex_inicial'].choices = [(str(nex), f'{nex}%') for nex in NEX_VALIDOS]
            self.fields['nex_inicial'].initial = '5'
        elif progressao == 'nivel_nex':
            self.fields.pop('nex_inicial')
            self.fields.pop('estagio_inicial')
            self.fields.pop('patente_inicial')
            self.fields.pop('cicatrizado_elemento')
            self.fields.pop('cicatrizado_perigo')
            self.fields['nivel_inicial'].choices = [
                (str(nivel), str(nivel)) for nivel in range(1, 21)
            ]
            self.fields['nivel_inicial'].initial = '1'
            self.fields['nex_paranormal'].choices = [
                (str(nex), f'{nex}%') for nex in range(100)
            ]
            self.fields['nex_paranormal'].initial = '0'
        else:
            self.fields.pop('nex_inicial')
            self.fields.pop('nivel_inicial')
            self.fields.pop('nex_paranormal')
            self.fields.pop('estagio_inicial')
            self.fields.pop('cicatrizado_elemento')
            self.fields.pop('cicatrizado_perigo')
            self.fields['patente_inicial'].required = True
            recruta = Patente.objects.filter(slug='recruta').first()
            if recruta:
                self.fields['patente_inicial'].initial = recruta.pk

        if progressao == 'patentes' and 'patente_inicial' in self.fields:
            recruta = Patente.objects.filter(slug='recruta').first()
            if recruta:
                self.fields['patente_inicial'].initial = recruta.pk

        if self.progressao is not None:
            for campo in ('nex_inicial', 'nivel_inicial', 'nex_paranormal', 'patente_inicial'):
                self.fields.pop(campo, None)
        if not incluir_trilha:
            self.fields.pop('trilha', None)
        if not incluir_cicatrizado:
            for campo in ('estagio_inicial', 'cicatrizado_elemento', 'cicatrizado_perigo'):
                self.fields.pop(campo, None)

        if 'nex_inicial' in self.fields:
            self.fields['nex_inicial'].required = True
        if 'nivel_inicial' in self.fields:
            self.fields['nivel_inicial'].required = True
            self.fields['nex_paranormal'].required = True
        if 'estagio_inicial' in self.fields:
            self.fields['estagio_inicial'].required = True
        if 'patente_inicial' in self.fields:
            self.fields['patente_inicial'].required = progressao == 'patentes'

        if incluir_treinamento:
            for pericia in pericias.values():
                self.fields[f'grau_pericia_{pericia.pk}'] = forms.ChoiceField(
                    label=f'Grau de treinamento · {pericia.nome}',
                    choices=self.GRAUS_TREINAMENTO,
                    initial='treinado',
                    widget=forms.Select(attrs={'data-skill-training': pericia.pk}),
                )

    def clean(self):
        dados = super().clean()
        progressao = self.progressao or dados
        trilha = dados.get('trilha') or self.trilha_inicial
        estagio_inicial = dados.get('estagio_inicial') or self.estagio_inicial_inicial
        cicatrizado_elemento = (
            dados.get('cicatrizado_elemento') or self.cicatrizado_elemento_inicial
        )
        cicatrizado_perigo = dados.get('cicatrizado_perigo') or self.cicatrizado_perigo_inicial
        if trilha and self.classe:
            if trilha.classe_id != self.classe.pk:
                self.add_error('trilha', 'A trilha não pertence à classe escolhida.')
            else:
                patente = progressao.get('patente_inicial')
                if self.progressao is not None and patente and not isinstance(patente, Patente):
                    patente = Patente.objects.filter(pk=patente).first()
                nivel = (
                    int(progressao['nivel_inicial'])
                    if progressao.get('nivel_inicial') else None
                )
                nex = (
                    int(progressao['nex_inicial'])
                    if progressao.get('nex_inicial') else None
                )
                if self.mesa.sistema_progressao == 'nivel_nex' and nivel:
                    nex = nex_equivalente_por_nivel(nivel)
                elif patente:
                    nex = nex_equivalente_por_nivel(max(1, patente.limite_pd))
                pericias_treinadas = {
                    pericia.slug for pericia in self.pericias.values()
                }
                if self.origem:
                    pericias_treinadas.update(
                        self.origem.pericias_treinadas.values_list('slug', flat=True)
                    )
                if not trilha_atende_pre_requisitos(
                    trilha,
                    classe=self.classe,
                    nex=nex,
                    nivel_experiencia=nivel,
                    estagio=int(estagio_inicial) if estagio_inicial else None,
                    patente=patente,
                    atributos=self.atributos,
                    pericias_treinadas=pericias_treinadas,
                ):
                    self.add_error(
                        'trilha' if 'trilha' in self.fields else None,
                        'A ficha ainda não atende aos pré-requisitos desta trilha.',
                    )

        if cicatrizado_elemento and not cicatrizado_perigo:
            self.add_error(
                'cicatrizado_perigo' if 'cicatrizado_perigo' in self.fields else None,
                'Informe o perigo paranormal enfrentado.',
            )
        if cicatrizado_perigo and not cicatrizado_elemento:
            self.add_error(
                'cicatrizado_elemento' if 'cicatrizado_elemento' in self.fields else None,
                'Escolha o elemento do perigo.',
            )
        if self.classe and self.classe.slug == 'sobrevivente':
            if (
                str(estagio_inicial) == '5'
                and bool(cicatrizado_elemento)
                != bool(cicatrizado_perigo)
            ):
                self.add_error(
                    None, 'No estágio 5, informe o elemento e o perigo de Cicatrizado.',
                )
        if self.incluir_treinamento and not self.livre and self.classe:
            if self.classe.slug == 'sobrevivente':
                aprimoramentos_disponiveis = 0
            else:
                if self.mesa.sistema_progressao == 'nex':
                    nex_efetivo = int(progressao.get('nex_inicial') or 5)
                elif self.mesa.sistema_progressao == 'nivel_nex':
                    nex_efetivo = nex_equivalente_por_nivel(
                        int(progressao.get('nivel_inicial') or 1),
                    )
                else:
                    patente = progressao.get('patente_inicial')
                    if self.progressao is not None and patente and not isinstance(patente, Patente):
                        patente = Patente.objects.filter(pk=patente).first()
                    nex_efetivo = nex_equivalente_por_nivel(
                        max(1, patente.limite_pd) if patente else 1,
                    )
                pericias_por_marco = {
                    'combatente': 2,
                    'especialista': 5,
                    'ocultista': 3,
                }.get(self.classe.slug, 0)
                aprimoramentos_disponiveis = (
                    pericias_por_marco + int(self.atributos.get('intelecto', 1))
                ) * (
                    int(nex_efetivo >= 35) + int(nex_efetivo >= 70)
                )
            graus = {'treinado': 0, 'veterano': 1, 'expert': 2}
            total_aprimoramentos = sum(
                graus.get(dados.get(f'grau_pericia_{pk}', 'treinado'), 0)
                for pk in self.pericias
            )
            if total_aprimoramentos > aprimoramentos_disponiveis:
                self.add_error(
                    None,
                    'Os graus escolhidos excedem os aprimoramentos de perícia '
                    'disponíveis nesta progressão.',
                )
        return dados


class RevisaoFichaForm(forms.Form):
    confirmar = forms.BooleanField(label='Confirmo os dados da ficha', required=True)

    def __init__(self, *args, livre=False, **kwargs):
        super().__init__(*args, **kwargs)
        if livre:
            self.fields['confirmar'].required = False


class HabilidadeFichaForm(forms.ModelForm):
    class Meta:
        model = HabilidadeFicha
        fields = ('nome', 'descricao')
        widgets = {
            'descricao': forms.Textarea(attrs={'rows': 3}),
        }


class FichaPoderForm(forms.Form):
    poder = forms.ModelChoiceField(
        queryset=Poder.objects.none(), label='Poder do catálogo', required=False,
        empty_label='Sem poder do catálogo',
        widget=PoderSelect,
    )
    nome_personalizado = forms.CharField(
        label='Nome', max_length=120, required=False,
    )
    resumo_personalizado = forms.CharField(
        label='Descrição', max_length=1000, required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
    )

    def __init__(self, *args, ficha, ficha_poder=None, **kwargs):
        self.ficha = ficha
        self.ficha_poder = ficha_poder
        super().__init__(*args, **kwargs)
        pericias_treinadas = set(
            ficha.pericias.exclude(grau='destreinado').values_list(
                'pericia__slug', flat=True,
            )
        )
        poderes_existentes = ficha.poderes.filter(poder__isnull=False)
        if ficha_poder:
            poderes_existentes = poderes_existentes.exclude(pk=ficha_poder.pk)
        poderes_escolhidos = set(
            poderes_existentes.values_list('poder__slug', flat=True)
        )
        poderes_atuais = poderes_existentes.values_list('poder_id', 'poder__elemento')
        quantidade_poderes = Counter(poder_id for poder_id, _ in poderes_atuais)
        poderes_elemento = Counter(
            elemento for _, elemento in poderes_atuais if elemento
        )
        elegiveis = {
            poder.pk
            for poder in Poder.objects.order_by('nome')
            if poder_atende_pre_requisitos(
                poder,
                ficha,
                pericias_treinadas=pericias_treinadas,
                poderes_escolhidos=poderes_escolhidos,
                quantidade_poderes_escolhidos=quantidade_poderes,
                poderes_elemento_escolhidos=poderes_elemento,
            )
        }
        self.elegiveis = elegiveis
        if ficha_poder and ficha_poder.poder_id:
            elegiveis.add(ficha_poder.poder_id)
        self.fields['poder'].queryset = Poder.objects.filter(
            pk__in=elegiveis,
        ).order_by('nome')
        if ficha_poder:
            self.initial.setdefault('poder', ficha_poder.poder_id)
            self.initial.setdefault(
                'nome_personalizado',
                ficha_poder.nome_personalizado or (
                    ficha_poder.poder.nome if ficha_poder.poder_id else ''
                ),
            )
            self.initial.setdefault(
                'resumo_personalizado',
                ficha_poder.resumo_personalizado or (
                    ficha_poder.poder.resumo if ficha_poder.poder_id else ''
                ),
            )

    def clean(self):
        dados = super().clean()
        poder = dados.get('poder')
        nome = (dados.get('nome_personalizado') or '').strip()
        resumo = (dados.get('resumo_personalizado') or '').strip()
        if not poder and (not nome or not resumo):
            raise ValidationError('Escolha um poder do catálogo ou informe nome e resumo personalizados.')
        elif poder and poder.pk not in self.elegiveis:
            self.add_error('poder', 'Este poder não atende aos pré-requisitos da ficha.')
        elif poder and len(resumo) > 500:
            self.add_error('resumo_personalizado', 'A descrição de um poder do catálogo deve ter até 500 caracteres.')
        return dados


class FichaRitualForm(forms.Form):
    ritual = forms.ModelChoiceField(
        queryset=Ritual.objects.none(), label='Ritual do catálogo', required=False,
        empty_label='Sem ritual do catálogo',
        widget=RitualSelect,
    )
    nome_personalizado = forms.CharField(
        label='Nome', max_length=120, required=False,
    )
    resumo_personalizado = forms.CharField(
        label='Descrição', max_length=500, required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
    )

    def __init__(self, *args, ficha_ritual=None, **kwargs):
        self.ficha_ritual = ficha_ritual
        super().__init__(*args, **kwargs)
        self.fields['ritual'].queryset = Ritual.objects.order_by('nome')
        if ficha_ritual:
            self.initial.setdefault('ritual', ficha_ritual.ritual_id)
            self.initial.setdefault('nome_personalizado', ficha_ritual.nome_personalizado)
            self.initial.setdefault('resumo_personalizado', ficha_ritual.resumo_personalizado)

    def clean(self):
        dados = super().clean()
        if not dados.get('ritual') and not (
            dados.get('nome_personalizado') and dados.get('resumo_personalizado')
        ):
            raise ValidationError('Escolha um ritual do catálogo ou preencha o placeholder personalizado.')
        return dados


class FichaPericiaAjusteForm(forms.Form):
    grau = forms.ChoiceField(label='Grau de treinamento', choices=FichaPericia.GRAUS)
    dados_extra = forms.IntegerField(
        label='Dados adicionais ou penalidade', min_value=-10, max_value=10,
    )
    bonus_extra = forms.IntegerField(
        label='Modificador numérico', min_value=-100, max_value=100,
    )


class FichaEdicaoForm(forms.Form):
    nome = forms.CharField(label='Nome do personagem', max_length=100)
    jogador = forms.CharField(label='Jogador (opcional)', max_length=80, required=False)
    conceito = forms.CharField(label='Conceito', max_length=240, required=False)
    aparencia = forms.CharField(label='Aparência', max_length=1000, required=False, widget=forms.Textarea(attrs={'rows': 3}))
    personalidade = forms.CharField(label='Personalidade', max_length=1000, required=False, widget=forms.Textarea(attrs={'rows': 3}))
    historia = forms.CharField(label='História', max_length=4000, required=False, widget=forms.Textarea(attrs={'rows': 5}))
    objetivo = forms.CharField(label='Objetivo', max_length=1000, required=False, widget=forms.Textarea(attrs={'rows': 3}))
    pv_max = forms.IntegerField(label='PV máximo', min_value=0, max_value=10000, required=False)
    pe_max = forms.IntegerField(label='PE máximo', min_value=0, max_value=10000, required=False)
    san_max = forms.IntegerField(label='SAN máximo', min_value=0, max_value=10000, required=False)
    pd_max = forms.IntegerField(label='PD máximo', min_value=0, max_value=10000, required=False)
    patente = forms.ModelChoiceField(
        label='Patente', queryset=Patente.objects.none(), required=False,
        empty_label='Sem patente registrada',
    )
    pontos_prestigio = forms.IntegerField(
        label='Pontos de prestígio', min_value=0, max_value=1000000, required=False,
    )
    afinidade_elemento = forms.ChoiceField(
        label='Afinidade elemental',
        choices=(('', 'Sem afinidade'), *Ficha.ELEMENTOS_AFINIDADE),
        required=False,
        help_text='Registre após desenvolver afinidade elemental; exige NEX equivalente de 50% ou mais.',
    )
    anotacoes_jogador = forms.CharField(label='Anotações privadas', max_length=8000, required=False, widget=forms.Textarea(attrs={'rows': 5}))
    anotacoes_mestre = forms.CharField(label='Anotações do mestre', max_length=8000, required=False, widget=forms.Textarea(attrs={'rows': 5}))
    versao = forms.IntegerField(widget=forms.HiddenInput)

    def __init__(self, *args, mestre=False, ficha=None, maximos=None, **kwargs):
        self.ficha = ficha
        super().__init__(*args, **kwargs)
        self.fields['patente'].queryset = Patente.objects.order_by(
            'pontos_prestigio', 'nome',
        )
        if maximos:
            for recurso in ('pv', 'pe', 'san', 'pd'):
                self.initial.setdefault(f'{recurso}_max', maximos[recurso])
        if not mestre:
            self.fields.pop('anotacoes_mestre')

    def clean_afinidade_elemento(self):
        afinidade = self.cleaned_data['afinidade_elemento']
        nex = nex_efetivo(self.ficha) if self.ficha else None
        if afinidade and self.ficha and (nex is None or nex < 50):
            raise ValidationError('Afinidade elemental exige NEX equivalente de pelo menos 50%.')
        return afinidade


class FichaAnotacoesForm(forms.Form):
    anotacoes_jogador = forms.CharField(
        label='Anotações do jogador', max_length=8000, required=False,
        widget=forms.Textarea(attrs={'rows': 7}),
    )
    anotacoes_mestre = forms.CharField(
        label='Anotações do mestre', max_length=8000, required=False,
        widget=forms.Textarea(attrs={'rows': 7}),
    )
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


class AvancoNivelForm(forms.Form):
    nivel_novo = forms.ChoiceField(label='Novo nível de experiência')
    versao = forms.IntegerField(widget=forms.HiddenInput)

    def __init__(self, *args, nivel_atual, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['nivel_novo'].choices = [
            (nivel, str(nivel)) for nivel in range(nivel_atual + 1, 21)
        ]


class ExposicaoParanormalForm(forms.Form):
    exposicao = forms.ChoiceField(
        label='Exposição paranormal',
        choices=(
            ('branda', 'Branda · +0% NEX'),
            ('moderada', 'Moderada · +1% NEX'),
            ('profunda', 'Profunda · +2% NEX'),
            ('total', 'Total · +5% NEX'),
            ('ritual_1', 'Aprender ritual de 1º círculo · +1% NEX'),
            ('ritual_2', 'Aprender ritual de 2º círculo · +2% NEX'),
            ('ritual_3', 'Aprender ritual de 3º círculo · +3% NEX'),
            ('ritual_4', 'Aprender ritual de 4º círculo · +4% NEX'),
        ),
    )
    versao = forms.IntegerField(widget=forms.HiddenInput)

    def __init__(self, *args, nex_atual, **kwargs):
        self.nex_atual = nex_atual
        super().__init__(*args, **kwargs)
        self.fields['exposicao'].help_text = (
            'Altera somente o NEX paranormal. O nível de experiência e as habilidades '
            'de classe permanecem iguais.'
        )

    def clean(self):
        dados = super().clean()
        exposicao = dados.get('exposicao')
        incrementos = {
            'branda': 0, 'moderada': 1, 'profunda': 2, 'total': 5,
            'ritual_1': 1, 'ritual_2': 2, 'ritual_3': 3, 'ritual_4': 4,
        }
        if exposicao and self.nex_atual + incrementos[exposicao] > 99:
            self.add_error('exposicao', 'O NEX não pode ultrapassar 99%.')
        return dados


class RegistroPrestigioForm(forms.Form):
    evento = forms.ChoiceField(label='Evento da missão', choices=RegistroPrestigio.EVENTOS)
    quantidade = forms.IntegerField(label='Quantidade', min_value=1, max_value=999, initial=1)
    versao = forms.IntegerField(widget=forms.HiddenInput)
    numero_sessao = forms.IntegerField(widget=forms.HiddenInput)

    def clean(self):
        dados = super().clean()
        evento = dados.get('evento')
        quantidade = dados.get('quantidade')
        if evento in {'solucao', 'pista'} and quantidade != 1:
            self.add_error('quantidade', 'Registre uma solução ou pista por vez.')
        return dados


class RecuperacaoPatenteForm(forms.Form):
    recurso = forms.ChoiceField(
        label='Recurso para recuperar',
        choices=(('pv_atual', 'PV (dormir)'), ('pd_atual', 'PD (relaxar)')),
    )
    versao = forms.IntegerField(widget=forms.HiddenInput)


class AvancoEstagioForm(forms.Form):
    estagio_novo = forms.ChoiceField(label='Novo estágio')
    versao = forms.IntegerField(widget=forms.HiddenInput)

    def __init__(self, *args, estagio_atual, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['estagio_novo'].choices = [
            (estagio, str(estagio)) for estagio in range(estagio_atual + 1, 6)
        ]


class CicatrizadoForm(forms.Form):
    elemento = forms.ChoiceField(
        label='Elemento do perigo',
        choices=Ficha.ELEMENTOS_CICATRIZADO,
    )
    perigo = forms.CharField(
        label='Perigo específico enfrentado',
        max_length=120,
        help_text='Ex.: uma criatura ou manifestação ligada ao elemento escolhido.',
    )


class UsarCicatrizadoForm(forms.Form):
    efeito = forms.ChoiceField(
        label='Reação de Cicatrizado',
        choices=(
            ('ignorar_mental', 'Sacrificar 1 PV máximo para ignorar dano mental'),
            ('ignorar_custo', 'Sacrificar 1 PV máximo para ignorar um custo de PE/PD'),
            ('reduzir_fisico', 'Sacrificar 1 ponto máximo de PE/PD para reduzir dano físico à metade'),
        ),
    )
    dano_fisico = forms.IntegerField(
        label='Dano físico recebido',
        min_value=1,
        max_value=10000,
        required=False,
    )

    def clean(self):
        dados = super().clean()
        if dados.get('efeito') == 'reduzir_fisico' and dados.get('dano_fisico') is None:
            self.add_error('dano_fisico', 'Informe o dano físico antes de aplicar a redução.')
        elif dados.get('efeito') != 'reduzir_fisico':
            dados['dano_fisico'] = None
        return dados


class FerimentoDebilitanteForm(forms.Form):
    acoes = (
        ('registrar', 'Registrar novo ferimento'),
        ('tratamento', 'Registrar sucesso em Medicina (DT 20)'),
        ('curar', 'Registrar recuperação após dormir'),
    )
    acao = forms.ChoiceField(label='Ação', choices=acoes)
    atributo = forms.ChoiceField(
        label='Atributo afetado',
        choices=FerimentoDebilitante.ATRIBUTOS,
        required=False,
    )
    ferimento = forms.ModelChoiceField(
        label='Ferimento',
        queryset=FerimentoDebilitante.objects.none(),
        required=False,
    )

    def __init__(self, *args, ficha, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ferimento'].queryset = ficha.ferimentos.filter(
            curado_em__isnull=True,
        ).order_by('criado_em', 'pk')

    def clean(self):
        dados = super().clean()
        if dados.get('acao') == 'registrar':
            if not dados.get('atributo'):
                self.add_error('atributo', 'Escolha o atributo afetado pelo ferimento.')
            if dados.get('ferimento'):
                self.add_error('ferimento', 'Não selecione um ferimento ao registrar outro.')
        elif dados.get('acao') in ('tratamento', 'curar'):
            if not dados.get('ferimento'):
                self.add_error('ferimento', 'Escolha um ferimento ativo.')
            if dados.get('atributo'):
                self.add_error('atributo', 'Não escolha um atributo ao atualizar um ferimento.')
        return dados


class ItemInventarioForm(forms.Form):
    nome = forms.CharField(label='Item', max_length=120)
    categoria = forms.ChoiceField(label='Categoria', choices=ItemCatalogo.CATEGORIAS)
    espacos = forms.IntegerField(label='Espaços por unidade', min_value=0, max_value=100)
    quantidade = forms.IntegerField(label='Quantidade', min_value=1, max_value=999)
    estado = forms.ChoiceField(label='Estado', choices=ItemInventario.ESTADOS)
    notas = forms.CharField(label='Descrição', max_length=500, required=False)


class ItemInventarioAjusteForm(forms.Form):
    quantidade = forms.IntegerField(min_value=1, max_value=999)
    estado = forms.ChoiceField(choices=ItemInventario.ESTADOS)


class EncontroCombateForm(forms.ModelForm):
    class Meta:
        model = EncontroCombate
        fields = ('nome',)
        labels = {'nome': 'Nome da cena de combate'}


class ParticipanteCombateForm(forms.ModelForm):
    ficha = forms.ModelChoiceField(
        queryset=Ficha.objects.none(), label='Ficha da mesa (opcional)', required=False,
    )
    ameaca = forms.ModelChoiceField(
        queryset=AmeacaMesa.objects.none(),
        label='Ameaça do bestiário (opcional)',
        required=False,
    )

    class Meta:
        model = ParticipanteCombate
        fields = ('ficha', 'ameaca', 'nome', 'iniciativa', 'surpreendido')
        labels = {
            'nome': 'Nome do participante ou ameaça',
            'iniciativa': 'Resultado de Iniciativa',
            'surpreendido': 'Surpreendido na primeira rodada',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ficha'].queryset = Ficha.objects.filter(status='ativa').order_by('nome')
        self.fields['ameaca'].queryset = AmeacaMesa.objects.filter(ativa=True).order_by('nome')
        self.fields['nome'].required = False
        self.fields['iniciativa'].help_text = 'Role Iniciativa fisicamente e informe o total.'

    def clean(self):
        dados = super().clean()
        ficha = dados.get('ficha')
        ameaca = dados.get('ameaca')
        nome = dados.get('nome', '').strip()
        if ficha:
            if ameaca:
                self.add_error('ameaca', 'Selecione uma ficha ou uma ameaça, não ambas.')
            dados['nome'] = ficha.nome
        elif ameaca and not nome:
            dados['nome'] = ameaca.nome
        elif not nome:
            self.add_error('nome', 'Informe o nome da ameaça ou selecione uma ficha.')
        return dados


class DanoCombateForm(forms.Form):
    dano = forms.IntegerField(label='Dano físico', min_value=1, max_value=1000)


class ConfiguracaoMesaForm(forms.Form):
    modo_recursos = forms.ChoiceField(label='Modo de recursos', choices=ConfiguracaoMesa.MODOS_RECURSOS)
    sistema_progressao = forms.ChoiceField(
        label='Sistema de progressão',
        choices=ConfiguracaoMesa.PROGRESSOES,
    )
    jogador_pode_subir_nex = forms.BooleanField(
        label='Jogadores podem avançar a progressão', required=False,
    )
    ferimentos_debilitantes = forms.BooleanField(
        label='Usar Ferimentos Debilitantes',
        required=False,
    )
    max_fichas_ativas = forms.IntegerField(label='Máximo de fichas ativas', min_value=1, max_value=20)

    def __init__(self, *args, sistema_progressao_atual=None, **kwargs):
        self.sistema_progressao_atual = sistema_progressao_atual
        super().__init__(*args, **kwargs)

    def clean_sistema_progressao(self):
        return self.cleaned_data['sistema_progressao']

    def clean(self):
        dados = super().clean()
        if (
            dados.get('sistema_progressao') == 'patentes'
            and dados.get('modo_recursos') != 'sem_sanidade'
        ):
            self.add_error(
                'modo_recursos',
                'A evolução por patentes usa o modo Sem Sanidade (PV e PD).',
            )
        return dados


class ConfiguracaoFichaForm(forms.Form):
    versao = forms.IntegerField(widget=forms.HiddenInput)
    modo_recursos = forms.ChoiceField(
        label='Modo de recursos', choices=ConfiguracaoMesa.MODOS_RECURSOS,
    )
    sistema_progressao = forms.ChoiceField(
        label='Sistema de progressão', choices=ConfiguracaoMesa.PROGRESSOES,
    )
    ferimentos_debilitantes = forms.BooleanField(
        label='Usar Ferimentos Debilitantes', required=False,
    )
    jogador_pode_subir_nex = forms.BooleanField(
        label='Permitir que o jogador avance a progressão', required=False,
    )
    numero_sessao = forms.IntegerField(
        label='Número da sessão', min_value=1, max_value=1000000,
    )

    def __init__(self, *args, classe=None, **kwargs):
        super().__init__(*args, **kwargs)
        classe_slug = classe.slug if isinstance(classe, Classe) else classe
        if classe_slug == 'sobrevivente':
            self.fields['sistema_progressao'].choices = [
                escolha for escolha in ConfiguracaoMesa.PROGRESSOES
                if escolha[0] != 'patentes'
            ]

    def clean(self):
        dados = super().clean()
        if (
            dados.get('sistema_progressao') == 'patentes'
            and dados.get('modo_recursos') != 'sem_sanidade'
        ):
            self.add_error(
                'modo_recursos',
                'A evolução por patentes usa o modo Sem Sanidade (PV e PD).',
            )
        return dados


class FichaStatusForm(forms.Form):
    status = forms.ChoiceField(
        choices=[(valor, rotulo) for valor, rotulo in Ficha.STATUS if valor in ('ativa', 'arquivada')],
    )
    versao = forms.IntegerField(widget=forms.HiddenInput)


class PendenciaAtributoForm(forms.Form):
    atributo = forms.ChoiceField(
        label='Atributo a aumentar',
        choices=[(nome, nome.replace('_', ' ').capitalize()) for nome in ATRIBUTOS],
    )

    def __init__(self, *args, ficha, **kwargs):
        self.ficha = ficha
        super().__init__(*args, **kwargs)

    def clean_atributo(self):
        atributo = self.cleaned_data['atributo']
        if getattr(self.ficha, atributo) >= 5:
            raise ValidationError('Esse atributo já está no limite.')
        return atributo


class PendenciaTreinamentoForm(forms.Form):
    pericias = forms.ModelMultipleChoiceField(
        queryset=Pericia.objects.none(),
        label='Perícias para aprimorar',
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, ficha, quantidade, **kwargs):
        self.quantidade = quantidade
        super().__init__(*args, **kwargs)
        expert_ids = ficha.pericias.filter(grau='expert').values_list('pericia_id', flat=True)
        self.fields['pericias'].queryset = Pericia.objects.exclude(
            pk__in=expert_ids,
        ).order_by('nome')
        self.fields['pericias'].help_text = f'Selecione exatamente {quantidade} perícia(s).'

    def clean_pericias(self):
        pericias = self.cleaned_data['pericias']
        if len(pericias) != self.quantidade:
            raise ValidationError(f'Selecione exatamente {self.quantidade} perícia(s).')
        return pericias


class EscolhaCatalogoDescrita(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f'{obj.nome} — {obj.resumo} ({obj.fonte})'


class PendenciaTrilhaForm(forms.Form):
    trilha = EscolhaCatalogoDescrita(
        queryset=Trilha.objects.none(),
        label='Trilha e descrição',
        empty_label='Escolha uma trilha do catálogo',
    )

    def __init__(self, *args, ficha, **kwargs):
        super().__init__(*args, **kwargs)
        if ficha.classe_id:
            self.fields['trilha'].queryset = Trilha.objects.filter(
                classe_id=ficha.classe_id,
            ).order_by('nome')

class PendenciaPoderForm(forms.Form):
    poder = EscolhaCatalogoDescrita(
        queryset=Poder.objects.none(),
        label='Habilidade e descrição',
        error_messages={
            'invalid_choice': 'Este poder não atende aos pré-requisitos desta ficha.',
        },
    )

    def __init__(self, *args, ficha, **kwargs):
        self.ficha = ficha
        super().__init__(*args, **kwargs)
        pericias_treinadas = set(
            ficha.pericias.exclude(grau='destreinado').values_list(
                'pericia__slug', flat=True,
            )
        )
        poderes_escolhidos = set(
            ficha.poderes.filter(poder__isnull=False).values_list('poder__slug', flat=True)
        )
        poderes_atuais = ficha.poderes.filter(poder__isnull=False).values_list(
            'poder_id', 'poder__elemento',
        )
        quantidade_poderes_escolhidos = Counter(poder_id for poder_id, _ in poderes_atuais)
        poderes_elemento_escolhidos = Counter(
            elemento for _, elemento in poderes_atuais if elemento
        )
        disponiveis = [
            poder.pk
            for poder in Poder.objects.order_by('nome')
            if poder_atende_pre_requisitos(
                poder,
                ficha,
                pericias_treinadas=pericias_treinadas,
                poderes_escolhidos=poderes_escolhidos,
                quantidade_poderes_escolhidos=quantidade_poderes_escolhidos,
                poderes_elemento_escolhidos=poderes_elemento_escolhidos,
            )
        ]
        self.fields['poder'].queryset = Poder.objects.filter(pk__in=disponiveis).order_by('nome')

    def clean(self):
        dados = super().clean()
        poder = dados.get('poder')
        if poder and not poder_atende_pre_requisitos(poder, self.ficha):
            self.add_error('poder', ValidationError(
                'A ficha não atende aos pré-requisitos estruturados deste poder.',
            ))
        return dados


class PendenciaRitualForm(forms.Form):
    ritual = forms.ModelChoiceField(
        queryset=Ritual.objects.none(),
        label='Ritual do catálogo (opcional)',
        required=False,
    )
    nome_personalizado = forms.CharField(label='Nome', max_length=120, required=False)
    resumo_personalizado = forms.CharField(
        label='Resumo mecânico curto',
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
    )
    circulo_personalizado = forms.ChoiceField(
        label='Círculo do ritual',
        choices=[(circulo, f'{circulo}º') for circulo in range(1, 5)],
        required=False,
    )

    def __init__(self, *args, nivel_nex=False, **kwargs):
        self.nivel_nex = nivel_nex
        super().__init__(*args, **kwargs)
        self.fields['ritual'].queryset = Ritual.objects.order_by('nome')
        self.fields['circulo_personalizado'].required = nivel_nex

    def clean(self):
        dados = super().clean()
        if not dados.get('ritual') and not (dados.get('nome_personalizado') and dados.get('resumo_personalizado')):
            raise ValidationError('Escolha um ritual do catálogo ou informe nome e resumo mecânico curto.')
        if dados.get('ritual'):
            dados['circulo_personalizado'] = str(dados['ritual'].circulo)
        return dados