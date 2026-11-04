import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django_ratelimit.decorators import ratelimit

from .forms import (
    AtributosFichaForm,
    AvancoEstagioForm,
    AvancoNivelForm,
    AvancoNexForm,
    CicatrizadoForm,
    ClasseFichaForm,
    ConceitoFichaForm,
    ConfiguracaoMesaForm,
    DanoCombateForm,
    EncontroCombateForm,
    ExposicaoParanormalForm,
    FichaEdicaoForm,
    FichaStatusForm,
    FerimentoDebilitanteForm,
    ItemInventarioAjusteForm,
    ItemInventarioForm,
    PendenciaAtributoForm,
    PendenciaPoderForm,
    PendenciaRitualForm,
    PendenciaTrilhaForm,
    PendenciaTreinamentoForm,
    OrigemFichaForm,
    PericiasFichaForm,
    ParticipanteCombateForm,
    RecuperacaoPatenteForm,
    RegistroPrestigioForm,
    RevisaoFichaForm,
    UsarCicatrizadoForm,
)
from .efeitos import explicar_teste
from .models import (
    Classe,
    Condicao,
    ConfiguracaoMesa,
    EncontroCombate,
    Ficha,
    FichaCondicao,
    FerimentoDebilitante,
    FichaPoder,
    FichaPericia,
    FichaRitual,
    ItemInventario,
    LogAlteracao,
    Origem,
    Patente,
    Pericia,
    ParticipanteCombate,
    Pendencia,
    RegistroPrestigio,
    Rolagem,
)
from .permissions import fichas_visiveis_para, is_mestre, pode_editar_ficha
from .regras import (
    ATRIBUTOS,
    NEX_VALIDOS,
    avaliar_dano_fisico,
    bonus_pericia,
    calcular_defesa,
    calcular_pd_max,
    calcular_pe_max,
    calcular_pv_max,
    calcular_san_max,
    capacidade_carga,
    espacos_usados,
    avaliar_teste_fisico,
    limite_pe_por_turno,
    modificadores_condicoes,
    nex_equivalente_por_nivel,
    pendencias_ao_subir_nex,
    pendencias_ao_subir_estagio,
    rolar_dano,
    rolar_teste,
)

SESSAO_WIZARD = 'fichas.criacao'
ETAPAS = ('conceito', 'atributos', 'origem', 'classe', 'pericias', 'revisao')
CAMPOS_AUDITAVEIS = (
    'nome', 'jogador', 'conceito', 'aparencia', 'personalidade', 'historia', 'objetivo',
)


def _mesa_configuracao():
    return ConfiguracaoMesa.objects.filter(pk=1).first() or ConfiguracaoMesa()


def _limite_recurso_turno(ficha, recurso, mesa):
    if recurso == 'pe':
        if mesa.modo_recursos != 'padrao':
            return None
        if ficha.classe_id and ficha.classe.slug == 'sobrevivente':
            nivel = 1
        elif ficha.patente_id:
            nivel = ficha.patente.limite_pd
        elif mesa.sistema_progressao == 'nivel_nex' and ficha.nivel_experiencia:
            nivel = ficha.nivel_experiencia
        else:
            nivel = ficha.nex or 5
        return limite_pe_por_turno(
            nex=nivel,
            classe=ficha.classe.slug if ficha.classe_id else 'combatente',
            ajuste=ficha.limite_pe_bonus,
        )
    if recurso == 'pd' and mesa.modo_recursos == 'sem_sanidade' and ficha.patente_id:
        return ficha.patente.limite_pd
    return None


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

    configuracao = _mesa_configuracao()
    usa_nivel_experiencia = configuracao.sistema_progressao == 'nivel_nex'
    usa_patentes = configuracao.sistema_progressao == 'patentes'
    sobrevivente = bool(classe and classe.slug == 'sobrevivente')
    if usa_patentes and sobrevivente:
        return None
    argumentos = {
        **atributos,
        'nex': None if sobrevivente or usa_patentes else (0 if usa_nivel_experiencia else 5),
        'estagio': 1 if sobrevivente else None,
    }
    nivel_experiencia = (
        0 if sobrevivente and usa_nivel_experiencia
        else 1 if classe and usa_nivel_experiencia and not sobrevivente
        else None
    )
    patente_inicial = Patente.objects.filter(slug='recruta').first() if usa_patentes else None
    if usa_patentes and patente_inicial is None:
        return None
    if classe:
        slug = classe.slug
        if slug not in ('combatente', 'especialista', 'ocultista', 'sobrevivente'):
            return None
        argumentos.update(
            pv_atual=calcular_pv_max(slug, vigor=atributos['vigor'], nex=5, estagio=1),
            pe_atual=0 if configuracao and configuracao.modo_recursos == 'sem_sanidade' else
            calcular_pe_max(slug, presenca=atributos['presenca'], nex=5, estagio=1),
            san_atual=0 if configuracao and configuracao.modo_recursos == 'sem_sanidade' else
            calcular_san_max(slug, nex=5, estagio=1),
        )
        if configuracao and configuracao.modo_recursos == 'sem_sanidade':
            nivel_inicial = patente_inicial.limite_pd if patente_inicial else 1
            nex_inicial = nex_equivalente_por_nivel(nivel_inicial)
            argumentos['pd_atual'] = calcular_pd_max(
                slug, presenca=atributos['presenca'], nex=nex_inicial, estagio=1,
            )

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
            patente=patente_inicial,
            nivel_experiencia=nivel_experiencia,
            **argumentos,
        )
        FichaPericia.objects.bulk_create([
            FichaPericia(ficha=ficha, pericia=pericia, grau='treinado')
            for pericia in pericias.values()
        ])
    return ficha


