from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from django_ratelimit.decorators import ratelimit

from .forms import (
    AmeacaMesaForm,
    CenaMesaForm,
    InscreverFichaMesaForm,
    MesaForm,
    PistaCenaForm,
)
from .models import (
    AmeacaMesa,
    CenaMesa,
    InscricaoMesa,
    Mesa,
    PistaCena,
    RegistroAmeaca,
    RegistroCena,
)
from fichas.forms import ConfiguracaoMesaForm
from fichas.models import (
    Condicao,
    ConfiguracaoFicha,
    ConfiguracaoMesa,
    Ficha,
    FichaCondicao,
    LogAlteracao,
    RegistroPrestigio,
    Rolagem,
)
from fichas.permissions import fichas_visiveis_para, is_mestre
from fichas.views import _configuracao_para_ficha, _maximos_ficha


def _sincronizar_configuracao_individual(ficha):
    mesa = ConfiguracaoMesa.objects.filter(pk=1).first() or ConfiguracaoMesa()
    sistema_progressao = mesa.sistema_progressao
    if ficha.classe_id and ficha.classe.slug == 'sobrevivente' and sistema_progressao == 'patentes':
        sistema_progressao = 'nex'
    ConfiguracaoFicha.objects.update_or_create(
        ficha=ficha,
        defaults={
            'modo_recursos': mesa.modo_recursos,
            'sistema_progressao': sistema_progressao,
            'ferimentos_debilitantes': mesa.ferimentos_debilitantes,
            'jogador_pode_subir_nex': mesa.jogador_pode_subir_nex,
            'numero_sessao': mesa.numero_sessao,
        },
    )


# Views privadas novas devem usar @login_required ou LoginRequiredMixin.
@login_required
def home(request):
    return render(request, 'home.html', {
        'fichas': fichas_visiveis_para(request.user).prefetch_related('mesas'),
        'mestre': is_mestre(request.user),
    })


@login_required
def lista_mesas(request):
    mestre = is_mestre(request.user)
    if mestre:
        return redirect(f'{reverse("painel_mestre")}#mesas')
    mesas_publicas = list(Mesa.objects.filter(publica=True).order_by('nome', 'pk'))
    mesas_inscritas = list(
        Mesa.objects.filter(inscricoes__ficha__dono=request.user).distinct().order_by('nome', 'pk')
    )
    mesas_do_mestre = list(
        Mesa.objects.filter(mestre=request.user).order_by('nome', 'pk')
    ) if mestre else []
    mesas_visiveis = list(dict.fromkeys(mesas_publicas + mesas_inscritas + mesas_do_mestre))
    for mesa in mesas_visiveis:
        mesa.inscricoes_visiveis = list(
            mesa.inscricoes.select_related('ficha__dono').order_by('inscrita_em', 'pk')
        )
    return render(request, 'core/mesas.html', {
        'mestre': mestre,
        'mesas_publicas': mesas_publicas,
        'mesas_inscritas': {mesa.pk for mesa in mesas_inscritas},
        'mesas_do_mestre': mesas_do_mestre,
        'mesas_visiveis': mesas_visiveis,
        'fichas_disponiveis': request.user.fichas.filter(status='ativa').order_by('nome', 'pk'),
        'formulario_inscricao': InscreverFichaMesaForm(user=request.user),
    })


@login_required
@require_POST
@ratelimit(key='user', rate='10/h', method='POST', block=True)
def criar_mesa(request):
    if not is_mestre(request.user):
        raise PermissionDenied
    form = MesaForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Não foi possível criar a mesa. Confira o nome e a visibilidade.')
        return redirect(f'{reverse("painel_mestre")}#mesas')
    mesa = form.save(commit=False)
    mesa.mestre = request.user
    mesa.save()
    if mesa.publica:
        messages.success(request, f'Mesa pública “{mesa.nome}” criada.')
    else:
        messages.success(
            request,
            f'Mesa privada “{mesa.nome}” criada. Código de acesso: {mesa.codigo_acesso}.',
        )
    return redirect(f'{reverse("painel_mestre")}#mesas')


