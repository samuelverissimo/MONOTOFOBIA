"""Explicações puras dos modificadores mecânicos aplicados a uma rolagem."""

from .regras import modificadores_condicoes, parametros_teste


def explicar_teste(
    atributo,
    condicoes,
    *,
    tipo,
    atributo_slug=None,
    pericia_slug=None,
    dados_extras=0,
    dados_pericia_extra=0,
    bonus_pericia=0,
    bonus_pericia_extra=0,
    bonus_pericia_contextual=0,
    bonus=0,
):
    """Calcula a pool e detalha a contribuição de cada condição e bônus."""
    if any(type(valor) is not int for valor in (
        dados_extras, dados_pericia_extra, bonus_pericia, bonus_pericia_extra,
        bonus_pericia_contextual, bonus,
    )):
        raise ValueError('Modificadores do teste devem ser inteiros.')

    extras_condicoes = 0
    quantidade_base = 2 if atributo == 0 else atributo
    nome_dado_base = 'dado' if quantidade_base == 1 else 'dados'
    linhas = [f'{quantidade_base} {nome_dado_base} base']
    for condicao in condicoes:
        modificadores = modificadores_condicoes(
            [condicao],
            tipo=tipo,
            atributo=atributo_slug,
            pericia_slug=pericia_slug,
        )
        extras = modificadores['dados_extras']
        extras_condicoes += extras
        if extras:
            sinal = '+' if extras > 0 else '−'
            linhas.append(f'{sinal}{abs(extras)} {condicao.nome}')

    dados_totais = dados_extras + dados_pericia_extra + extras_condicoes
    if dados_pericia_extra:
        sinal = '+' if dados_pericia_extra > 0 else '−'
        linhas.append(f'{sinal}{abs(dados_pericia_extra)} dados adicionais da perícia')
    if dados_extras:
        sinal = '+' if dados_extras > 0 else '−'
        modificador = 'modificador' if abs(dados_extras) == 1 else 'modificadores'
        linhas.append(f'{sinal}{abs(dados_extras)} {modificador} situacionais')

    quantidade, escolher_menor = parametros_teste(atributo, dados_totais)
    if bonus_pericia:
        sinal = '+' if bonus_pericia > 0 else '−'
        linhas.append(f'{sinal}{abs(bonus_pericia)} treinamento')
    if bonus_pericia_extra:
        sinal = '+' if bonus_pericia_extra > 0 else '−'
        linhas.append(f'{sinal}{abs(bonus_pericia_extra)} modificador da perícia')
    if bonus_pericia_contextual:
        sinal = '+' if bonus_pericia_contextual > 0 else '−'
        linhas.append(f'{sinal}{abs(bonus_pericia_contextual)} modificador contextual da perícia')
    if bonus:
        sinal = '+' if bonus > 0 else '−'
        linhas.append(f'{sinal}{abs(bonus)} bônus situacional')
    nome_dado_final = 'dado' if quantidade == 1 else 'dados'
    final = 'final' if quantidade == 1 else 'finais'
    linhas.append(
        f'{quantidade} {nome_dado_final} {final}; usar o {"menor" if escolher_menor else "maior"}.'
    )
    return {
        'dados_extras': dados_totais,
        'quantidade_dados': quantidade,
        'ordem': 'menor' if escolher_menor else 'maior',
        'bonus_total': (
            bonus_pericia + bonus_pericia_extra + bonus_pericia_contextual + bonus
        ),
        'detalhamento': linhas,
    }
