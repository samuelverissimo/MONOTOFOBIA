import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django_ratelimit.decorators import ratelimit

from .forms import (
    AtributosFichaForm,
    AvancoNexForm,
    ClasseFichaForm,
    ConceitoFichaForm,
    ConfiguracaoMesaForm,
    FichaEdicaoForm,
    FichaStatusForm,
    ItemInventarioAjusteForm,
    ItemInventarioForm,
    OrigemFichaForm,
    PericiasFichaForm,
    RevisaoFichaForm,
)
from .models import (
    Classe,
    Condicao,
    ConfiguracaoMesa,
    Ficha,
    FichaCondicao,
    FichaPericia,
    ItemInventario,
    LogAlteracao,
    Origem,
    Pericia,
    Pendencia,
    Rolagem,
)
from .permissions import fichas_visiveis_para, is_mestre, pode_editar_ficha
from .regras import (
    ATRIBUTOS,
    NEX_VALIDOS,
    bonus_pericia,
    calcular_pd_max,
    calcular_pe_max,
    calcular_pv_max,
    calcular_san_max,
    capacidade_carga,
    espacos_usados,
    pendencias_ao_subir_nex,
    rolar_teste,
)

SESSAO_WIZARD = 'fichas.criacao'
ETAPAS = ('conceito', 'atributos', 'origem', 'classe', 'pericias', 'revisao')
CAMPOS_AUDITAVEIS = (
    'nome', 'jogador', 'conceito', 'aparencia', 'personalidade', 'historia', 'objetivo',
)


def _mesa_configuracao():
    return ConfiguracaoMesa.objects.filter(pk=1).first() or ConfiguracaoMesa()


@login_required
@require_GET
def iniciar_criacao(request):
    mesa = _mesa_configuracao()
    if request.user.fichas.filter(status='ativa').count() >= mesa.max_fichas_ativas:
        messages.error(request, 'Você já atingiu o limite de fichas ativas da mesa.')
        return redirect('home')
    request.session[SESSAO_WIZARD] = {
        'etapa': 1,
        'livre': bool(is_mestre(request.user) and request.GET.get('livre') == '1'),
        'dados': {},
    }
    return redirect('fichas:criar', etapa=1)


def _classe_da_sessao(dados):
    classe_id = dados.get('classe')
    return Classe.objects.filter(pk=classe_id).first() if classe_id else None


def _origem_da_sessao(dados):
    origem_id = dados.get('origem')
    return Origem.objects.filter(pk=origem_id).first() if origem_id else None


def _formulario(etapa, request, estado):
    dados = estado['dados']
    livre = estado['livre']
    initial = {}
    form_data = request.POST if request.method == 'POST' else None
    if etapa == 1:
        initial = {campo: dados[campo] for campo in ('nome', 'conceito', 'aparencia', 'personalidade', 'historia', 'objetivo') if campo in dados}
        return ConceitoFichaForm(form_data, initial=initial, livre=livre)
    if etapa == 2:
        initial = dados.get('atributos', {})
        return AtributosFichaForm(form_data, initial=initial, livre=livre)
    if etapa == 3:
        initial = {'origem': dados.get('origem')}
        return OrigemFichaForm(form_data, initial=initial, livre=livre)
    if etapa == 4:
        initial = {'classe': dados.get('classe')}
        return ClasseFichaForm(form_data, initial=initial, livre=livre)
    if etapa == 5:
        classe = _classe_da_sessao(dados)
        origem = _origem_da_sessao(dados)
        if not livre and (classe is None or origem is None):
            return None
        initial = {'pericias_escolhidas': dados.get('pericias_escolhidas', [])}
        initial.update({
            f'pericia_obrigatoria_{indice}': pericia_id
            for indice, pericia_id in enumerate(dados.get('pericias_obrigatorias', []))
        })
        return PericiasFichaForm(
            form_data,
            initial=initial,
            classe=classe,
            origem=origem,
            intelecto=int(dados.get('atributos', {}).get('intelecto', 1)),
            livre=livre,
        )
    if etapa == 6:
        return RevisaoFichaForm(form_data, livre=livre)
    return None