@login_required
@require_POST
@ratelimit(key='user', rate='10/h', method='POST', block=True)
def inscrever_ficha_mesa(request):
    form = InscreverFichaMesaForm(request.POST, user=request.user)
    if not form.is_valid():
        erros = ' '.join(
            str(erro)
            for campo_erros in form.errors.values()
            for erro in campo_erros
        )
        messages.error(request, f'Não foi possível inscrever a ficha: {erros}')
        return redirect('lista_mesas')

    dados = form.cleaned_data
    if dados['mesa']:
        mesa = dados['mesa']
    else:
        mesa = Mesa.objects.filter(
            publica=False, codigo_acesso=dados['codigo_acesso'],
        ).first()
        if mesa is None:
            messages.error(request, 'Código de mesa privada inválido.')
            return redirect('lista_mesas')

    ficha = dados['ficha']
    with transaction.atomic():
        ficha = Ficha.objects.select_for_update().select_related(
            'classe',
        ).get(pk=ficha.pk)
        configuracao_mesa = ConfiguracaoMesa.objects.filter(pk=1).first() or ConfiguracaoMesa()
        configuracao_individual = ConfiguracaoFicha.objects.select_for_update().filter(
            ficha=ficha,
        ).first()
        if (
            configuracao_individual
            and (not ficha.classe_id or ficha.classe.slug != 'sobrevivente')
            and any(
                getattr(configuracao_individual, campo) != getattr(configuracao_mesa, campo)
                for campo in ('modo_recursos', 'sistema_progressao', 'ferimentos_debilitantes')
            )
        ):
            messages.error(
                request,
                'Ajuste modo de recursos, progressão e regras opcionais para coincidir '
                'com a mesa antes de inscrever esta ficha.',
            )
            return redirect('lista_mesas')
        if InscricaoMesa.objects.select_for_update().filter(mesa=mesa, ficha=ficha).exists():
            messages.error(request, 'Esta ficha já está inscrita nessa mesa.')
            return redirect('lista_mesas')
        InscricaoMesa.objects.create(mesa=mesa, ficha=ficha)
        _sincronizar_configuracao_individual(ficha)
    messages.success(request, f'Ficha “{ficha.nome}” inscrita na mesa “{mesa.nome}”.')
    return redirect('lista_mesas')


@login_required
@require_POST
@ratelimit(key='user', rate='30/h', method='POST', block=True)
def remover_inscricao_mesa(request, mesa_pk, ficha_pk):
    mesa = get_object_or_404(Mesa, pk=mesa_pk)
    inscricoes = InscricaoMesa.objects.filter(mesa=mesa, ficha_id=ficha_pk)
    if not is_mestre(request.user) or mesa.mestre_id != request.user.pk:
        inscricoes = inscricoes.filter(ficha__dono=request.user)
    with transaction.atomic():
        inscricao = get_object_or_404(
            inscricoes.select_for_update().select_related('ficha__classe'),
        )
        ficha = Ficha.objects.select_for_update().select_related('classe').get(
            pk=inscricao.ficha_id,
        )
        nome_ficha = ficha.nome
        inscricao.delete()
        if not InscricaoMesa.objects.filter(ficha=ficha).exists():
            _sincronizar_configuracao_individual(ficha)
    messages.success(request, f'Ficha “{nome_ficha}” removida da mesa “{mesa.nome}”.')
    if is_mestre(request.user) and mesa.mestre_id == request.user.pk:
        return redirect(f'{reverse("painel_mestre")}#mesas')
    return redirect('lista_mesas')


@login_required
@require_POST
@ratelimit(key='user', rate='10/h', method='POST', block=True)
def excluir_mesa(request, pk):
    mesa = get_object_or_404(Mesa, pk=pk, mestre=request.user)
    nome = mesa.nome
    with transaction.atomic():
        fichas = list(
            Ficha.objects.select_for_update().select_related('classe').filter(
                inscricoes_mesa__mesa=mesa,
            ).distinct()
        )
        mesa.delete()
        for ficha in fichas:
            if not InscricaoMesa.objects.filter(ficha=ficha).exists():
                _sincronizar_configuracao_individual(ficha)
    messages.success(request, f'Mesa “{nome}” excluída. As fichas não foram apagadas.')
    return redirect(f'{reverse("painel_mestre")}#mesas')


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
    return contexto_painel_mestre(request)


