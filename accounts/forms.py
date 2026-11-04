from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError
import unicodedata

User = get_user_model()
NOMES_RESERVADOS = {
    'samukamestre',
    'mestre',
    'admin',
    'administrator',
    'root',
    'staff',
    'suporte',
    'moderador',
}


class SecureAuthenticationForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        'invalid_login': 'Usuário ou senha inválidos.',
        'inactive': 'Usuário ou senha inválidos.',
    }


class AccountProfileForm(forms.Form):
    nome = forms.CharField(label='Nome', max_length=150, required=False)
    username = forms.CharField(label='Nome de usuário', max_length=150)
    email = forms.EmailField(label='E-mail', max_length=254)
    tipo_conta = forms.ChoiceField(
        label='Tipo de conta',
        choices=(('jogador', 'Jogador'), ('mestre', 'Mestre')),
    )

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        superusers = User._default_manager.filter(is_superuser=True).exclude(
            pk=user.pk,
        ).count()
        self.fields['tipo_conta'].initial = 'mestre' if user.is_superuser else 'jogador'
        if not user.is_superuser:
            self.fields['tipo_conta'].disabled = True
        if superusers == 0 and user.is_superuser:
            self.fields['tipo_conta'].help_text = (
                'Este é o último mestre; mantenha ao menos uma conta mestre ativa.'
            )
        elif not user.is_superuser:
            self.fields['tipo_conta'].help_text = (
                'Apenas um mestre pode alterar permissões. Contas de jogador não podem '
                'se promover.'
            )

    def clean_username(self):
        username = unicodedata.normalize('NFKC', self.cleaned_data['username']).strip()
        username = User.normalize_username(username).lower()
        chave_reservada = ''.join(
            caractere for caractere in username.casefold() if caractere.isalnum()
        )
        if (
            chave_reservada in NOMES_RESERVADOS
            and username.casefold() != self.user.username.casefold()
        ):
            raise ValidationError('Este nome de usuário não está disponível.')
        if User._default_manager.filter(username__iexact=username).exclude(
            pk=self.user.pk,
        ).exists():
            raise ValidationError('Este nome de usuário já está em uso.')
        return username

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User._default_manager.filter(email__iexact=email).exclude(
            pk=self.user.pk,
        ).exists():
            raise ValidationError('Já existe uma conta com este e-mail.')
        return email

    def clean_tipo_conta(self):
        tipo = self.cleaned_data['tipo_conta']
        if tipo == 'mestre' and not self.user.is_superuser:
            raise ValidationError('Somente um mestre pode conceder permissões de mestre.')
        if tipo == 'jogador' and self.user.is_superuser and not User._default_manager.filter(
            is_superuser=True,
        ).exclude(pk=self.user.pk).exists():
            raise ValidationError('Não é possível remover o último mestre da aplicação.')
        return tipo

    def save(self):
        self.user.username = self.cleaned_data['username']
        self.user.first_name = self.cleaned_data['nome'].strip()
        self.user.email = self.cleaned_data['email']
        mestre = self.cleaned_data['tipo_conta'] == 'mestre'
        self.user.is_superuser = mestre
        self.user.is_staff = mestre
        self.user.save(update_fields=(
            'username', 'first_name', 'email', 'is_superuser', 'is_staff',
        ))
        return self.user


class RegisterForm(UserCreationForm):
    email = forms.EmailField(label='E-mail', max_length=254)

    class Meta:
        model = User
        fields = ('username', 'email')

    def clean_username(self):
        username = unicodedata.normalize('NFKC', self.cleaned_data['username']).strip()
        username = User.normalize_username(username).lower()
        chave_reservada = ''.join(caractere for caractere in username.casefold() if caractere.isalnum())
        if chave_reservada in NOMES_RESERVADOS:
            raise ValidationError('Este nome de usuário não está disponível.')
        if User._default_manager.filter(username__iexact=username).exists():
            raise ValidationError('Este nome de usuário já está em uso.')
        return username

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User._default_manager.filter(email__iexact=email).exists():
            raise ValidationError('Já existe uma conta com este e-mail.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data['username']
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user