def _dados_formulario(etapa, form):
    dados = form.cleaned_data
    if etapa == 3:
        return {'origem': dados['origem'].pk if dados['origem'] else None}
    if etapa == 4:
        return {'classe': dados['classe'].pk if dados['classe'] else None}
    if etapa == 5:
        obrigatorias = [
            dados[f'pericia_obrigatoria_{indice}'].pk
            for indice in range(len(form.classe.pericias_obrigatorias or []))
            if dados.get(f'pericia_obrigatoria_{indice}')
        ] if not form.livre else []
        return {
            'pericias_obrigatorias': obrigatorias,
            'pericias_escolhidas': [item.pk for item in dados.get('pericias_escolhidas', [])],
        }
    if etapa == 6:
        return {}
    if etapa == 2:
        return {'atributos': {nome: dados[nome] for nome in ('agilidade', 'forca', 'intelecto', 'presenca', 'vigor')}}
    return dados


def _criar_ficha(request, estado):
    dados = estado['dados']
    classe = _classe_da_sessao(dados)
    origem = _origem_da_sessao(dados)
    atributos = dados.get('atributos', {})
    validacao_atributos = AtributosFichaForm(atributos, classe=classe, livre=estado['livre'])
    if not validacao_atributos.is_valid():
        return None

    if not estado['livre'] and (classe is None or origem is None):
        return None

    escolhas_pericia = dados.get('pericias_escolhidas', []) + dados.get('pericias_obrigatorias', [])
    if origem:
        escolhas_pericia += list(origem.pericias_treinadas.values_list('pk', flat=True))
    pericias = Pericia.objects.in_bulk(set(escolhas_pericia))
    if len(pericias) != len(set(escolhas_pericia)):
        return None

    sobrevivente = bool(classe and classe.slug == 'sobrevivente')
    argumentos = {
        **atributos,
        'nex': None if sobrevivente else 5,
        'estagio': 1 if sobrevivente else None,
    }
    if classe:
        slug = classe.slug
        if slug not in ('combatente', 'especialista', 'ocultista', 'sobrevivente'):
            return None
        try:
            configuracao = ConfiguracaoMesa.objects.get(pk=1)
        except ConfiguracaoMesa.DoesNotExist:
            configuracao = None
        argumentos.update(
            pv_atual=calcular_pv_max(slug, vigor=atributos['vigor'], nex=5, estagio=1),
            pe_atual=0 if configuracao and configuracao.modo_recursos == 'sem_sanidade' else
            calcular_pe_max(slug, presenca=atributos['presenca'], nex=5, estagio=1),
            san_atual=0 if configuracao and configuracao.modo_recursos == 'sem_sanidade' else
            calcular_san_max(slug, nex=5, estagio=1),
        )
        if configuracao and configuracao.modo_recursos == 'sem_sanidade':
            argumentos['pd_atual'] = calcular_pd_max(slug, presenca=atributos['presenca'], nex=5, estagio=1)

    with transaction.atomic():
        dono = request.user.__class__.objects.select_for_update().get(pk=request.user.pk)
        mesa = ConfiguracaoMesa.objects.select_for_update().filter(pk=1).first() or ConfiguracaoMesa()
        if dono.fichas.filter(status='ativa').count() >= mesa.max_fichas_ativas:
            return None
        ficha = Ficha.objects.create(
            dono=dono,
            nome=dados['nome'],
            conceito=dados.get('conceito', ''),
            aparencia=dados.get('aparencia', ''),
            personalidade=dados.get('personalidade', ''),
            historia=dados.get('historia', ''),
            objetivo=dados.get('objetivo', ''),
            classe=classe,
            origem=origem,
            **argumentos,
        )
        FichaPericia.objects.bulk_create([
            FichaPericia(ficha=ficha, pericia=pericia, grau='treinado')
            for pericia in pericias.values()
        ])
    return ficha


