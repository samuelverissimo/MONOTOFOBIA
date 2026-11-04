"""Cálculos puros das regras. Fontes: OPRPG e SaH nas páginas impressas citadas."""

import math
import secrets
from collections.abc import Iterable, Mapping


CLASSES = {
    'combatente': {'pv': (20, 4), 'pe': (2, 2), 'san': (12, 3), 'pd': (6, 3), 'pericias': 1},
    'especialista': {'pv': (16, 3), 'pe': (3, 3), 'san': (16, 4), 'pd': (8, 4), 'pericias': 7},
    'ocultista': {'pv': (12, 2), 'pe': (4, 4), 'san': (20, 5), 'pd': (10, 5), 'pericias': 3},
    'sobrevivente': {'pv': (8, 2), 'pe': (2, 1), 'san': (8, 2), 'pd': (4, 2), 'pericias': 1},
}
NEX_VALIDOS = tuple(range(5, 100, 5)) + (99,)
GRAUS_PERICIA = {'destreinado': 0, 'treinado': 5, 'veterano': 10, 'expert': 15}
ATRIBUTOS = ('agilidade', 'forca', 'intelecto', 'presenca', 'vigor')


def _classe(classe):
    chave = str(classe).strip().casefold()
    if chave not in CLASSES:
        raise ValueError('Classe inválida.')
    return chave


def _validar_atributo(valor):
    if isinstance(valor, bool) or not isinstance(valor, int) or not 0 <= valor <= 5:
        raise ValueError('Atributo deve ser um inteiro entre 0 e 5.')


def _niveis_nex(nex):
    if nex not in NEX_VALIDOS:
        raise ValueError('NEX deve ser 5%, 10% ... 95% ou 99%.')
    return 19 if nex == 99 else (nex - 5) // 5


def _validar_estagio(estagio):
    if isinstance(estagio, bool) or not isinstance(estagio, int) or not 1 <= estagio <= 5:
        raise ValueError('Estágio deve ser um inteiro entre 1 e 5.')


def calcular_pv_max(classe, vigor, nex=5, estagio=1, ajuste=0):
    """PV inicial e incrementos. OPRPG pp. 25, 29, 33; SaH p. 30."""
    classe = _classe(classe)
    _validar_atributo(vigor)
    base, incremento = CLASSES[classe]['pv']
    if classe == 'sobrevivente':
        _validar_estagio(estagio)
        return max(0, base + vigor + (estagio - 1) * incremento + ajuste)
    aumentos = _niveis_nex(nex)
    return max(0, base + vigor + aumentos * (incremento + vigor) + ajuste)


def calcular_pe_max(classe, presenca, nex=5, estagio=1, ajuste=0):
    """PE inicial e incrementos. OPRPG pp. 25, 29, 33; SaH p. 30."""
    classe = _classe(classe)
    _validar_atributo(presenca)
    base, incremento = CLASSES[classe]['pe']
    if classe == 'sobrevivente':
        _validar_estagio(estagio)
        return max(0, base + presenca + (estagio - 1) * incremento + ajuste)
    aumentos = _niveis_nex(nex)
    return max(0, base + presenca + aumentos * (incremento + presenca) + ajuste)


def calcular_san_max(classe, nex=5, estagio=1, ajuste=0):
    """SAN inicial e progressão. OPRPG pp. 25, 29, 33; SaH p. 30."""
    classe = _classe(classe)
    base, incremento = CLASSES[classe]['san']
    if classe == 'sobrevivente':
        _validar_estagio(estagio)
        return max(0, base + (estagio - 1) * incremento + ajuste)
    return max(0, base + _niveis_nex(nex) * incremento + ajuste)


def calcular_pd_max(classe, presenca, nex=5, estagio=1, ajuste=0):
    """PD da regra opcional sem Sanidade. SaH pp. 104-105."""
    classe = _classe(classe)
    _validar_atributo(presenca)
    base, incremento = CLASSES[classe]['pd']
    if classe == 'sobrevivente':
        _validar_estagio(estagio)
        return max(0, base + presenca + (estagio - 1) * incremento + ajuste)
    aumentos = _niveis_nex(nex)
    return max(0, base + presenca + aumentos * (incremento + presenca) + ajuste)


def limite_pe_por_turno(nex=5, classe='combatente', ajuste=0):
    """Limite por turno: NEX/5 arredondado para cima; Sobrevivente fica em 1."""
    classe = _classe(classe)
    if classe == 'sobrevivente':
        return 1
    _niveis_nex(nex)
    return min(20, max(1, math.ceil(nex / 5) + ajuste))


def calcular_defesa(agilidade, bonus=0, sobrecarregado=False):
    """Defesa base e penalidade de carga. OPRPG pp. 36 e 53."""
    _validar_atributo(agilidade)
    return 10 + agilidade + bonus - (5 if sobrecarregado else 0)


def capacidade_carga(forca):
    """Espaços máximos normais; Força 0 permite 2. OPRPG p. 53."""
    _validar_atributo(forca)
    return 2 if forca == 0 else 5 * forca


def espacos_usados(itens: Iterable):
    """Soma espaços vezes quantidade, sem acessar o banco. OPRPG pp. 52-53."""
    total = 0
    for item in itens:
        obter = item.get if isinstance(item, Mapping) else lambda chave, padrao=0: getattr(item, chave, padrao)
        espacos = obter('espacos', 0)
        quantidade = obter('quantidade', 1)
        if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in (espacos, quantidade)):
            raise ValueError('Espaços e quantidade devem ser inteiros não negativos.')
        total += espacos * quantidade
    return total


