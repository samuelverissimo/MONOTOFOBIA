from django import forms

from .models import AmeacaMesa, CenaMesa, PistaCena


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
