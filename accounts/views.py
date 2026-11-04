from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import CreateView
from django_ratelimit.decorators import ratelimit
from django.views.decorators.http import require_http_methods

from .forms import AccountProfileForm, RegisterForm

User = get_user_model()


@method_decorator(
    ratelimit(key='ip', rate='5/h', method='POST', block=True),
    name='dispatch',
)
class RegisterView(CreateView):
    form_class = RegisterForm
    template_name = 'registration/register.html'
    success_url = reverse_lazy('login')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('home')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, 'Cadastro realizado. Você já pode entrar.')
        return super().form_valid(form)


@login_required
@require_http_methods(['GET', 'POST'])
@ratelimit(key='user', rate='10/m', method='POST', block=True)
def profile(request):
    profile_form = AccountProfileForm(
        user=request.user,
        initial={
            'nome': request.user.first_name,
            'username': request.user.username,
            'email': request.user.email,
        },
    )
    password_form = PasswordChangeForm(user=request.user)

    if request.method == 'POST':
        acao = request.POST.get('acao')
        if acao == 'perfil':
            with transaction.atomic():
                user = User._default_manager.select_for_update().get(pk=request.user.pk)
                profile_form = AccountProfileForm(request.POST, user=user)
                if profile_form.is_valid():
                    if (
                        user.is_superuser
                        and profile_form.cleaned_data['tipo_conta'] == 'jogador'
                        and not User._default_manager.select_for_update().filter(
                            is_superuser=True,
                        ).exclude(pk=user.pk).exists()
                    ):
                        profile_form.add_error(
                            'tipo_conta',
                            'Não é possível remover o último mestre da aplicação.',
                        )
                    else:
                        profile_form.save()
                        messages.success(request, 'Perfil atualizado.')
                        return redirect('account_profile')
        elif acao == 'senha':
            password_form = PasswordChangeForm(user=request.user, data=request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, 'Senha alterada com sucesso.')
                return redirect('account_profile')
        else:
            profile_form.add_error(None, 'Ação inválida.')

    return render(request, 'registration/profile.html', {
        'form': profile_form,
        'password_form': password_form,
        'tipo_conta': 'Mestre' if request.user.is_superuser else 'Jogador',
    }, status=400 if request.method == 'POST' else 200)
