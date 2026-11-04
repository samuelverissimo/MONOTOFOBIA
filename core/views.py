from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST
from django_ratelimit.decorators import ratelimit

from .forms import AmeacaMesaForm, CenaMesaForm, PistaCenaForm
from .models import AmeacaMesa, CenaMesa, PistaCena, RegistroAmeaca, RegistroCena
from fichas.models import Condicao, ConfiguracaoMesa, Ficha, FichaCondicao, LogAlteracao, Rolagem
from fichas.permissions import fichas_visiveis_para, is_mestre


# Views privadas novas devem usar @login_required ou LoginRequiredMixin.
@login_required
def home(request):
    return render(request, 'home.html', {'fichas': fichas_visiveis_para(request.user)})


@require_GET
def service_worker(request):
    response = render(
        request, 'service-worker.js', content_type='application/javascript; charset=utf-8',
    )
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-cache'
    return response


@login_required
def painel_mestre(request):
    if not is_mestre(request.user):
        raise PermissionDenied
    fichas = Ficha.objects.select_related('dono', 'classe').order_by('status', 'nome', 'pk')
    contagens_status = _contagens_status()
    rolagens = list(Rolagem.objects.select_related(
        'ficha', 'usuario',
    ).order_by('-criada_em', '-pk')[:25])
    status_counts = {
        item['rotulo']: item['total']
        for item in contagens_status
    }
    return render(request, 'core/painel_mestre.html', {
        'fichas': fichas,
        'fichas_ativas': Ficha.objects.filter(status='ativa').order_by('nome', 'pk'),
        'condicoes': Condicao.objects.order_by('categoria', 'nome'),
        'contagens_status': contagens_status,
        'rolagens_recentes': rolagens,
        'cursor_rolagens': max((rolagem.pk for rolagem in rolagens), default=0),
        'numero_sessao': (
            ConfiguracaoMesa.objects.filter(pk=1).values_list('numero_sessao', flat=True).first()
            or 1
        ),
    })


def _contagens_status():
    contagens = {
        item['status']: item['total']
        for item in Ficha.objects.values('status').annotate(total=Count('pk'))
    }
    return [
        {'valor': value, 'rotulo': label, 'total': contagens.get(value, 0)}
        for value, label in Ficha.STATUS
    ]


@login_required
@require_GET
@ratelimit(key='user', rate='120/m', method='GET', block=True)
def atualizacoes_painel_mestre(request):
    if not is_mestre(request.user):
        raise PermissionDenied
    cursor_texto = request.GET.get('desde', '0')
    if not cursor_texto.isdecimal() or len(cursor_texto) > 18:
        return JsonResponse({'erro': 'Cursor de rolagens inválido.'}, status=400)
    cursor = int(cursor_texto)
    fichas = Ficha.objects.select_related('dono', 'classe').order_by('status', 'nome', 'pk')
    novas_rolagens = list(Rolagem.objects.filter(pk__gt=cursor).select_related(
        'ficha', 'usuario',
    ).order_by('pk')[:50])
    cursor_novo = max((rolagem.pk for rolagem in novas_rolagens), default=cursor)
    return JsonResponse({
        'contagens_status': _contagens_status(),
        'fichas': [
            {
                'id': ficha.pk,
                'nome': ficha.nome,
                'jogador': ficha.dono.username,
                'classe': str(ficha.classe) if ficha.classe_id else 'Sem classe',
                'status': ficha.get_status_display(),
            }
            for ficha in fichas
        ],
        'rolagens': [
            {
                'id': rolagem.pk,
                'ficha': rolagem.ficha.nome,
                'descricao': rolagem.descricao,
                'dados': rolagem.dados,
                'bonus': rolagem.bonus,
                'total': rolagem.total,
                'usuario': rolagem.usuario.username,
                'criada_em': rolagem.criada_em.isoformat(),
                'secreta': rolagem.secreta,
            }
            for rolagem in novas_rolagens
        ],
        'cursor': cursor_novo,
    })


