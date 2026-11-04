from django import forms

from fichas.models import Ficha

from .models import AmeacaMesa, CenaMesa, Mesa, PistaCena


class CenaMesaForm(forms.ModelForm):
    class Meta:
        model = CenaMesa
        fields = ('nome', 'tipo', 'descricao_jogadores', 'anotacoes_mestre')
        widgets = {
            'descricao_jogadores': forms.Textarea(attrs={'rows': 4}),
            'anotacoes_mestre': forms.Textarea(attrs={'rows': 5}),
        }


class PistaCenaForm(forms.ModelForm):
    class Meta:
        model = PistaCena
        fields = ('titulo', 'conteudo')
        widgets = {'conteudo': forms.Textarea(attrs={'rows': 4})}


class AmeacaMesaForm(forms.ModelForm):
    class Meta:
        model = AmeacaMesa
        fields = (
            'nome', 'categoria', 'defesa', 'pv', 'deslocamento', 'resistencias',
            'vulnerabilidades', 'imunidades', 'acoes', 'anotacoes_mestre',
        )
        widgets = {
            'acoes': forms.Textarea(attrs={'rows': 5}),
            'anotacoes_mestre': forms.Textarea(attrs={'rows': 5}),
        }


class MesaForm(forms.ModelForm):
    class Meta:
        model = Mesa
        fields = ('nome', 'publica')
        labels = {'publica': 'Mesa pública (qualquer jogador pode entrar)'}


class InscreverFichaMesaForm(forms.Form):
    ficha = forms.ModelChoiceField(queryset=Ficha.objects.none(), label='Ficha')
    mesa = forms.ModelChoiceField(
        queryset=Mesa.objects.none(), required=False, label='Mesa pública',
        empty_label='Escolha uma mesa pública',
    )
    codigo_acesso = forms.RegexField(
        regex=r'^[0-9]{8}$',
        required=False,
        min_length=8,
        max_length=8,
        label='Código da mesa privada',
        error_messages={'invalid': 'O código deve conter exatamente 8 dígitos.'},
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ficha'].queryset = Ficha.objects.filter(
            dono=user, status='ativa',
        ).order_by('nome', 'pk')
        self.fields['mesa'].queryset = Mesa.objects.filter(publica=True).order_by('nome', 'pk')

    def clean(self):
        dados = super().clean()
        if 'ficha' not in dados:
            return dados
        if bool(dados.get('mesa')) == bool(dados.get('codigo_acesso')):
            raise forms.ValidationError('Escolha uma mesa pública ou informe o código de uma mesa privada.')
        return dados