def _ler_json(request, campos, opcionais=()):
    if request.content_type != 'application/json':
        return None, JsonResponse({'erro': 'Envie JSON.'}, status=415)
    try:
        conteudo = json.loads(request.body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, JsonResponse({'erro': 'JSON inválido.'}, status=400)
    if (
        type(conteudo) is not dict
        or not set(campos).issubset(conteudo)
        or not set(conteudo).issubset(set(campos) | set(opcionais))
    ):
        return None, JsonResponse({'erro': 'Campos inválidos.'}, status=400)
    return conteudo, None


def _garantir_ficha_editavel(request, ficha):
    if not pode_editar_ficha(request.user, ficha):
        raise PermissionDenied
    if not is_mestre(request.user) and ficha.status != 'ativa':
        raise PermissionDenied('Fichas inativas são somente leitura para o jogador.')


def _ficha_editavel(request, pk, *, bloquear=False):
    fichas = fichas_visiveis_para(request.user).filter(pk=pk)
    if bloquear:
        fichas = fichas.select_for_update()
    ficha = get_object_or_404(fichas)
    _garantir_ficha_editavel(request, ficha)
    return ficha


def _aplicar_delta_recurso(ficha, usuario, recurso, delta):
    recursos = {'pv': ('pv_atual', 'ajuste_pv_max'), 'pe': ('pe_atual', 'ajuste_pe_max'),
                'san': ('san_atual', 'ajuste_san_max'), 'pd': ('pd_atual', 'ajuste_pd_max')}
    if (
        type(recurso) is not str or (recurso not in recursos and recurso != 'pv_temporario')
        or type(delta) is not int or abs(delta) > 1000
    ):
        raise ValueError('Alteração de recurso inválida.')
    if recurso == 'pv_temporario':
        atual = ficha.pv_temporario
        novo = max(0, atual + delta)
        aplicado = novo - atual
        if novo != atual:
            ficha.pv_temporario = novo
            ficha.save(update_fields=('pv_temporario', 'atualizada_em'))
            LogAlteracao.objects.create(
                ficha=ficha, usuario=usuario, e_mestre=is_mestre(usuario),
                campo='pv_temporario', valor_antigo=str(atual), valor_novo=str(novo),
            )
        return {
            'recurso': recurso,
            'atual': novo,
            'maximo': None,
            'aplicado': aplicado,
            'sobrou': delta - aplicado,
            'pv_temporario': novo,
            'pv_temporario_aplicado': 0,
        }
    configuracao = ConfiguracaoMesa.objects.filter(pk=1).first()
    modo_recursos = configuracao.modo_recursos if configuracao else 'padrao'
    if modo_recursos == 'sem_sanidade' and recurso in ('pe', 'san'):
        raise ValueError('Este recurso não está ativo nesta mesa.')
    if modo_recursos == 'padrao' and recurso == 'pd':
        raise ValueError('Este recurso não está ativo nesta mesa.')
    campo, _ = recursos[recurso]
    atual = getattr(ficha, campo)
    maximo = _maximos_ficha(ficha).get(recurso, 0)
    temporario_aplicado = 0
    temporario_anterior = ficha.pv_temporario
    atual_limitado = min(maximo, max(0, atual))
    correcao_por_limite = atual_limitado - atual
    if recurso == 'pv' and delta < 0:
        # PV temporários absorvem o dano antes dos PV; excesso após PV zero não é aplicado.
        dano = -delta
        temporario_aplicado = min(temporario_anterior, dano)
        ficha.pv_temporario -= temporario_aplicado
        dano -= temporario_aplicado
        novo = max(0, atual_limitado - dano)
        pv_aplicado = atual_limitado - novo
        aplicado = -(temporario_aplicado + pv_aplicado)
        sobrou = -(dano - pv_aplicado)
    else:
        novo = min(maximo, max(0, atual_limitado + delta))
        aplicado = novo - atual_limitado
        sobrou = delta - aplicado

    campos_atualizados = []
    if novo != atual:
        setattr(ficha, campo, novo)
        campos_atualizados.append(campo)
        LogAlteracao.objects.create(
            ficha=ficha, usuario=usuario, e_mestre=is_mestre(usuario),
            campo=campo, valor_antigo=str(atual), valor_novo=str(novo),
        )
    if temporario_aplicado:
        campos_atualizados.append('pv_temporario')
        LogAlteracao.objects.create(
            ficha=ficha, usuario=usuario, e_mestre=is_mestre(usuario),
            campo='pv_temporario', valor_antigo=str(temporario_anterior),
            valor_novo=str(ficha.pv_temporario),
        )
    if recurso == 'pv' and atual > 0 and novo == 0 and delta < 0:
        for slug, nome, resumo in (
            ('inconsciente', 'Inconsciente', 'Não pode realizar ações ou reações.'),
            ('morrendo', 'Morrendo', 'Com 0 PV; três turnos iniciados nesta cena causam a morte.'),
        ):
            condicao, _ = Condicao.objects.get_or_create(
                slug=slug,
                defaults={
                    'nome': nome,
                    'fonte': 'OPRPG p.311',
                    'resumo': resumo,
                    'personalizado': False,
                    'categoria': 'outra',
                    'termina_fim_cena': False,
                },
            )
            _, criada = FichaCondicao.objects.get_or_create(ficha=ficha, condicao=condicao)
            if criada:
                LogAlteracao.objects.create(
                    ficha=ficha, usuario=usuario, e_mestre=is_mestre(usuario),
                    campo='condicao', valor_novo=condicao.nome,
                )
    elif recurso == 'pv' and atual == 0 and novo > 0:
        inconsciente = Condicao.objects.filter(slug='inconsciente').first()
        if inconsciente:
            removidas, _ = FichaCondicao.objects.filter(
                ficha=ficha, condicao=inconsciente,
            ).delete()
            if removidas:
                LogAlteracao.objects.create(
                    ficha=ficha, usuario=usuario, e_mestre=is_mestre(usuario),
                    campo='condicao', valor_antigo=inconsciente.nome,
                )
    if campos_atualizados:
        ficha.save(update_fields=(*campos_atualizados, 'atualizada_em'))
    return {
        'recurso': recurso,
        'atual': novo,
        'maximo': maximo,
        'aplicado': aplicado,
        'sobrou': sobrou,
        'correcao_por_limite': correcao_por_limite,
        'pv_temporario': ficha.pv_temporario if recurso == 'pv' else None,
        'pv_temporario_aplicado': temporario_aplicado,
    }


@login_required
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def alterar_recurso(request, pk):
    conteudo, erro = _ler_json(request, ('recurso', 'delta'))
    if erro:
        return erro
    if type(conteudo['recurso']) is not str or type(conteudo['delta']) is not int:
        return JsonResponse({'erro': 'Alteração de recurso inválida.'}, status=400)
    if abs(conteudo['delta']) > 1000:
        return JsonResponse({'erro': 'Alteração de recurso inválida.'}, status=400)
    with transaction.atomic():
        ficha = _ficha_editavel(request, pk, bloquear=True)
        try:
            resultado = _aplicar_delta_recurso(
                ficha, request.user, conteudo['recurso'], conteudo['delta'],
            )
        except ValueError as erro:
            return JsonResponse({'erro': str(erro)}, status=400)
    return JsonResponse(resultado)


@login_required
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def alterar_condicao(request, pk):
    conteudo, erro = _ler_json(
        request, ('acao', 'condicao'), opcionais=('turnos_restantes',),
    )
    if erro:
        return erro
    if type(conteudo['acao']) is not str or conteudo['acao'] not in ('adicionar', 'remover', 'escalar') or type(conteudo['condicao']) is not int:
        return JsonResponse({'erro': 'Operação inválida.'}, status=400)
    turnos_restantes = conteudo.get('turnos_restantes')
    if conteudo['acao'] == 'adicionar':
        if turnos_restantes is not None and (
            type(turnos_restantes) is not int or not 1 <= turnos_restantes <= 99
        ):
            return JsonResponse({'erro': 'A duração deve ser de 1 a 99 turnos.'}, status=400)
    elif turnos_restantes is not None:
        return JsonResponse({'erro': 'A duração só pode ser informada ao adicionar.'}, status=400)
    condicao = get_object_or_404(
        Condicao.objects.select_related('proxima_escalada'), pk=conteudo['condicao'],
    )
    if condicao.slug == 'morrendo' and turnos_restantes is not None:
        return JsonResponse(
            {'erro': 'Morrendo usa o contador próprio da cena de combate.'}, status=400,
        )
    removida = None
    condicao_ativa = None
    with transaction.atomic():
        ficha = _ficha_editavel(request, pk, bloquear=True)
        if conteudo['acao'] == 'escalar':
            ativa = FichaCondicao.objects.select_for_update().filter(
                ficha=ficha, condicao=condicao,
            ).first()
            if ativa is None or condicao.proxima_escalada_id is None:
                return JsonResponse({'erro': 'Esta condição não pode ser escalada agora.'}, status=400)
            removida = {'id': condicao.pk, 'nome': condicao.nome}
            turnos_restantes = ativa.turnos_restantes
            FichaCondicao.objects.filter(pk=ativa.pk).delete()
            condicao = condicao.proxima_escalada
            condicao_ativa, criada = FichaCondicao.objects.get_or_create(
                ficha=ficha, condicao=condicao,
                defaults={'turnos_restantes': turnos_restantes},
            )
            duracao_anterior = condicao_ativa.turnos_restantes
            if not criada and duracao_anterior != turnos_restantes:
                condicao_ativa.turnos_restantes = turnos_restantes
                condicao_ativa.save(update_fields=('turnos_restantes',))
                LogAlteracao.objects.create(
                    ficha=ficha, usuario=request.user, e_mestre=is_mestre(request.user),
                    campo='condicao.duracao',
                    valor_antigo='' if duracao_anterior is None else str(duracao_anterior),
                    valor_novo='' if turnos_restantes is None else str(turnos_restantes),
                )
            ativa = True
            alterada = True
        elif conteudo['acao'] == 'adicionar':
            condicao_ativa, criada = FichaCondicao.objects.get_or_create(
                ficha=ficha, condicao=condicao,
                defaults={'turnos_restantes': turnos_restantes},
            )
            ativa = True
            alterada = criada
        else:
            quantidade, _ = FichaCondicao.objects.filter(ficha=ficha, condicao=condicao).delete()
            alterada = quantidade > 0
            ativa = False
        if alterada:
            LogAlteracao.objects.create(
                ficha=ficha, usuario=request.user, e_mestre=is_mestre(request.user),
                campo='condicao',
                valor_antigo=removida['nome'] if removida else ('' if ativa else condicao.nome),
                valor_novo=(
                    f'{condicao.nome} (duração: {turnos_restantes} turnos)'
                    if ativa and turnos_restantes else condicao.nome if ativa else ''
                ),
            )
    return JsonResponse({
        'condicao': condicao.pk,
        'nome': condicao.nome,
        'resumo': condicao.resumo,
        'ativa': ativa,
        'removida': removida,
        'turnos_restantes': (
            condicao_ativa.turnos_restantes if condicao_ativa else None
        ),
        'proxima_escalada': (
            {'id': condicao.proxima_escalada_id, 'nome': condicao.proxima_escalada.nome}
            if condicao.proxima_escalada_id else None
        ),
    })


@login_required
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def adicionar_item(request, pk):
    ficha = _ficha_editavel(request, pk)
    form = ItemInventarioForm(request.POST)
    if not form.is_valid():
        return render(
            request, 'fichas/detalhe.html',
            _contexto_detalhe(request, ficha, formulario_item=form), status=400,
        )
    with transaction.atomic():
        ficha = _ficha_editavel(request, pk, bloquear=True)
        item = ItemInventario.objects.create(ficha=ficha, **form.cleaned_data)
        LogAlteracao.objects.create(
            ficha=ficha, usuario=request.user, e_mestre=is_mestre(request.user),
            campo='inventario', valor_novo=item.nome,
        )
    messages.success(request, 'Item adicionado ao inventário.')
    return redirect('fichas:detalhe', pk=pk)


@login_required
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def atualizar_item(request, pk, item_pk):
    ficha = _ficha_editavel(request, pk)
    item = get_object_or_404(ItemInventario.objects.filter(ficha=ficha), pk=item_pk)
    form = ItemInventarioAjusteForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Quantidade ou estado inválido; o item não foi alterado.')
        return redirect('fichas:detalhe', pk=pk)
    with transaction.atomic():
        ficha = _ficha_editavel(request, pk, bloquear=True)
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
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def remover_item(request, pk, item_pk):
    ficha = _ficha_editavel(request, pk)
    with transaction.atomic():
        ficha = _ficha_editavel(request, pk, bloquear=True)
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
def gerenciar_ferimento(request, pk):
    ficha = _ficha_editavel(request, pk)
    if not is_mestre(request.user):
        return HttpResponseForbidden('Somente o mestre pode registrar ou tratar ferimentos.')
    mesa = ConfiguracaoMesa.objects.filter(pk=1).first() or ConfiguracaoMesa()
    if not mesa.ferimentos_debilitantes:
        messages.error(request, 'Ferimentos Debilitantes não estão habilitados nesta mesa.')
        return redirect('fichas:detalhe', pk=pk)

    form = FerimentoDebilitanteForm(request.POST, ficha=ficha)
    if not form.is_valid():
        return render(
            request, 'fichas/detalhe.html',
            _contexto_detalhe(request, ficha, formulario_ferimento=form),
            status=400,
        )

    recurso_pv_anterior = None
    with transaction.atomic():
        ficha = _ficha_editavel(request, pk, bloquear=True)
        mesa = ConfiguracaoMesa.objects.select_for_update().filter(pk=1).first()
        if mesa is None or not mesa.ferimentos_debilitantes:
            messages.error(request, 'Ferimentos Debilitantes não estão habilitados nesta mesa.')
            return redirect('fichas:detalhe', pk=pk)
        acao = form.cleaned_data['acao']
        if acao == 'registrar':
            atributo = form.cleaned_data['atributo']
            FerimentoDebilitante.objects.create(ficha=ficha, atributo=atributo)
            LogAlteracao.objects.create(
                ficha=ficha, usuario=request.user, e_mestre=True,
                campo='ferimento_debilitante', valor_novo=atributo,
            )
            if atributo == 'vigor':
                recurso_pv_anterior = ficha.pv_atual
                ficha.pv_atual = min(ficha.pv_atual, _maximos_ficha(ficha)['pv'])
        else:
            ferimento = get_object_or_404(
                ficha.ferimentos.select_for_update().filter(curado_em__isnull=True),
                pk=form.cleaned_data['ferimento'].pk,
            )
            if acao == 'tratamento':
                if ferimento.tratamento_aprovado_em is not None:
                    messages.error(request, 'O tratamento deste ferimento já foi registrado.')
                    return redirect('fichas:detalhe', pk=pk)
                ferimento.tratamento_aprovado_em = timezone.now()
                ferimento.save(update_fields=('tratamento_aprovado_em',))
                LogAlteracao.objects.create(
                    ficha=ficha, usuario=request.user, e_mestre=True,
                    campo='ferimento_tratamento',
                    valor_novo=f'{ferimento.atributo}; Medicina DT 20 aprovada',
                )
            elif acao == 'curar':
                if ferimento.tratamento_aprovado_em is None:
                    messages.error(request, 'Registre primeiro o sucesso em Medicina (DT 20).')
                    return redirect('fichas:detalhe', pk=pk)
                ferimento.curado_em = timezone.now()
                ferimento.save(update_fields=('curado_em',))
                LogAlteracao.objects.create(
                    ficha=ficha, usuario=request.user, e_mestre=True,
                    campo='ferimento_debilitante',
                    valor_antigo=ferimento.atributo,
                    valor_novo='curado após dormir',
                )

        ficha.versao += 1
        campos = ['versao', 'atualizada_em']
        if recurso_pv_anterior is not None:
            campos.append('pv_atual')
            if ficha.pv_atual != recurso_pv_anterior:
                LogAlteracao.objects.create(
                    ficha=ficha, usuario=request.user, e_mestre=True,
                    campo='pv_atual', valor_antigo=str(recurso_pv_anterior),
                    valor_novo=str(ficha.pv_atual),
                )
        ficha.save(update_fields=tuple(campos))

    messages.success(request, 'Ferimento Debilitante atualizado.')
    return redirect('fichas:detalhe', pk=pk)


@login_required
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def rolar_ficha(request, pk):
    conteudo, erro = _ler_json(
        request,
        ('tipo', 'alvo', 'bonus'),
        ('dados_extras', 'dados_fisicos', 'dt', 'kit_disponivel', 'perigo_cicatrizado'),
    )
    if erro:
        return erro
    dados_extras = conteudo.get('dados_extras', 0)
    if (
        conteudo['tipo'] not in ('atributo', 'pericia', 'livre')
        or type(conteudo['bonus']) is not int or abs(conteudo['bonus']) > 100
        or type(dados_extras) is not int or abs(dados_extras) > 10
        or ('kit_disponivel' in conteudo and type(conteudo['kit_disponivel']) is not bool)
        or (
            'perigo_cicatrizado' in conteudo
            and (
                not isinstance(conteudo['perigo_cicatrizado'], str)
                or len(conteudo['perigo_cicatrizado']) > 120
            )
        )
    ):
        return JsonResponse({'erro': 'Parâmetros de rolagem inválidos.'}, status=400)
    fisicos = 'dados_fisicos' in conteudo
    if fisicos and type(conteudo['dados_fisicos']) is not list:
        return JsonResponse({'erro': 'Informe os resultados dos dados físicos como uma lista.'}, status=400)
    dt = conteudo.get('dt')
    if 'dt' in conteudo and dt is not None and (type(dt) is not int or not 1 <= dt <= 1000):
        return JsonResponse({'erro': 'A DT deve ser um inteiro entre 1 e 1000.'}, status=400)
    if not fisicos and 'dt' in conteudo:
        return JsonResponse({'erro': 'A DT só pode ser enviada junto dos resultados físicos.'}, status=400)
    with transaction.atomic():
        ficha = _ficha_editavel(request, pk, bloquear=True)
        condicoes_ativas = [
            item.condicao
            for item in ficha.condicoes.select_related('condicao')
        ]
        bonus_treinamento = 0
        atributo_slug = None
        pericia_slug = None
        if conteudo['tipo'] == 'atributo':
            if conteudo['alvo'] not in ATRIBUTOS:
                return JsonResponse({'erro': 'Atributo inválido.'}, status=400)
            descricao = conteudo['alvo'].capitalize()
            atributo = getattr(ficha, conteudo['alvo'])
            atributo_slug = conteudo['alvo']
        elif conteudo['tipo'] == 'pericia':
            if type(conteudo['alvo']) is not int:
                return JsonResponse({'erro': 'Perícia inválida.'}, status=400)
            pericia = get_object_or_404(Pericia, pk=conteudo['alvo'])
            ficha_pericia = ficha.pericias.filter(pericia=pericia).first()
            grau = ficha_pericia.grau if ficha_pericia else 'destreinado'
            if pericia.somente_treinada and grau == 'destreinado':
                return JsonResponse({'erro': 'Esta perícia exige treinamento.'}, status=400)
            extra_treinamento = ficha_pericia.bonus_extra if ficha_pericia else 0
            carga_usada = espacos_usados(ficha.inventario.all())
            sobrecarregado = carga_usada > capacidade_carga(ficha.forca)
            kit_disponivel = conteudo.get('kit_disponivel', True) or not pericia.exige_kit
            bonus_treinamento = bonus_pericia(
                grau,
                bonus_extra=extra_treinamento,
                kit_disponivel=kit_disponivel,
                penalidade_carga=-5 if sobrecarregado and pericia.penalidade_carga else 0,
            )
            atributo = getattr(ficha, pericia.atributo)
            atributo_slug = pericia.atributo
            pericia_slug = pericia.slug
            descricao = pericia.nome
        else:
            if type(conteudo['alvo']) is not int or not 1 <= conteudo['alvo'] <= 10:
                return JsonResponse({'erro': 'A quantidade de dados deve ficar entre um e dez.'}, status=400)
            atributo = 1
            dados_extras += conteudo['alvo'] - 1
            descricao = f'{conteudo["alvo"]}d20 livre'

        mesa = ConfiguracaoMesa.objects.filter(pk=1).first() or ConfiguracaoMesa()
        if mesa.ferimentos_debilitantes and atributo_slug:
            ferimentos_ativos = ficha.ferimentos.filter(
                atributo=atributo_slug, curado_em__isnull=True,
            ).count()
            if ferimentos_ativos:
                dados_extras -= ferimentos_ativos
                descricao = f'{descricao} — Ferimento Debilitante'[:120]

        perigo_cicatrizado = conteudo.get('perigo_cicatrizado')
        if perigo_cicatrizado is not None:
            if (
                conteudo['tipo'] != 'pericia'
                or pericia_slug not in {'fortitude', 'reflexos', 'vontade'}
                or ficha.classe_id is None or ficha.classe.slug != 'sobrevivente'
                or ficha.estagio != 5
                or perigo_cicatrizado != ficha.cicatrizado_perigo
                or not ficha.cicatrizado_elemento
            ):
                return JsonResponse(
                    {'erro': 'Cicatrizado só penaliza testes de resistência contra o perigo registrado.'},
                    status=400,
                )
            dados_extras -= 1
            descricao = f'{descricao} — Cicatrizado'[:120]

        try:
            explicacao = explicar_teste(
                atributo,
                condicoes_ativas,
                tipo=conteudo['tipo'],
                atributo_slug=atributo_slug,
                pericia_slug=pericia_slug,
                dados_extras=dados_extras,
                bonus_pericia=bonus_treinamento,
                bonus=conteudo['bonus'],
            )
            dados_extras = explicacao['dados_extras']
            if fisicos:
                resultado = avaliar_teste_fisico(
                    atributo,
                    conteudo['dados_fisicos'],
                    bonus_pericia=bonus_treinamento,
                    dados_extras=dados_extras,
                    bonus=conteudo['bonus'],
                    dt=dt,
                )
            else:
                resultado = rolar_teste(
                    atributo,
                    bonus_pericia=bonus_treinamento,
                    dados_extras=dados_extras,
                    bonus=conteudo['bonus'],
                )
        except ValueError as erro:
            return JsonResponse({'erro': str(erro)}, status=400)

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
        'quantidade_dados': resultado['quantidade_dados'],
        'ordem': resultado['ordem'],
        'dt': resultado['dt'],
        'sucesso': resultado['sucesso'],
        'detalhamento': explicacao['detalhamento'],
    })