@login_required
@require_POST
@ratelimit(key='user', rate='6/m', method='POST', block=True)
def aplicar_condicao_em_grupo(request):
    if not is_mestre(request.user):
        raise PermissionDenied
    ids_texto = request.POST.getlist('fichas')
    condicao_texto = request.POST.get('condicao', '')
    if (
        not ids_texto or len(ids_texto) > 50
        or any(not item.isdecimal() or len(item) > 18 for item in ids_texto)
        or len(set(ids_texto)) != len(ids_texto)
        or not condicao_texto.isdecimal() or len(condicao_texto) > 18
    ):
        messages.error(request, 'Selecione uma condição e de 1 a 50 fichas ativas, sem duplicatas.')
        return redirect('painel_mestre')
    ids = [int(item) for item in ids_texto]
    with transaction.atomic():
        fichas = list(
            Ficha.objects.select_for_update().filter(pk__in=ids, status='ativa').order_by('pk')
        )
        if len(fichas) != len(ids):
            messages.error(request, 'Uma ou mais fichas selecionadas não estão ativas.')
            return redirect('painel_mestre')
        condicao = Condicao.objects.filter(pk=int(condicao_texto)).first()
        if condicao is None:
            messages.error(request, 'A condição selecionada não existe.')
            return redirect('painel_mestre')
        adicionadas = 0
        for ficha in fichas:
            _, criada = FichaCondicao.objects.get_or_create(ficha=ficha, condicao=condicao)
            if criada:
                adicionadas += 1
                LogAlteracao.objects.create(
                    ficha=ficha, usuario=request.user, e_mestre=True,
                    campo='condicao', valor_novo=condicao.nome,
                )
    messages.success(
        request,
        f'{condicao.nome} aplicada a {adicionadas} ficha(s); condições já ativas foram mantidas.',
    )
    return redirect('painel_mestre')


@login_required
def lista_cenas(request):
    mestre = is_mestre(request.user)
    cenas = CenaMesa.objects.all() if mestre else CenaMesa.objects.filter(ativa=True)
    return render(request, 'core/cenas.html', {
        'cenas': cenas,
        'mestre': mestre,
        'formulario_cena': CenaMesaForm() if mestre else None,
    })


@login_required
def detalhe_cena(request, pk):
    mestre = is_mestre(request.user)
    cenas = CenaMesa.objects.all() if mestre else CenaMesa.objects.filter(ativa=True)
    cena = get_object_or_404(cenas, pk=pk)
    pistas = cena.pistas.all() if mestre else cena.pistas.exclude(estado='oculta')
    return render(request, 'core/cena.html', {
        'cena': cena,
        'pistas': pistas,
        'mestre': mestre,
        'estados_pista': PistaCena.ESTADOS if mestre else (),
        'formulario_pista': PistaCenaForm() if mestre else None,
    })


@login_required
@require_POST
@ratelimit(key='user', rate='20/h', method='POST', block=True)
def criar_cena(request):
    if not is_mestre(request.user):
        raise PermissionDenied
    form = CenaMesaForm(request.POST)
    if not form.is_valid():
        return render(request, 'core/cenas.html', {
            'cenas': CenaMesa.objects.all(),
            'mestre': True,
            'formulario_cena': form,
        }, status=400)
    with transaction.atomic():
        cena = form.save(commit=False)
        cena.criado_por = request.user
        cena.save()
        RegistroCena.objects.create(cena=cena, usuario=request.user, acao='criada')
    messages.success(request, 'Cena criada. Ela só aparece aos jogadores quando for ativada.')
    return redirect('detalhe_cena', pk=cena.pk)


@login_required
@require_POST
@ratelimit(key='user', rate='60/h', method='POST', block=True)
def alterar_estado_cena(request, pk):
    if not is_mestre(request.user):
        raise PermissionDenied
    ativo = request.POST.get('ativa')
    if ativo not in {'0', '1'}:
        messages.error(request, 'Estado de publicação inválido.')
        return redirect('detalhe_cena', pk=pk)
    with transaction.atomic():
        cena = get_object_or_404(CenaMesa.objects.select_for_update(), pk=pk)
        cena.ativa = ativo == '1'
        cena.save(update_fields=('ativa', 'atualizada_em'))
        RegistroCena.objects.create(
            cena=cena, usuario=request.user, acao='publicada' if cena.ativa else 'ocultada',
        )
    messages.success(request, 'Cena visível aos jogadores.' if cena.ativa else 'Cena ocultada dos jogadores.')
    return redirect('detalhe_cena', pk=pk)


@login_required
@require_POST
@ratelimit(key='user', rate='30/h', method='POST', block=True)
def adicionar_pista(request, pk):
    if not is_mestre(request.user):
        raise PermissionDenied
    form = PistaCenaForm(request.POST)
    cena = get_object_or_404(CenaMesa, pk=pk)
    if not form.is_valid():
        messages.error(request, 'Confira o título e o conteúdo da pista.')
        return redirect('detalhe_cena', pk=pk)
    with transaction.atomic():
        pista = form.save(commit=False)
        pista.cena = cena
        pista.save()
        RegistroCena.objects.create(
            cena=cena, usuario=request.user, acao=f'pista_criada:{pista.pk}',
        )
    messages.success(request, 'Pista registrada e mantida oculta até ser revelada.')
    return redirect('detalhe_cena', pk=pk)


