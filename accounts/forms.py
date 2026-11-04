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