@login_required
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def calcular_dano_ficha(request, pk):
    conteudo, erro = _ler_json(
        request,
        ('quantidade_dados', 'faces', 'bonus', 'multiplicador_critico'),
        ('dados_fisicos',),
    )
    if erro:
        return erro
    quantidade = conteudo['quantidade_dados']
    faces = conteudo['faces']
    bonus = conteudo['bonus']
    multiplicador = conteudo['multiplicador_critico']
    if any(type(valor) is not int for valor in (quantidade, faces, bonus, multiplicador)):
        return JsonResponse({'erro': 'Informe valores inteiros para os dados de dano.'}, status=400)
    if (
        not 1 <= quantidade <= 30 or not 2 <= faces <= 100
        or not 1 <= multiplicador <= 10 or abs(bonus) > 1000
    ):
        return JsonResponse({'erro': 'Dados de dano fora dos limites permitidos.'}, status=400)
    fisicos = 'dados_fisicos' in conteudo
    if fisicos and type(conteudo['dados_fisicos']) is not list:
        return JsonResponse({'erro': 'Informe os resultados físicos como uma lista.'}, status=400)

    _ficha_editavel(request, pk)
    try:
        if fisicos:
            resultado = avaliar_dano_fisico(
                quantidade, faces, conteudo['dados_fisicos'], bonus, multiplicador,
            )
        else:
            resultado = rolar_dano(quantidade, faces, bonus, multiplicador)
    except ValueError as erro:
        return JsonResponse({'erro': str(erro)}, status=400)

    with transaction.atomic():
        ficha = _ficha_editavel(request, pk, bloquear=True)
        rolagem = Rolagem.objects.create(
            ficha=ficha,
            usuario=request.user,
            tipo='dano',
            descricao=f'{quantidade}d{faces}' + (
                f' crítico ×{multiplicador}' if multiplicador > 1 else ''
            ),
            dados=resultado['dados'],
            bonus=resultado['bonus'],
            total=resultado['total'],
        )
    return JsonResponse({
        'id': rolagem.pk,
        'descricao': rolagem.descricao,
        'dados': rolagem.dados,
        'bonus': rolagem.bonus,
        'total': rolagem.total,
        'fisicos': fisicos,
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


def _contexto_detalhe(
    request, ficha, formulario_avanco=None, formulario_item=None, formulario_estagio=None,
    formulario_ferimento=None, formulario_nivel=None, formulario_exposicao=None,
    formulario_prestigio=None, formulario_recuperacao_patente=None,
):
    mesa = ConfiguracaoMesa.objects.filter(pk=1).first() or ConfiguracaoMesa()
    ativas = list(ficha.condicoes.select_related(
        'condicao', 'condicao__proxima_escalada',
    ).order_by('condicao__nome'))
    condicoes = [item.condicao for item in ativas]
    ferimentos_ativos = list(
        ficha.ferimentos.filter(curado_em__isnull=True).order_by('criado_em', 'pk')
    ) if mesa.ferimentos_debilitantes else []
    ferimentos_por_atributo = {
        atributo: -sum(ferimento.atributo == atributo for ferimento in ferimentos_ativos)
        for atributo in ATRIBUTOS
    }
    ids_condicoes_ativas = [item.condicao_id for item in ativas]
    ficha_pericias = list(ficha.pericias.select_related('pericia').order_by('pericia__nome'))
    treinamento_por_pericia = {item.pericia_id: item for item in ficha_pericias}
    itens_inventario = list(ficha.inventario.order_by('nome', 'pk'))
    carga_usada = espacos_usados(itens_inventario)
    carga_maxima = capacidade_carga(ficha.forca)
    carga_excedida = carga_usada > carga_maxima
    nomes_atributos = {
        'agilidade': 'Agilidade',
        'forca': 'Força',
        'intelecto': 'Intelecto',
        'presenca': 'Presença',
        'vigor': 'Vigor',
    }
    alvos_rolagem = [
        {
            'tipo': 'atributo',
            'id': nome,
            'nome': nomes_atributos[nome],
            'atributo_valor': getattr(ficha, nome),
            'bonus_treinamento': 0,
            'treinamento_obrigatorio': False,
            'treinado': True,
            'dados_condicao': modificadores_condicoes(
                condicoes, tipo='atributo', atributo=nome,
            )['dados_extras'],
            'dados_ferimentos': ferimentos_por_atributo[nome],
        }
        for nome in ATRIBUTOS
    ]
    for pericia in Pericia.objects.order_by('nome'):
        ficha_pericia = treinamento_por_pericia.get(pericia.pk)
        grau = ficha_pericia.grau if ficha_pericia else 'destreinado'
        extra_treinamento = ficha_pericia.bonus_extra if ficha_pericia else 0
        alvos_rolagem.append({
            'tipo': 'pericia',
            'id': pericia.pk,
            'nome': pericia.nome,
            'atributo_valor': getattr(ficha, pericia.atributo),
            'atributo_nome': nomes_atributos[pericia.atributo],
            'bonus_treinamento': bonus_pericia(grau, bonus_extra=extra_treinamento),
            'treinamento_obrigatorio': pericia.somente_treinada,
            'treinado': grau != 'destreinado',
            'pericia_slug': pericia.slug,
            'dados_ferimentos': ferimentos_por_atributo[pericia.atributo],
            'dados_condicao': modificadores_condicoes(
                condicoes,
                tipo='pericia',
                atributo=pericia.atributo,
                pericia_slug=pericia.slug,
            )['dados_extras'],
            'penalidade_carga': (
                -5 if carga_excedida and pericia.penalidade_carga else 0
            ),
            'exige_kit': pericia.exige_kit,
        })
    modificadores_defesa = modificadores_condicoes(condicoes, tipo='livre')
    defesa = calcular_defesa(
        ficha.agilidade,
        bonus=ficha.defesa_bonus + modificadores_defesa['defesa'],
        sobrecarregado=carga_excedida,
    )
    classe = ficha.classe.slug if ficha.classe_id else None
    maximos = _maximos_ficha(ficha)
    pode_avancar = bool(
        classe and classe != 'sobrevivente' and ficha.nex is not None
        and any(nex > ficha.nex for nex in NEX_VALIDOS)
        and mesa.sistema_progressao == 'nex'
        and (is_mestre(request.user) or (
            ficha.dono_id == request.user.pk and ficha.status == 'ativa'
            and mesa.jogador_pode_subir_nex
        ))
    )
    if formulario_avanco is None and pode_avancar:
        proximo_nex = next((nex for nex in NEX_VALIDOS if nex > ficha.nex), '')
        formulario_avanco = AvancoNexForm(
            nex_atual=ficha.nex,
            initial={'nex_novo': proximo_nex, 'versao': ficha.versao},
        )
    pode_avancar_nivel = bool(
        classe and classe != 'sobrevivente'
        and ficha.nivel_experiencia is not None and ficha.nivel_experiencia < 20
        and mesa.sistema_progressao == 'nivel_nex'
        and (is_mestre(request.user) or (
            ficha.dono_id == request.user.pk and ficha.status == 'ativa'
            and mesa.jogador_pode_subir_nex
        ))
    )
    if formulario_nivel is None and pode_avancar_nivel:
        formulario_nivel = AvancoNivelForm(
            nivel_atual=ficha.nivel_experiencia,
            initial={
                'nivel_novo': ficha.nivel_experiencia + 1,
                'versao': ficha.versao,
            },
        )
    pode_registrar_exposicao = bool(
        is_mestre(request.user) and mesa.sistema_progressao == 'nivel_nex'
        and classe and classe != 'sobrevivente' and ficha.nex is not None
    )
    if formulario_exposicao is None and pode_registrar_exposicao:
        formulario_exposicao = ExposicaoParanormalForm(
            nex_atual=ficha.nex,
            initial={'versao': ficha.versao},
        )
    pode_registrar_prestigio = bool(
        is_mestre(request.user) and mesa.sistema_progressao == 'patentes'
        and classe in ('combatente', 'especialista', 'ocultista')
    )
    if formulario_prestigio is None and pode_registrar_prestigio:
        formulario_prestigio = RegistroPrestigioForm(initial={
            'versao': ficha.versao,
            'numero_sessao': mesa.numero_sessao,
        })
    pode_recuperar_patente = bool(
        mesa.sistema_progressao == 'patentes' and ficha.patente_id
        and classe in ('combatente', 'especialista', 'ocultista')
        and pode_editar_ficha(request.user, ficha)
        and (is_mestre(request.user) or ficha.status == 'ativa')
    )
    if formulario_recuperacao_patente is None and pode_recuperar_patente:
        formulario_recuperacao_patente = RecuperacaoPatenteForm(
            initial={'versao': ficha.versao},
        )
    pode_avancar_estagio = bool(
        classe == 'sobrevivente' and ficha.estagio is not None and ficha.estagio < 5
        and is_mestre(request.user)
    )
    if formulario_estagio is None and pode_avancar_estagio:
        formulario_estagio = AvancoEstagioForm(
            estagio_atual=ficha.estagio,
            initial={'estagio_novo': ficha.estagio + 1, 'versao': ficha.versao},
        )
    pode_editar = pode_editar_ficha(request.user, ficha) and (
        is_mestre(request.user) or ficha.status == 'ativa'
    )
    if formulario_item is None and pode_editar:
        formulario_item = ItemInventarioForm()
    if formulario_ferimento is None and is_mestre(request.user) and mesa.ferimentos_debilitantes:
        formulario_ferimento = FerimentoDebilitanteForm(ficha=ficha)
    return {
        'ficha': ficha,
        'ficha_pericias': ficha_pericias,
        'ficha_poderes': ficha.poderes.select_related('poder').order_by('pk'),
        'ficha_rituais': ficha.rituais.select_related('ritual').order_by('pk'),
        'alvos_rolagem': alvos_rolagem,
        'condicoes_ativas': ativas,
        'condicoes_disponiveis': Condicao.objects.exclude(pk__in=ids_condicoes_ativas).order_by('nome'),
        'atributos': ATRIBUTOS,
        'maximos': maximos,
        'modo_recursos': mesa.modo_recursos,
        'pendencias': ficha.pendencias.filter(resolvida=False).order_by('criada_em', 'pk'),
        'pode_avancar_nex': pode_avancar,
        'formulario_avanco': formulario_avanco,
        'pode_avancar_nivel': pode_avancar_nivel,
        'formulario_nivel': formulario_nivel,
        'pode_registrar_exposicao': pode_registrar_exposicao,
        'formulario_exposicao': formulario_exposicao,
        'pode_registrar_prestigio': pode_registrar_prestigio,
        'formulario_prestigio': formulario_prestigio,
        'pode_recuperar_patente': pode_recuperar_patente,
        'formulario_recuperacao_patente': formulario_recuperacao_patente,
        'registros_prestigio': ficha.registros_prestigio.select_related(
            'usuario',
        ).order_by('-criada_em')[:20],
        'pode_avancar_estagio': pode_avancar_estagio,
        'formulario_estagio': formulario_estagio,
        'formulario_ferimento': formulario_ferimento,
        'ferimentos_debilitantes': ferimentos_ativos,
        'modo_ferimentos_debilitantes': mesa.ferimentos_debilitantes,
        'habilidades_estagio': (
            ficha.classe.habilidades_por_nex.get(str(ficha.estagio), [])
            if classe == 'sobrevivente' and ficha.classe_id and ficha.estagio else []
        ),
        'formulario_item': formulario_item,
        'itens_inventario': itens_inventario,
        'carga_usada': carga_usada,
        'carga_maxima': carga_maxima,
        'carga_excedida': carga_excedida,
        'defesa': defesa,
        'pode_editar': pode_editar,
        'pode_alterar_status': pode_editar_ficha(request.user, ficha),
        'estados_item': ItemInventario.ESTADOS,
        'mestre': is_mestre(request.user),
        'numero_sessao': mesa.numero_sessao,
        'formulario_cicatrizado': UsarCicatrizadoForm(),
        'cicatrizado_disponivel': bool(
            ficha.estagio == 5 and ficha.cicatrizado_elemento
            and ficha.cicatrizado_perigo
            and ficha.cicatrizado_sessao_usada != mesa.numero_sessao
        ),
    }


def _maximos_ficha(ficha):
    classe = ficha.classe.slug if ficha.classe_id else None
    maximos = {'pv': 0, 'pe': 0, 'san': 0, 'pd': 0}
    if not classe:
        return maximos
    mesa = _mesa_configuracao()
    if mesa.sistema_progressao == 'nivel_nex' and classe != 'sobrevivente':
        nivel = ficha.nivel_experiencia or 1
        nex_progressao = nex_equivalente_por_nivel(nivel)
    elif mesa.sistema_progressao == 'patentes' and ficha.patente_id:
        nex_progressao = nex_equivalente_por_nivel(ficha.patente.limite_pd)
    else:
        nex_progressao = ficha.nex or 5
    argumentos = {'nex': nex_progressao, 'estagio': ficha.estagio or 1}
    maximos.update(
        pv=calcular_pv_max(classe, ficha.vigor, **argumentos, ajuste=ficha.ajuste_pv_max),
        pe=calcular_pe_max(classe, ficha.presenca, **argumentos, ajuste=ficha.ajuste_pe_max),
        san=calcular_san_max(classe, **argumentos, ajuste=ficha.ajuste_san_max),
        pd=calcular_pd_max(classe, ficha.presenca, **argumentos, ajuste=ficha.ajuste_pd_max),
    )
    if mesa.ferimentos_debilitantes:
        ferimentos_vigor = ficha.ferimentos.filter(
            atributo='vigor', curado_em__isnull=True,
        ).count()
        nivel_efetivo = ficha.patente.limite_pd if (
            mesa.sistema_progressao == 'patentes' and ficha.patente_id
        ) else ficha.nivel_experiencia or (
            (ficha.nex + 4) // 5 if ficha.nex is not None else 0
        )
        maximos['pv'] = max(0, maximos['pv'] - ferimentos_vigor * nivel_efetivo)
    return maximos


@login_required
def detalhe_ficha(request, pk):
    ficha = get_object_or_404(fichas_visiveis_para(request.user), pk=pk)
    return render(request, 'fichas/detalhe.html', _contexto_detalhe(request, ficha))


@login_required
@require_GET
@ratelimit(key='user', rate='30/m', method='GET', block=True)
def atualizacoes_ficha(request, pk):
    ficha = get_object_or_404(fichas_visiveis_para(request.user).select_related('classe'), pk=pk)
    mesa = _mesa_configuracao()
    recursos = {'pv': ficha.pv_atual}
    if mesa.modo_recursos == 'padrao':
        recursos.update(pe=ficha.pe_atual, san=ficha.san_atual)
    else:
        recursos['pd'] = ficha.pd_atual
    maximos = _maximos_ficha(ficha)
    if mesa.modo_recursos == 'padrao':
        maximos = {key: maximos[key] for key in ('pv', 'pe', 'san')}
    else:
        maximos = {key: maximos[key] for key in ('pv', 'pd')}
    ferimentos_por_atributo = {
        atributo: -ficha.ferimentos.filter(
            atributo=atributo, curado_em__isnull=True,
        ).count() if mesa.ferimentos_debilitantes else 0
        for atributo in ATRIBUTOS
    }
    condicoes_ativas = list(ficha.condicoes.select_related(
        'condicao', 'condicao__proxima_escalada',
    ).order_by('condicao__nome'))
    condicoes = [item.condicao for item in condicoes_ativas]
    carga_usada = espacos_usados(ficha.inventario.all())
    sobrecarregado = carga_usada > capacidade_carga(ficha.forca)
    modificadores_defesa = modificadores_condicoes(condicoes, tipo='livre')
    defesa = calcular_defesa(
        ficha.agilidade,
        bonus=ficha.defesa_bonus + modificadores_defesa['defesa'],
        sobrecarregado=sobrecarregado,
    )
    alvos_rolagem = [
        {
            'tipo': 'atributo',
            'id': nome,
            'dados_condicao': modificadores_condicoes(
                condicoes, tipo='atributo', atributo=nome,
            )['dados_extras'],
            'dados_ferimentos': ferimentos_por_atributo[nome],
            'penalidade_carga': 0,
        }
        for nome in ATRIBUTOS
    ] + [
        {
            'tipo': 'pericia',
            'id': pericia.pk,
            'pericia_slug': pericia.slug,
            'dados_condicao': modificadores_condicoes(
                condicoes,
                tipo='pericia',
                atributo=pericia.atributo,
                pericia_slug=pericia.slug,
            )['dados_extras'],
            'dados_ferimentos': ferimentos_por_atributo[pericia.atributo],
            'penalidade_carga': (
                -5 if sobrecarregado and pericia.penalidade_carga else 0
            ),
        }
        for pericia in Pericia.objects.all()
    ]
    return JsonResponse({
        'modo_recursos': mesa.modo_recursos,
        'recursos': recursos,
        'maximos': maximos,
        'pv_temporario': ficha.pv_temporario,
        'condicoes': [
            {
                'id': item.pk,
                'nome': item.nome,
                'resumo': item.resumo,
                'turnos_restantes': ficha_condicao.turnos_restantes,
                'proxima_escalada': (
                    {'id': item.proxima_escalada_id, 'nome': item.proxima_escalada.nome}
                    if item.proxima_escalada_id else None
                ),
            }
            for ficha_condicao, item in zip(condicoes_ativas, condicoes)
        ],
        'defesa': defesa,
        'alvos_rolagem': alvos_rolagem,
        'condicoes_disponiveis': list(
            Condicao.objects.exclude(pk__in=[item.pk for item in condicoes])
            .order_by('nome').values('pk', 'nome')
        ),
    })


@login_required
def historico_rolagens(request):
    mestre = is_mestre(request.user)
    fichas = fichas_visiveis_para(request.user).select_related('classe').order_by('nome', 'pk')
    rolagens = Rolagem.objects.filter(ficha__in=fichas).select_related(
        'ficha', 'usuario',
    ).order_by('-criada_em', '-pk')
    if not mestre:
        rolagens = rolagens.filter(secreta=False)

    ficha_id = request.GET.get('ficha', '')
    ficha_selecionada = None
    if ficha_id:
        if not ficha_id.isdecimal():
            return render(request, '404.html', status=404)
        ficha_selecionada = get_object_or_404(fichas, pk=int(ficha_id))
        rolagens = rolagens.filter(ficha=ficha_selecionada)

    pagina = Paginator(rolagens, 50).get_page(request.GET.get('pagina'))
    return render(request, 'fichas/rolagens.html', {
        'rolagens': pagina,
        'fichas': fichas,
        'ficha_selecionada': ficha_selecionada,
        'mestre': mestre,
    })


@login_required
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def alterar_status_ficha(request, pk):
    ficha = get_object_or_404(fichas_visiveis_para(request.user), pk=pk)
    if not pode_editar_ficha(request.user, ficha):
        raise PermissionDenied
    form = FichaStatusForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Status inválido; a ficha não foi alterada.')
        return redirect('fichas:detalhe', pk=pk)

    with transaction.atomic():
        ficha = Ficha.objects.select_for_update().filter(pk=pk).first()
        if ficha is None:
            return render(request, '404.html', status=404)
        if not pode_editar_ficha(request.user, ficha):
            raise PermissionDenied
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
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def avancar_nex(request, pk):
    ficha = _ficha_editavel(request, pk)
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
        _garantir_ficha_editavel(request, atual)
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
                quantidade=pendencia.get('quantidade', 1),
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
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def avancar_nivel(request, pk):
    ficha = _ficha_editavel(request, pk)
    mesa = _mesa_configuracao()
    autorizado = is_mestre(request.user) or (
        ficha.dono_id == request.user.pk and mesa.jogador_pode_subir_nex
    )
    if not autorizado:
        return HttpResponseForbidden('Somente o mestre pode avançar o nível nesta mesa.')
    if (
        mesa.sistema_progressao != 'nivel_nex'
        or not ficha.classe_id or ficha.classe.slug not in ('combatente', 'especialista', 'ocultista')
        or ficha.nivel_experiencia is None or ficha.nivel_experiencia >= 20
    ):
        messages.error(request, 'Esta ficha não pode avançar por nível de experiência.')
        return redirect('fichas:detalhe', pk=pk)

    form = AvancoNivelForm(request.POST, nivel_atual=ficha.nivel_experiencia)
    if not form.is_valid():
        return render(
            request, 'fichas/detalhe.html',
            _contexto_detalhe(request, ficha, formulario_nivel=form), status=400,
        )
    nivel_novo = int(form.cleaned_data['nivel_novo'])
    versao = form.cleaned_data['versao']

    with transaction.atomic():
        atual = Ficha.objects.select_for_update().select_related('classe').filter(pk=pk).first()
        if atual is None:
            return render(request, '404.html', status=404)
        _garantir_ficha_editavel(request, atual)
        mesa_atual = _mesa_configuracao()
        autorizado_atual = is_mestre(request.user) or (
            atual.dono_id == request.user.pk and mesa_atual.jogador_pode_subir_nex
        )
        if not autorizado_atual:
            return HttpResponseForbidden('Somente o mestre pode avançar o nível nesta mesa.')
        if mesa_atual.sistema_progressao != 'nivel_nex':
            messages.error(request, 'A mesa não está usando Nível de Experiência e NEX.')
            return redirect('fichas:detalhe', pk=pk)
        if (
            atual.versao != versao
            or atual.nivel_experiencia != ficha.nivel_experiencia
        ):
            form.add_error(None, 'A ficha mudou em outra sessão. Recarregue antes de avançar.')
            return render(
                request, 'fichas/detalhe.html',
                _contexto_detalhe(request, atual, formulario_nivel=form), status=409,
            )
        formulario_atual = AvancoNivelForm(
            request.POST, nivel_atual=atual.nivel_experiencia,
        )
        if not formulario_atual.is_valid():
            return render(
                request, 'fichas/detalhe.html',
                _contexto_detalhe(request, atual, formulario_nivel=formulario_atual),
                status=400,
            )
        if atual.classe_id is None or atual.classe.slug not in (
            'combatente', 'especialista', 'ocultista',
        ):
            messages.error(request, 'Esta ficha não pode avançar por nível de experiência.')
            return redirect('fichas:detalhe', pk=pk)

        nivel_novo = int(formulario_atual.cleaned_data['nivel_novo'])
        nex_anterior = nex_equivalente_por_nivel(atual.nivel_experiencia)
        nex_novo = nex_equivalente_por_nivel(nivel_novo)
        try:
            pendencias = pendencias_ao_subir_nex(
                atual.classe.slug, nex_anterior, nex_novo, intelecto=atual.intelecto,
            )
        except ValueError as erro:
            formulario_atual.add_error('nivel_novo', str(erro))
            return render(
                request, 'fichas/detalhe.html',
                _contexto_detalhe(request, atual, formulario_nivel=formulario_atual),
                status=400,
            )

        atualizados = Ficha.objects.filter(pk=pk, versao=versao).update(
            nivel_experiencia=nivel_novo, versao=F('versao') + 1,
            atualizada_em=timezone.now(),
        )
        if not atualizados:
            formulario_atual.add_error(None, 'A ficha mudou em outra sessão. Recarregue antes de avançar.')
            return render(
                request, 'fichas/detalhe.html',
                _contexto_detalhe(request, atual, formulario_nivel=formulario_atual),
                status=409,
            )
        Pendencia.objects.bulk_create([
            Pendencia(
                ficha=atual,
                tipo=pendencia['tipo'],
                descricao=pendencia['descricao'],
                fonte=pendencia['fonte'],
                quantidade=pendencia.get('quantidade', 1),
            )
            for pendencia in pendencias
        ])
        LogAlteracao.objects.create(
            ficha=atual, usuario=request.user, e_mestre=is_mestre(request.user),
            campo='nivel_experiencia', valor_antigo=str(ficha.nivel_experiencia),
            valor_novo=str(nivel_novo),
        )
    messages.success(request, f'Nível avançado para {nivel_novo}. Escolhas pendentes foram registradas.')
    return redirect('fichas:detalhe', pk=pk)


@login_required
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def registrar_exposicao(request, pk):
    ficha = _ficha_editavel(request, pk)
    mesa = _mesa_configuracao()
    if not is_mestre(request.user):
        return HttpResponseForbidden('Somente o mestre pode registrar exposição paranormal.')
    if (
        mesa.sistema_progressao != 'nivel_nex'
        or not ficha.classe_id or ficha.classe.slug == 'sobrevivente'
        or ficha.nex is None
    ):
        messages.error(request, 'Esta ficha não usa registro separado de exposição.')
        return redirect('fichas:detalhe', pk=pk)

    form = ExposicaoParanormalForm(request.POST, nex_atual=ficha.nex)
    if not form.is_valid():
        return render(
            request, 'fichas/detalhe.html',
            _contexto_detalhe(request, ficha, formulario_exposicao=form), status=400,
        )
    incrementos = {
        'branda': 0, 'moderada': 1, 'profunda': 2, 'total': 5,
        'ritual_1': 1, 'ritual_2': 2, 'ritual_3': 3, 'ritual_4': 4,
    }

    with transaction.atomic():
        atual = Ficha.objects.select_for_update().select_related('classe').filter(pk=pk).first()
        if atual is None:
            return render(request, '404.html', status=404)
        _garantir_ficha_editavel(request, atual)
        mesa_atual = _mesa_configuracao()
        if not is_mestre(request.user):
            return HttpResponseForbidden('Somente o mestre pode registrar exposição paranormal.')
        if mesa_atual.sistema_progressao != 'nivel_nex':
            messages.error(request, 'A mesa não está usando Nível de Experiência e NEX.')
            return redirect('fichas:detalhe', pk=pk)
        if atual.versao != form.cleaned_data['versao'] or atual.nex != ficha.nex:
            form.add_error(None, 'A ficha mudou em outra sessão. Recarregue antes de registrar exposição.')
            return render(
                request, 'fichas/detalhe.html',
                _contexto_detalhe(request, atual, formulario_exposicao=form), status=409,
            )
        formulario_atual = ExposicaoParanormalForm(
            request.POST, nex_atual=atual.nex,
        )
        if not formulario_atual.is_valid():
            return render(
                request, 'fichas/detalhe.html',
                _contexto_detalhe(request, atual, formulario_exposicao=formulario_atual),
                status=400,
            )
        exposicao = formulario_atual.cleaned_data['exposicao']
        nex_novo = atual.nex + incrementos[exposicao]
        atualizados = Ficha.objects.filter(pk=pk, versao=atual.versao, nex=atual.nex).update(
            nex=nex_novo, versao=F('versao') + 1, atualizada_em=timezone.now(),
        )
        if not atualizados:
            formulario_atual.add_error(None, 'A ficha mudou em outra sessão. Recarregue antes de registrar.')
            return render(
                request, 'fichas/detalhe.html',
                _contexto_detalhe(request, atual, formulario_exposicao=formulario_atual),
                status=409,
            )
        LogAlteracao.objects.create(
            ficha=atual, usuario=request.user, e_mestre=True,
            campo='nex_exposicao',
            valor_antigo=str(atual.nex),
            valor_novo=f'{nex_novo}; {exposicao}',
        )
    messages.success(request, f'Exposição registrada. NEX atual: {nex_novo}%.')
    return redirect('fichas:detalhe', pk=pk)


@login_required
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def registrar_prestigio(request, pk):
    ficha = _ficha_editavel(request, pk)
    if not is_mestre(request.user):
        return HttpResponseForbidden('Somente o mestre pode registrar pontos de prestígio.')
    mesa = _mesa_configuracao()
    if mesa.sistema_progressao != 'patentes':
        messages.error(request, 'A mesa não está usando evolução por patentes.')
        return redirect('fichas:detalhe', pk=pk)

    form = RegistroPrestigioForm(request.POST)
    if not form.is_valid():
        return render(
            request, 'fichas/detalhe.html',
            _contexto_detalhe(request, ficha, formulario_prestigio=form), status=400,
        )

    valores_evento = {'solucao': 10, 'pista': 2, 'inocente': -2, 'membro': -5}
    patente_atual = None
    patente_nova = None
    with transaction.atomic():
        mesa_atual = ConfiguracaoMesa.objects.select_for_update().filter(pk=1).first()
        if mesa_atual is None or mesa_atual.sistema_progressao != 'patentes':
            return HttpResponseForbidden('A evolução por patentes não está disponível nesta mesa.')
        atual = Ficha.objects.select_for_update().select_related(
            'classe', 'patente',
        ).filter(pk=pk).first()
        if atual is None:
            return render(request, '404.html', status=404)
        _garantir_ficha_editavel(request, atual)
        if (
            atual.versao != form.cleaned_data['versao']
            or mesa_atual.numero_sessao != form.cleaned_data['numero_sessao']
        ):
            form.add_error(None, 'A ficha ou a sessão mudou. Recarregue antes de registrar.')
            return render(
                request, 'fichas/detalhe.html',
                _contexto_detalhe(request, atual, formulario_prestigio=form), status=409,
            )
        if atual.classe_id is None or atual.classe.slug not in (
            'combatente', 'especialista', 'ocultista',
        ):
            messages.error(request, 'Esta ficha não é compatível com evolução por patentes.')
            return redirect('fichas:detalhe', pk=pk)

        evento = form.cleaned_data['evento']
        quantidade = form.cleaned_data['quantidade']
        registros_da_missao = RegistroPrestigio.objects.filter(
            ficha=atual, numero_sessao=mesa_atual.numero_sessao,
        )
        if evento == 'solucao' and registros_da_missao.filter(evento='solucao').exists():
            form.add_error('evento', 'A solução desta missão já foi registrada para esta ficha.')
        if evento == 'pista' and registros_da_missao.filter(evento='pista').count() >= 3:
            form.add_error('evento', 'O limite de três pistas adicionais nesta missão já foi atingido.')
        if form.errors:
            return render(
                request, 'fichas/detalhe.html',
                _contexto_detalhe(request, atual, formulario_prestigio=form), status=400,
            )

        delta = valores_evento[evento] * quantidade
        total_anterior = atual.pontos_prestigio
        total_novo = total_anterior + delta
        patente_atual = atual.patente or Patente.objects.get(slug='recruta')
        patente_nova = Patente.objects.filter(
            pontos_prestigio__lte=total_novo,
        ).order_by('-pontos_prestigio').first()
        if patente_nova is None or patente_nova.pontos_prestigio < patente_atual.pontos_prestigio:
            patente_nova = patente_atual

        nivel_anterior = patente_atual.limite_pd
        nivel_novo = patente_nova.limite_pd
        pendencias = []
        if nivel_novo > nivel_anterior:
            try:
                pendencias = pendencias_ao_subir_nex(
                    atual.classe.slug,
                    nex_equivalente_por_nivel(nivel_anterior),
                    nex_equivalente_por_nivel(nivel_novo),
                    intelecto=atual.intelecto,
                )
            except ValueError as erro:
                form.add_error(None, str(erro))
                return render(
                    request, 'fichas/detalhe.html',
                    _contexto_detalhe(request, atual, formulario_prestigio=form), status=400,
                )

        maximos_anteriores = _maximos_ficha(atual)
        atual.patente = patente_nova
        maximos_novos = _maximos_ficha(atual)
        pv_novo = min(
            maximos_novos['pv'],
            max(0, atual.pv_atual + maximos_novos['pv'] - maximos_anteriores['pv']),
        )
        pd_novo = min(
            maximos_novos['pd'],
            max(0, atual.pd_atual + maximos_novos['pd'] - maximos_anteriores['pd']),
        )
        atualizados = Ficha.objects.filter(
            pk=pk, versao=form.cleaned_data['versao'],
        ).update(
            pontos_prestigio=total_novo,
            patente=patente_nova,
            pv_atual=pv_novo,
            pd_atual=pd_novo,
            versao=F('versao') + 1,
            atualizada_em=timezone.now(),
        )
        if not atualizados:
            form.add_error(None, 'A ficha mudou em outra sessão. Recarregue antes de registrar.')
            return render(
                request, 'fichas/detalhe.html',
                _contexto_detalhe(request, atual, formulario_prestigio=form), status=409,
            )
        RegistroPrestigio.objects.create(
            ficha=atual,
            usuario=request.user,
            numero_sessao=mesa_atual.numero_sessao,
            evento=evento,
            quantidade=quantidade,
            delta=delta,
        )
        LogAlteracao.objects.create(
            ficha=atual, usuario=request.user, e_mestre=True,
            campo='pontos_prestigio', valor_antigo=str(total_anterior),
            valor_novo=str(total_novo),
        )
        if patente_nova.pk != patente_atual.pk:
            LogAlteracao.objects.create(
                ficha=atual, usuario=request.user, e_mestre=True,
                campo='patente', valor_antigo=patente_atual.nome,
                valor_novo=patente_nova.nome,
            )
            Pendencia.objects.bulk_create([
                Pendencia(
                    ficha=atual,
                    tipo=pendencia['tipo'],
                    descricao=pendencia['descricao'],
                    fonte=pendencia['fonte'],
                    quantidade=pendencia.get('quantidade', 1),
                )
                for pendencia in pendencias
            ])

    if patente_nova.pk != patente_atual.pk:
        messages.success(
            request,
            f'Prestígio registrado. A ficha foi promovida a {patente_nova.nome}; '
            'os benefícios pendentes foram registrados.',
        )
    else:
        messages.success(request, 'Pontos de prestígio registrados.')
    return redirect('fichas:detalhe', pk=pk)


@login_required
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def recuperar_recurso_patente(request, pk):
    ficha = _ficha_editavel(request, pk)
    if _mesa_configuracao().sistema_progressao != 'patentes' or not ficha.patente_id:
        messages.error(request, 'Esta ficha não usa recuperação por patente.')
        return redirect('fichas:detalhe', pk=pk)
    form = RecuperacaoPatenteForm(request.POST)
    if not form.is_valid():
        return render(
            request, 'fichas/detalhe.html',
            _contexto_detalhe(request, ficha, formulario_recuperacao_patente=form),
            status=400,
        )

    recurso = form.cleaned_data['recurso']
    with transaction.atomic():
        mesa = ConfiguracaoMesa.objects.select_for_update().filter(pk=1).first()
        if mesa is None or mesa.sistema_progressao != 'patentes':
            messages.error(request, 'A mesa não está usando recuperação por patente.')
            return redirect('fichas:detalhe', pk=pk)
        atual = Ficha.objects.select_for_update().select_related(
            'classe', 'patente',
        ).filter(pk=pk).first()
        if atual is None:
            return render(request, '404.html', status=404)
        _garantir_ficha_editavel(request, atual)
        if not atual.patente_id:
            messages.error(request, 'A mesa não está usando recuperação por patente.')
            return redirect('fichas:detalhe', pk=pk)
        if atual.versao != form.cleaned_data['versao']:
            form.add_error(None, 'A ficha mudou em outra sessão. Recarregue antes de recuperar.')
            return render(
                request, 'fichas/detalhe.html',
                _contexto_detalhe(request, atual, formulario_recuperacao_patente=form),
                status=409,
            )
        maximos = _maximos_ficha(atual)
        valor_atual = getattr(atual, recurso)
        valor_maximo = maximos['pv' if recurso == 'pv_atual' else 'pd']
        recuperado = min(atual.patente.recuperacao, valor_maximo - valor_atual)
        if recuperado <= 0:
            form.add_error('recurso', 'Esse recurso já está no máximo.')
            return render(
                request, 'fichas/detalhe.html',
                _contexto_detalhe(request, atual, formulario_recuperacao_patente=form),
                status=400,
            )
        atualizados = Ficha.objects.filter(
            pk=pk, versao=form.cleaned_data['versao'],
        ).update(
            **{
                recurso: valor_atual + recuperado,
                'versao': F('versao') + 1,
                'atualizada_em': timezone.now(),
            },
        )
        if not atualizados:
            form.add_error(None, 'A ficha mudou em outra sessão. Recarregue antes de recuperar.')
            return render(
                request, 'fichas/detalhe.html',
                _contexto_detalhe(request, atual, formulario_recuperacao_patente=form),
                status=409,
            )
        LogAlteracao.objects.create(
            ficha=atual, usuario=request.user, e_mestre=is_mestre(request.user),
            campo=recurso,
            valor_antigo=str(valor_atual),
            valor_novo=str(valor_atual + recuperado),
        )
    messages.success(
        request,
        f'Você recuperou {recuperado} ponto{"s" if recuperado != 1 else ""} '
        f'de {recurso[:2].upper()}.',
    )
    return redirect('fichas:detalhe', pk=pk)


@login_required
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def avancar_estagio(request, pk):
    ficha = _ficha_editavel(request, pk)
    if not is_mestre(request.user):
        return HttpResponseForbidden('Somente o mestre pode avançar o estágio nesta mesa.')
    if (
        not ficha.classe_id or ficha.classe.slug != 'sobrevivente'
        or ficha.estagio is None or ficha.estagio >= 5
    ):
        messages.error(request, 'Esta ficha não pode avançar por estágio.')
        return redirect('fichas:detalhe', pk=pk)

    form = AvancoEstagioForm(request.POST, estagio_atual=ficha.estagio)
    if not form.is_valid():
        return render(
            request, 'fichas/detalhe.html',
            _contexto_detalhe(request, ficha, formulario_estagio=form),
            status=400,
        )
    estagio_novo = int(form.cleaned_data['estagio_novo'])
    versao = form.cleaned_data['versao']

    with transaction.atomic():
        atual = Ficha.objects.select_for_update().filter(pk=pk).first()
        if atual is None:
            return render(request, '404.html', status=404)
        _garantir_ficha_editavel(request, atual)
        if (
            atual.classe_id is None or atual.classe.slug != 'sobrevivente'
            or atual.estagio is None or atual.estagio >= 5
        ):
            messages.error(request, 'Esta ficha não pode avançar por estágio.')
            return redirect('fichas:detalhe', pk=pk)
        if not is_mestre(request.user):
            return HttpResponseForbidden('Somente o mestre pode avançar o estágio nesta mesa.')
        if atual.versao != versao or atual.estagio != ficha.estagio:
            form.add_error(None, 'A ficha mudou em outra sessão. Recarregue antes de avançar.')
            return render(
                request, 'fichas/detalhe.html',
                _contexto_detalhe(request, atual, formulario_estagio=form),
                status=409,
            )
        try:
            pendencias = pendencias_ao_subir_estagio(atual.estagio, estagio_novo)
        except ValueError as erro:
            form.add_error('estagio_novo', str(erro))
            return render(
                request, 'fichas/detalhe.html',
                _contexto_detalhe(request, atual, formulario_estagio=form),
                status=400,
            )
        atualizados = Ficha.objects.filter(
            pk=pk, versao=versao, estagio=atual.estagio,
        ).update(
            estagio=estagio_novo,
            versao=F('versao') + 1,
            atualizada_em=timezone.now(),
        )
        if not atualizados:
            form.add_error(None, 'A ficha mudou em outra sessão. Recarregue antes de avançar.')
            return render(
                request, 'fichas/detalhe.html',
                _contexto_detalhe(request, atual, formulario_estagio=form),
                status=409,
            )
        Pendencia.objects.bulk_create([
            Pendencia(
                ficha=atual,
                tipo=pendencia['tipo'],
                descricao=pendencia['descricao'],
                fonte=pendencia['fonte'],
                quantidade=pendencia.get('quantidade', 1),
            )
            for pendencia in pendencias
        ])
        LogAlteracao.objects.create(
            ficha=atual,
            usuario=request.user,
            e_mestre=is_mestre(request.user),
            campo='estagio',
            valor_antigo=str(atual.estagio),
            valor_novo=str(estagio_novo),
        )
    messages.success(request, f'Estágio avançado para {estagio_novo}. Escolhas pendentes foram registradas.')
    return redirect('fichas:detalhe', pk=pk)


@login_required
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def usar_cicatrizado(request, pk):
    form = UsarCicatrizadoForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Informe uma reação válida de Cicatrizado.')
        return redirect('fichas:detalhe', pk=pk)

    with transaction.atomic():
        ficha = _ficha_editavel(request, pk, bloquear=True)
        mesa = ConfiguracaoMesa.objects.select_for_update().filter(pk=1).first()
        if mesa is None:
            mesa = ConfiguracaoMesa()
        if (
            ficha.classe_id is None or ficha.classe.slug != 'sobrevivente'
            or ficha.estagio != 5 or not ficha.cicatrizado_elemento
            or not ficha.cicatrizado_perigo
        ):
            messages.error(request, 'Cicatrizado ainda não foi registrado nesta ficha.')
            return redirect('fichas:detalhe', pk=pk)
        if ficha.cicatrizado_sessao_usada == mesa.numero_sessao:
            messages.error(request, 'Cicatrizado já foi usado nesta sessão.')
            return redirect('fichas:detalhe', pk=pk)

        efeito = form.cleaned_data['efeito']
        maximos_antes = _maximos_ficha(ficha)
        if efeito in ('ignorar_mental', 'ignorar_custo'):
            if maximos_antes['pv'] < 1:
                messages.error(request, 'Não há PV máximo disponível para sacrificar.')
                return redirect('fichas:detalhe', pk=pk)
            ficha.ajuste_pv_max -= 1
            maximo_novo = maximos_antes['pv'] - 1
            pv_anterior = ficha.pv_atual
            ficha.pv_atual = min(ficha.pv_atual, maximo_novo)
            campo_ajuste = 'ajuste_pv_max'
            recurso_afetado = 'pv'
        else:
            campo_ajuste = (
                'ajuste_pd_max' if mesa.modo_recursos == 'sem_sanidade'
                else 'ajuste_pe_max'
            )
            recurso_afetado = 'pd' if campo_ajuste == 'ajuste_pd_max' else 'pe'
            if maximos_antes[recurso_afetado] < 1:
                messages.error(request, 'Não há PE/PD máximo disponível para sacrificar.')
                return redirect('fichas:detalhe', pk=pk)
            setattr(ficha, campo_ajuste, getattr(ficha, campo_ajuste) - 1)
            maximo_novo = maximos_antes[recurso_afetado] - 1
            campo_atual = 'pd_atual' if recurso_afetado == 'pd' else 'pe_atual'
            recurso_anterior = getattr(ficha, campo_atual)
            setattr(ficha, campo_atual, min(recurso_anterior, maximo_novo))

        ficha.cicatrizado_sessao_usada = mesa.numero_sessao
        campos = [
            campo_ajuste, 'cicatrizado_sessao_usada', 'versao', 'atualizada_em',
        ]
        if recurso_afetado == 'pv':
            campos.append('pv_atual')
        else:
            campos.append('pd_atual' if recurso_afetado == 'pd' else 'pe_atual')
        ficha.versao += 1
        ficha.save(update_fields=tuple(dict.fromkeys(campos)))
        LogAlteracao.objects.create(
            ficha=ficha,
            usuario=request.user,
            e_mestre=is_mestre(request.user),
            campo='cicatrizado',
            valor_antigo='disponível',
            valor_novo=f'{efeito}; sacrifício permanente de {recurso_afetado.upper()}',
        )
        LogAlteracao.objects.create(
            ficha=ficha,
            usuario=request.user,
            e_mestre=is_mestre(request.user),
            campo=campo_ajuste,
            valor_antigo=str(getattr(ficha, campo_ajuste) + 1),
            valor_novo=str(getattr(ficha, campo_ajuste)),
        )
        if recurso_afetado == 'pv' and ficha.pv_atual != pv_anterior:
            LogAlteracao.objects.create(
                ficha=ficha,
                usuario=request.user,
                e_mestre=is_mestre(request.user),
                campo='pv_atual',
                valor_antigo=str(pv_anterior),
                valor_novo=str(ficha.pv_atual),
            )
        elif recurso_afetado != 'pv' and getattr(ficha, campo_atual) != recurso_anterior:
            LogAlteracao.objects.create(
                ficha=ficha,
                usuario=request.user,
                e_mestre=is_mestre(request.user),
                campo=campo_atual,
                valor_antigo=str(recurso_anterior),
                valor_novo=str(getattr(ficha, campo_atual)),
            )
        if efeito == 'reduzir_fisico':
            dano = form.cleaned_data['dano_fisico']
            messages.info(
                request,
                f'Cicatrizado: aplique {dano // 2} dano físico (metade de {dano}, arredondada para baixo).',
            )
    if efeito != 'reduzir_fisico':
        messages.success(
            request,
            'Cicatrizado usado. O dano/custo escolhido é ignorado; o sacrifício de recurso máximo é permanente.',
        )
    return redirect('fichas:detalhe', pk=pk)


def _formulario_pendencia(request, ficha, pendencia):
    kwargs = {'data': request.POST} if request.method == 'POST' else {}
    if pendencia.tipo == 'atributo':
        return PendenciaAtributoForm(ficha=ficha, **kwargs)
    if pendencia.tipo == 'treinamento':
        return PendenciaTreinamentoForm(
            ficha=ficha, quantidade=pendencia.quantidade, **kwargs,
        )
    if pendencia.tipo == 'trilha':
        return PendenciaTrilhaForm(ficha=ficha, **kwargs)
    if pendencia.tipo in ('poder', 'versatilidade'):
        return PendenciaPoderForm(ficha=ficha, **kwargs)
    if pendencia.tipo == 'ritual':
        return PendenciaRitualForm(
            nivel_nex=(
                _mesa_configuracao().sistema_progressao == 'nivel_nex'
                and ficha.classe_id is not None
                and ficha.classe.slug == 'ocultista'
            ),
            **kwargs,
        )
    if pendencia.tipo == 'cicatrizado':
        return CicatrizadoForm(**kwargs)
    return None


@login_required
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def resolver_pendencia(request, pk, pendencia_pk):
    ficha = _ficha_editavel(request, pk)
    pendencia = get_object_or_404(
        ficha.pendencias.filter(resolvida=False), pk=pendencia_pk,
    )
    form = _formulario_pendencia(request, ficha, pendencia)
    if form is None:
        messages.error(request, 'O tipo desta pendência não pode ser resolvido.')
        return redirect('fichas:detalhe', pk=pk)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            ficha = _ficha_editavel(request, pk, bloquear=True)
            pendencia = get_object_or_404(
                ficha.pendencias.select_for_update().filter(resolvida=False),
                pk=pendencia_pk,
            )
            form = _formulario_pendencia(request, ficha, pendencia)
            if form is None or not form.is_valid():
                return render(request, 'fichas/resolver_pendencia.html', {
                    'ficha': ficha,
                    'pendencia': pendencia,
                    'form': form,
                }, status=400)
            valores_auditados = []
            if pendencia.tipo == 'atributo':
                atributo = form.cleaned_data['atributo']
                anterior = getattr(ficha, atributo)
                setattr(ficha, atributo, anterior + 1)
                ficha.save(update_fields=(atributo, 'atualizada_em'))
                valores_auditados.append((f'atributo.{atributo}', str(anterior), str(anterior + 1)))
            elif pendencia.tipo == 'treinamento':
                ordem_graus = [grau for grau, _ in FichaPericia.GRAUS]
                for pericia in form.cleaned_data['pericias']:
                    ficha_pericia = FichaPericia.objects.select_for_update().filter(
                        ficha=ficha, pericia=pericia,
                    ).first()
                    grau_anterior = ficha_pericia.grau if ficha_pericia else 'destreinado'
                    grau_novo = ordem_graus[ordem_graus.index(grau_anterior) + 1]
                    if ficha_pericia:
                        ficha_pericia.grau = grau_novo
                        ficha_pericia.save(update_fields=('grau',))
                    else:
                        FichaPericia.objects.create(
                            ficha=ficha, pericia=pericia, grau=grau_novo,
                        )
                    valores_auditados.append((
                        f'pericia.{pericia.slug}', grau_anterior, grau_novo,
                    ))
            elif pendencia.tipo == 'trilha':
                trilha = form.cleaned_data['trilha']
                anterior = (
                    ficha.trilha.nome if ficha.trilha_id
                    else ficha.trilha_nome_personalizado
                )
                if trilha:
                    ficha.trilha = trilha
                    ficha.trilha_nome_personalizado = ''
                    ficha.trilha_resumo_personalizado = ''
                    ficha.trilha_fonte_personalizada = ''
                    nome = trilha.nome
                else:
                    ficha.trilha = None
                    ficha.trilha_nome_personalizado = form.cleaned_data['nome_personalizado']
                    ficha.trilha_resumo_personalizado = form.cleaned_data['resumo_personalizado']
                    ficha.trilha_fonte_personalizada = 'Personalizado'
                    nome = ficha.trilha_nome_personalizado
                ficha.save(update_fields=(
                    'trilha', 'trilha_nome_personalizado', 'trilha_resumo_personalizado',
                    'trilha_fonte_personalizada', 'atualizada_em',
                ))
                valores_auditados.append(('trilha', anterior, nome))
            elif pendencia.tipo == 'cicatrizado':
                if ficha.classe_id is None or ficha.classe.slug != 'sobrevivente' or ficha.estagio != 5:
                    messages.error(request, 'Cicatrizado só pode ser registrado no estágio 5 do Sobrevivente.')
                    return redirect('fichas:detalhe', pk=pk)
                elemento = form.cleaned_data['elemento']
                perigo = form.cleaned_data['perigo']
                anterior = ficha.cicatrizado_perigo
                ficha.cicatrizado_elemento = elemento
                ficha.cicatrizado_perigo = perigo
                ficha.save(update_fields=(
                    'cicatrizado_elemento', 'cicatrizado_perigo', 'atualizada_em',
                ))
                valores_auditados.append(('cicatrizado.perigo', anterior, perigo))
                valores_auditados.append(('cicatrizado.elemento', '', elemento))
            elif pendencia.tipo in ('poder', 'versatilidade'):
                poder = form.cleaned_data.get('poder')
                nome = poder.nome if poder else form.cleaned_data['nome_personalizado']
                if poder:
                    FichaPoder.objects.create(
                        ficha=ficha, poder=poder, fonte=poder.fonte,
                    )
                else:
                    FichaPoder.objects.create(
                        ficha=ficha,
                        nome_personalizado=nome,
                        resumo_personalizado=form.cleaned_data['resumo_personalizado'],
                        fonte='Personalizado',
                    )
                valores_auditados.append(('poder', '', nome))
            else:
                ritual = form.cleaned_data.get('ritual')
                nome = ritual.nome if ritual else form.cleaned_data['nome_personalizado']
                circulo = ritual.circulo if ritual else int(
                    form.cleaned_data['circulo_personalizado']
                ) if form.cleaned_data.get('circulo_personalizado') else None
                if ritual:
                    FichaRitual.objects.create(
                        ficha=ficha, ritual=ritual, fonte=ritual.fonte,
                    )
                else:
                    FichaRitual.objects.create(
                        ficha=ficha,
                        nome_personalizado=nome,
                        resumo_personalizado=form.cleaned_data['resumo_personalizado'],
                        fonte='Personalizado',
                    )
                valores_auditados.append(('ritual', '', nome))
                if (
                    circulo is not None
                    and _mesa_configuracao().sistema_progressao == 'nivel_nex'
                    and ficha.classe_id is not None
                    and ficha.classe.slug == 'ocultista'
                ):
                    nex_anterior = ficha.nex
                    ficha.nex = min(99, ficha.nex + circulo)
                    ficha.save(update_fields=('nex', 'atualizada_em'))
                    valores_auditados.append((
                        'nex_ritual', str(nex_anterior),
                        f'{ficha.nex}; ritual de {circulo}º círculo',
                    ))

            for campo, valor_antigo, valor_novo in valores_auditados:
                LogAlteracao.objects.create(
                    ficha=ficha,
                    usuario=request.user,
                    e_mestre=is_mestre(request.user),
                    campo=campo,
                    valor_antigo=valor_antigo,
                    valor_novo=valor_novo,
                )
            pendencia.resolvida = True
            pendencia.save(update_fields=('resolvida',))
            LogAlteracao.objects.create(
                ficha=ficha,
                usuario=request.user,
                e_mestre=is_mestre(request.user),
                campo='pendencia',
                valor_antigo=pendencia.tipo,
                valor_novo='resolvida',
            )
            ficha.versao = F('versao') + 1
            ficha.save(update_fields=('versao', 'atualizada_em'))
        messages.success(request, 'Escolha registrada e pendência resolvida.')
        return redirect('fichas:detalhe', pk=pk)
    return render(request, 'fichas/resolver_pendencia.html', {
        'ficha': ficha,
        'pendencia': pendencia,
        'form': form,
    }, status=400 if request.method == 'POST' else 200)


@login_required
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def editar_ficha(request, pk):
    ficha = _ficha_editavel(request, pk)
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
                ficha = _ficha_editavel(request, pk, bloquear=True)
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
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def configurar_mesa(request):
    if not is_mestre(request.user):
        return HttpResponseForbidden('Somente o mestre pode configurar a mesa.')
    mesa = ConfiguracaoMesa.objects.filter(pk=1).first()
    if mesa is None:
        mesa = ConfiguracaoMesa.objects.create()
    if request.method == 'POST':
        form = ConfiguracaoMesaForm(
            request.POST, sistema_progressao_atual=mesa.sistema_progressao,
        )
        if form.is_valid():
            with transaction.atomic():
                mesa = ConfiguracaoMesa.objects.select_for_update().get(pk=1)
                if (
                    form.cleaned_data['sistema_progressao'] != mesa.sistema_progressao
                    and Ficha.objects.exists()
                ):
                    form.add_error(
                        'sistema_progressao',
                        'Não é possível trocar a progressão depois que fichas foram criadas.',
                    )
                    return render(
                        request, 'fichas/configuracao_mesa.html',
                        {'form': form, 'mesa': mesa}, status=400,
                    )
                ativou_ferimentos = (
                    not mesa.ferimentos_debilitantes
                    and form.cleaned_data['ferimentos_debilitantes']
                )
                for campo, valor in form.cleaned_data.items():
                    setattr(mesa, campo, valor)
                mesa.save(update_fields=tuple(form.cleaned_data))
                if ativou_ferimentos:
                    fichas_com_ferimento_vigor = Ficha.objects.filter(
                        ferimentos__atributo='vigor',
                        ferimentos__curado_em__isnull=True,
                    ).distinct().select_for_update().order_by('pk')
                    for ficha in fichas_com_ferimento_vigor:
                        pv_anterior = ficha.pv_atual
                        ficha.pv_atual = min(pv_anterior, _maximos_ficha(ficha)['pv'])
                        if ficha.pv_atual != pv_anterior:
                            ficha.versao += 1
                            ficha.save(update_fields=('pv_atual', 'versao', 'atualizada_em'))
                            LogAlteracao.objects.create(
                                ficha=ficha,
                                usuario=request.user,
                                e_mestre=True,
                                campo='pv_atual',
                                valor_antigo=str(pv_anterior),
                                valor_novo=str(ficha.pv_atual),
                            )
            messages.success(request, 'Configurações da mesa salvas.')
            return redirect('fichas:configurar_mesa')
    else:
        form = ConfiguracaoMesaForm(initial={
            'modo_recursos': mesa.modo_recursos,
            'sistema_progressao': mesa.sistema_progressao,
            'jogador_pode_subir_nex': mesa.jogador_pode_subir_nex,
            'ferimentos_debilitantes': mesa.ferimentos_debilitantes,
            'max_fichas_ativas': mesa.max_fichas_ativas,
        })
    return render(request, 'fichas/configuracao_mesa.html', {'form': form, 'mesa': mesa})


def _encontro_do_mestre(request, pk, *, bloquear=False):
    if not is_mestre(request.user):
        raise PermissionDenied
    encontros = EncontroCombate.objects.all()
    if bloquear:
        encontros = encontros.select_for_update()
    return get_object_or_404(encontros, pk=pk)


@login_required
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def gerenciar_encontros(request):
    if not is_mestre(request.user):
        raise PermissionDenied
    if request.method == 'POST':
        form = EncontroCombateForm(request.POST)
        if form.is_valid():
            encontro = form.save(commit=False)
            encontro.criado_por = request.user
            encontro.save()
            messages.success(request, 'Cena de combate criada. Adicione participantes e resultados de Iniciativa.')
            return redirect('fichas:encontro_combate', pk=encontro.pk)
    else:
        form = EncontroCombateForm()
    return render(request, 'fichas/encontros_combate.html', {
        'form': form,
        'encontros': EncontroCombate.objects.prefetch_related(
            'participantes', 'participantes__ficha__condicoes__condicao',
        ).all(),
    }, status=400 if request.method == 'POST' else 200)


@login_required
def encontro_combate(request, pk):
    encontro = _encontro_do_mestre(request, pk)
    participantes = list(
        encontro.participantes.select_related(
            'ficha__classe', 'ficha__patente', 'ameaca',
        )
        .order_by('-iniciativa', 'pk')
    )
    mesa = _mesa_configuracao()
    for participante in participantes:
        if participante.ficha_id:
            participante.limite_pe_turno = _limite_recurso_turno(participante.ficha, 'pe', mesa)
            participante.limite_pd_turno = _limite_recurso_turno(participante.ficha, 'pd', mesa)
    atual = (
        participantes[encontro.indice_turno]
        if 0 <= encontro.indice_turno < len(participantes) else None
    )
    form = ParticipanteCombateForm()
    return render(request, 'fichas/encontro_combate.html', {
        'encontro': encontro,
        'participantes': participantes,
        'atual': atual,
        'form_participante': form,
        'form_dano': DanoCombateForm(),
        'modo_recursos': mesa.modo_recursos,
    })


@login_required
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def adicionar_participante_combate(request, pk):
    form = ParticipanteCombateForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Confira o nome/ficha e o resultado de Iniciativa.')
        return redirect('fichas:encontro_combate', pk=pk)
    with transaction.atomic():
        encontro = _encontro_do_mestre(request, pk, bloquear=True)
        if not encontro.ativo or encontro.indice_turno >= 0:
            messages.error(request, 'Adicione participantes antes de iniciar a ordem de turnos.')
            return redirect('fichas:encontro_combate', pk=pk)
        ficha = form.cleaned_data['ficha']
        if ficha:
            ficha = get_object_or_404(
                fichas_visiveis_para(request.user).select_for_update(), pk=ficha.pk,
            )
            if not pode_editar_ficha(request.user, ficha):
                raise PermissionDenied
            if ParticipanteCombate.objects.filter(ficha=ficha, encontro__ativo=True).exists():
                messages.error(request, 'Esta ficha já participa de uma cena de combate ativa.')
                return redirect('fichas:encontro_combate', pk=pk)
            if ParticipanteCombate.objects.filter(encontro=encontro, ficha=ficha).exists():
                messages.error(request, 'Esta ficha já participa desta cena.')
                return redirect('fichas:encontro_combate', pk=pk)
        participante = form.save(commit=False)
        participante.encontro = encontro
        participante.ficha = ficha
        participante.save()
        if ficha:
            LogAlteracao.objects.create(
                ficha=ficha, usuario=request.user, e_mestre=True,
                campo='combate.iniciativa', valor_novo=str(participante.iniciativa),
            )
    return redirect('fichas:encontro_combate', pk=pk)


@login_required
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def registrar_acao_combate(request, pk, participante_pk):
    with transaction.atomic():
        encontro = _encontro_do_mestre(request, pk, bloquear=True)
        participantes = list(encontro.participantes.select_for_update().order_by('-iniciativa', 'pk'))
        participante = get_object_or_404(
            encontro.participantes.select_for_update(), pk=participante_pk,
        )
        if (
            not encontro.ativo or encontro.indice_turno < 0
            or encontro.indice_turno >= len(participantes)
            or participantes[encontro.indice_turno].pk != participante.pk
        ):
            messages.error(request, 'Ações só podem ser registradas para quem está no turno atual.')
            return redirect('fichas:encontro_combate', pk=pk)
        ficha = None
        if participante.ficha_id:
            ficha = get_object_or_404(fichas_visiveis_para(request.user), pk=participante.ficha_id)
            if not pode_editar_ficha(request.user, ficha):
                raise PermissionDenied
            if ficha.pv_atual <= 0:
                messages.error(request, 'Personagem inconsciente não pode realizar ações normais.')
                return redirect('fichas:encontro_combate', pk=pk)

        acao = request.POST.get('acao')
        if acao == 'padrao':
            if participante.acao_padrao_usada or participante.acao_completa_usada or participante.acoes_movimento_usadas >= 2:
                messages.error(request, 'A ação padrão não está disponível neste turno.')
                return redirect('fichas:encontro_combate', pk=pk)
            participante.acao_padrao_usada = True
            campo = 'acao_padrao_usada'
        elif acao == 'movimento':
            if participante.acao_completa_usada or participante.acoes_movimento_usadas >= 2:
                messages.error(request, 'Não há outra ação de movimento disponível neste turno.')
                return redirect('fichas:encontro_combate', pk=pk)
            participante.acoes_movimento_usadas += 1
            campo = 'acoes_movimento_usadas'
        elif acao == 'completa':
            if (
                participante.acao_completa_usada or participante.acao_padrao_usada
                or participante.acoes_movimento_usadas
            ):
                messages.error(request, 'A ação completa exige que as ações padrão e de movimento estejam livres.')
                return redirect('fichas:encontro_combate', pk=pk)
            participante.acao_completa_usada = True
            campo = 'acao_completa_usada'
        elif acao == 'reacao_defensiva':
            if participante.reacao_defensiva_usada:
                messages.error(request, 'A reação defensiva já foi usada nesta rodada.')
                return redirect('fichas:encontro_combate', pk=pk)
            participante.reacao_defensiva_usada = True
            campo = 'reacao_defensiva_usada'
        else:
            messages.error(request, 'Ação inválida.')
            return redirect('fichas:encontro_combate', pk=pk)
        participante.save(update_fields=(campo,))
        if ficha:
            LogAlteracao.objects.create(
                ficha=ficha, usuario=request.user, e_mestre=True,
                campo='combate.acao', valor_novo=acao,
            )
    return redirect('fichas:encontro_combate', pk=pk)


@login_required
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def gastar_recurso_combate(request, pk, participante_pk):
    recurso = request.POST.get('recurso')
    quantidade_texto = request.POST.get('quantidade', '')
    if (
        recurso not in {'pe', 'pd'}
        or not quantidade_texto.isdecimal()
        or len(quantidade_texto) > 4
        or not 1 <= int(quantidade_texto) <= 1000
    ):
        messages.error(request, 'Informe PE ou PD e um gasto inteiro entre 1 e 1000.')
        return redirect('fichas:encontro_combate', pk=pk)
    quantidade = int(quantidade_texto)
    with transaction.atomic():
        encontro = _encontro_do_mestre(request, pk, bloquear=True)
        participantes = list(encontro.participantes.select_for_update().order_by('-iniciativa', 'pk'))
        participante = get_object_or_404(
            encontro.participantes.select_for_update().select_related('ficha__classe', 'ficha__patente'),
            pk=participante_pk,
        )
        if (
            not encontro.ativo or encontro.indice_turno < 0
            or encontro.indice_turno >= len(participantes)
            or participantes[encontro.indice_turno].pk != participante.pk
        ):
            messages.error(request, 'Recursos só podem ser gastos por quem está no turno atual.')
            return redirect('fichas:encontro_combate', pk=pk)
        if not participante.ficha_id:
            messages.error(request, 'O participante precisa estar vinculado a uma ficha.')
            return redirect('fichas:encontro_combate', pk=pk)
        ficha = get_object_or_404(
            fichas_visiveis_para(request.user).select_for_update().select_related('classe', 'patente'),
            pk=participante.ficha_id,
        )
        if not pode_editar_ficha(request.user, ficha):
            raise PermissionDenied
        mesa = _mesa_configuracao()
        if recurso == 'pe':
            limite = _limite_recurso_turno(ficha, 'pe', mesa)
            if limite is None:
                messages.error(request, 'PE não está ativo nesta mesa.')
                return redirect('fichas:encontro_combate', pk=pk)
            campo_gasto = 'pe_gasto_turno'
            recurso_campo = 'pe'
        else:
            limite = _limite_recurso_turno(ficha, 'pd', mesa)
            if limite is None:
                messages.error(request, 'PD por turno exige modo Sem Sanidade e uma ficha com patente.')
                return redirect('fichas:encontro_combate', pk=pk)
            campo_gasto = 'pd_gasto_turno'
            recurso_campo = 'pd'

        ja_gasto = getattr(participante, campo_gasto)
        if ja_gasto + quantidade > limite:
            messages.error(request, f'Este gasto ultrapassa o limite de {limite} {recurso.upper()} por turno.')
            return redirect('fichas:encontro_combate', pk=pk)
        if getattr(ficha, f'{recurso_campo}_atual') < quantidade:
            messages.error(request, f'{recurso.upper()} insuficientes.')
            return redirect('fichas:encontro_combate', pk=pk)

        _aplicar_delta_recurso(ficha, request.user, recurso_campo, -quantidade)
        setattr(participante, campo_gasto, ja_gasto + quantidade)
        participante.save(update_fields=(campo_gasto,))
        LogAlteracao.objects.create(
            ficha=ficha, usuario=request.user, e_mestre=True,
            campo='combate.recurso', valor_antigo=str(ja_gasto),
            valor_novo=str(ja_gasto + quantidade),
        )
    messages.success(
        request,
        f'{quantidade} {recurso.upper()} gastos neste turno ({ja_gasto + quantidade}/{limite}).',
    )
    return redirect('fichas:encontro_combate', pk=pk)


@login_required
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def aplicar_dano_combate(request, pk, participante_pk):
    form = DanoCombateForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Informe um valor de dano entre 1 e 1000.')
        return redirect('fichas:encontro_combate', pk=pk)
    with transaction.atomic():
        encontro = _encontro_do_mestre(request, pk, bloquear=True)
        if not encontro.ativo:
            messages.error(request, 'Não é possível aplicar dano em uma cena encerrada.')
            return redirect('fichas:encontro_combate', pk=pk)
        participante = get_object_or_404(
            encontro.participantes.select_for_update(), pk=participante_pk,
        )
        if not participante.ficha_id:
            messages.error(request, 'O participante não está vinculado a uma ficha.')
            return redirect('fichas:encontro_combate', pk=pk)
        ficha = get_object_or_404(
            fichas_visiveis_para(request.user).select_for_update(),
            pk=participante.ficha_id,
        )
        if not pode_editar_ficha(request.user, ficha):
            raise PermissionDenied
        resultado = _aplicar_delta_recurso(
            ficha, request.user, 'pv', -form.cleaned_data['dano'],
        )
        mensagens = [f"Dano aplicado: {abs(resultado['aplicado'])}."]
        if resultado['pv_temporario_aplicado']:
            mensagens.append(
                f"PV temporários absorveram {resultado['pv_temporario_aplicado']}."
            )
        if resultado['sobrou']:
            mensagens.append(f"Excesso não aplicado: {abs(resultado['sobrou'])}.")
        messages.success(request, ' '.join(mensagens))
    return redirect('fichas:encontro_combate', pk=pk)


@login_required
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def avancar_turno_combate(request, pk):
    with transaction.atomic():
        encontro = _encontro_do_mestre(request, pk, bloquear=True)
        participantes = list(
            encontro.participantes.select_for_update().select_related('ficha')
            .order_by('-iniciativa', 'pk')
        )
        if not encontro.ativo or not participantes:
            messages.error(request, 'A cena não está ativa ou não possui participantes.')
            return redirect('fichas:encontro_combate', pk=pk)

        proximo_indice = encontro.indice_turno + 1
        if proximo_indice >= len(participantes):
            encontro.rodada += 1
            proximo_indice = 0
            for participante in participantes:
                participante.reacao_defensiva_usada = False
                participante.save(update_fields=('reacao_defensiva_usada',))
        while encontro.rodada == 1 and participantes[proximo_indice].surpreendido:
            proximo_indice += 1
            if proximo_indice >= len(participantes):
                encontro.rodada += 1
                proximo_indice = 0
                for participante in participantes:
                    participante.reacao_defensiva_usada = False
                    participante.save(update_fields=('reacao_defensiva_usada',))

        participante = participantes[proximo_indice]
        participante.acao_padrao_usada = False
        participante.acoes_movimento_usadas = 0
        participante.acao_completa_usada = False
        participante.pe_gasto_turno = 0
        participante.pd_gasto_turno = 0
        participante.save(update_fields=(
            'acao_padrao_usada', 'acoes_movimento_usadas', 'acao_completa_usada',
            'pe_gasto_turno', 'pd_gasto_turno',
        ))
        if participante.ficha_id:
            ficha = get_object_or_404(fichas_visiveis_para(request.user), pk=participante.ficha_id)
            if not pode_editar_ficha(request.user, ficha):
                raise PermissionDenied
            for condicao_temporaria in FichaCondicao.objects.select_for_update().filter(
                ficha=ficha, turnos_restantes__isnull=False,
            ).exclude(condicao__slug='morrendo').select_related('condicao'):
                anterior = condicao_temporaria.turnos_restantes
                if anterior <= 1:
                    condicao_temporaria.delete()
                    LogAlteracao.objects.create(
                        ficha=ficha, usuario=request.user, e_mestre=True,
                        campo='condicao', valor_antigo=condicao_temporaria.condicao.nome,
                        valor_novo='Expirada no início do turno',
                    )
                else:
                    condicao_temporaria.turnos_restantes = anterior - 1
                    condicao_temporaria.save(update_fields=('turnos_restantes',))
                    LogAlteracao.objects.create(
                        ficha=ficha, usuario=request.user, e_mestre=True,
                        campo='condicao.duracao', valor_antigo=str(anterior),
                        valor_novo=str(anterior - 1),
                    )
            morrendo = FichaCondicao.objects.select_for_update().filter(
                ficha=ficha, condicao__slug='morrendo',
            ).first()
            if ficha.pv_atual == 0 and morrendo:
                morrendo.turnos_morrendo += 1
                morrendo.save(update_fields=('turnos_morrendo',))
                LogAlteracao.objects.create(
                    ficha=ficha, usuario=request.user, e_mestre=True,
                    campo='combate.turnos_morrendo', valor_novo=str(morrendo.turnos_morrendo),
                )
                if morrendo.turnos_morrendo >= 3 and ficha.status != 'morta':
                    status_anterior = ficha.status
                    ficha.status = 'morta'
                    ficha.versao += 1
                    ficha.save(update_fields=('status', 'versao', 'atualizada_em'))
                    LogAlteracao.objects.create(
                        ficha=ficha, usuario=request.user, e_mestre=True,
                        campo='status', valor_antigo=status_anterior, valor_novo='morta',
                    )
        encontro.indice_turno = proximo_indice
        encontro.save(update_fields=('rodada', 'indice_turno', 'atualizado_em'))
    return redirect('fichas:encontro_combate', pk=pk)


@login_required
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def estabilizar_combate(request, pk, participante_pk):
    with transaction.atomic():
        encontro = _encontro_do_mestre(request, pk, bloquear=True)
        participante = get_object_or_404(
            encontro.participantes.select_for_update(), pk=participante_pk, ficha__isnull=False,
        )
        ficha = get_object_or_404(fichas_visiveis_para(request.user), pk=participante.ficha_id)
        if not pode_editar_ficha(request.user, ficha):
            raise PermissionDenied
        if request.POST.get('confirmar') != 'on':
            messages.error(request, 'Confirme que o teste físico de Medicina DT 20 foi bem-sucedido.')
            return redirect('fichas:encontro_combate', pk=pk)
        morrendo = FichaCondicao.objects.select_for_update().filter(
            ficha=ficha, condicao__slug='morrendo',
        ).first()
        if morrendo is None or ficha.status == 'morta':
            messages.error(request, 'Este personagem não pode ser estabilizado.')
            return redirect('fichas:encontro_combate', pk=pk)
        morrendo.delete()
        LogAlteracao.objects.create(
            ficha=ficha, usuario=request.user, e_mestre=True,
            campo='condicao', valor_antigo='Morrendo', valor_novo='Estabilizado (Medicina DT 20)',
        )
    return redirect('fichas:encontro_combate', pk=pk)


@login_required
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def encerrar_encontro_combate(request, pk):
    with transaction.atomic():
        encontro = _encontro_do_mestre(request, pk, bloquear=True)
        for ficha_condicao in FichaCondicao.objects.select_for_update().filter(
            ficha__participacoes_combate__encontro=encontro,
            condicao__slug='morrendo',
            turnos_morrendo__gt=0,
        ).select_related('ficha'):
            anterior = ficha_condicao.turnos_morrendo
            ficha_condicao.turnos_morrendo = 0
            ficha_condicao.save(update_fields=('turnos_morrendo',))
            LogAlteracao.objects.create(
                ficha=ficha_condicao.ficha, usuario=request.user, e_mestre=True,
                campo='combate.turnos_morrendo', valor_antigo=str(anterior), valor_novo='0',
            )
        condicoes_fim_cena = FichaCondicao.objects.select_for_update().filter(
            ficha__participacoes_combate__encontro=encontro,
            condicao__termina_fim_cena=True,
        ).select_related('ficha', 'condicao')
        for ficha_condicao in condicoes_fim_cena:
            ficha_condicao.delete()
            LogAlteracao.objects.create(
                ficha=ficha_condicao.ficha,
                usuario=request.user,
                e_mestre=True,
                campo='condicao',
                valor_antigo=ficha_condicao.condicao.nome,
                valor_novo='',
            )
        encontro.ativo = False
        encontro.save(update_fields=('ativo', 'atualizado_em'))
    return redirect('fichas:encontro_combate', pk=pk)