@login_required
@require_POST
@ratelimit(key='user', rate='60/h', method='POST', block=True)
def alterar_estado_pista(request, pk, pista_pk):
    if not is_mestre(request.user):
        raise PermissionDenied
    estado = request.POST.get('estado')
    if estado not in {'oculta', 'revelada', 'anotada'}:
        messages.error(request, 'Estado de pista inválido.')
        return redirect('detalhe_cena', pk=pk)
    with transaction.atomic():
        cena = get_object_or_404(CenaMesa.objects.select_for_update(), pk=pk)
        pista = get_object_or_404(
            PistaCena.objects.select_for_update().filter(cena=cena), pk=pista_pk,
        )
        pista.estado = estado
        pista.save(update_fields=('estado', 'atualizada_em'))
        RegistroCena.objects.create(
            cena=cena, usuario=request.user, acao=f'pista_{estado}:{pista.pk}',
        )
    messages.success(request, 'Estado da pista atualizado.')
    return redirect('detalhe_cena', pk=pk)


@login_required
def lista_ameacas(request):
    if not is_mestre(request.user):
        raise PermissionDenied
    ameacas = list(AmeacaMesa.objects.all())
    for ameaca in ameacas:
        ameaca.formulario_edicao = AmeacaMesaForm(instance=ameaca)
    return render(request, 'core/ameacas.html', {
        'ameacas': ameacas,
        'formulario': AmeacaMesaForm(),
    })


@login_required
@require_POST
@ratelimit(key='user', rate='20/h', method='POST', block=True)
def criar_ameaca(request):
    if not is_mestre(request.user):
        raise PermissionDenied
    form = AmeacaMesaForm(request.POST)
    if not form.is_valid():
        ameacas = list(AmeacaMesa.objects.all())
        for ameaca in ameacas:
            ameaca.formulario_edicao = AmeacaMesaForm(instance=ameaca)
        return render(request, 'core/ameacas.html', {
            'ameacas': ameacas,
            'formulario': form,
        }, status=400)
    with transaction.atomic():
        ameaca = form.save(commit=False)
        ameaca.criado_por = request.user
        ameaca.save()
        RegistroAmeaca.objects.create(ameaca=ameaca, usuario=request.user, acao='criada')
    messages.success(request, 'Ameaça adicionada ao bestiário privado do mestre.')
    return redirect('lista_ameacas')


@login_required
@require_POST
@ratelimit(key='user', rate='60/h', method='POST', block=True)
def editar_ameaca(request, pk):
    if not is_mestre(request.user):
        raise PermissionDenied
    with transaction.atomic():
        ameaca = get_object_or_404(AmeacaMesa.objects.select_for_update(), pk=pk)
        form = AmeacaMesaForm(request.POST, instance=ameaca)
        if not form.is_valid():
            ameacas = list(AmeacaMesa.objects.all())
            for item in ameacas:
                item.formulario_edicao = (
                    form if item.pk == ameaca.pk else AmeacaMesaForm(instance=item)
                )
            return render(request, 'core/ameacas.html', {
                'ameacas': ameacas,
                'formulario': AmeacaMesaForm(),
            }, status=400)
        form.save()
        RegistroAmeaca.objects.create(ameaca=ameaca, usuario=request.user, acao='editada')
    messages.success(request, 'Registro da ameaça atualizado.')
    return redirect('lista_ameacas')


@login_required
@require_POST
@ratelimit(key='user', rate='60/h', method='POST', block=True)
def alterar_estado_ameaca(request, pk):
    if not is_mestre(request.user):
        raise PermissionDenied
    ativo = request.POST.get('ativa')
    if ativo not in {'0', '1'}:
        messages.error(request, 'Estado do registro inválido.')
        return redirect('lista_ameacas')
    with transaction.atomic():
        ameaca = get_object_or_404(AmeacaMesa.objects.select_for_update(), pk=pk)
        ameaca.ativa = ativo == '1'
        ameaca.save(update_fields=('ativa', 'atualizada_em'))
        RegistroAmeaca.objects.create(ameaca=ameaca, usuario=request.user, acao='editada')
    messages.success(request, 'Registro do bestiário atualizado.')
    return redirect('lista_ameacas')


@login_required
@require_POST
@ratelimit(key='user', rate='6/h', method='POST', block=True)
def iniciar_nova_sessao(request):
    if not is_mestre(request.user):
        raise PermissionDenied
    with transaction.atomic():
        mesa, _ = ConfiguracaoMesa.objects.select_for_update().get_or_create(pk=1)
        mesa.numero_sessao += 1
        mesa.save(update_fields=('numero_sessao',))
    messages.success(
        request,
        f'Sessão {mesa.numero_sessao} iniciada. Os usos por sessão foram renovados.',
    )
    return redirect('painel_mestre')
