import json
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from fichas.models import (
    Atributo,
    Classe,
    Condicao,
    ItemCatalogo,
    Origem,
    Patente,
    Pericia,
    Poder,
    Ritual,
    Trilha,
    validar_efeitos_condicao,
)
from fichas.pre_requisitos import validar_pre_requisitos


DATA_DIR = Path(__file__).resolve().parents[2] / 'dados'


class Command(BaseCommand):
    help = 'Carrega ou atualiza catálogos básicos de regras pelos slugs dos JSONs.'

    def _ler(self, nome):
        caminho = DATA_DIR / nome
        try:
            dados = json.loads(caminho.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as erro:
            raise CommandError(f'Não foi possível ler {nome}.') from erro
        if not isinstance(dados, list):
            raise CommandError(f'{nome} deve conter uma lista JSON.')
        for registro in dados:
            if not isinstance(registro, dict) or not registro.get('slug') or not registro.get('fonte'):
                raise CommandError(f'Registro sem slug ou fonte em {nome}.')
        return dados

    def _atualizar(self, modelo, registro, campos=None):
        dados = {key: value for key, value in registro.items() if key != 'slug'}
        if campos is not None:
            dados = {key: value for key, value in dados.items() if key in campos}
        objeto, criado = modelo.objects.update_or_create(slug=registro['slug'], defaults=dados)
        return objeto, criado

    @transaction.atomic
    def handle(self, *args, **options):
        contagens = {'criados': 0, 'atualizados': 0}

        for arquivo, modelo in (
            ('atributos.json', Atributo),
            ('pericias.json', Pericia),
            ('classes.json', Classe),
            ('patentes.json', Patente),
        ):
            for registro in self._ler(arquivo):
                _, criado = self._atualizar(modelo, registro)
                contagens['criados' if criado else 'atualizados'] += 1

        for arquivo in ('origens_oprgp.json', 'origens_sah.json'):
            for registro in self._ler(arquivo):
                dados = {
                    'nome': registro['nome'],
                    'fonte': registro['fonte'],
                    'personalizado': registro.get('personalizado', False),
                    'resumo': registro['resumo'],
                    'pericias_especializadas': registro.get('especializacoes', {}),
                    'escolhas_pericia': registro.get('escolhas_pericia', 0),
                    'poder_nome': registro['poder_nome'],
                    'poder_resumo': registro['poder_resumo'],
                }
                origem, criado = Origem.objects.update_or_create(slug=registro['slug'], defaults=dados)
                contagens['criados' if criado else 'atualizados'] += 1

                slugs_pericias = registro.get('pericias', [])
                pericias = list(Pericia.objects.filter(slug__in=slugs_pericias))
                if len(pericias) != len(set(slugs_pericias)):
                    raise CommandError(f'Perícia referenciada ausente na origem {origem.slug}.')
                origem.pericias_treinadas.set(pericias)

        for registro in self._ler('trilhas.json'):
            classe_slug = registro.get('classe_slug')
            classe = Classe.objects.filter(slug=classe_slug).first()
            if classe is None:
                raise CommandError(f'Classe {classe_slug} ausente na trilha {registro["slug"]}.')
            try:
                validar_pre_requisitos(registro.get('pre_requisitos', {}))
            except ValidationError as erro:
                raise CommandError(
                    f"Pré-requisitos inválidos para a trilha {registro['slug']}."
                ) from erro
            dados = {
                key: value
                for key, value in registro.items()
                if key in {
                    'nome', 'fonte', 'personalizado', 'resumo', 'habilidades',
                    'pre_requisitos',
                }
            }
            objeto, criado = Trilha.objects.update_or_create(
                slug=registro['slug'], defaults={**dados, 'classe': classe},
            )
            contagens['criados' if criado else 'atualizados'] += 1

        for arquivo, modelo, campos in (
            ('poderes.json', Poder, {
                'nome', 'fonte', 'personalizado', 'resumo', 'tipo', 'pre_requisitos', 'custo',
            }),
            ('rituais.json', Ritual, {
                'nome', 'fonte', 'personalizado', 'resumo', 'circulo', 'elemento',
                'execucao', 'alcance', 'alvo_area', 'duracao', 'resistencia', 'custo',
            }),
            ('itens_oprgp.json', ItemCatalogo, {
                'nome', 'fonte', 'personalizado', 'resumo', 'categoria', 'espacos', 'tipo',
                'proficiencia', 'tipo_arma', 'empunhadura', 'dano', 'critico_margem',
                'critico_multiplicador', 'alcance', 'tipo_dano', 'bonus_defesa',
                'campos_adicionais',
            }),
            ('itens_sah.json', ItemCatalogo, {
                'nome', 'fonte', 'personalizado', 'resumo', 'categoria', 'espacos', 'tipo',
                'proficiencia', 'tipo_arma', 'empunhadura', 'dano', 'critico_margem',
                'critico_multiplicador', 'alcance', 'tipo_dano', 'bonus_defesa',
                'campos_adicionais',
            }),
        ):
            for registro in self._ler(arquivo):
                if modelo in (Poder, Trilha):
                    try:
                        validar_pre_requisitos(registro.get('pre_requisitos', {}))
                    except ValidationError as erro:
                        raise CommandError(
                            f"Pré-requisitos inválidos para o registro {registro['slug']}."
                        ) from erro
                _, criado = self._atualizar(modelo, registro, campos=campos)
                contagens['criados' if criado else 'atualizados'] += 1

        condicoes_por_slug = {}
        registros_condicoes = self._ler('condicoes.json')
        for registro in registros_condicoes:
            try:
                validar_efeitos_condicao(registro.get('efeitos', {}))
            except ValidationError as erro:
                raise CommandError(
                    f"Efeitos inválidos para a condição {registro['slug']}."
                ) from erro
            dados = {
                key: value
                for key, value in registro.items()
                if key not in {'slug', 'proxima_escalada_slug'}
            }
            condicao, criado = Condicao.objects.update_or_create(slug=registro['slug'], defaults=dados)
            contagens['criados' if criado else 'atualizados'] += 1
            condicoes_por_slug[condicao.slug] = (condicao, registro.get('proxima_escalada_slug'))

        for condicao, proxima_slug in condicoes_por_slug.values():
            proxima = Condicao.objects.filter(slug=proxima_slug).first() if proxima_slug else None
            if proxima_slug and proxima is None:
                raise CommandError(f'Escalada {proxima_slug} não existe para {condicao.slug}.')
            if condicao.proxima_escalada_id != getattr(proxima, 'pk', None):
                condicao.proxima_escalada = proxima
                condicao.save(update_fields=('proxima_escalada',))

        self.stdout.write(self.style.SUCCESS(
            'Regras carregadas: '
            f"{contagens['criados']} criados, {contagens['atualizados']} atualizados."
        ))