def bonus_pericia(grau, bonus_extra=0, kit_disponivel=True, penalidade_carga=0):
    """Bônus por grau e modificadores de kit/carga. OPRPG p. 40 e tabela p. 41."""
    chave = str(grau).strip().casefold()
    if chave not in GRAUS_PERICIA:
        raise ValueError('Grau de perícia inválido.')
    return GRAUS_PERICIA[chave] + bonus_extra - (0 if kit_disponivel else 5) + penalidade_carga


def pericias_treinadas_disponiveis(classe, intelecto):
    """Escolhas adicionais por classe e Intelecto. OPRPG pp. 25, 29, 33; SaH p. 30."""
    classe = _classe(classe)
    _validar_atributo(intelecto)
    return CLASSES[classe]['pericias'] + intelecto


def validar_atributos_iniciais(atributos, classe='combatente', livre=False):
    """Valida distribuição inicial de pontos. OPRPG pp. 14-15; SaH p. 30."""
    classe = _classe(classe)
    if not isinstance(atributos, Mapping) or any(nome not in atributos for nome in ATRIBUTOS):
        raise ValueError('Informe os cinco atributos.')
    valores = [atributos[nome] for nome in ATRIBUTOS]
    limite = 5 if livre else 3
    if any(isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= limite for v in valores):
        raise ValueError(f'Atributos devem ser inteiros entre 0 e {limite}.')
    if livre:
        return True
    total_esperado = 8 if classe == 'sobrevivente' else 9
    if sum(valores) != total_esperado or valores.count(0) > 1:
        raise ValueError('A distribuição não corresponde aos pontos iniciais da classe.')
    return True


def rolar_teste(atributo, bonus_pericia=0, dados_extras=0, bonus=0, rng=None):
    """Rola d20, com atributos 0 e pools negativas conforme OPRPG pp. 11 e 40."""
    _validar_atributo(atributo)
    if isinstance(dados_extras, bool) or not isinstance(dados_extras, int):
        raise ValueError('Dados extras devem ser inteiros.')
    gerador = rng if rng is not None else secrets.SystemRandom()

    if atributo == 0:
        quantidade = 2 + dados_extras
        dados = 2 + abs(dados_extras) if quantidade < 1 else quantidade
        escolher_menor = True
    else:
        quantidade = atributo + dados_extras
        if quantidade < 1:
            # O livro manda inverter a penalidade abaixo de um dado e escolher o pior.
            dados = atributo + abs(dados_extras)
            escolher_menor = True
        else:
            dados = quantidade
            escolher_menor = False

    resultados = [gerador.randint(1, 20) for _ in range(dados)]
    escolhido = min(resultados) if escolher_menor else max(resultados)
    return {
        'dados': resultados,
        'dado_escolhido': escolhido,
        'ordem': 'menor' if escolher_menor else 'maior',
        'bonus': bonus_pericia + bonus,
        'total': escolhido + bonus_pericia + bonus,
    }


def rolar_dano(quantidade_dados, faces, bonus=0, multiplicador_critico=1, rng=None):
    """Rola dano; crítico multiplica dados, nunca o bônus. OPRPG pp. 64 e 92."""
    valores = (quantidade_dados, faces, multiplicador_critico)
    if any(isinstance(v, bool) or not isinstance(v, int) for v in valores):
        raise ValueError('Dados, faces e multiplicador devem ser inteiros.')
    if quantidade_dados < 0 or faces < 2 or multiplicador_critico < 1:
        raise ValueError('Parâmetros de dano inválidos.')
    gerador = rng if rng is not None else secrets.SystemRandom()
    resultados = [
        gerador.randint(1, faces)
        for _ in range(quantidade_dados * multiplicador_critico)
    ]
    return {'dados': resultados, 'bonus': bonus, 'total': sum(resultados) + bonus}


def pendencias_ao_subir_nex(classe, nex_anterior, nex_novo, intelecto=0):
    """Lista escolhas pendentes por marcos de NEX. OPRPG pp. 25, 29 e 33."""
    classe = _classe(classe)
    if classe == 'sobrevivente':
        raise ValueError('Sobreviventes avançam por estágio, não por NEX.')
    if nex_anterior not in NEX_VALIDOS or nex_novo not in NEX_VALIDOS or nex_novo <= nex_anterior:
        raise ValueError('A progressão deve avançar entre NEX válidos.')
    _validar_atributo(intelecto)
    marcos = [nex for nex in NEX_VALIDOS if nex_anterior < nex <= nex_novo]
    pendencias = []
    for nex in marcos:
        if nex == 10:
            pendencias.append({'tipo': 'trilha', 'descricao': 'Escolher uma trilha.', 'fonte': 'OPRPG p. 25'})
        if nex in (20, 50, 80, 95):
            pendencias.append({'tipo': 'atributo', 'descricao': 'Aumentar um atributo em +1.', 'fonte': 'OPRPG p. 25'})
        if nex in (35, 70):
            pendencias.append({
                'tipo': 'treinamento',
                'descricao': f'Aprimorar {5 + intelecto} perícias em um grau.',
                'fonte': 'OPRPG p. 25',
            })
        if nex == 50:
            pendencias.append({'tipo': 'versatilidade', 'descricao': 'Escolher versatilidade.', 'fonte': 'OPRPG p. 25'})
        if nex in (15, 30, 45, 60, 75, 90):
            tipo = {'combatente': 'poder de combatente', 'especialista': 'poder de especialista', 'ocultista': 'poder de ocultista'}[classe]
            pendencias.append({'tipo': 'poder', 'descricao': f'Escolher {tipo}.', 'fonte': 'OPRPG p. 25'})
        if classe == 'ocultista':
            pendencias.append({'tipo': 'ritual', 'descricao': 'Aprender um ritual.', 'fonte': 'OPRPG p. 33'})
    return pendencias