def _ler_json(request, campos):
    if request.content_type != 'application/json':
        return None, JsonResponse({'erro': 'Envie JSON.'}, status=415)
    try:
        conteudo = json.loads(request.body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, JsonResponse({'erro': 'JSON inválido.'}, status=400)
    if type(conteudo) is not dict or set(conteudo) != set(campos):
        return None, JsonResponse({'erro': 'Campos inválidos.'}, status=400)
    return conteudo, None


def _ficha_editavel(request, pk):
    return get_object_or_404(fichas_visiveis_para(request.user), pk=pk)


@login_required
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def alterar_recurso(request, pk):
    conteudo, erro = _ler_json(request, ('recurso', 'delta'))
    if erro:
        return erro
    recursos = {'pv': ('pv_atual', 'ajuste_pv_max'), 'pe': ('pe_atual', 'ajuste_pe_max'),
                'san': ('san_atual', 'ajuste_san_max'), 'pd': ('pd_atual', 'ajuste_pd_max')}
    if type(conteudo['recurso']) is not str or conteudo['recurso'] not in recursos:
        return JsonResponse({'erro': 'Alteração de recurso inválida.'}, status=400)
    if type(conteudo['delta']) is not int or abs(conteudo['delta']) > 1000:
        return JsonResponse({'erro': 'Alteração de recurso inválida.'}, status=400)

    with transaction.atomic():
        ficha = get_object_or_404(Ficha.objects.select_for_update().filter(
            pk=pk, pk__in=fichas_visiveis_para(request.user).values('pk')
        ))
        try:
            configuracao = ConfiguracaoMesa.objects.get(pk=1)
        except ConfiguracaoMesa.DoesNotExist:
            configuracao = None
        modo_recursos = configuracao.modo_recursos if configuracao else 'padrao'
        if modo_recursos == 'sem_sanidade' and conteudo['recurso'] in ('pe', 'san'):
            return JsonResponse({'erro': 'Este recurso não está ativo nesta mesa.'}, status=400)
        if modo_recursos == 'padrao' and conteudo['recurso'] == 'pd':
            return JsonResponse({'erro': 'Este recurso não está ativo nesta mesa.'}, status=400)
        campo, ajuste = recursos[conteudo['recurso']]
        atual = getattr(ficha, campo)
        novo = atual + conteudo['delta']
        if ficha.classe_id:
            slug = ficha.classe.slug
            if conteudo['recurso'] == 'pv':
                maximo = calcular_pv_max(slug, ficha.vigor, ficha.nex or 5, ficha.estagio or 1, getattr(ficha, ajuste))
            elif conteudo['recurso'] == 'pe':
                maximo = calcular_pe_max(slug, ficha.presenca, ficha.nex or 5, ficha.estagio or 1, getattr(ficha, ajuste))
            elif conteudo['recurso'] == 'san':
                maximo = calcular_san_max(slug, ficha.nex or 5, ficha.estagio or 1, getattr(ficha, ajuste))
            else:
                maximo = calcular_pd_max(slug, ficha.presenca, ficha.nex or 5, ficha.estagio or 1, getattr(ficha, ajuste))
        else:
            maximo = 0
        if novo < 0 or novo > maximo:
            return JsonResponse({'erro': 'O valor precisa ficar entre zero e o máximo.'}, status=400)
        setattr(ficha, campo, novo)
        ficha.save(update_fields=(campo, 'atualizada_em'))
        LogAlteracao.objects.create(
            ficha=ficha, usuario=request.user, e_mestre=is_mestre(request.user),
            campo=campo, valor_antigo=str(atual), valor_novo=str(novo),
        )
    return JsonResponse({'recurso': conteudo['recurso'], 'atual': novo, 'maximo': maximo})


@login_required
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def alterar_condicao(request, pk):
    conteudo, erro = _ler_json(request, ('acao', 'condicao'))
    if erro:
        return erro
    if type(conteudo['acao']) is not str or conteudo['acao'] not in ('adicionar', 'remover') or type(conteudo['condicao']) is not int:
        return JsonResponse({'erro': 'Operação inválida.'}, status=400)
    ficha = _ficha_editavel(request, pk)
    condicao = get_object_or_404(Condicao, pk=conteudo['condicao'])
    with transaction.atomic():
        if conteudo['acao'] == 'adicionar':
            _, criada = FichaCondicao.objects.get_or_create(ficha=ficha, condicao=condicao)
            ativa = True
        else:
            quantidade, _ = FichaCondicao.objects.filter(ficha=ficha, condicao=condicao).delete()
            criada = quantidade > 0
            ativa = False
        if criada:
            LogAlteracao.objects.create(
                ficha=ficha, usuario=request.user, e_mestre=is_mestre(request.user),
                campo='condicao', valor_antigo='' if ativa else condicao.nome,
                valor_novo=condicao.nome if ativa else '',
            )
    return JsonResponse({'condicao': condicao.pk, 'ativa': ativa})


@login_required
@require_POST
def adicionar_item(request, pk):
    ficha = _ficha_editavel(request, pk)
    form = ItemInventarioForm(request.POST)
    if not form.is_valid():
        return render(
            request, 'fichas/detalhe.html',
            _contexto_detalhe(request, ficha, formulario_item=form), status=400,
        )
    with transaction.atomic():
        ficha = Ficha.objects.select_for_update().get(pk=ficha.pk)
        item = ItemInventario.objects.create(ficha=ficha, **form.cleaned_data)
        LogAlteracao.objects.create(
            ficha=ficha, usuario=request.user, e_mestre=is_mestre(request.user),
            campo='inventario', valor_novo=item.nome,
        )
    messages.success(request, 'Item adicionado ao inventário.')
    return redirect('fichas:detalhe', pk=pk)


@login_required
@require_POST
def atualizar_item(request, pk, item_pk):
    ficha = _ficha_editavel(request, pk)
    item = get_object_or_404(ItemInventario.objects.filter(ficha=ficha), pk=item_pk)
    form = ItemInventarioAjusteForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Quantidade ou estado inválido; o item não foi alterado.')
        return redirect('fichas:detalhe', pk=pk)
    with transaction.atomic():
        item = get_object_or_404(
            ItemInventario.objects.select_for_update().filter(ficha=ficha), pk=item_pk
        )
        antigo = {'quantidade': item.quantidade, 'estado': item.estado}
        novo = form.cleaned_data
        for campo, valor in novo.items():
            setattr(item, campo, valor)
        item.save(update_fields=('quantidade', 'estado'))
        for campo, valor in novo.items():
            if antigo[campo] != valor:
                LogAlteracao.objects.create(
                    ficha=ficha, usuario=request.user, e_mestre=is_mestre(request.user),
                    campo=f'inventario.{campo}', valor_antigo=str(antigo[campo]), valor_novo=str(valor),
                )
    messages.success(request, 'Item atualizado.')
    return redirect('fichas:detalhe', pk=pk)


@login_required
@require_POST
def remover_item(request, pk, item_pk):
    ficha = _ficha_editavel(request, pk)
    with transaction.atomic():
        item = get_object_or_404(
            ItemInventario.objects.select_for_update().filter(ficha=ficha), pk=item_pk
        )
        nome = item.nome
        item.delete()
        LogAlteracao.objects.create(
            ficha=ficha, usuario=request.user, e_mestre=is_mestre(request.user),
            campo='inventario', valor_antigo=nome,
        )
    messages.success(request, 'Item removido do inventário.')
    return redirect('fichas:detalhe', pk=pk)


@login_required
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def rolar_ficha(request, pk):
    conteudo, erro = _ler_json(request, ('tipo', 'alvo', 'bonus'))
    if erro:
        return erro
    if conteudo['tipo'] not in ('atributo', 'pericia', 'livre') or type(conteudo['bonus']) is not int or abs(conteudo['bonus']) > 100:
        return JsonResponse({'erro': 'Parâmetros de rolagem inválidos.'}, status=400)
    ficha = _ficha_editavel(request, pk)
    if conteudo['tipo'] == 'atributo':
        if conteudo['alvo'] not in ATRIBUTOS:
            return JsonResponse({'erro': 'Atributo inválido.'}, status=400)
        descricao = conteudo['alvo'].capitalize()
        resultado = rolar_teste(getattr(ficha, conteudo['alvo']), bonus=conteudo['bonus'])
    elif conteudo['tipo'] == 'pericia':
        if type(conteudo['alvo']) is not int:
            return JsonResponse({'erro': 'Perícia inválida.'}, status=400)
        pericia = get_object_or_404(Pericia, pk=conteudo['alvo'])
        ficha_pericia = ficha.pericias.filter(pericia=pericia).first()
        grau = ficha_pericia.grau if ficha_pericia else 'destreinado'
        bonus_treino = ficha_pericia.bonus_extra if ficha_pericia else 0
        resultado = rolar_teste(
            getattr(ficha, pericia.atributo),
            bonus_pericia=bonus_pericia(grau, bonus_extra=bonus_treino),
            bonus=conteudo['bonus'],
        )
        descricao = pericia.nome
    else:
        if type(conteudo['alvo']) is not int or not 1 <= conteudo['alvo'] <= 10:
            return JsonResponse({'erro': 'A quantidade de dados deve ficar entre um e dez.'}, status=400)
        resultado = rolar_teste(1, dados_extras=conteudo['alvo'] - 1, bonus=conteudo['bonus'])
        descricao = f'{conteudo["alvo"]}d20 livre'

    rolagem = Rolagem.objects.create(
        ficha=ficha,
        usuario=request.user,
        tipo=conteudo['tipo'],
        descricao=descricao,
        dados=resultado['dados'],
        dado_escolhido=resultado['dado_escolhido'],
        bonus=resultado['bonus'],
        total=resultado['total'],
    )
    return JsonResponse({
        'id': rolagem.pk,
        'descricao': rolagem.descricao,
        'dados': rolagem.dados,
        'dado_escolhido': rolagem.dado_escolhido,
        'bonus': rolagem.bonus,
        'total': rolagem.total,
    })


@login_required
def criar_ficha(request, etapa):
    estado = request.session.get(SESSAO_WIZARD)
    if not estado or etapa != estado.get('etapa') or not 1 <= etapa <= len(ETAPAS):
        return redirect('fichas:iniciar')
    estado['livre'] = bool(estado.get('livre') and is_mestre(request.user))
    if request.method == 'POST' and 'voltar' in request.POST and etapa > 1:
        estado['etapa'] = etapa - 1
        request.session[SESSAO_WIZARD] = estado
        return redirect('fichas:criar', etapa=etapa - 1)
    form = _formulario(etapa, request, estado)
    if form is None:
        request.session.pop(SESSAO_WIZARD, None)
        messages.error(request, 'Não foi possível continuar a criação da ficha. Inicie novamente.')
        return redirect('fichas:iniciar')

    if request.method == 'POST' and form.is_valid():
        estado['dados'].update(_dados_formulario(etapa, form))
        if etapa == 4 and not estado['livre']:
            classe = form.cleaned_data['classe']
            atributos_form = AtributosFichaForm(
                estado['dados'].get('atributos', {}), classe=classe
            )
            if not atributos_form.is_valid():
                estado['etapa'] = 2
                request.session[SESSAO_WIZARD] = estado
                messages.error(request, 'Atributos incompatíveis com a classe escolhida. Ajuste a distribuição.')
                return redirect('fichas:criar', etapa=2)
        if etapa == len(ETAPAS):
            ficha = _criar_ficha(request, estado)
            if ficha is None:
                mesa = _mesa_configuracao()
                if request.user.fichas.filter(status='ativa').count() >= mesa.max_fichas_ativas:
                    request.session.pop(SESSAO_WIZARD, None)
                    messages.error(request, 'Você já atingiu o limite de fichas ativas da mesa.')
                    return redirect('home')
                form.add_error(None, 'Os dados da sessão não passaram pela validação final. Inicie novamente.')
                request.session.pop(SESSAO_WIZARD, None)
                return render(request, 'fichas/wizard.html', {
                    'form': form, 'etapa': etapa, 'etapa_nome': ETAPAS[etapa - 1],
                    'etapas': ETAPAS, 'livre': estado['livre'],
                })
            request.session.pop(SESSAO_WIZARD, None)
            messages.success(request, 'Ficha criada.')
            return redirect('fichas:detalhe', pk=ficha.pk)
        estado['etapa'] = etapa + 1
        request.session[SESSAO_WIZARD] = estado
        return redirect('fichas:criar', etapa=etapa + 1)

    request.session[SESSAO_WIZARD] = estado
    classe = _classe_da_sessao(estado['dados']) if etapa == 6 else None
    origem = _origem_da_sessao(estado['dados']) if etapa == 6 else None
    return render(request, 'fichas/wizard.html', {
        'form': form,
        'etapa': etapa,
        'etapa_nome': ETAPAS[etapa - 1],
        'etapas': ETAPAS,
        'livre': estado['livre'],
        'revisao': {
            **estado['dados'],
            'classe_nome': classe.nome if classe else 'Sem classe',
            'origem_nome': origem.nome if origem else 'Sem origem',
        } if etapa == 6 else None,
    })


def _contexto_detalhe(request, ficha, formulario_avanco=None, formulario_item=None):
    ativas = ficha.condicoes.select_related('condicao').order_by('condicao__nome')
    ids_condicoes_ativas = ativas.values_list('condicao_id', flat=True)
    classe = ficha.classe.slug if ficha.classe_id else None
    argumentos = {'nex': ficha.nex or 5, 'estagio': ficha.estagio or 1}
    maximos = {'pv': 0, 'pe': 0, 'san': 0, 'pd': 0}
    if classe:
        maximos.update(
            pv=calcular_pv_max(classe, ficha.vigor, **argumentos, ajuste=ficha.ajuste_pv_max),
            pe=calcular_pe_max(classe, ficha.presenca, **argumentos, ajuste=ficha.ajuste_pe_max),
            san=calcular_san_max(classe, **argumentos, ajuste=ficha.ajuste_san_max),
            pd=calcular_pd_max(classe, ficha.presenca, **argumentos, ajuste=ficha.ajuste_pd_max),
        )
    mesa = ConfiguracaoMesa.objects.filter(pk=1).first() or ConfiguracaoMesa()
    pode_avancar = bool(
        classe and classe != 'sobrevivente' and ficha.nex is not None
        and any(nex > ficha.nex for nex in NEX_VALIDOS)
        and mesa.sistema_progressao == 'nex'
        and (is_mestre(request.user) or (
            ficha.dono_id == request.user.pk and mesa.jogador_pode_subir_nex
        ))
    )
    if formulario_avanco is None and pode_avancar:
        proximo_nex = next((nex for nex in NEX_VALIDOS if nex > ficha.nex), '')
        formulario_avanco = AvancoNexForm(
            nex_atual=ficha.nex,
            initial={'nex_novo': proximo_nex, 'versao': ficha.versao},
        )
    pode_editar = pode_editar_ficha(request.user, ficha)
    if formulario_item is None and pode_editar:
        formulario_item = ItemInventarioForm()
    itens_inventario = list(ficha.inventario.order_by('nome', 'pk'))
    carga_usada = espacos_usados(itens_inventario)
    carga_maxima = capacidade_carga(ficha.forca)
    return {
        'ficha': ficha,
        'ficha_pericias': ficha.pericias.select_related('pericia').order_by('pericia__nome'),
        'condicoes_ativas': ativas,
        'condicoes_disponiveis': Condicao.objects.exclude(pk__in=ids_condicoes_ativas).order_by('nome'),
        'atributos': ATRIBUTOS,
        'maximos': maximos,
        'modo_recursos': mesa.modo_recursos,
        'pendencias': ficha.pendencias.filter(resolvida=False).order_by('criada_em', 'pk'),
        'pode_avancar_nex': pode_avancar,
        'formulario_avanco': formulario_avanco,
        'formulario_item': formulario_item,
        'itens_inventario': itens_inventario,
        'carga_usada': carga_usada,
        'carga_maxima': carga_maxima,
        'carga_excedida': carga_usada > carga_maxima,
        'pode_editar': pode_editar,
        'estados_item': ItemInventario.ESTADOS,
        'mestre': is_mestre(request.user),
    }


@login_required
def detalhe_ficha(request, pk):
    ficha = get_object_or_404(fichas_visiveis_para(request.user), pk=pk)
    return render(request, 'fichas/detalhe.html', _contexto_detalhe(request, ficha))


@login_required
@require_POST
def alterar_status_ficha(request, pk):
    ficha = _ficha_editavel(request, pk)
    form = FichaStatusForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Status inválido; a ficha não foi alterada.')
        return redirect('fichas:detalhe', pk=pk)

    with transaction.atomic():
        ficha = Ficha.objects.select_for_update().filter(pk=pk).first()
        if ficha is None:
            return render(request, '404.html', status=404)
        if ficha.versao != form.cleaned_data['versao']:
            messages.error(request, 'A ficha mudou em outra sessão. Recarregue antes de alterar o status.')
            return redirect('fichas:detalhe', pk=pk)
        status_novo = form.cleaned_data['status']
        if ficha.status not in ('ativa', 'arquivada') or ficha.status == status_novo:
            messages.error(request, 'Esta transição de status não é permitida.')
            return redirect('fichas:detalhe', pk=pk)
        if status_novo == 'ativa':
            dono = request.user.__class__.objects.select_for_update().get(pk=ficha.dono_id)
            mesa = ConfiguracaoMesa.objects.select_for_update().filter(pk=1).first() or ConfiguracaoMesa()
            ativas = dono.fichas.filter(status='ativa').exclude(pk=ficha.pk).count()
            if ativas >= mesa.max_fichas_ativas:
                messages.error(request, 'O limite de fichas ativas já foi atingido.')
                return redirect('fichas:detalhe', pk=pk)
        agora = timezone.now()
        atualizados = Ficha.objects.filter(pk=pk, versao=form.cleaned_data['versao']).update(
            status=status_novo, versao=F('versao') + 1, atualizada_em=agora,
        )
        if not atualizados:
            messages.error(request, 'A ficha mudou em outra sessão. Recarregue antes de alterar o status.')
            return redirect('fichas:detalhe', pk=pk)
        LogAlteracao.objects.create(
            ficha=ficha, usuario=request.user, e_mestre=is_mestre(request.user),
            campo='status', valor_antigo=ficha.status, valor_novo=status_novo,
        )
    messages.success(request, 'Status da ficha atualizado.')
    return redirect('fichas:detalhe', pk=pk)


@login_required
@require_POST
def avancar_nex(request, pk):
    ficha = get_object_or_404(fichas_visiveis_para(request.user), pk=pk)
    mesa = ConfiguracaoMesa.objects.filter(pk=1).first() or ConfiguracaoMesa()
    autorizado = is_mestre(request.user) or (
        ficha.dono_id == request.user.pk and mesa.jogador_pode_subir_nex
    )
    if not autorizado:
        return HttpResponseForbidden('Somente o mestre pode avançar o NEX nesta mesa.')
    if (
        not ficha.classe_id or ficha.classe.slug == 'sobrevivente' or ficha.nex is None
        or mesa.sistema_progressao != 'nex'
        or ficha.classe.slug not in ('combatente', 'especialista', 'ocultista')
    ):
        messages.error(request, 'Esta ficha não usa progressão padrão por NEX.')
        return redirect('fichas:detalhe', pk=pk)

    form = AvancoNexForm(request.POST, nex_atual=ficha.nex)
    if not form.is_valid():
        return render(request, 'fichas/detalhe.html', _contexto_detalhe(request, ficha, form), status=400)
    nex_novo = int(form.cleaned_data['nex_novo'])
    versao = form.cleaned_data['versao']

    with transaction.atomic():
        atual = Ficha.objects.select_for_update().filter(pk=pk).first()
        if atual is None:
            return render(request, '404.html', status=404)
        mesa_atual = ConfiguracaoMesa.objects.filter(pk=1).first() or ConfiguracaoMesa()
        autorizado_atual = is_mestre(request.user) or (
            atual.dono_id == request.user.pk and mesa_atual.jogador_pode_subir_nex
        )
        if not autorizado_atual:
            return HttpResponseForbidden('Somente o mestre pode avançar o NEX nesta mesa.')
        if mesa_atual.sistema_progressao != 'nex':
            messages.error(request, 'A mesa não está usando progressão padrão por NEX.')
            return redirect('fichas:detalhe', pk=pk)
        if atual.versao != versao or atual.nex != ficha.nex:
            form.add_error(None, 'A ficha mudou em outra sessão. Recarregue antes de avançar.')
            return render(request, 'fichas/detalhe.html', _contexto_detalhe(request, atual, form), status=409)
        if atual.classe_id is None or atual.classe.slug not in ('combatente', 'especialista', 'ocultista'):
            messages.error(request, 'Esta ficha não usa progressão padrão por NEX.')
            return redirect('fichas:detalhe', pk=pk)
        try:
            pendencias = pendencias_ao_subir_nex(
                atual.classe.slug, atual.nex, nex_novo, intelecto=atual.intelecto
            )
        except ValueError as erro:
            form.add_error('nex_novo', str(erro))
            return render(request, 'fichas/detalhe.html', _contexto_detalhe(request, atual, form), status=400)

        agora = timezone.now()
        atualizados = Ficha.objects.filter(pk=pk, versao=versao, nex=ficha.nex).update(
            nex=nex_novo, versao=F('versao') + 1, atualizada_em=agora,
        )
        if not atualizados:
            form.add_error(None, 'A ficha mudou em outra sessão. Recarregue antes de avançar.')
            return render(request, 'fichas/detalhe.html', _contexto_detalhe(request, atual, form), status=409)
        Pendencia.objects.bulk_create([
            Pendencia(
                ficha=atual,
                tipo=pendencia['tipo'],
                descricao=pendencia['descricao'],
                fonte=pendencia['fonte'],
            )
            for pendencia in pendencias
        ])
        LogAlteracao.objects.create(
            ficha=atual, usuario=request.user, e_mestre=is_mestre(request.user),
            campo='nex', valor_antigo=str(ficha.nex), valor_novo=str(nex_novo),
        )
    messages.success(request, f'NEX avançado para {nex_novo}%. Escolhas pendentes foram registradas.')
    return redirect('fichas:detalhe', pk=pk)


@login_required
def editar_ficha(request, pk):
    ficha = get_object_or_404(fichas_visiveis_para(request.user), pk=pk)
    mestre = is_mestre(request.user)
    if request.method == 'POST':
        form = FichaEdicaoForm(request.POST, mestre=mestre)
        if form.is_valid():
            valores = {
                campo: form.cleaned_data[campo]
                for campo in form.fields
                if campo not in ('versao', 'anotacoes_mestre')
            }
            if mestre:
                valores['anotacoes_mestre'] = form.cleaned_data['anotacoes_mestre']
            agora = timezone.now()
            with transaction.atomic():
                atualizados = Ficha.objects.filter(pk=pk, versao=form.cleaned_data['versao']).update(
                    **valores, versao=F('versao') + 1, atualizada_em=agora
                )
                if atualizados:
                    LogAlteracao.objects.bulk_create([
                        LogAlteracao(
                            ficha=ficha,
                            usuario=request.user,
                            e_mestre=mestre,
                            campo=campo,
                            valor_antigo=str(getattr(ficha, campo))[:500],
                            valor_novo=str(valores[campo])[:500],
                        )
                        for campo in CAMPOS_AUDITAVEIS
                        if campo in valores and getattr(ficha, campo) != valores[campo]
                    ])
            if not atualizados:
                form.add_error(None, 'A ficha foi alterada em outra sessão. Recarregue antes de editar.')
                return render(request, 'fichas/editar.html', {'form': form, 'ficha': ficha}, status=409)
            messages.success(request, 'Alterações salvas.')
            return redirect('fichas:detalhe', pk=pk)
    else:
        form = FichaEdicaoForm(
            initial={
                campo: getattr(ficha, campo)
                for campo in FichaEdicaoForm(mestre=mestre).fields
                if hasattr(ficha, campo)
            },
            mestre=mestre,
        )
    return render(request, 'fichas/editar.html', {'form': form, 'ficha': ficha})


@login_required
def configurar_mesa(request):
    if not is_mestre(request.user):
        return HttpResponseForbidden('Somente o mestre pode configurar a mesa.')
    mesa = ConfiguracaoMesa.objects.filter(pk=1).first()
    if mesa is None:
        mesa = ConfiguracaoMesa.objects.create()
    if request.method == 'POST':
        form = ConfiguracaoMesaForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                mesa = ConfiguracaoMesa.objects.select_for_update().get(pk=1)
                for campo, valor in form.cleaned_data.items():
                    setattr(mesa, campo, valor)
                mesa.save(update_fields=tuple(form.cleaned_data))
            messages.success(request, 'Configurações da mesa salvas.')
            return redirect('fichas:configurar_mesa')
    else:
        form = ConfiguracaoMesaForm(initial={
            'modo_recursos': mesa.modo_recursos,
            'jogador_pode_subir_nex': mesa.jogador_pode_subir_nex,
            'max_fichas_ativas': mesa.max_fichas_ativas,
        })
    return render(request, 'fichas/configuracao_mesa.html', {'form': form, 'mesa': mesa})