def _recursos_painel_ficha(ficha):
    mesa_ficha = _configuracao_para_ficha(ficha)
    try:
        maximos = _maximos_ficha(ficha, mesa_ficha)
    except ValueError:
        maximos = {'pv': 0, 'pe': 0, 'san': 0, 'pd': 0}
    recursos_ativos = (
        (('pv', 'PV'), ('pe', 'PE'), ('san', 'SAN'))
        if mesa_ficha.modo_recursos == 'padrao'
        else (('pv', 'PV'), ('pd', 'PD'))
    )
    return [
        {
            'chave': chave,
            'rotulo': rotulo,
            'atual': getattr(ficha, f'{chave}_atual'),
            'maximo': maximos[chave],
        }
        for chave, rotulo in recursos_ativos
    ]


def contexto_painel_mestre(
    request, *, formulario_configuracao=None, formulario_cena=None, status=200,
):
    if not is_mestre(request.user):
        raise PermissionDenied
    fichas = list(Ficha.objects.select_related(
        'dono', 'classe', 'patente',
    ).order_by('status', 'nome', 'pk'))
    for ficha in fichas:
        ficha.recursos_painel = _recursos_painel_ficha(ficha)
    filtro_rolagem = request.GET.get('ficha', '')
    rolagens_queryset = Rolagem.objects.select_related(
        'ficha', 'usuario',
    ).order_by('-criada_em', '-pk')
    if filtro_rolagem:
        if not filtro_rolagem.isdecimal():
            return render(request, '404.html', status=404)
        rolagens_queryset = rolagens_queryset.filter(ficha_id=int(filtro_rolagem))
    pagina_rolagens = Paginator(rolagens_queryset, 50).get_page(
        request.GET.get('pagina'),
    )
    rolagens = list(pagina_rolagens.object_list)
    parametros = request.GET.copy()
    parametros.pop('pagina', None)
    url_anterior = ''
    url_proxima = ''
    if pagina_rolagens.has_previous():
        parametros['pagina'] = pagina_rolagens.previous_page_number()
        url_anterior = f'{reverse("painel_mestre")}?{parametros.urlencode()}#historico'
    if pagina_rolagens.has_next():
        parametros['pagina'] = pagina_rolagens.next_page_number()
        url_proxima = f'{reverse("painel_mestre")}?{parametros.urlencode()}#historico'
    mesa = ConfiguracaoMesa.objects.filter(pk=1).first() or ConfiguracaoMesa()
    if formulario_configuracao is None:
        formulario_configuracao = ConfiguracaoMesaForm(initial={
            'modo_recursos': mesa.modo_recursos,
            'sistema_progressao': mesa.sistema_progressao,
            'jogador_pode_subir_nex': mesa.jogador_pode_subir_nex,
            'ferimentos_debilitantes': mesa.ferimentos_debilitantes,
            'max_fichas_ativas': mesa.max_fichas_ativas,
        })
    return render(request, 'core/painel_mestre.html', {
        'fichas': fichas,
        'condicoes': Condicao.objects.order_by('categoria', 'nome'),
        'contagens_status': _contagens_status(),
        'rolagens_recentes': rolagens,
        'rolagens_paginadas': pagina_rolagens,
        'filtro_rolagem': filtro_rolagem,
        'url_anterior_rolagens': url_anterior,
        'url_proxima_rolagens': url_proxima,
        'poll_rolagens': pagina_rolagens.number == 1 and not filtro_rolagem,
        'cursor_rolagens': Rolagem.objects.order_by('-pk').values_list(
            'pk', flat=True,
        ).first() or 0,
        'numero_sessao': mesa.numero_sessao,
        'formulario_configuracao': formulario_configuracao,
        'formulario_mesa': MesaForm(),
        'mesas_mestre': Mesa.objects.filter(mestre=request.user).prefetch_related(
            'inscricoes__ficha__dono',
        ),
        'cenas_mestre': _cenas_para_painel(),
        'formulario_cena': formulario_cena or CenaMesaForm(),
    }, status=status)


