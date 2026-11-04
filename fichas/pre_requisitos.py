from collections.abc import Mapping

from django.core.exceptions import ValidationError

from .regras import ATRIBUTOS, nex_equivalente_por_nivel


_CAMPOS = {
    'classe_slug',
    'trilha_slug',
    'nex_min',
    'nivel_min',
    'estagio_min',
    'patente_slug',
    'atributos_min',
    'pericias_treinadas',
    'poderes',
}


def validar_pre_requisitos(valor):
    if not isinstance(valor, Mapping) or set(valor) - _CAMPOS:
        raise ValidationError('Pré-requisitos devem usar somente campos estruturados conhecidos.')

    for campo in ('classe_slug', 'trilha_slug', 'patente_slug'):
        requisito = valor.get(campo)
        if requisito is not None and (
            not isinstance(requisito, str) or not requisito or requisito != requisito.strip()
            or len(requisito) > 140
        ):
            raise ValidationError(f'{campo} deve ser um slug não vazio.')

    for campo, minimo, maximo in (
        ('nex_min', 0, 99),
        ('nivel_min', 1, 20),
        ('estagio_min', 1, 5),
    ):
        requisito = valor.get(campo)
        if requisito is not None and (
            type(requisito) is not int or not minimo <= requisito <= maximo
        ):
            raise ValidationError(f'{campo} está fora dos limites permitidos.')

    atributos = valor.get('atributos_min', {})
    if not isinstance(atributos, Mapping) or any(
        atributo not in ATRIBUTOS
        or type(minimo) is not int
        or not 0 <= minimo <= 5
        for atributo, minimo in atributos.items()
    ):
        raise ValidationError('atributos_min deve mapear atributos conhecidos a valores entre 0 e 5.')

    for campo in ('pericias_treinadas', 'poderes'):
        requisitos = valor.get(campo, [])
        if (
            not isinstance(requisitos, list)
            or len(requisitos) > 50
            or any(
                not isinstance(slug, str) or not slug or slug != slug.strip()
                or len(slug) > 140
                for slug in requisitos
            )
            or len(set(requisitos)) != len(requisitos)
        ):
            raise ValidationError(f'{campo} deve ser uma lista de slugs únicos.')

    return valor


def nex_efetivo(ficha):
    if ficha.nivel_experiencia is not None and ficha.nivel_experiencia > 0:
        return nex_equivalente_por_nivel(ficha.nivel_experiencia)
    if ficha.patente_id:
        nivel = max(1, ficha.patente.limite_pd)
        return nex_equivalente_por_nivel(nivel)
    return ficha.nex


def poder_atende_pre_requisitos(poder, ficha, *, pericias_treinadas=None, poderes_escolhidos=None):
    requisitos = validar_pre_requisitos(poder.pre_requisitos)
    if not requisitos:
        return True

    classe_slug = ficha.classe.slug if ficha.classe_id else None
    trilha_slug = ficha.trilha.slug if ficha.trilha_id else None
    if requisitos.get('classe_slug') and requisitos['classe_slug'] != classe_slug:
        return False
    if requisitos.get('trilha_slug') and requisitos['trilha_slug'] != trilha_slug:
        return False

    nex_min = requisitos.get('nex_min')
    nex = nex_efetivo(ficha)
    if nex_min is not None and (nex is None or nex < nex_min):
        return False
    nivel_min = requisitos.get('nivel_min')
    if nivel_min is not None and (
        ficha.nivel_experiencia is None or ficha.nivel_experiencia < nivel_min
    ):
        return False
    patente_slug = requisitos.get('patente_slug')
    if patente_slug and (
        ficha.patente_id is None or ficha.patente.slug != patente_slug
    ):
        return False
    estagio_min = requisitos.get('estagio_min')
    if estagio_min is not None and (ficha.estagio is None or ficha.estagio < estagio_min):
        return False

    if any(
        getattr(ficha, atributo) < minimo
        for atributo, minimo in requisitos.get('atributos_min', {}).items()
    ):
        return False

    if pericias_treinadas is None:
        pericias_treinadas = set(
            ficha.pericias.exclude(grau='destreinado').values_list('pericia__slug', flat=True)
        )
    if not set(requisitos.get('pericias_treinadas', ())).issubset(pericias_treinadas):
        return False

    if poderes_escolhidos is None:
        poderes_escolhidos = set(
            ficha.poderes.filter(poder__isnull=False).values_list('poder__slug', flat=True)
        )
    return set(requisitos.get('poderes', ())).issubset(poderes_escolhidos)


def trilha_atende_pre_requisitos(
    trilha,
    *,
    classe,
    nex,
    nivel_experiencia,
    estagio,
    patente,
    atributos,
    pericias_treinadas,
):
    requisitos = validar_pre_requisitos(trilha.pre_requisitos)
    if requisitos.get('classe_slug') and requisitos['classe_slug'] != classe.slug:
        return False
    nex_min = requisitos.get('nex_min')
    if nex_min is not None and (nex is None or nex < nex_min):
        return False
    nivel_min = requisitos.get('nivel_min')
    if nivel_min is not None and (
        nivel_experiencia is None or nivel_experiencia < nivel_min
    ):
        return False
    estagio_min = requisitos.get('estagio_min')
    if estagio_min is not None and (estagio is None or estagio < estagio_min):
        return False
    patente_slug = requisitos.get('patente_slug')
    if patente_slug and (patente is None or patente.slug != patente_slug):
        return False
    if any(atributos.get(nome, 0) < minimo for nome, minimo in requisitos.get('atributos_min', {}).items()):
        return False
    if not set(requisitos.get('pericias_treinadas', ())).issubset(pericias_treinadas):
        return False
    return not requisitos.get('poderes')