def _cenas_para_painel():
    cenas = list(CenaMesa.objects.prefetch_related('pistas'))
    for cena in cenas:
        cena.formulario_pista = PistaCenaForm()
        cena.estados_pista = PistaCena.ESTADOS
    return cenas


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
    fichas = list(Ficha.objects.select_related('dono', 'classe', 'patente').order_by('status', 'nome', 'pk'))
    for ficha in fichas:
        ficha.recursos_painel = _recursos_painel_ficha(ficha)
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
                'selecionavel': ficha.status == 'ativa',
                'recursos': ficha.recursos_painel,
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
    if mestre:
        return redirect(f'{reverse("painel_mestre")}#cenas')
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
        return contexto_painel_mestre(request, formulario_cena=form, status=400)
    with transaction.atomic():
        cena = form.save(commit=False)
        cena.criado_por = request.user
        cena.save()
        RegistroCena.objects.create(cena=cena, usuario=request.user, acao='criada')
    messages.success(request, 'Cena criada. Ela só aparece aos jogadores quando for ativada.')
    return redirect(f'{reverse("painel_mestre")}#cenas')


@login_required
@require_POST
@ratelimit(key='user', rate='60/h', method='POST', block=True)
def alterar_estado_cena(request, pk):
    if not is_mestre(request.user):
        raise PermissionDenied
    ativo = request.POST.get('ativa')
    if ativo not in {'0', '1'}:
        messages.error(request, 'Estado de publicação inválido.')
        return redirect(f'{reverse("painel_mestre")}#cenas')
    with transaction.atomic():
        cena = get_object_or_404(CenaMesa.objects.select_for_update(), pk=pk)
        cena.ativa = ativo == '1'
        cena.save(update_fields=('ativa', 'atualizada_em'))
        RegistroCena.objects.create(
            cena=cena, usuario=request.user, acao='publicada' if cena.ativa else 'ocultada',
        )
    messages.success(request, 'Cena visível aos jogadores.' if cena.ativa else 'Cena ocultada dos jogadores.')
    return redirect(f'{reverse("painel_mestre")}#cenas')


@login_required
@require_POST
@ratelimit(key='user', rate='6/h', method='POST', block=True)
def excluir_cena(request, pk):
    if not is_mestre(request.user):
        raise PermissionDenied
    with transaction.atomic():
        cena = get_object_or_404(CenaMesa.objects.select_for_update(), pk=pk)
        nome = cena.nome
        cena.delete()
    messages.success(request, f'Cena “{nome}” excluída com suas pistas e registros.')
    return redirect(f'{reverse("painel_mestre")}#cenas')


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
        return redirect(f'{reverse("painel_mestre")}#cenas')
    with transaction.atomic():
        pista = form.save(commit=False)
        pista.cena = cena
        pista.save()
        RegistroCena.objects.create(
            cena=cena, usuario=request.user, acao=f'pista_criada:{pista.pk}',
        )
    messages.success(request, 'Pista registrada e mantida oculta até ser revelada.')
    return redirect(f'{reverse("painel_mestre")}#cenas')


@login_required
@require_POST
@ratelimit(key='user', rate='60/h', method='POST', block=True)
def alterar_estado_pista(request, pk, pista_pk):
    if not is_mestre(request.user):
        raise PermissionDenied
    estado = request.POST.get('estado')
    if estado not in {'oculta', 'revelada', 'anotada'}:
        messages.error(request, 'Estado de pista inválido.')
        return redirect(f'{reverse("painel_mestre")}#cenas')
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
    return redirect(f'{reverse("painel_mestre")}#cenas')


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
        ConfiguracaoFicha.objects.update(numero_sessao=mesa.numero_sessao)
    messages.success(
        request,
        f'Sessão {mesa.numero_sessao} iniciada. Os usos por sessão foram renovados.',
    )
    return redirect('painel_mestre')


@login_required
@require_POST
@ratelimit(key='user', rate='3/h', method='POST', block=True)
def limpar_contagem_sessoes(request):
    if not is_mestre(request.user):
        raise PermissionDenied
    with transaction.atomic():
        mesa, _ = ConfiguracaoMesa.objects.select_for_update().get_or_create(pk=1)
        mesa.numero_sessao = 0
        mesa.save(update_fields=('numero_sessao',))
        ConfiguracaoFicha.objects.update(numero_sessao=0)
        RegistroPrestigio.objects.update(numero_sessao=0)
        Ficha.objects.filter(cicatrizado_sessao_usada__isnull=False).update(
            cicatrizado_sessao_usada=None,
        )
    messages.success(
        request,
        'Contagem zerada sem apagar registros. Inicie a próxima sessão para começar em 1.',
    )
    return redirect('painel_mestre')
