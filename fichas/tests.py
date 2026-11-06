import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils.crypto import get_random_string

from core.models import AmeacaMesa, InscricaoMesa, Mesa
from fichas.efeitos import explicar_teste
from fichas.forms import ConfiguracaoFichaForm, CriacaoInicialForm
from fichas.models import (
    Atributo,
    Classe,
    Condicao,
    ConfiguracaoFicha,
    ConfiguracaoMesa,
    EncontroCombate,
    Ficha,
    FichaCondicao,
    FerimentoDebilitante,
    HabilidadeFicha,
    FichaPoder,
    FichaPericia,
    FichaRitual,
    ItemCatalogo,
    ItemInventario,
    LogAlteracao,
    Origem,
    Patente,
    Pericia,
    ParticipanteCombate,
    Pendencia,
    Poder,
    RegistroPrestigio,
    Rolagem,
    Ritual,
    Trilha,
)
from fichas.permissions import fichas_visiveis_para, is_mestre, pode_editar_ficha, pode_ver_ficha
from fichas.pre_requisitos import poder_atende_pre_requisitos, validar_pre_requisitos
from fichas.regras import (
    avaliar_teste_fisico,
    avaliar_dano_fisico,
    bonus_pericia,
    calcular_defesa,
    calcular_pd_max,
    calcular_pe_max,
    calcular_pv_max,
    calcular_san_max,
    capacidade_carga,
    espacos_usados,
    limite_pe_por_turno,
    modificadores_condicoes,
    nex_equivalente_por_nivel,
    nivel_equivalente_por_nex,
    pericias_treinadas_disponiveis,
    pendencias_ao_subir_estagio,
    pendencias_ao_subir_nex,
    rolar_dano,
    rolar_teste,
    validar_atributos_iniciais,
)
from fichas.forms import (
    AtributosFichaForm,
    ConceitoFichaForm,
    ConfiguracaoMesaForm,
    FichaEdicaoForm,
    FichaStatusForm,
    ItemInventarioForm,
    PericiasFichaForm,
    ProgressaoInicialForm,
    RegistroPrestigioForm,
)

User = get_user_model()


class FixedDice:
    def __init__(self, values):
        self.values = iter(values)

    def randint(self, _minimum, _maximum):
        return next(self.values)


class RegrasTests(SimpleTestCase):
    def test_elemental_and_alternative_skill_prerequisites_are_structured(self):
        self.assertEqual(validar_pre_requisitos({
            'poderes_elemento_min': {'morte': 2},
            'pericias_treinadas_uma_de': ['luta', 'pontaria'],
        }), {
            'poderes_elemento_min': {'morte': 2},
            'pericias_treinadas_uma_de': ['luta', 'pontaria'],
        })
        with self.assertRaises(ValidationError):
            validar_pre_requisitos({'poderes_elemento_min': {'medo': True}})
        with self.assertRaises(ValidationError):
            validar_pre_requisitos({'pericias_treinadas_uma_de': ['luta', 'luta']})

    def test_experience_level_maps_to_class_progression(self):
        self.assertEqual(nex_equivalente_por_nivel(1), 5)
        self.assertEqual(nex_equivalente_por_nivel(19), 95)
        self.assertEqual(nex_equivalente_por_nivel(20), 99)
        with self.assertRaises(ValueError):
            nex_equivalente_por_nivel(0)
        self.assertEqual(
            [nivel_equivalente_por_nex(nex) for nex in (10, 40, 65, 99)],
            [2, 8, 13, 20],
        )
        with self.assertRaises(ValueError):
            nivel_equivalente_por_nex(98)

    def test_combatente_pv_nex_99_vigor_3(self):
        self.assertEqual(calcular_pv_max('combatente', vigor=3, nex=99), 156)

    def test_initial_and_increased_resources(self):
        self.assertEqual(calcular_pv_max('especialista', vigor=1), 17)
        self.assertEqual(calcular_pe_max('especialista', presenca=2, nex=20), 20)
        self.assertEqual(calcular_san_max('ocultista', nex=20), 35)
        self.assertEqual(calcular_pd_max('sobrevivente', presenca=2, estagio=3), 10)

    def test_bianca_specialist_has_ten_class_skill_choices(self):
        self.assertEqual(pericias_treinadas_disponiveis('especialista', intelecto=3), 10)

    def test_attributes_validate_regular_and_survivor_budgets(self):
        regular = {'agilidade': 2, 'forca': 0, 'intelecto': 3, 'presenca': 3, 'vigor': 1}
        survivor = {'agilidade': 2, 'forca': 0, 'intelecto': 2, 'presenca': 3, 'vigor': 1}
        self.assertTrue(validar_atributos_iniciais(regular, 'especialista'))
        self.assertTrue(validar_atributos_iniciais(survivor, 'sobrevivente'))
        with self.assertRaises(ValueError):
            validar_atributos_iniciais({**regular, 'forca': 1}, 'especialista')

    def test_carrying_capacity_defense_and_skill_bonus(self):
        self.assertEqual(capacidade_carga(0), 2)
        self.assertEqual(capacidade_carga(2), 10)
        self.assertEqual(capacidade_carga(3), 15)
        self.assertEqual(espacos_usados([{'espacos': 2, 'quantidade': 3}, {'espacos': 0}]), 6)
        self.assertEqual(calcular_defesa(2, sobrecarregado=True), 7)
        self.assertEqual(bonus_pericia('expert', kit_disponivel=False, penalidade_carga=-5), 5)

    def test_condition_modifiers_apply_to_matching_tests_and_defense(self):
        abalado = Condicao(efeitos={'dados_teste': -1, 'bonus_defesa': -5})
        debilitado = Condicao(efeitos={'dados_atributo_agilidade_forca_vigor': -2})
        ataque_corpo_a_corpo = Condicao(efeitos={
            'dados_ataque': -1,
            'dados_ataque_luta': -2,
            'dados_pericia_agilidade_forca': -2,
        })

        pericia = modificadores_condicoes(
            [abalado, debilitado, ataque_corpo_a_corpo],
            tipo='pericia',
            atributo='forca',
            pericia_slug='luta',
        )
        atributo = modificadores_condicoes(
            [abalado, debilitado, ataque_corpo_a_corpo],
            tipo='atributo',
            atributo='forca',
        )

        self.assertEqual(pericia, {'dados_extras': -8, 'bonus': 0, 'defesa': -5})
        self.assertEqual(atributo, {'dados_extras': -3, 'bonus': 0, 'defesa': -5})
        with self.assertRaises(ValueError):
            modificadores_condicoes(
                [Condicao(efeitos={'texto_livre': -1})], tipo='atributo', atributo='forca',
            )

    def test_test_explanation_lists_each_condition_and_reuses_negative_pool_rule(self):
        explicacao = explicar_teste(
            3,
            [
                Condicao(nome='Abalado', efeitos={'dados_teste': -1}),
                Condicao(nome='Fraco', efeitos={'dados_pericia': -1}),
            ],
            tipo='pericia',
            atributo_slug='forca',
            pericia_slug='luta',
            bonus_pericia=5,
            bonus=2,
        )
        self.assertEqual(
            (explicacao['quantidade_dados'], explicacao['ordem'], explicacao['bonus_total']),
            (1, 'maior', 7),
        )
        self.assertEqual(
            explicacao['detalhamento'],
            [
                '3 dados base',
                '−1 Abalado',
                '−1 Fraco',
                '+5 treinamento',
                '+2 bônus situacional',
                '1 dado final; usar o maior.',
            ],
        )
        penalizado = explicar_teste(
            1,
            [Condicao(nome='Penalidade dupla', efeitos={'dados_teste': -2})],
            tipo='atributo',
            atributo_slug='forca',
        )
        self.assertEqual((penalizado['quantidade_dados'], penalizado['ordem']), (3, 'menor'))

    def test_turn_limits_and_level_up_pending_choices(self):
        self.assertEqual(limite_pe_por_turno(5), 1)
        self.assertEqual(limite_pe_por_turno(99), 20)
        self.assertEqual(limite_pe_por_turno(99, classe='sobrevivente'), 1)
        self.assertEqual(
            [item['tipo'] for item in pendencias_ao_subir_nex('combatente', 5, 10)],
            ['trilha'],
        )
        self.assertEqual(
            [item['tipo'] for item in pendencias_ao_subir_nex('combatente', 10, 15)],
            ['poder'],
        )
        pendencias = pendencias_ao_subir_nex('especialista', 5, 20, intelecto=3)
        self.assertEqual([item['tipo'] for item in pendencias], ['trilha', 'poder', 'atributo'])
        with self.assertRaises(ValueError):
            pendencias_ao_subir_nex('sobrevivente', 5, 10)

    def test_survivor_stage_advancement_creates_documented_choices(self):
        pendencias = pendencias_ao_subir_estagio(1, 5)
        self.assertEqual(
            [pendencia['tipo'] for pendencia in pendencias],
            ['trilha', 'atributo', 'cicatrizado'],
        )
        self.assertTrue(all(pendencia['fonte'] == 'SaH p.31' for pendencia in pendencias))
        with self.assertRaises(ValueError):
            pendencias_ao_subir_estagio(4, 3)

    def test_rolls_follow_attribute_zero_and_negative_pool_rules(self):
        zero = rolar_teste(0, rng=FixedDice([19, 3]))
        self.assertEqual((zero['dados'], zero['dado_escolhido'], zero['ordem']), ([19, 3], 3, 'menor'))
        zero_penalizado = rolar_teste(0, dados_extras=-2, rng=FixedDice([19, 18, 14, 2]))
        self.assertEqual((zero_penalizado['dados'], zero_penalizado['dado_escolhido']), ([19, 18, 14, 2], 2))
        ordinary = rolar_teste(3, bonus_pericia=5, rng=FixedDice([3, 18, 8]))
        self.assertEqual((ordinary['dado_escolhido'], ordinary['total']), (18, 23))
        negative = rolar_teste(1, dados_extras=-2, rng=FixedDice([18, 12, 4]))
        self.assertEqual((negative['dados'], negative['dado_escolhido'], negative['ordem']), ([18, 12, 4], 4, 'menor'))

    def test_physical_rolls_validate_pool_choose_correct_die_and_compare_dt(self):
        resultado = avaliar_teste_fisico(
            3, [4, 18, 8], bonus_pericia=5, dados_extras=0, bonus=-2, dt=21,
        )
        self.assertEqual(
            (resultado['dado_escolhido'], resultado['bonus'], resultado['total'],
             resultado['ordem'], resultado['sucesso']),
            (18, 3, 21, 'maior', True),
        )
        penalizado = avaliar_teste_fisico(1, [18, 12, 4], dados_extras=-2, dt=5)
        self.assertEqual((penalizado['dado_escolhido'], penalizado['ordem'], penalizado['sucesso']),
                         (4, 'menor', False))
        with self.assertRaises(ValueError):
            avaliar_teste_fisico(3, [1, 2])
        with self.assertRaises(ValueError):
            avaliar_teste_fisico(1, [0])
        with self.assertRaises(ValueError):
            avaliar_teste_fisico(1, [True])

    def test_critical_damage_multiplies_dice_not_numeric_bonus(self):
        damage = rolar_dano(2, 6, bonus=3, multiplicador_critico=2, rng=FixedDice([2, 3, 4, 5]))
        self.assertEqual(damage['total'], 17)

    def test_physical_damage_validates_critical_dice_and_adds_bonus_once(self):
        damage = avaliar_dano_fisico(2, 6, [2, 3, 4, 5], bonus=3, multiplicador_critico=2)
        self.assertEqual(damage, {'dados': [2, 3, 4, 5], 'bonus': 3, 'total': 17})
        with self.assertRaises(ValueError):
            avaliar_dano_fisico(2, 6, [2, 3], multiplicador_critico=2)
        with self.assertRaises(ValueError):
            avaliar_dano_fisico(1, 6, [True])
        with self.assertRaises(ValueError):
            avaliar_dano_fisico(1, 6, [7])


class ProgressaoInicialFormTests(TestCase):
    def test_initial_progression_form_only_shows_the_table_mode(self):
        nex = ProgressaoInicialForm(mesa=ConfiguracaoMesa(sistema_progressao='nex'))
        self.assertEqual(set(nex.fields), {'nex_inicial'})
        self.assertEqual(nex.fields['nex_inicial'].initial, '5')

        level = ProgressaoInicialForm(
            mesa=ConfiguracaoMesa(sistema_progressao='nivel_nex'),
        )
        self.assertEqual(set(level.fields), {'nivel_inicial', 'nex_paranormal'})
        self.assertEqual(level.fields['nivel_inicial'].initial, '1')
        self.assertEqual(level.fields['nex_paranormal'].initial, '0')

        rank = ProgressaoInicialForm(mesa=ConfiguracaoMesa(sistema_progressao='patentes'))
        self.assertEqual(set(rank.fields), {'patente_inicial'})
        self.assertTrue(rank.fields['patente_inicial'].required)
        patente = Patente.objects.create(
            nome='Recruta', slug='recruta', fonte='teste', resumo='', credito='I',
        )
        rank = ProgressaoInicialForm(mesa=ConfiguracaoMesa(sistema_progressao='patentes'))
        self.assertEqual(rank.fields['patente_inicial'].initial, patente.pk)


class FichaWizardFormTests(SimpleTestCase):

    def test_attribute_form_accepts_both_initial_budgets_before_class_step(self):
        regular = {
            'agilidade': 2,
            'forca': 0,
            'intelecto': 3,
            'presenca': 3,
            'vigor': 1,
        }
        survivor = {**regular, 'intelecto': 2}
        self.assertTrue(AtributosFichaForm(regular).is_valid())
        self.assertTrue(AtributosFichaForm(survivor).is_valid())
        self.assertFalse(AtributosFichaForm({**regular, 'intelecto': 4}).is_valid())

    def test_free_attribute_budget_requires_view_supplied_master_flag(self):
        free_data = {
            'agilidade': 4,
            'forca': 2,
            'intelecto': 2,
            'presenca': 1,
            'vigor': 1,
        }
        self.assertFalse(AtributosFichaForm(free_data).is_valid())
        self.assertTrue(AtributosFichaForm(free_data, livre=True).is_valid())
        self.assertTrue(ConceitoFichaForm({}, livre=True).is_valid())

    def test_edit_form_whitelist_hides_master_notes_from_players(self):
        jogador = set(FichaEdicaoForm(mestre=False).fields)
        mestre = set(FichaEdicaoForm(mestre=True).fields)
        self.assertNotIn('anotacoes_mestre', jogador)
        self.assertIn('anotacoes_mestre', mestre)
        self.assertNotIn('dono', jogador)
        self.assertIn('versao', jogador)
        self.assertNotIn('status', jogador)
        self.assertNotIn('nex', jogador)

    def test_elemental_affinity_requires_nex_equivalent_50(self):
        ficha = Ficha(nex=45)
        dados = {'nome': 'Agente', 'versao': 1, 'afinidade_elemento': 'morte'}
        self.assertFalse(FichaEdicaoForm(dados, mestre=False, ficha=ficha).is_valid())
        ficha.nex = 50
        self.assertTrue(FichaEdicaoForm(dados, mestre=False, ficha=ficha).is_valid())


class FichaInventarioFormTests(SimpleTestCase):
    def test_inventory_form_accepts_only_known_categories_states_and_bounds(self):
        dados = {
            'nome': 'Lanterna', 'categoria': 'I', 'espacos': 1,
            'quantidade': 2, 'estado': 'guardado', 'notas': '',
        }
        self.assertTrue(ItemInventarioForm(dados).is_valid())
        self.assertEqual(ItemInventarioForm().fields['notas'].label, 'Descrição')
        self.assertFalse(ItemInventarioForm({**dados, 'categoria': 'V'}).is_valid())
        self.assertFalse(ItemInventarioForm({**dados, 'espacos': -1}).is_valid())
        self.assertFalse(ItemInventarioForm({**dados, 'quantidade': 0}).is_valid())
        self.assertFalse(ItemInventarioForm({**dados, 'estado': 'voando'}).is_valid())


class ConfiguracaoMesaFormTests(SimpleTestCase):
    def test_form_accepts_only_supported_configuration_values(self):
        dados = {
            'modo_recursos': 'padrao', 'jogador_pode_subir_nex': 'on',
            'max_fichas_ativas': 4, 'sistema_progressao': 'nivel_nex',
        }
        form = ConfiguracaoMesaForm(dados)
        self.assertTrue(form.is_valid())
        self.assertIn('sistema_progressao', form.fields)
        self.assertFalse(ConfiguracaoMesaForm({**dados, 'modo_recursos': 'inventado'}).is_valid())
        self.assertFalse(ConfiguracaoMesaForm({**dados, 'max_fichas_ativas': 0}).is_valid())
        self.assertTrue(ConfiguracaoMesaForm({
            **dados, 'sistema_progressao': 'patentes',
            'modo_recursos': 'sem_sanidade',
        }).is_valid())
        self.assertTrue(ConfiguracaoMesaForm({
            **dados, 'modo_recursos': 'sem_sanidade',
            'sistema_progressao': 'patentes',
        }).is_valid())

    def test_standalone_patent_progression_requires_no_sanity_mode(self):
        dados = {
            'versao': 1,
            'modo_recursos': 'sem_sanidade',
            'sistema_progressao': 'patentes',
            'numero_sessao': 1,
        }
        self.assertTrue(ConfiguracaoFichaForm(dados).is_valid())
        self.assertFalse(ConfiguracaoFichaForm({
            **dados, 'modo_recursos': 'padrao',
        }).is_valid())

    def test_prestige_form_restricts_solution_and_clue_quantities(self):
        dados = {'evento': 'solucao', 'quantidade': 2, 'versao': 1, 'numero_sessao': 1}
        self.assertFalse(RegistroPrestigioForm(dados).is_valid())
        dados.update(evento='pista', quantidade=1)
        self.assertTrue(RegistroPrestigioForm(dados).is_valid())
        dados.update(evento='inocente', quantidade=1000)
        self.assertFalse(RegistroPrestigioForm(dados).is_valid())

    def test_status_form_allows_only_archive_and_restore(self):
        self.assertTrue(FichaStatusForm({'status': 'arquivada', 'versao': 1}).is_valid())
        self.assertFalse(FichaStatusForm({'status': 'morta', 'versao': 1}).is_valid())


class FichaPermissionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password=get_random_string(32))
        self.other = User.objects.create_user(username='other', password=get_random_string(32))
        self.master = User.objects.create_superuser(
            username='master', email='master@example.com', password=get_random_string(32)
        )
        self.ficha = Ficha.objects.create(dono=self.owner, nome='Agente', nex=5)

    def test_owner_and_master_permissions(self):
        self.assertTrue(pode_ver_ficha(self.owner, self.ficha))
        self.assertTrue(pode_editar_ficha(self.owner, self.ficha))
        self.assertFalse(pode_ver_ficha(self.other, self.ficha))
        self.assertFalse(pode_editar_ficha(self.other, self.ficha))
        self.assertTrue(is_mestre(self.master))
        self.assertTrue(pode_ver_ficha(self.master, self.ficha))
        self.assertTrue(pode_editar_ficha(self.master, self.ficha))

    def test_visible_queryset_is_scoped(self):
        Ficha.objects.create(dono=self.other, nome='Outra ficha', nex=5)
        self.assertEqual(list(fichas_visiveis_para(self.owner)), [self.ficha])
        self.assertEqual(fichas_visiveis_para(self.master).count(), 2)


class FichaViewsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='ficha-owner', password=get_random_string(32))
        self.other = User.objects.create_user(username='ficha-other', password=get_random_string(32))
        self.master = User.objects.create_superuser(
            username='ficha-master', email='ficha-master@example.com', password=get_random_string(32)
        )
        self.classe = Classe.objects.create(
            nome='Combatente', slug='combatente', fonte='OPRPG', resumo='',
            pericias_obrigatorias=[['luta']],
        )
        self.origem = Origem.objects.create(
            nome='Acadêmico', slug='academico', fonte='OPRPG', resumo='',
            poder_nome='Saber é poder', poder_resumo='',
        )
        self.fortitude = self._pericia('fortitude', 'vigor')
        self.luta = self._pericia('luta', 'forca')
        self.pontaria = self._pericia('pontaria', 'agilidade')
        self.origem.pericias_treinadas.add(self.fortitude)
        self.ficha = Ficha.objects.create(
            dono=self.owner, nome='Agente', classe=self.classe, nex=5,
            pv_atual=10, anotacoes_jogador='privada', anotacoes_mestre='segredo do mestre',
        )

    @staticmethod
    def _pericia(slug, atributo):
        return Pericia.objects.create(
            nome=slug.capitalize(), slug=slug, fonte='OPRPG', resumo='', atributo=atributo,
        )

    def test_detail_renders_track_milestones_and_power_affinity(self):
        trilha = Trilha.objects.create(
            nome='Trilha de teste', slug='trilha-de-teste', fonte='teste', resumo='',
            classe=self.classe, pre_requisitos={'classe_slug': 'combatente'},
            habilidades=[{'nex': 10, 'nome': 'Primeiro marco', 'resumo': 'Resumo da habilidade.'}],
        )
        self.ficha.trilha = trilha
        self.ficha.afinidade_elemento = 'morte'
        self.ficha.save(update_fields=('trilha', 'afinidade_elemento'))
        poder = Poder.objects.create(
            nome='Poder de teste', slug='poder-de-teste', fonte='teste', resumo='Resumo base.',
            tipo='paranormal', elemento='morte', afinidade_resumo='Efeito por repetição.',
        )
        FichaPoder.objects.create(ficha=self.ficha, poder=poder)
        self.client.force_login(self.owner)

        response = self.client.get(reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))

        self.assertContains(response, 'Primeiro marco')
        self.assertContains(response, 'NEX 10%')
        self.assertContains(response, 'Afinidade elemental:')
        self.assertContains(response, 'Efeito por repetição.')

    def test_initial_skill_picker_is_one_list_and_excludes_origin_skills(self):
        form = PericiasFichaForm(
            classe=self.classe,
            origem=self.origem,
            intelecto=0,
        )

        self.assertEqual(set(form.fields), {'pericias_escolhidas'})
        self.assertEqual(form.quantidade_escolhas, 2)
        opcoes = set(form.fields['pericias_escolhidas'].queryset.values_list('pk', flat=True))
        self.assertNotIn(self.fortitude.pk, opcoes)
        self.assertIn(self.luta.pk, opcoes)
        self.assertIn(self.pontaria.pk, opcoes)

    def test_owner_can_adjust_skill_dice_and_numeric_modifier(self):
        ficha_pericia = FichaPericia.objects.create(
            ficha=self.ficha, pericia=self.luta, grau='treinado',
        )
        url = reverse(
            'fichas:ajustar_pericia',
            kwargs={'pk': self.ficha.pk, 'pericia_pk': self.luta.pk},
        )
        self.client.force_login(self.owner)
        detalhe_inicial = self.client.get(
            reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}),
        )
        self.assertContains(detalhe_inicial, 'data-roll-result')
        self.assertContains(detalhe_inicial, 'js/ficha.js?v=10')
        self.assertContains(detalhe_inicial, 'Editar grau e modificadores')
        self.assertContains(detalhe_inicial, 'data-roll-trigger')

        response = self.client.post(url, {
            'grau': 'veterano', 'dados_extra': '-1', 'bonus_extra': '2',
        })

        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        ficha_pericia.refresh_from_db()
        self.assertEqual(
            (ficha_pericia.grau, ficha_pericia.dados_extra, ficha_pericia.bonus_extra),
            ('veterano', -1, 2),
        )
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=self.ficha, campo=f'pericia.{self.luta.pk}.grau',
            valor_antigo='treinado', valor_novo='veterano',
        ).exists())
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=self.ficha, campo=f'pericia.{self.luta.pk}.dados_extra', valor_antigo='0',
            valor_novo='-1',
        ).exists())
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=self.ficha, campo=f'pericia.{self.luta.pk}.bonus_extra', valor_antigo='0',
            valor_novo='2',
        ).exists())
        ficha_pericia.dados_extra = 0
        ficha_pericia.grau = 'treinado'
        ficha_pericia.save(update_fields=('grau', 'dados_extra'))
        self.ficha.forca = 3
        self.ficha.save(update_fields=('forca',))
        detalhe = self.client.get(reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.assertContains(detalhe, '3 dado(s) +7')
        self.assertContains(detalhe, 'Treinamento +5')
        self.assertContains(detalhe, 'Modificador +2')
        self.assertContains(detalhe, 'data-roll-type="pericia"')
        rolagem = self.client.post(
            reverse('fichas:rolar', kwargs={'pk': self.ficha.pk}),
            data='{"tipo":"pericia","alvo":%d,"bonus":0}' % self.luta.pk,
            content_type='application/json',
        )
        self.assertEqual(rolagem.status_code, 200)
        self.assertEqual(rolagem.json()['bonus'], 7)
        self.assertIn('+5 treinamento', rolagem.json()['detalhamento'])
        self.assertIn('+2 modificador da perícia', rolagem.json()['detalhamento'])

        self.client.force_login(self.other)
        self.assertEqual(self.client.post(
            url, {'grau': 'treinado', 'dados_extra': '0', 'bonus_extra': '0'},
        ).status_code, 404)

    def test_experience_mode_separates_acquired_and_upcoming_track_levels(self):
        ConfiguracaoMesa.objects.create(sistema_progressao='nivel_nex')
        trilha = Trilha.objects.create(
            nome='Trilha de níveis', slug='trilha-de-niveis', fonte='teste', resumo='',
            classe=self.classe,
            habilidades=[
                {'nex': 10, 'nome': 'Marco nível 2', 'resumo': 'Adquirido.'},
                {'nex': 40, 'nome': 'Marco nível 8', 'resumo': 'Adquirido.'},
                {'nex': 65, 'nome': 'Marco nível 13', 'resumo': 'Futuro.'},
                {'nex': 99, 'nome': 'Marco nível 20', 'resumo': 'Futuro.'},
            ],
        )
        self.ficha.trilha = trilha
        self.ficha.nivel_experiencia = 8
        self.ficha.nex = 20
        self.ficha.save(update_fields=('trilha', 'nivel_experiencia', 'nex'))
        self.client.force_login(self.master)

        response = self.client.get(reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))

        self.assertContains(response, 'Nível 8')
        self.assertContains(response, 'Exposição paranormal: NEX 20%')
        self.assertContains(response, 'Marco nível 2')
        self.assertContains(response, 'Marco nível 8')
        self.assertContains(response, 'Próximas aquisições')
        self.assertContains(response, 'Marco nível 13')
        self.assertContains(response, 'Marco nível 20')
        self.assertNotContains(response, 'NEX 65%')
        self.assertNotContains(response, 'NEX 99%')

    def test_selecting_survivor_track_shows_current_stage_ability_automatically(self):
        survivor = Classe.objects.create(
            nome='Sobrevivente', slug='sobrevivente', fonte='SaH', resumo='',
        )
        trilha = Trilha.objects.create(
            nome='Durão', slug='durão', fonte='SaH p.31', resumo='Resistente.',
            classe=survivor,
            habilidades=[
                {'estagio': 2, 'nome': 'Casca inicial', 'resumo': 'Habilidade disponível.'},
                {'estagio': 4, 'nome': 'Golpe futuro', 'resumo': 'Habilidade futura.'},
            ],
        )
        self.ficha.classe = survivor
        self.ficha.estagio = 2
        self.ficha.nex = None
        self.ficha.save(update_fields=('classe', 'estagio', 'nex'))
        pendencia = Pendencia.objects.create(
            ficha=self.ficha, tipo='trilha', descricao='Escolher trilha.', fonte='SaH p.31',
        )
        self.client.force_login(self.owner)

        response = self.client.post(reverse(
            'fichas:resolver_pendencia',
            kwargs={'pk': self.ficha.pk, 'pendencia_pk': pendencia.pk},
        ), {'trilha': trilha.pk})

        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        detalhe = self.client.get(reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.assertContains(detalhe, 'Habilidades adquiridas')
        self.assertContains(detalhe, 'Casca inicial')
        self.assertContains(detalhe, 'Habilidade disponível.')
        self.assertNotContains(detalhe, 'Registrar a primeira habilidade da trilha')

    def test_survivor_creation_starts_at_stage_one_without_progression_or_track_fields(self):
        survivor = Classe.objects.create(
            nome='Sobrevivente', slug='sobrevivente', fonte='SaH', resumo='',
            progressao='estagio',
        )
        self.client.force_login(self.owner)
        self.client.get(reverse('fichas:iniciar'))
        response = self.client.get(reverse('fichas:criar', kwargs={'etapa': 1}))
        self.assertContains(response, 'Conceito')
        self.assertContains(response, 'Origem')
        self.assertContains(response, 'Classe')
        self.assertContains(response, 'Atributos')
        self.assertContains(response, 'Perícias')
        self.assertNotContains(response, 'NEX inicial')
        self.assertNotContains(response, 'Trilha (opcional)')
        self.assertContains(response, 'Acadêmico')
        self.assertContains(response, 'data-origin-pericias=')
        self.assertContains(response, 'data-slug="sobrevivente"')
        self.assertNotContains(response, 'Aparência')
        self.assertNotContains(response, 'História')
        self.assertNotContains(response, 'grau_pericia_')
        self.assertNotContains(response, 'Perícia obrigatória')
        self.assertNotContains(response, 'data-mandatory-slot')
        self.assertNotContains(response, 'Etapas da criação')

        response = self.client.post(reverse('fichas:criar', kwargs={'etapa': 1}), {
            'nome': 'Sobrevivente', 'conceito': 'Resiliente', 'aparencia': 'Casaco',
            'personalidade': 'Cauteloso', 'historia': 'Sobreviveu.', 'objetivo': 'Viver',
            'classe': survivor.pk,
            'origem': self.origem.pk,
            'agilidade': 2,
            'forca': 2,
            'intelecto': 1,
            'presenca': 1,
            'vigor': 2,
            'pericias_escolhidas': [self.luta.pk, self.pontaria.pk],
            'confirmar': 'on',
            f'grau_pericia_{self.fortitude.pk}': 'treinado',
            f'grau_pericia_{self.luta.pk}': 'treinado',
            f'grau_pericia_{self.pontaria.pk}': 'treinado',
        })

        self.assertEqual(response.status_code, 302, response.get('Location'))
        ficha = Ficha.objects.get(nome='Sobrevivente')
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': ficha.pk}))
        self.assertEqual((ficha.estagio, ficha.nex, ficha.trilha), (1, None, None))

    def test_owner_can_complete_creation_wizard(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('fichas:iniciar'))
        self.assertRedirects(response, reverse('fichas:criar', kwargs={'etapa': 1}))

        response = self.client.post(reverse('fichas:criar', kwargs={'etapa': 1}), {
            'nome': 'Nova agente', 'conceito': 'Investigadora', 'aparencia': 'Casaco escuro',
            'personalidade': 'Atenta', 'historia': 'Chegou recentemente à Ordem.', 'objetivo': 'Investigar o caso',
            'nex_inicial': '5', 'origem': self.origem.pk, 'classe': self.classe.pk,
            'agilidade': 3, 'forca': 2, 'intelecto': 0, 'presenca': 1, 'vigor': 3,
            'pericias_escolhidas': [self.luta.pk, self.pontaria.pk],
            'confirmar': 'on',
            f'grau_pericia_{self.fortitude.pk}': 'treinado',
            f'grau_pericia_{self.luta.pk}': 'treinado',
            f'grau_pericia_{self.pontaria.pk}': 'treinado',
        })

        ficha = Ficha.objects.get(nome='Nova agente')
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': ficha.pk}))
        self.assertEqual((ficha.dono, ficha.pv_atual, ficha.pe_atual, ficha.san_atual), (self.owner, 23, 3, 12))
        self.assertSetEqual(
            set(ficha.pericias.values_list('pericia__slug', flat=True)),
            {'fortitude', 'luta', 'pontaria'},
        )

    def test_creation_in_experience_mode_starts_at_level_one_and_nex_zero(self):
        ConfiguracaoMesa.objects.create(sistema_progressao='nivel_nex')
        self.client.force_login(self.owner)
        self.client.get(reverse('fichas:iniciar'))
        response = self.client.post(reverse('fichas:criar', kwargs={'etapa': 1}), {
            'nome': 'Agente de nível', 'conceito': 'Investigadora', 'aparencia': 'Casaco escuro',
            'personalidade': 'Atenta', 'historia': 'Chegou à Ordem.', 'objetivo': 'Investigar',
            'nivel_inicial': '1', 'nex_paranormal': '0',
            'origem': self.origem.pk, 'classe': self.classe.pk,
            'agilidade': 3, 'forca': 2, 'intelecto': 0, 'presenca': 1, 'vigor': 3,
            'pericias_escolhidas': [self.luta.pk, self.pontaria.pk],
            'confirmar': 'on',
            f'grau_pericia_{self.fortitude.pk}': 'treinado',
            f'grau_pericia_{self.luta.pk}': 'treinado',
            f'grau_pericia_{self.pontaria.pk}': 'treinado',
        })
        self.assertEqual(response.status_code, 302, response.get('Location'))
        ficha = Ficha.objects.get(nome='Agente de nível')
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': ficha.pk}))
        self.assertEqual((ficha.nex, ficha.nivel_experiencia, ficha.pv_atual), (0, 1, 23))

    def test_creation_starts_at_default_nex_with_initial_skills_trained(self):
        self.client.force_login(self.owner)
        self.client.get(reverse('fichas:iniciar'))
        dados = {
            'nome': 'Agente inicial', 'conceito': 'Investigadora',
            'aparencia': 'Casaco escuro', 'personalidade': 'Atenta',
            'historia': 'Chegou à Ordem.', 'objetivo': 'Investigar',
            'origem': self.origem.pk, 'classe': self.classe.pk,
            'agilidade': 3, 'forca': 2, 'intelecto': 0, 'presenca': 1, 'vigor': 3,
            'pericias_escolhidas': [self.luta.pk, self.pontaria.pk],
        }
        response = self.client.post(
            reverse('fichas:criar', kwargs={'etapa': 1}), dados,
        )
        self.assertEqual(response.status_code, 302, response.content.decode())
        ficha = Ficha.objects.get(nome='Agente inicial')
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': ficha.pk}))
        self.assertEqual((ficha.nex, ficha.nivel_experiencia, ficha.trilha), (5, None, None))
        self.assertEqual(ficha.origem, self.origem)
        self.assertEqual(
            dict(ficha.pericias.values_list('pericia__slug', 'grau')),
            {'fortitude': 'treinado', 'luta': 'treinado', 'pontaria': 'treinado'},
        )

    def test_survivor_creation_cannot_start_with_advanced_skill_degrees(self):
        sobrevivente = Classe.objects.create(
            nome='Sobrevivente', slug='sobrevivente', fonte='SaH', resumo='',
        )
        mesa = ConfiguracaoMesa.objects.create()
        form = CriacaoInicialForm(
            data={
                'confirmar': 'on',
                'estagio_inicial': '3',
                f'grau_pericia_{self.luta.pk}': 'veterano',
            },
            mesa=mesa,
            classe=sobrevivente,
            origem=self.origem,
            atributos={'intelecto': 1},
            pericia_ids=[self.luta.pk],
        )

        self.assertFalse(form.is_valid())
        self.assertIn(
            'Os graus escolhidos excedem os aprimoramentos de perícia disponíveis '
            'nesta progressão.',
            form.non_field_errors(),
        )

    def test_free_creation_mode_is_granted_only_to_master(self):
        self.client.force_login(self.other)
        self.client.get(f"{reverse('fichas:iniciar')}?livre=1")
        self.assertFalse(self.client.session['fichas.criacao']['livre'])

        self.client.force_login(self.master)
        self.client.get(f"{reverse('fichas:iniciar')}?livre=1")
        self.assertTrue(self.client.session['fichas.criacao']['livre'])
        response = self.client.post(reverse('fichas:criar', kwargs={'etapa': 1}), {
            'nex_inicial': '5', 'agilidade': 4, 'forca': 4,
            'intelecto': 4, 'presenca': 4, 'vigor': 4,
        })
        self.assertEqual(response.status_code, 302, response.get('Location'))
        ficha = Ficha.objects.get(dono=self.master, agilidade=4, forca=4, intelecto=4, presenca=4, vigor=4)
        self.assertIsNone(ficha.classe_id)

    def test_foreign_ficha_is_not_discoverable_or_editable(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk})).status_code, 404)
        self.assertEqual(self.client.get(reverse('fichas:editar', kwargs={'pk': self.ficha.pk})).status_code, 404)
        self.assertEqual(self.client.post(
            reverse('fichas:recurso', kwargs={'pk': self.ficha.pk}),
            data='{"recurso":"pv","delta":1}', content_type='application/json',
        ).status_code, 404)

    def test_edit_uses_version_and_ignores_privileged_fields_for_owner(self):
        self.client.force_login(self.owner)
        url = reverse('fichas:editar', kwargs={'pk': self.ficha.pk})
        dados = {
            'nome': 'Nome atualizado', 'jogador': '', 'conceito': '', 'aparencia': '',
            'personalidade': '', 'historia': '', 'objetivo': '',
            'anotacoes_jogador': 'anotação nova', 'versao': 1,
            'anotacoes_mestre': 'tentativa de alteração', 'status': 'morta', 'nex': 99,
        }
        response = self.client.post(url, dados)
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.ficha.refresh_from_db()
        self.assertEqual((self.ficha.nome, self.ficha.versao, self.ficha.status, self.ficha.nex),
                         ('Nome atualizado', 2, 'ativa', 5))
        self.assertEqual(self.ficha.anotacoes_mestre, 'segredo do mestre')
        self.assertFalse(LogAlteracao.objects.filter(valor_novo__contains='anotação nova').exists())
        self.assertFalse(LogAlteracao.objects.filter(valor_novo__contains='segredo do mestre').exists())
        response = self.client.post(url, dados)
        self.assertEqual(response.status_code, 409)

    def test_notes_tab_saves_player_and_master_notes_with_versioning(self):
        url = reverse('fichas:salvar_anotacoes', kwargs={'pk': self.ficha.pk})
        detalhe_url = reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk})
        self.client.force_login(self.owner)
        detalhe = self.client.get(detalhe_url)
        self.assertContains(detalhe, 'name="anotacoes_jogador"')
        self.assertNotContains(detalhe, 'name="anotacoes_mestre"')

        response = self.client.post(url, {
            'anotacoes_jogador': 'Pista: a porta estava aberta.',
            'anotacoes_mestre': 'Tentativa de escrita',
            'versao': self.ficha.versao,
        })

        self.assertRedirects(response, f'{detalhe_url}#anotacoes')
        self.ficha.refresh_from_db()
        self.assertEqual(self.ficha.anotacoes_jogador, 'Pista: a porta estava aberta.')
        self.assertEqual(self.ficha.anotacoes_mestre, 'segredo do mestre')
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=self.ficha, campo='anotacoes_jogador',
            valor_novo='Pista: a porta estava aberta.',
        ).exists())
        self.assertEqual(self.ficha.versao, 2)

        self.client.force_login(self.master)
        response = self.client.post(url, {
            'anotacoes_jogador': 'Pista: a porta estava aberta.',
            'anotacoes_mestre': 'A porta foi aberta por dentro.',
            'versao': self.ficha.versao,
        })
        self.assertRedirects(response, f'{detalhe_url}#anotacoes')
        self.ficha.refresh_from_db()
        self.assertEqual(self.ficha.anotacoes_mestre, 'A porta foi aberta por dentro.')

    def test_edit_sets_resource_maxima_and_independent_patent(self):
        patente = Patente.objects.create(
            nome='Recruta', slug='recruta-independente', fonte='teste',
            credito='Baixo', limite_pd=1, recuperacao=1,
        )
        self.client.force_login(self.owner)

        response = self.client.post(reverse('fichas:editar', kwargs={'pk': self.ficha.pk}), {
            'nome': self.ficha.nome,
            'jogador': '',
            'conceito': '',
            'aparencia': '',
            'personalidade': '',
            'historia': '',
            'objetivo': '',
            'afinidade_elemento': '',
            'anotacoes_jogador': '',
            'versao': self.ficha.versao,
            'pv_max': 25,
            'pe_max': 8,
            'san_max': 15,
            'pd_max': 9,
            'pontos_prestigio': 17,
            'patente': patente.pk,
        })

        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.ficha.refresh_from_db()
        self.assertEqual(self.ficha.nex, 5)
        self.assertEqual((self.ficha.patente, self.ficha.pontos_prestigio), (patente, 17))
        self.assertEqual(
            (self.ficha.ajuste_pv_max, self.ficha.ajuste_pe_max,
             self.ficha.ajuste_san_max, self.ficha.ajuste_pd_max),
            (4, 5, 3, 2),
        )

    def test_resource_condition_and_roll_endpoints_validate_and_persist(self):
        self.client.force_login(self.owner)
        resource = reverse('fichas:recurso', kwargs={'pk': self.ficha.pk})
        response = self.client.post(resource, data='{"recurso":"pv","delta":2}', content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['aplicado'], 2)
        self.ficha.refresh_from_db()
        self.assertEqual(self.ficha.pv_atual, 12)
        response = self.client.post(resource, data='{"recurso":"pv","delta":999}', content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['atual'], 1011)
        self.assertEqual(response.json()['temporario'], 990)
        self.assertEqual(response.json()['aplicado'], 999)
        self.assertEqual(response.json()['sobrou'], 0)
        self.assertEqual(self.client.post(resource, data='{"recurso":"pv","delta":true}', content_type='application/json').status_code, 400)
        self.assertEqual(self.client.post(resource, data='{"recurso":[],"delta":1}', content_type='application/json').status_code, 400)
        self.assertEqual(self.client.post(resource, data='{"recurso":"pd","delta":1}', content_type='application/json').status_code, 400)

        ConfiguracaoMesa.objects.create(modo_recursos='sem_sanidade')
        self.assertEqual(self.client.post(resource, data='{"recurso":"pe","delta":1}', content_type='application/json').status_code, 400)
        self.assertEqual(self.client.post(resource, data='{"recurso":"pd","delta":1}', content_type='application/json').status_code, 200)

        condicao = Condicao.objects.create(nome='Abalado', slug='abalado', fonte='OPRPG', resumo='')
        condition_url = reverse('fichas:condicao', kwargs={'pk': self.ficha.pk})
        response = self.client.post(
            condition_url, data=f'{{"acao":"adicionar","condicao":{condicao.pk}}}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(FichaCondicao.objects.filter(ficha=self.ficha, condicao=condicao).exists())
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=self.ficha, campo='condicao', valor_novo=condicao.nome,
        ).exists())

        roll_url = reverse('fichas:rolar', kwargs={'pk': self.ficha.pk})
        response = self.client.post(
            roll_url, data='{"tipo":"pericia","alvo":%d,"bonus":0}' % self.luta.pk,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Rolagem.objects.filter(ficha=self.ficha, usuario=self.owner).count(), 1)
        self.assertEqual(response.json()['total'], response.json()['dado_escolhido'] + 0)
        self.assertEqual(self.client.post(
            roll_url, data='{}', content_type='application/json',
        ).status_code, 400)

    def test_temporary_resources_are_excess_over_maximum_and_audited(self):
        resource = reverse('fichas:recurso', kwargs={'pk': self.ficha.pk})
        self.client.force_login(self.owner)

        response = self.client.post(
            resource,
            data='{"recurso":"pv","delta":7}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['atual'], 17)
        self.assertEqual(response.json()['temporario'], 0)
        self.ficha.refresh_from_db()
        self.assertEqual(self.ficha.pv_atual, 17)
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=self.ficha, campo='pv_atual', valor_antigo='10', valor_novo='17',
        ).exists())

        response = self.client.post(
            resource,
            data='{"recurso":"pv","delta":-9}',
            content_type='application/json',
        )
        self.assertEqual((response.status_code, response.json()['atual']), (200, 8))
        self.assertEqual(response.json()['temporario'], 0)
        estado = self.client.get(
            reverse('fichas:atualizacoes', kwargs={'pk': self.ficha.pk}),
        ).json()
        self.assertNotIn('pv_temporario', estado)

        self.client.force_login(self.other)
        self.assertEqual(self.client.post(
            resource,
            data='{"recurso":"pv","delta":1}',
            content_type='application/json',
        ).status_code, 404)

        self.client.force_login(self.owner)
        response = self.client.get(reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.assertContains(response, 'data-session-mode-toggle')
        self.assertContains(response, 'data-wake-lock-toggle')
        self.assertContains(response, 'data-overflow="pv"')
        self.assertNotContains(response, 'data-resource-panel="pv_temporario"')
        for faces in (4, 6, 8, 10, 12, 20):
            self.assertContains(response, f'data-die-face="{faces}"')
            self.assertContains(response, f'dices%20vector/d{faces}.svg')

    def test_resource_increment_crosses_maximum_then_depletes_temporary_first(self):
        self.client.force_login(self.owner)
        configuracao = ConfiguracaoMesa.objects.create()
        recursos = (
            ('pv', 'pv_atual', 21),
            ('pe', 'pe_atual', 3),
            ('san', 'san_atual', 12),
        )
        for recurso, campo, maximo in recursos:
            with self.subTest(recurso=recurso):
                diferenca = min(4, maximo)
                setattr(self.ficha, campo, maximo - diferenca)
                self.ficha.save(update_fields=(campo,))
                url = reverse('fichas:recurso', kwargs={'pk': self.ficha.pk})
                resposta = self.client.post(
                    url,
                    data=json.dumps({'recurso': recurso, 'delta': 5}),
                    content_type='application/json',
                )
                self.assertEqual(resposta.status_code, 200)
                self.assertEqual(
                    (resposta.json()['atual'], resposta.json()['temporario']),
                    (maximo + 5 - diferenca, 5 - diferenca),
                )
                resposta = self.client.post(
                    url,
                    data=json.dumps({'recurso': recurso, 'delta': -1}),
                    content_type='application/json',
                )
                self.assertEqual(
                    resposta.json()['atual'],
                    maximo + max(0, 4 - diferenca),
                )
                self.assertEqual(
                    resposta.json()['temporario'], max(0, 4 - diferenca),
                )

        configuracao.modo_recursos = 'sem_sanidade'
        configuracao.save(update_fields=('modo_recursos',))
        self.ficha.pd_atual = 3
        self.ficha.save(update_fields=('pd_atual',))
        resposta = self.client.post(
            reverse('fichas:recurso', kwargs={'pk': self.ficha.pk}),
            data='{"recurso":"pd","delta":5}',
            content_type='application/json',
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual((resposta.json()['atual'], resposta.json()['temporario']), (8, 1))

    def test_damage_endpoint_evaluates_physical_dice_and_persists_roll(self):
        self.client.force_login(self.owner)
        url = reverse('fichas:calcular_dano', kwargs={'pk': self.ficha.pk})
        response = self.client.post(
            url,
            data=json.dumps({
                'quantidade_dados': 2, 'faces': 6, 'bonus': 3,
                'multiplicador_critico': 2, 'dados_fisicos': [2, 3, 4, 5],
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.json()['dados'], response.json()['total']), ([2, 3, 4, 5], 17))
        registro = Rolagem.objects.get(pk=response.json()['id'])
        self.assertEqual((registro.tipo, registro.bonus, registro.total), ('dano', 3, 17))
        self.assertEqual(self.client.post(
            url,
            data='{"quantidade_dados":2,"faces":6,"bonus":0,"multiplicador_critico":2,"dados_fisicos":[1]}',
            content_type='application/json',
        ).status_code, 400)
        digital = self.client.post(
            url,
            data='{"quantidade_dados":2,"faces":6,"bonus":3,"multiplicador_critico":2}',
            content_type='application/json',
        )
        self.assertEqual(digital.status_code, 200)
        self.assertEqual(len(digital.json()['dados']), 4)
        self.assertEqual(digital.json()['total'], sum(digital.json()['dados']) + 3)
        self.assertEqual(self.client.post(
            url,
            data='{"quantidade_dados":1000000,"faces":6,"bonus":0,"multiplicador_critico":1}',
            content_type='application/json',
        ).status_code, 400)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(
            url,
            data='{"quantidade_dados":1,"faces":6,"bonus":0,"multiplicador_critico":1,"dados_fisicos":[3]}',
            content_type='application/json',
        ).status_code, 404)

    def test_zero_pv_applies_combat_conditions_and_healing_only_ends_unconscious(self):
        self.client.force_login(self.owner)
        url = reverse('fichas:recurso', kwargs={'pk': self.ficha.pk})
        response = self.client.post(url, data='{"recurso":"pv","delta":-10}', content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(self.ficha.condicoes.values_list('condicao__slug', flat=True)),
            {'inconsciente', 'morrendo'},
        )
        self.client.post(url, data='{"recurso":"pv","delta":1}', content_type='application/json')
        self.assertEqual(
            set(self.ficha.condicoes.values_list('condicao__slug', flat=True)),
            {'morrendo'},
        )
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=self.ficha, campo='condicao', valor_novo='Morrendo',
        ).exists())

    def test_master_combat_tracker_skips_surprised_and_tracks_actions_privately(self):
        self.client.force_login(self.master)
        create = self.client.post(reverse('fichas:encontros_combate'), {'nome': 'Estacionamento'})
        self.assertEqual(create.status_code, 302)
        encontro = EncontroCombate.objects.get(nome='Estacionamento')
        add_url = reverse('fichas:adicionar_participante_combate', kwargs={'pk': encontro.pk})
        ameaca = AmeacaMesa.objects.create(
            criado_por=self.master, nome='Observador do Véu', categoria='anomalia',
            defesa=17, pv=38, acoes='Olhar penetrante.',
            anotacoes_mestre='Evita a luz direta.',
        )
        self.client.post(add_url, {
            'ameaca': ameaca.pk, 'nome': '', 'iniciativa': 8,
        })
        self.client.post(add_url, {
            'nome': 'Ameaça oculta', 'iniciativa': 20, 'surpreendido': 'on',
        })
        self.client.post(add_url, {
            'ficha': self.ficha.pk, 'nome': '', 'iniciativa': 10,
        })
        detail_url = reverse('fichas:encontro_combate', kwargs={'pk': encontro.pk})
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse('fichas:encontros_combate')).status_code, 403)
        self.assertEqual(self.client.post(
            reverse('fichas:encontros_combate'), {'nome': 'Cena indevida'},
        ).status_code, 403)
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 403)
        self.client.force_login(self.master)
        response = self.client.get(detail_url)
        self.assertContains(response, 'Olhar penetrante.')
        self.assertContains(response, 'Evita a luz direta.')
        self.assertContains(self.client.get(reverse('painel_mestre')), 'Combates')
        self.client.post(
            reverse('fichas:avancar_turno_combate', kwargs={'pk': encontro.pk}),
        )
        encontro.refresh_from_db()
        atual = list(encontro.participantes.order_by('-iniciativa', 'pk'))[encontro.indice_turno]
        self.assertEqual(atual.ficha, self.ficha)
        action_url = reverse(
            'fichas:registrar_acao_combate',
            kwargs={'pk': encontro.pk, 'participante_pk': atual.pk},
        )
        self.client.post(action_url, {'acao': 'padrao'})
        atual.refresh_from_db()
        self.assertTrue(atual.acao_padrao_usada)
        self.client.post(action_url, {'acao': 'completa'})
        atual.refresh_from_db()
        self.assertFalse(atual.acao_completa_usada)
        self.client.post(action_url, {'acao': 'reacao_defensiva'})
        atual.refresh_from_db()
        self.assertTrue(atual.reacao_defensiva_usada)
        self.client.post(action_url, {'acao': 'reacao_defensiva'})
        atual.refresh_from_db()
        self.assertTrue(atual.reacao_defensiva_usada)
        self.client.post(reverse('fichas:avancar_turno_combate', kwargs={'pk': encontro.pk}))
        self.client.post(reverse('fichas:avancar_turno_combate', kwargs={'pk': encontro.pk}))
        atual.refresh_from_db()
        self.assertFalse(atual.reacao_defensiva_usada)
        page = self.client.get(detail_url)
        self.assertContains(page, 'Ameaça oculta')
        self.assertContains(page, 'Aplicar dano físico')
        self.client.force_login(self.owner)
        self.assertNotContains(self.client.get(reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk})), 'Ameaça oculta')

    def test_combat_turn_enforces_pe_limit_and_resets_turn_spend(self):
        self.client.force_login(self.master)
        encontro = EncontroCombate.objects.create(criado_por=self.master, nome='Uso de PE')
        participante = ParticipanteCombate.objects.create(
            encontro=encontro, ficha=self.ficha, nome=self.ficha.nome, iniciativa=10,
        )
        encontro.indice_turno = 0
        encontro.save(update_fields=('indice_turno',))
        url = reverse(
            'fichas:gastar_recurso_combate',
            kwargs={'pk': encontro.pk, 'participante_pk': participante.pk},
        )

        response = self.client.post(url, {'recurso': 'pe', 'quantidade': 2})
        self.assertRedirects(response, reverse('fichas:encontro_combate', kwargs={'pk': encontro.pk}))
        participante.refresh_from_db()
        self.ficha.refresh_from_db()
        self.assertEqual((participante.pe_gasto_turno, self.ficha.pe_atual), (0, 0))

        self.ficha.pe_atual = 3
        self.ficha.save(update_fields=('pe_atual',))
        response = self.client.post(url, {'recurso': 'pe', 'quantidade': 1})
        self.assertEqual(response.status_code, 302)
        participante.refresh_from_db()
        self.ficha.refresh_from_db()
        self.assertEqual((participante.pe_gasto_turno, self.ficha.pe_atual), (1, 2))
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=self.ficha, campo='combate.recurso', valor_antigo='0', valor_novo='1',
        ).exists())

        response = self.client.post(url, {'recurso': 'pe', 'quantidade': 1})
        self.assertEqual(response.status_code, 302)
        participante.refresh_from_db()
        self.assertEqual(participante.pe_gasto_turno, 1)

        self.client.post(reverse(
            'fichas:avancar_turno_combate', kwargs={'pk': encontro.pk},
        ))
        participante.refresh_from_db()
        self.assertEqual(participante.pe_gasto_turno, 0)

    def test_patent_pd_spending_respects_turn_limit_and_master_access(self):
        ConfiguracaoMesa.objects.create(modo_recursos='sem_sanidade', sistema_progressao='patentes')
        patente = Patente.objects.create(
            nome='Agente Especial', slug='agente-especial', fonte='SaH p.108',
            resumo='', credito='IV', limite_pd=3, recuperacao=1,
        )
        self.ficha.patente = patente
        self.ficha.nex = None
        self.ficha.pd_atual = 5
        self.ficha.save(update_fields=('patente', 'nex', 'pd_atual'))
        encontro = EncontroCombate.objects.create(criado_por=self.master, nome='Uso de PD')
        participante = ParticipanteCombate.objects.create(
            encontro=encontro, ficha=self.ficha, nome=self.ficha.nome, iniciativa=10,
        )
        encontro.indice_turno = 0
        encontro.save(update_fields=('indice_turno',))
        url = reverse(
            'fichas:gastar_recurso_combate',
            kwargs={'pk': encontro.pk, 'participante_pk': participante.pk},
        )
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(url, {'recurso': 'pd', 'quantidade': 1}).status_code, 403)

        self.client.force_login(self.master)
        self.assertEqual(self.client.post(url, {'recurso': 'pd', 'quantidade': 3}).status_code, 302)
        self.ficha.refresh_from_db()
        participante.refresh_from_db()
        self.assertEqual((self.ficha.pd_atual, participante.pd_gasto_turno), (2, 3))
        self.client.post(url, {'recurso': 'pd', 'quantidade': 1})
        participante.refresh_from_db()
        self.assertEqual(participante.pd_gasto_turno, 3)

    def test_only_master_can_apply_physical_damage_to_linked_combatant(self):
        encontro = EncontroCombate.objects.create(criado_por=self.master, nome='Arquivo')
        participante = ParticipanteCombate.objects.create(
            encontro=encontro, ficha=self.ficha, nome=self.ficha.nome, iniciativa=10,
        )
        dano_url = reverse(
            'fichas:aplicar_dano_combate',
            kwargs={'pk': encontro.pk, 'participante_pk': participante.pk},
        )
        self.ficha.pv_atual = 12
        self.ficha.save(update_fields=('pv_atual',))

        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(dano_url, {'dano': 4}).status_code, 403)
        self.ficha.refresh_from_db()
        self.assertEqual(self.ficha.pv_atual, 12)

        self.client.force_login(self.master)
        self.assertEqual(self.client.post(dano_url, {'dano': 4}).status_code, 302)
        self.ficha.refresh_from_db()
        self.assertEqual(self.ficha.pv_atual, 8)

        self.assertEqual(self.client.post(dano_url, {'dano': 10}).status_code, 302)
        self.ficha.refresh_from_db()
        self.assertEqual(self.ficha.pv_atual, 0)
        self.assertEqual(
            set(self.ficha.condicoes.values_list('condicao__slug', flat=True)),
            {'inconsciente', 'morrendo'},
        )

    def test_morrendo_counts_started_turns_and_stabilization_is_master_recorded(self):
        self.client.force_login(self.owner)
        self.client.post(
            reverse('fichas:recurso', kwargs={'pk': self.ficha.pk}),
            data='{"recurso":"pv","delta":-10}', content_type='application/json',
        )
        self.client.force_login(self.master)
        encontro = EncontroCombate.objects.create(criado_por=self.master, nome='Armazém')
        participante = ParticipanteCombate.objects.create(
            encontro=encontro, ficha=self.ficha, nome=self.ficha.nome, iniciativa=10,
        )
        for _ in range(2):
            self.client.post(reverse('fichas:avancar_turno_combate', kwargs={'pk': encontro.pk}))
        morrendo = FichaCondicao.objects.get(ficha=self.ficha, condicao__slug='morrendo')
        self.assertEqual(morrendo.turnos_morrendo, 2)
        estabilizar_url = reverse(
            'fichas:estabilizar_combate',
            kwargs={'pk': encontro.pk, 'participante_pk': participante.pk},
        )
        self.assertEqual(self.client.post(estabilizar_url, {'confirmar': 'on'}).status_code, 302)
        self.assertFalse(FichaCondicao.objects.filter(
            ficha=self.ficha, condicao__slug='morrendo',
        ).exists())
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=self.ficha, valor_novo='Estabilizado (Medicina DT 20)',
        ).exists())

    def test_three_started_turns_morrendo_in_one_encounter_mark_character_dead(self):
        self.client.force_login(self.owner)
        self.client.post(
            reverse('fichas:recurso', kwargs={'pk': self.ficha.pk}),
            data='{"recurso":"pv","delta":-10}', content_type='application/json',
        )
        self.client.force_login(self.master)
        encontro = EncontroCombate.objects.create(criado_por=self.master, nome='Subsolo')
        ParticipanteCombate.objects.create(
            encontro=encontro, ficha=self.ficha, nome=self.ficha.nome, iniciativa=10,
        )
        url = reverse('fichas:avancar_turno_combate', kwargs={'pk': encontro.pk})
        for _ in range(3):
            self.client.post(url)
        self.ficha.refresh_from_db()
        morrendo = FichaCondicao.objects.get(ficha=self.ficha, condicao__slug='morrendo')
        self.assertEqual((self.ficha.status, morrendo.turnos_morrendo), ('morta', 3))
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=self.ficha, campo='status', valor_novo='morta',
        ).exists())

    def test_combat_tracker_enforces_unambiguous_condition_action_restrictions(self):
        self.client.force_login(self.master)
        encontro = EncontroCombate.objects.create(criado_por=self.master, nome='Restrições')
        participante = ParticipanteCombate.objects.create(
            encontro=encontro, ficha=self.ficha, nome=self.ficha.nome, iniciativa=10,
        )
        encontro.indice_turno = 0
        encontro.save(update_fields=('indice_turno',))
        url = reverse(
            'fichas:registrar_acao_combate',
            kwargs={'pk': encontro.pk, 'participante_pk': participante.pk},
        )

        for slug, acao in (('atordoado', 'padrao'), ('pasmo', 'movimento')):
            condicao = Condicao.objects.create(
                nome=slug.capitalize(), slug=slug, fonte='Personalizado', resumo='',
            )
            FichaCondicao.objects.create(ficha=self.ficha, condicao=condicao)
            response = self.client.post(url, {'acao': acao}, follow=True)
            self.assertContains(response, 'A condição ativa impede ações normais')
            participante.refresh_from_db()
            self.assertFalse(participante.acao_padrao_usada)
            self.assertEqual(participante.acoes_movimento_usadas, 0)
            FichaCondicao.objects.filter(ficha=self.ficha, condicao=condicao).delete()

        enjoado = Condicao.objects.create(
            nome='Enjoado', slug='enjoado', fonte='Personalizado', resumo='',
        )
        FichaCondicao.objects.create(ficha=self.ficha, condicao=enjoado)
        response = self.client.post(url, {'acao': 'completa'}, follow=True)
        self.assertContains(response, 'Enjoado não permite ação completa')
        participante.refresh_from_db()
        self.assertFalse(participante.acao_completa_usada)
        self.assertEqual(self.client.post(url, {'acao': 'padrao'}).status_code, 302)
        participante.refresh_from_db()
        self.assertTrue(participante.acao_padrao_usada)

        inconsciente = Condicao.objects.create(
            nome='Inconsciente', slug='inconsciente', fonte='Personalizado', resumo='',
        )
        FichaCondicao.objects.create(ficha=self.ficha, condicao=inconsciente)
        response = self.client.post(url, {'acao': 'reacao_defensiva'}, follow=True)
        self.assertContains(response, 'não pode realizar ações ou reações')
        participante.refresh_from_db()
        self.assertFalse(participante.reacao_defensiva_usada)

    def test_ending_encounter_removes_end_of_scene_conditions_and_preserves_others(self):
        expires = Condicao.objects.create(
            nome='Condição até o fim da cena',
            slug='condicao-fim-cena',
            fonte='Personalizado',
            resumo='',
            termina_fim_cena=True,
        )
        persists = Condicao.objects.create(
            nome='Condição persistente',
            slug='condicao-persistente',
            fonte='Personalizado',
            resumo='',
            termina_fim_cena=False,
        )
        FichaCondicao.objects.create(ficha=self.ficha, condicao=expires)
        FichaCondicao.objects.create(ficha=self.ficha, condicao=persists)
        self.client.force_login(self.master)
        encontro = EncontroCombate.objects.create(criado_por=self.master, nome='Cena de teste')
        ParticipanteCombate.objects.create(
            encontro=encontro, ficha=self.ficha, nome=self.ficha.nome, iniciativa=10,
        )

        response = self.client.post(
            reverse('fichas:encerrar_encontro_combate', kwargs={'pk': encontro.pk}),
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(FichaCondicao.objects.filter(
            ficha=self.ficha, condicao=expires,
        ).exists())
        self.assertTrue(FichaCondicao.objects.filter(
            ficha=self.ficha, condicao=persists,
        ).exists())
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=self.ficha,
            campo='condicao',
            valor_antigo=expires.nome,
            valor_novo='',
        ).exists())
        encontro.refresh_from_db()
        self.assertFalse(encontro.ativo)

    def test_roll_applies_condition_load_and_missing_kit_modifiers(self):
        self.client.force_login(self.owner)
        self.luta.penalidade_carga = True
        self.luta.exige_kit = True
        self.luta.save(update_fields=('penalidade_carga', 'exige_kit'))
        ItemInventario.objects.create(ficha=self.ficha, nome='Carga', espacos=6)
        FichaPericia.objects.create(ficha=self.ficha, pericia=self.luta, grau='treinado')
        abalado = Condicao.objects.create(
            nome='Abalado', slug='abalado', fonte='OPRPG p.310', resumo='',
            efeitos={'dados_teste': -1},
        )
        FichaCondicao.objects.create(ficha=self.ficha, condicao=abalado)

        response = self.client.post(
            reverse('fichas:rolar', kwargs={'pk': self.ficha.pk}),
            data=(
                '{"tipo":"pericia","alvo":%d,"bonus":0,"dados_fisicos":[8,12],'
                '"kit_disponivel":false,"dt":3}'
            ) % self.luta.pk,
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            (response.json()['dados'], response.json()['dado_escolhido'],
             response.json()['bonus'], response.json()['total'], response.json()['sucesso']),
            ([8, 12], 8, -5, 3, True),
        )

    def test_cicatrizado_penalizes_resistance_only_against_marked_danger(self):
        self.client.force_login(self.owner)
        sobrevivente = Classe.objects.create(
            nome='Sobrevivente', slug='sobrevivente', fonte='SaH p.31', resumo='',
            progressao='estagio',
        )
        self.ficha.classe = sobrevivente
        self.ficha.nex = None
        self.ficha.estagio = 5
        self.ficha.cicatrizado_elemento = 'morte'
        self.ficha.cicatrizado_perigo = 'Criatura de Morte'
        self.ficha.save(update_fields=(
            'classe', 'nex', 'estagio', 'cicatrizado_elemento', 'cicatrizado_perigo',
        ))
        url = reverse('fichas:rolar', kwargs={'pk': self.ficha.pk})
        response = self.client.post(
            url,
            data=(
                '{"tipo":"pericia","alvo":%d,"bonus":0,"dados_fisicos":[4,18],'
                '"perigo_cicatrizado":"Criatura de Morte"}'
            ) % self.fortitude.pk,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['quantidade_dados'], 2)
        self.assertEqual(response.json()['ordem'], 'menor')
        self.assertIn('Cicatrizado', response.json()['descricao'])

        response = self.client.post(
            url,
            data=(
                '{"tipo":"pericia","alvo":%d,"bonus":0,'
                '"perigo_cicatrizado":"Criatura de Morte"}'
            ) % self.luta.pk,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_debilitating_wounds_affect_rolls_max_pv_and_master_cure_flow(self):
        cache.clear()
        ConfiguracaoMesa.objects.create(ferimentos_debilitantes=True)
        self.ficha.pv_atual = 21
        self.ficha.save(update_fields=('pv_atual',))
        self.client.force_login(self.owner)
        url = reverse('fichas:gerenciar_ferimento', kwargs={'pk': self.ficha.pk})
        response = self.client.post(url, {'acao': 'registrar', 'atributo': 'vigor'})
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.master)
        response = self.client.post(url, {'acao': 'registrar', 'atributo': 'vigor'})
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        ferimento = FerimentoDebilitante.objects.get(ficha=self.ficha)
        self.ficha.refresh_from_db()
        self.assertEqual(self.ficha.pv_atual, 21)
        self.assertEqual(self.client.get(
            reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk})
        ).context['maximos']['pv'], 20)
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=self.ficha, campo='ferimento_debilitante', valor_novo='vigor',
        ).exists())
        self.assertFalse(LogAlteracao.objects.filter(
            ficha=self.ficha, campo='pv_atual', valor_novo='20',
        ).exists())

        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('fichas:rolar', kwargs={'pk': self.ficha.pk}),
            data=json.dumps({
                'tipo': 'pericia', 'alvo': self.fortitude.pk, 'bonus': 0,
                'dados_fisicos': [4, 18],
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual((response.json()['quantidade_dados'], response.json()['ordem']), (2, 'menor'))

        self.client.force_login(self.master)
        response = self.client.post(url, {'acao': 'tratamento', 'ferimento': ferimento.pk})
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        ferimento.refresh_from_db()
        self.assertIsNotNone(ferimento.tratamento_aprovado_em)
        response = self.client.post(url, {'acao': 'curar', 'ferimento': ferimento.pk})
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        ferimento.refresh_from_db()
        self.assertIsNotNone(ferimento.curado_em)
        self.ficha.refresh_from_db()
        self.assertEqual(self.client.get(
            reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk})
        ).context['maximos']['pv'], 21)
        self.assertEqual(self.ficha.pv_atual, 21)

    def test_condition_escalation_is_audited_and_updates_defense_poll(self):
        self.client.force_login(self.owner)
        apavorado = Condicao.objects.create(
            nome='Apavorado', slug='apavorado', fonte='OPRPG p.310', resumo='Resumo público.',
        )
        abalado = Condicao.objects.create(
            nome='Abalado', slug='abalado', fonte='OPRPG p.310', resumo='Resumo.',
            efeitos={'dados_teste': -1, 'bonus_defesa': -5},
            proxima_escalada=apavorado,
        )
        ficha_condicao = FichaCondicao.objects.create(
            ficha=self.ficha, condicao=abalado, anotacao='nota privada da condição',
            turnos_restantes=3,
        )
        response = self.client.post(
            reverse('fichas:condicao', kwargs={'pk': self.ficha.pk}),
            data=f'{{"acao":"escalar","condicao":{abalado.pk}}}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['condicao'], apavorado.pk)
        self.assertEqual(response.json()['removida']['id'], abalado.pk)
        self.assertFalse(FichaCondicao.objects.filter(pk=ficha_condicao.pk).exists())
        self.assertTrue(FichaCondicao.objects.filter(ficha=self.ficha, condicao=apavorado).exists())
        self.assertEqual(response.json()['turnos_restantes'], 3)
        self.assertEqual(
            FichaCondicao.objects.get(ficha=self.ficha, condicao=apavorado).turnos_restantes,
            3,
        )
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=self.ficha, campo='condicao',
            valor_antigo='Abalado', valor_novo='Apavorado (duração: 3 turnos)',
        ).exists())

        FichaCondicao.objects.create(
            ficha=self.ficha, condicao=abalado, anotacao='não enviar ao jogador',
        )
        atualizacoes = self.client.get(
            reverse('fichas:atualizacoes', kwargs={'pk': self.ficha.pk}),
        )
        self.assertEqual(atualizacoes.status_code, 200)
        self.assertEqual(atualizacoes.json()['defesa'], 6)
        self.assertEqual(atualizacoes.json()['condicoes'][0]['resumo'], 'Resumo.')
        self.assertIsNone(atualizacoes.json()['condicoes'][0]['turnos_restantes'])
        self.assertNotContains(atualizacoes, 'não enviar ao jogador')
        self.assertNotContains(atualizacoes, 'segredo do mestre')

    def test_timed_condition_counts_down_on_affected_turn_and_expires_with_audit(self):
        condition = Condicao.objects.create(
            nome='Condição temporária', slug='condicao-temporaria',
            fonte='Personalizado', resumo='',
        )
        self.client.force_login(self.owner)
        condition_url = reverse('fichas:condicao', kwargs={'pk': self.ficha.pk})
        response = self.client.post(
            condition_url,
            data=f'{{"acao":"adicionar","condicao":{condition.pk},"turnos_restantes":2}}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['turnos_restantes'], 2)
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=self.ficha, campo='condicao',
            valor_novo='Condição temporária (duração: 2 turnos)',
        ).exists())

        encontro = EncontroCombate.objects.create(criado_por=self.master, nome='Duração')
        ParticipanteCombate.objects.create(
            encontro=encontro, ficha=self.ficha, nome=self.ficha.nome, iniciativa=10,
        )
        self.client.force_login(self.master)
        avancar = reverse('fichas:avancar_turno_combate', kwargs={'pk': encontro.pk})
        self.client.post(avancar)
        ficha_condicao = FichaCondicao.objects.get(ficha=self.ficha, condicao=condition)
        self.assertEqual(ficha_condicao.turnos_restantes, 1)
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=self.ficha, campo='condicao.duracao',
            valor_antigo='2', valor_novo='1',
        ).exists())

        self.client.post(avancar)
        self.assertFalse(FichaCondicao.objects.filter(
            ficha=self.ficha, condicao=condition,
        ).exists())
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=self.ficha, campo='condicao',
            valor_antigo='Condição temporária',
            valor_novo='Expirada no início do turno',
        ).exists())

    def test_condition_duration_validation_and_morrendo_counter_are_separate(self):
        condition = Condicao.objects.create(
            nome='Abalado', slug='abalado', fonte='Personalizado', resumo='',
        )
        morrendo = Condicao.objects.create(
            nome='Morrendo', slug='morrendo', fonte='Personalizado', resumo='',
        )
        self.client.force_login(self.owner)
        url = reverse('fichas:condicao', kwargs={'pk': self.ficha.pk})
        for duration in ('true', '0', '100', '"2"'):
            response = self.client.post(
                url,
                data=f'{{"acao":"adicionar","condicao":{condition.pk},"turnos_restantes":{duration}}}',
                content_type='application/json',
            )
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post(
            url,
            data=f'{{"acao":"adicionar","condicao":{morrendo.pk},"turnos_restantes":1}}',
            content_type='application/json',
        ).status_code, 400)

        FichaCondicao.objects.create(
            ficha=self.ficha, condicao=morrendo, turnos_restantes=1,
        )
        encontro = EncontroCombate.objects.create(criado_por=self.master, nome='Morrendo')
        ParticipanteCombate.objects.create(
            encontro=encontro, ficha=self.ficha, nome=self.ficha.nome, iniciativa=10,
        )
        self.client.force_login(self.master)
        self.client.post(reverse('fichas:avancar_turno_combate', kwargs={'pk': encontro.pk}))
        morrendo_ativa = FichaCondicao.objects.get(ficha=self.ficha, condicao=morrendo)
        self.assertEqual(morrendo_ativa.turnos_restantes, 1)
        self.assertEqual(morrendo_ativa.turnos_morrendo, 0)

    def test_pending_attribute_and_training_choices_are_resolved_and_audited(self):
        self.client.force_login(self.owner)
        atributo = Pendencia.objects.create(
            ficha=self.ficha, tipo='atributo', descricao='Aumentar atributo.',
            fonte='OPRPG p.25',
        )
        detalhe = self.client.get(reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.assertContains(detalhe, 'data-dismiss-pending')
        self.assertContains(detalhe, 'data-pending-signature=')
        response = self.client.post(
            reverse(
                'fichas:resolver_pendencia',
                kwargs={'pk': self.ficha.pk, 'pendencia_pk': atributo.pk},
            ),
            {'atributo': 'agilidade'},
        )

        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.ficha.refresh_from_db()
        atributo.refresh_from_db()
        self.assertEqual(self.ficha.agilidade, 2)
        self.assertTrue(atributo.resolvida)
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=self.ficha, campo='atributo.agilidade', valor_antigo='1', valor_novo='2',
        ).exists())

        treinamento = Pendencia.objects.create(
            ficha=self.ficha, tipo='treinamento', descricao='Aprimorar 2 perícias.',
            fonte='OPRPG p.25', quantidade=2,
        )
        response = self.client.post(
            reverse(
                'fichas:resolver_pendencia',
                kwargs={'pk': self.ficha.pk, 'pendencia_pk': treinamento.pk},
            ),
            {'pericias': [self.fortitude.pk, self.luta.pk]},
        )
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.assertTrue(Pendencia.objects.get(pk=treinamento.pk).resolvida)
        self.assertEqual(
            set(self.ficha.pericias.filter(grau='treinado').values_list('pericia_id', flat=True)),
            {self.fortitude.pk, self.luta.pk},
        )
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=self.ficha, campo='pericia.luta', valor_antigo='destreinado',
            valor_novo='treinado',
        ).exists())

    def test_legacy_track_skill_pending_is_hidden_and_resolved_automatically(self):
        trilha = Trilha.objects.create(
            nome='Trilha escolhida', slug='trilha-escolhida', fonte='SaH p.31',
            resumo='', classe=self.classe,
            habilidades=[{'nex': 10, 'nome': 'Primeira habilidade', 'resumo': 'Já automática.'}],
        )
        self.ficha.trilha = trilha
        self.ficha.nex = 10
        self.ficha.save(update_fields=('trilha', 'nex'))
        pendencia = Pendencia.objects.create(
            ficha=self.ficha, tipo='poder',
            descricao='Registrar a primeira habilidade da trilha.', fonte='SaH p.31',
        )
        self.client.force_login(self.owner)

        detalhe = self.client.get(reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.assertNotContains(detalhe, 'Registrar a primeira habilidade da trilha')
        resposta = self.client.post(reverse(
            'fichas:resolver_pendencia',
            kwargs={'pk': self.ficha.pk, 'pendencia_pk': pendencia.pk},
        ), {})

        self.assertRedirects(resposta, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.assertTrue(Pendencia.objects.get(pk=pendencia.pk).resolvida)

    def test_pending_catalog_power_and_track_choices_show_descriptions(self):
        self.client.force_login(self.owner)
        trilha_catalogada = Trilha.objects.create(
            nome='Linha de frente', slug='linha-de-frente', fonte='OPRPG p.26',
            resumo='Protege o grupo no combate.', classe=self.classe,
        )
        trilha = Pendencia.objects.create(
            ficha=self.ficha, tipo='trilha', descricao='Escolher trilha.',
            fonte='OPRPG p.25',
        )
        url_trilha = reverse(
            'fichas:resolver_pendencia',
            kwargs={'pk': self.ficha.pk, 'pendencia_pk': trilha.pk},
        )
        response = self.client.get(url_trilha)
        self.assertContains(response, 'Linha de frente')
        self.assertContains(response, 'Protege o grupo no combate.')
        self.assertContains(response, 'OPRPG p.26')
        response = self.client.post(
            url_trilha,
            {'trilha': trilha_catalogada.pk},
        )
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.ficha.refresh_from_db()
        self.assertEqual(self.ficha.trilha, trilha_catalogada)
        self.assertTrue(Pendencia.objects.get(pk=trilha.pk).resolvida)

        poder_catalogado = Poder.objects.create(
            nome='Poder de apoio', slug='poder-de-apoio', fonte='OPRPG p.25',
            resumo='Uma habilidade catalogada para o agente.', tipo='geral',
        )
        poder = Pendencia.objects.create(
            ficha=self.ficha, tipo='poder', descricao='Escolher poder.',
            fonte='OPRPG p.25',
        )
        url_poder = reverse(
            'fichas:resolver_pendencia',
            kwargs={'pk': self.ficha.pk, 'pendencia_pk': poder.pk},
        )
        response = self.client.get(url_poder)
        self.assertContains(response, 'Poder de apoio')
        self.assertContains(response, 'Uma habilidade catalogada para o agente.')
        self.assertNotContains(response, 'Resumo mecânico curto')
        response = self.client.post(
            url_poder,
            {'nome_personalizado': 'Poder próprio', 'resumo_personalizado': 'Efeito mecânico breve.'},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(FichaPoder.objects.filter(ficha=self.ficha).exists())
        response = self.client.post(url_poder, {'poder': poder_catalogado.pk})
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.assertEqual(FichaPoder.objects.get(ficha=self.ficha).poder, poder_catalogado)
        self.assertTrue(Pendencia.objects.get(pk=poder.pk).resolvida)

        ritual = Pendencia.objects.create(
            ficha=self.ficha, tipo='ritual', descricao='Aprender ritual.',
            fonte='OPRPG p.33',
        )
        response = self.client.post(
            reverse(
                'fichas:resolver_pendencia',
                kwargs={'pk': self.ficha.pk, 'pendencia_pk': ritual.pk},
            ),
            {'nome_personalizado': 'Ritual próprio', 'resumo_personalizado': 'Efeito curto.'},
        )
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.assertEqual(FichaRitual.objects.get(ficha=self.ficha).nome_personalizado, 'Ritual próprio')
        self.assertTrue(Pendencia.objects.get(pk=ritual.pk).resolvida)

    def test_power_catalog_prerequisites_are_validated_for_current_sheet(self):
        self.ficha.intelecto = 3
        self.ficha.save(update_fields=('intelecto',))
        FichaPericia.objects.create(ficha=self.ficha, pericia=self.luta, grau='treinado')
        available = Poder.objects.create(
            nome='Poder elegível',
            slug='poder-elegivel',
            fonte='Personalizado',
            resumo='',
            tipo='geral',
            pre_requisitos={
                'classe_slug': 'combatente',
                'nex_min': 5,
                'atributos_min': {'intelecto': 3},
                'pericias_treinadas': ['luta'],
            },
        )
        unavailable = Poder.objects.create(
            nome='Poder indisponível',
            slug='poder-indisponivel',
            fonte='Personalizado',
            resumo='',
            tipo='geral',
            pre_requisitos={'nex_min': 10},
        )
        pending = Pendencia.objects.create(
            ficha=self.ficha, tipo='poder', descricao='Escolher poder.',
            fonte='Personalizado',
        )
        self.client.force_login(self.owner)
        url = reverse(
            'fichas:resolver_pendencia',
            kwargs={'pk': self.ficha.pk, 'pendencia_pk': pending.pk},
        )

        response = self.client.get(url)
        self.assertContains(response, available.nome)
        self.assertNotContains(response, unavailable.nome)
        response = self.client.post(url, {'poder': unavailable.pk})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(FichaPoder.objects.filter(ficha=self.ficha).exists())
        self.assertFalse(Pendencia.objects.get(pk=pending.pk).resolvida)

        response = self.client.post(url, {'poder': available.pk})
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.assertEqual(FichaPoder.objects.get(ficha=self.ficha).poder, available)
        self.assertTrue(Pendencia.objects.get(pk=pending.pk).resolvida)

    def test_power_prerequisite_schema_rejects_unknown_fields_and_boolean_numbers(self):
        poder = Poder(
            nome='Poder inválido',
            slug='poder-invalido',
            fonte='Personalizado',
            resumo='',
            tipo='geral',
            pre_requisitos={'nex_min': True, 'campo_desconhecido': 'valor'},
        )
        with self.assertRaises(ValidationError):
            poder.full_clean()

    def test_learning_ritual_in_experience_mode_increases_exposure_by_circle(self):
        mesa = ConfiguracaoMesa.objects.create(sistema_progressao='nivel_nex')
        ocultista = Classe.objects.create(
            nome='Ocultista', slug='ocultista', fonte='OPRPG', resumo='',
        )
        self.ficha.classe = ocultista
        self.ficha.nex = 0
        self.ficha.nivel_experiencia = 1
        self.ficha.save(update_fields=('classe', 'nex', 'nivel_experiencia'))
        ritual = Pendencia.objects.create(
            ficha=self.ficha, tipo='ritual', descricao='Aprender ritual.',
            fonte='SaH p.99',
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse(
                'fichas:resolver_pendencia',
                kwargs={'pk': self.ficha.pk, 'pendencia_pk': ritual.pk},
            ),
            {
                'nome_personalizado': 'Ritual próprio',
                'resumo_personalizado': 'Efeito mecânico curto.',
                'circulo_personalizado': '2',
            },
        )
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.ficha.refresh_from_db()
        self.assertEqual((self.ficha.nex, self.ficha.nivel_experiencia), (2, 1))
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=self.ficha, campo='nex_ritual',
            valor_novo='2; ritual de 2º círculo',
        ).exists())
        self.assertEqual(mesa.sistema_progressao, 'nivel_nex')

    def test_physical_roll_endpoint_persists_result_and_checks_training(self):
        self.client.force_login(self.owner)
        FichaPericia.objects.create(ficha=self.ficha, pericia=self.luta, grau='treinado')
        roll_url = reverse('fichas:rolar', kwargs={'pk': self.ficha.pk})

        response = self.client.post(
            roll_url,
            data='{"tipo":"pericia","alvo":%d,"bonus":0,"dados_extras":0,"dados_fisicos":[12],"dt":17}'
            % self.luta.pk,
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            (response.json()['dados'], response.json()['bonus'], response.json()['total'],
             response.json()['dt'], response.json()['sucesso']),
            ([12], 5, 17, 17, True),
        )
        self.assertTrue(Rolagem.objects.filter(
            ficha=self.ficha, tipo='pericia', total=17, dado_escolhido=12,
        ).exists())

        pilotagem = self._pericia('pilotagem', 'agilidade')
        pilotagem.somente_treinada = True
        pilotagem.save(update_fields=('somente_treinada',))
        response = self.client.post(
            roll_url,
            data='{"tipo":"pericia","alvo":%d,"bonus":0,"dados_fisicos":[12]}'
            % pilotagem.pk,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_pv_damage_consumes_overflow_before_base_and_clamps_at_zero(self):
        self.client.force_login(self.owner)
        self.ficha.pv_atual = 5
        self.ficha.save(update_fields=('pv_atual',))
        resource = reverse('fichas:recurso', kwargs={'pk': self.ficha.pk})

        response = self.client.post(
            resource, data='{"recurso":"pv","delta":-10}', content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            (response.json()['atual'], response.json()['temporario_aplicado'],
             response.json()['aplicado'], response.json()['sobrou']),
            (0, 0, -5, -5),
        )
        self.ficha.refresh_from_db()
        self.assertEqual(self.ficha.pv_atual, 0)
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=self.ficha, campo='pv_atual', valor_antigo='5', valor_novo='0',
        ).exists())

        maximo = calcular_pv_max('combatente', self.ficha.vigor, self.ficha.nex)
        self.ficha.pv_atual = maximo - 1
        self.ficha.save(update_fields=('pv_atual',))
        response = self.client.post(
            resource, data='{"recurso":"pv","delta":10}', content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.json()['atual'], response.json()['aplicado'], response.json()['sobrou']),
                         (maximo + 9, 10, 0))
        self.ficha.pv_atual = maximo + 7
        self.ficha.save(update_fields=('pv_atual',))
        response = self.client.post(
            resource, data='{"recurso":"pv","delta":-1}', content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            (response.json()['atual'], response.json()['aplicado'],
             response.json()['sobrou'], response.json()['temporario_aplicado']),
            (maximo + 6, -1, 0, 1),
        )

    def test_inactive_sheets_are_read_only_for_owner_and_editable_by_master(self):
        condicao = Condicao.objects.create(
            nome='Abalado', slug='abalado', fonte='OPRPG', resumo='',
        )
        for status in ('arquivada', 'morta', 'aposentada'):
            with self.subTest(status=status):
                ficha = Ficha.objects.create(
                    dono=self.owner, nome=f'Ficha {status}', classe=self.classe,
                    nex=5, pv_atual=10, status=status,
                )
                item = ItemInventario.objects.create(
                    ficha=ficha, nome='Lanterna', categoria='0',
                )
                self.client.force_login(self.owner)
                urls = (
                    (reverse('fichas:recurso', kwargs={'pk': ficha.pk}),
                     '{"recurso":"pv","delta":1}', 'application/json'),
                    (reverse('fichas:condicao', kwargs={'pk': ficha.pk}),
                     f'{{"acao":"adicionar","condicao":{condicao.pk}}}', 'application/json'),
                    (reverse('fichas:rolar', kwargs={'pk': ficha.pk}),
                     '{"tipo":"livre","alvo":1,"bonus":0}', 'application/json'),
                )
                for url, data, content_type in urls:
                    response = self.client.post(url, data=data, content_type=content_type)
                    self.assertEqual(response.status_code, 403)
                self.assertEqual(self.client.get(reverse('fichas:editar', kwargs={'pk': ficha.pk})).status_code, 403)
                self.assertEqual(self.client.post(reverse('fichas:editar', kwargs={'pk': ficha.pk})).status_code, 403)
                self.assertEqual(self.client.post(
                    reverse('fichas:avancar_nex', kwargs={'pk': ficha.pk}),
                    {'nex_novo': '10', 'versao': 1},
                ).status_code, 403)
                self.assertEqual(self.client.post(
                    reverse('fichas:adicionar_item', kwargs={'pk': ficha.pk}),
                    {'nome': 'Outro', 'categoria': '0', 'espacos': 1, 'quantidade': 1, 'estado': 'guardado'},
                ).status_code, 403)
                self.assertEqual(self.client.post(
                    reverse('fichas:atualizar_item', kwargs={'pk': ficha.pk, 'item_pk': item.pk}),
                    {'quantidade': 2, 'estado': 'guardado'},
                ).status_code, 403)
                self.assertEqual(self.client.post(
                    reverse('fichas:remover_item', kwargs={'pk': ficha.pk, 'item_pk': item.pk}),
                ).status_code, 403)
                self.assertNotContains(
                    self.client.get(reverse('fichas:detalhe', kwargs={'pk': ficha.pk})),
                    'data-resource="pv"',
                )
                self.assertFalse(FichaCondicao.objects.filter(ficha=ficha).exists())
                self.assertEqual(ItemInventario.objects.filter(ficha=ficha).count(), 1)

                self.client.force_login(self.master)
                response = self.client.post(
                    reverse('fichas:recurso', kwargs={'pk': ficha.pk}),
                    data='{"recurso":"pv","delta":1}', content_type='application/json',
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(LogAlteracao.objects.filter(
                    ficha=ficha, usuario=self.master, campo='pv_atual',
                ).exists())
                self.assertEqual(self.client.post(
                    reverse('fichas:condicao', kwargs={'pk': ficha.pk}),
                    data=f'{{"acao":"adicionar","condicao":{condicao.pk}}}',
                    content_type='application/json',
                ).status_code, 200)

    def test_csrf_token_is_available_in_meta_and_cookie_stays_httponly(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))

        self.assertContains(response, '<meta name="csrf-token" content="')
        self.assertTrue(response.cookies['csrftoken']['httponly'])

    def test_player_detail_shows_simple_digital_roll_ui_but_hides_master_notes(self):
        self.client.force_login(self.owner)
        condicao = Condicao.objects.create(
            nome='Temporária', slug='temporaria', fonte='Personalizado', resumo='',
        )
        FichaCondicao.objects.create(
            ficha=self.ficha, condicao=condicao, turnos_restantes=2,
        )

        response = self.client.get(reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))

        self.assertContains(response, 'Rolar teste')
        self.assertContains(response, 'Ajustes opcionais')
        self.assertContains(response, 'data-roll-result')
        self.assertContains(response, 'data-damage-form')
        self.assertNotContains(response, 'damage-critical-multiplier')
        self.assertContains(response, '<section class="roll-panel sheet-roll-panel roll-advanced-panel"')
        self.assertContains(response, 'href="#anotacoes"')
        self.assertContains(response, 'id="anotacoes"')
        self.assertContains(response, 'class="attribute-roll-card defense-card"')
        self.assertNotContains(response, 'Dados físicos (principal)')
        self.assertNotContains(response, 'Resultados dos dados físicos')
        self.assertContains(response, 'data-attribute-value="1"')
        self.assertContains(response, 'id="condition-turns"')
        self.assertContains(response, 'Turnos restantes: 2.')
        self.assertNotContains(response, 'segredo do mestre')
        self.client.force_login(self.master)
        response = self.client.get(reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.assertContains(response, 'segredo do mestre')

    def test_sheet_overview_shows_progression_prestige_movement_and_table(self):
        mesa = Mesa.objects.create(
            mestre=self.master, nome='Arquivo Central', publica=True,
        )
        InscricaoMesa.objects.create(mesa=mesa, ficha=self.ficha)
        self.ficha.deslocamento_bonus = 3
        self.ficha.pontos_prestigio = 12
        self.ficha.save(update_fields=('deslocamento_bonus', 'pontos_prestigio'))
        self.client.force_login(self.owner)

        response = self.client.get(reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))

        self.assertContains(response, 'NEX 5%')
        self.assertContains(response, '12')
        self.assertContains(response, '12 m')
        self.assertContains(response, mesa.nome)

    def test_owner_and_master_can_manage_custom_sheet_abilities(self):
        add_url = reverse('fichas:adicionar_habilidade', kwargs={'pk': self.ficha.pk})
        self.client.force_login(self.owner)
        response = self.client.post(add_url, {
            'nome': 'Reflexos rápidos', 'descricao': 'Uma habilidade personalizada.',
        })
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        habilidade = HabilidadeFicha.objects.get(ficha=self.ficha)
        self.assertEqual(habilidade.criada_por, self.owner)
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=self.ficha, campo='habilidade.adicionada', valor_novo=habilidade.nome,
        ).exists())
        response = self.client.post(reverse(
            'fichas:editar_habilidade',
            kwargs={'pk': self.ficha.pk, 'habilidade_pk': habilidade.pk},
        ), {
            'nome': 'Reflexos treinados', 'descricao': 'Texto atualizado.',
        })
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        habilidade.refresh_from_db()
        self.assertEqual((habilidade.nome, habilidade.descricao), (
            'Reflexos treinados', 'Texto atualizado.',
        ))
        self.assertContains(
            self.client.get(reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk})),
            'Texto atualizado.',
        )

        self.client.force_login(self.other)
        self.assertEqual(self.client.post(add_url, {
            'nome': 'Não autorizada', 'descricao': 'Outro usuário.',
        }).status_code, 404)

        self.client.force_login(self.master)
        response = self.client.post(add_url, {
            'nome': 'Ordem do mestre', 'descricao': 'Incluída pelo mestre.',
        })
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        habilidade_mestre = HabilidadeFicha.objects.get(nome='Ordem do mestre')
        self.assertEqual(habilidade_mestre.criada_por, self.master)
        self.assertEqual(self.client.post(reverse(
            'fichas:remover_habilidade',
            kwargs={'pk': self.ficha.pk, 'habilidade_pk': habilidade_mestre.pk},
        )).status_code, 302)
        self.assertFalse(HabilidadeFicha.objects.filter(pk=habilidade_mestre.pk).exists())

    def test_unified_ability_form_creates_custom_ability_or_catalog_power(self):
        poder = Poder.objects.create(
            nome='Poder selecionável', slug='poder-selecionavel',
            fonte='OPRPG p.25', resumo='Descrição original.', tipo='geral',
        )
        url = reverse('fichas:adicionar_habilidade', kwargs={'pk': self.ficha.pk})
        self.client.force_login(self.owner)
        response = self.client.get(reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.assertContains(response, 'Habilidade ou poder')
        self.assertContains(response, 'data-power-name="Poder selecionável"')

        response = self.client.post(url, {
            'poder': '', 'nome_personalizado': 'Habilidade própria',
            'resumo_personalizado': 'Descrição própria.',
        })

        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        habilidade = HabilidadeFicha.objects.get(ficha=self.ficha)
        self.assertEqual((habilidade.nome, habilidade.descricao), (
            'Habilidade própria', 'Descrição própria.',
        ))

        response = self.client.post(url, {
            'poder': poder.pk,
            'nome_personalizado': 'Poder editado',
            'resumo_personalizado': 'Descrição editada.',
        })

        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        ficha_poder = FichaPoder.objects.get(ficha=self.ficha, poder=poder)
        self.assertEqual((ficha_poder.nome_personalizado, ficha_poder.resumo_personalizado), (
            'Poder editado', 'Descrição editada.',
        ))

    def test_owner_can_manage_catalog_and_placeholder_powers_and_rituals(self):
        poder = Poder.objects.create(
            nome='Poder de catálogo', slug='poder-ficha-catalogo',
            fonte='OPRPG p.25', resumo='Resumo do catálogo.', tipo='geral',
        )
        ritual = Ritual.objects.create(
            nome='Ritual de catálogo', slug='ritual-ficha-catalogo',
            fonte='OPRPG p.120', resumo='Resumo do ritual.', circulo=1,
            elemento='energia', execucao='Padrão', alcance='Curto',
            alvo_area='1 ser', duracao='Instantânea', custo='1 PE',
        )
        self.client.force_login(self.owner)
        response = self.client.get(reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.assertContains(response, 'Adicionar')
        self.assertContains(response, 'Poder do catálogo')
        self.assertContains(response, 'Ritual de catálogo')

        url_poder = reverse('fichas:adicionar_poder_ficha', kwargs={'pk': self.ficha.pk})
        poder_bloqueado = Poder.objects.create(
            nome='Poder bloqueado', slug='poder-ficha-bloqueado',
            fonte='OPRPG p.25', resumo='Requer progressão maior.', tipo='geral',
            pre_requisitos={'nex_min': 10},
        )
        response = self.client.post(url_poder, {'poder': poder_bloqueado.pk})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(FichaPoder.objects.filter(ficha=self.ficha).exists())

        response = self.client.post(url_poder, {'poder': poder.pk})
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        ficha_poder = FichaPoder.objects.get(ficha=self.ficha)
        self.assertEqual(ficha_poder.poder, poder)

        response = self.client.post(
            reverse('fichas:editar_poder_ficha', kwargs={
                'pk': self.ficha.pk, 'poder_pk': ficha_poder.pk,
            }),
            {'poder': poder.pk, 'resumo_personalizado': 'Anotação da ficha.'},
        )
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        ficha_poder.refresh_from_db()
        self.assertEqual(ficha_poder.resumo_personalizado, 'Anotação da ficha.')

        response = self.client.post(url_poder, {
            'poder': '', 'nome_personalizado': 'Poder próprio',
            'resumo_personalizado': 'Efeito por definir.',
        })
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        poder_personalizado = FichaPoder.objects.get(nome_personalizado='Poder próprio')
        self.assertIsNone(poder_personalizado.poder_id)

        url_ritual = reverse('fichas:adicionar_ritual_ficha', kwargs={'pk': self.ficha.pk})
        response = self.client.post(url_ritual, {'ritual': ritual.pk})
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        ficha_ritual = FichaRitual.objects.get(ficha=self.ficha, ritual=ritual)
        response = self.client.post(url_ritual, {
            'ritual': '', 'nome_personalizado': 'Ritual placeholder',
            'resumo_personalizado': 'Resumo pendente de catálogo.',
        })
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        placeholder = FichaRitual.objects.get(nome_personalizado='Ritual placeholder')
        self.assertIsNone(placeholder.ritual_id)

        response = self.client.post(reverse('fichas:editar_ritual_ficha', kwargs={
            'pk': self.ficha.pk, 'ritual_pk': ficha_ritual.pk,
        }), {'ritual': ritual.pk, 'resumo_personalizado': 'Nota de preparação.'})
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        ficha_ritual.refresh_from_db()
        self.assertEqual(ficha_ritual.resumo_personalizado, 'Nota de preparação.')
        self.assertEqual(self.client.post(reverse(
            'fichas:remover_ritual_ficha',
            kwargs={'pk': self.ficha.pk, 'ritual_pk': placeholder.pk},
        )).status_code, 302)
        self.assertFalse(FichaRitual.objects.filter(pk=placeholder.pk).exists())

    def test_catalog_power_form_accepts_autofilled_name_and_description(self):
        poder = Poder.objects.create(
            nome='Poder de catálogo', slug='poder-ficha-autofill',
            fonte='OPRPG p.25', resumo='Resumo do catálogo.', tipo='geral',
        )
        self.client.force_login(self.owner)

        response = self.client.post(reverse('fichas:adicionar_poder_ficha', kwargs={'pk': self.ficha.pk}), {
            'poder': poder.pk,
            'nome_personalizado': poder.nome,
            'resumo_personalizado': poder.resumo,
        })

        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.assertEqual(FichaPoder.objects.get(ficha=self.ficha).poder, poder)

    def test_owner_can_delete_sheet_and_remove_its_combat_participant(self):
        outra_ficha = Ficha.objects.create(dono=self.other, nome='Outro agente', nex=5)
        encontro = EncontroCombate.objects.create(criado_por=self.master, nome='Combate ativo')
        participante_ficha = ParticipanteCombate.objects.create(
            encontro=encontro, ficha=self.ficha, nome=self.ficha.nome, iniciativa=20,
        )
        ParticipanteCombate.objects.create(
            encontro=encontro, ficha=outra_ficha, nome=outra_ficha.nome, iniciativa=10,
        )
        encontro.indice_turno = 0
        encontro.save(update_fields=('indice_turno',))
        excluir_url = reverse('fichas:excluir', kwargs={'pk': self.ficha.pk})

        self.client.force_login(self.other)
        self.assertEqual(self.client.post(excluir_url).status_code, 404)
        self.assertTrue(Ficha.objects.filter(pk=self.ficha.pk).exists())

        self.client.force_login(self.owner)
        response = self.client.get(excluir_url)
        self.assertEqual(response.status_code, 405)
        response = self.client.post(excluir_url)
        self.assertRedirects(response, reverse('home'))
        self.assertFalse(Ficha.objects.filter(pk=self.ficha.pk).exists())
        self.assertFalse(ParticipanteCombate.objects.filter(pk=participante_ficha.pk).exists())
        encontro.refresh_from_db()
        self.assertEqual(encontro.indice_turno, -1)

    def test_digital_roll_can_compare_result_with_difficulty(self):
        self.client.force_login(self.owner)
        with patch('fichas.regras.secrets.SystemRandom', return_value=FixedDice([12])):
            response = self.client.post(
                reverse('fichas:rolar', kwargs={'pk': self.ficha.pk}),
                data=json.dumps({
                    'tipo': 'atributo', 'alvo': 'agilidade', 'bonus': 0, 'dt': 12,
                }),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            (response.json()['dados'], response.json()['total'],
             response.json()['dt'], response.json()['sucesso']),
            ([12], 12, 12, True),
        )

    def test_polling_endpoint_is_scoped_and_excludes_private_notes_and_hidden_resources(self):
        condicao = Condicao.objects.create(
            nome='Abalado', slug='abalado-poll', fonte='OPRPG p. 40', resumo='',
        )
        FichaCondicao.objects.create(
            ficha=self.ficha, condicao=condicao, anotacao='nota que não deve ir ao JSON',
        )
        self.client.force_login(self.owner)
        url = reverse('fichas:atualizacoes', kwargs={'pk': self.ficha.pk})

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['recursos'].keys(), {'pv', 'pe', 'san'})
        self.assertEqual(response.json()['maximos'].keys(), {'pv', 'pe', 'san'})
        self.assertEqual(response.json()['condicoes'], [{
            'id': condicao.pk,
            'nome': 'Abalado',
            'resumo': condicao.resumo,
            'turnos_restantes': None,
            'proxima_escalada': None,
        }])
        self.assertNotIn('anotacao', response.json())
        self.assertNotContains(response, 'nota que não deve ir ao JSON')
        self.assertNotContains(response, 'segredo do mestre')
        self.assertEqual(
            self.client.get(reverse('fichas:atualizacoes', kwargs={'pk': 999999})).status_code,
            404,
        )

        ConfiguracaoMesa.objects.create(modo_recursos='sem_sanidade')
        response = self.client.get(url)
        self.assertEqual(response.json()['recursos'].keys(), {'pv', 'pd'})
        self.assertEqual(response.json()['maximos'].keys(), {'pv', 'pd'})
        self.assertNotIn('san', response.json()['recursos'])
        self.assertEqual(response.json()['modo_recursos'], 'sem_sanidade')

    def test_all_requested_write_views_have_per_user_rate_limits(self):
        self.client.force_login(self.master)
        item = ItemInventario.objects.create(ficha=self.ficha, nome='Lanterna', categoria='0')
        dados_requisicoes = (
            (reverse('fichas:adicionar_item', kwargs={'pk': self.ficha.pk}), {}),
            (reverse('fichas:atualizar_item', kwargs={'pk': self.ficha.pk, 'item_pk': item.pk}), {}),
            (reverse('fichas:remover_item', kwargs={'pk': self.ficha.pk, 'item_pk': item.pk}), {}),
            (reverse('fichas:status', kwargs={'pk': self.ficha.pk}), {'status': 'morta'}),
            (reverse('fichas:avancar_nex', kwargs={'pk': self.ficha.pk}), {}),
            (reverse('fichas:editar', kwargs={'pk': self.ficha.pk}), {}),
            (reverse('fichas:configurar_mesa'), {}),
            (reverse('fichas:gerenciar_ferimento', kwargs={'pk': self.ficha.pk}),
             {'acao': 'registrar', 'atributo': 'superficial'}),
        )
        for url, dados in dados_requisicoes:
            with self.subTest(url=url):
                cache.clear()
                with patch('django_ratelimit.core.time.time', return_value=1_700_000_000):
                    respostas = [self.client.post(url, dados) for _ in range(31)]
                self.assertEqual(respostas[-1].status_code, 403)

    def test_json_endpoints_enforce_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        response = csrf_client.post(
            reverse('fichas:recurso', kwargs={'pk': self.ficha.pk}),
            data='{"recurso":"pv","delta":1}', content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_inventory_add_update_delete_and_capacity(self):
        self.client.force_login(self.owner)
        add_url = reverse('fichas:adicionar_item', kwargs={'pk': self.ficha.pk})
        response = self.client.post(add_url, {
            'nome': 'Kit de campo', 'categoria': 'I', 'espacos': 2,
            'quantidade': 3, 'estado': 'guardado', 'notas': 'nota privada',
            'dono': self.other.pk, 'ficha': self.ficha.pk + 100,
        })
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        item = ItemInventario.objects.get(ficha=self.ficha)
        self.assertEqual((item.nome, item.quantidade, item.ficha_id), ('Kit de campo', 3, self.ficha.pk))
        self.assertEqual(espacos_usados(list(self.ficha.inventario.all())), 6)
        self.assertFalse(LogAlteracao.objects.filter(valor_novo='nota privada').exists())
        self.assertContains(self.client.get(reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk})), 'Carga excedida')

        response = self.client.post(
            reverse('fichas:atualizar_item', kwargs={'pk': self.ficha.pk, 'item_pk': item.pk}),
            {'quantidade': 2, 'estado': 'empunhado'},
        )
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        item.refresh_from_db()
        self.assertEqual((item.quantidade, item.estado), (2, 'empunhado'))
        self.assertEqual(espacos_usados(list(self.ficha.inventario.all())), 4)

        response = self.client.post(
            reverse('fichas:remover_item', kwargs={'pk': self.ficha.pk, 'item_pk': item.pk}),
        )
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.assertFalse(ItemInventario.objects.filter(pk=item.pk).exists())

    def test_inventory_is_scoped_and_rejects_invalid_values(self):
        item = ItemInventario.objects.create(
            ficha=self.ficha, nome='Lanterna', categoria='0', espacos=1, quantidade=1,
        )
        self.client.force_login(self.other)
        response = self.client.post(reverse('fichas:remover_item', kwargs={
            'pk': self.ficha.pk, 'item_pk': item.pk,
        }))
        self.assertEqual(response.status_code, 404)

        self.client.force_login(self.owner)
        response = self.client.post(reverse('fichas:adicionar_item', kwargs={'pk': self.ficha.pk}), {
            'nome': 'Item inválido', 'categoria': 'V', 'espacos': -1,
            'quantidade': 0, 'estado': 'voando',
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ItemInventario.objects.filter(ficha=self.ficha).count(), 1)


    def test_active_limit_is_enforced_and_archiving_frees_a_slot(self):
        ConfiguracaoMesa.objects.create(max_fichas_ativas=1)
        self.client.force_login(self.owner)
        response = self.client.get(reverse('fichas:iniciar'))
        self.assertRedirects(response, reverse('home'))
        self.assertNotIn('fichas.criacao', self.client.session)

        response = self.client.post(reverse('fichas:status', kwargs={'pk': self.ficha.pk}), {
            'status': 'arquivada', 'versao': 1,
        })
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.ficha.refresh_from_db()
        self.assertEqual((self.ficha.status, self.ficha.versao), ('arquivada', 2))
        response = self.client.get(reverse('fichas:iniciar'))
        self.assertRedirects(response, reverse('fichas:criar', kwargs={'etapa': 1}))

        response = self.client.post(reverse('fichas:status', kwargs={'pk': self.ficha.pk}), {
            'status': 'ativa', 'versao': 1,
        })
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.ficha.refresh_from_db()
        self.assertEqual(self.ficha.status, 'arquivada')

    def test_restore_cannot_exceed_active_limit_and_foreign_status_is_hidden(self):
        ConfiguracaoMesa.objects.create(max_fichas_ativas=1)
        arquivada = Ficha.objects.create(
            dono=self.owner, nome='Arquivada', nex=5, status='arquivada',
        )
        self.client.force_login(self.owner)
        response = self.client.post(reverse('fichas:status', kwargs={'pk': arquivada.pk}), {
            'status': 'ativa', 'versao': 1,
        })
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': arquivada.pk}))
        arquivada.refresh_from_db()
        self.assertEqual(arquivada.status, 'arquivada')

        self.client.force_login(self.other)
        response = self.client.post(reverse('fichas:status', kwargs={'pk': self.ficha.pk}), {
            'status': 'arquivada', 'versao': 1,
        })
        self.assertEqual(response.status_code, 404)

    def test_creation_rechecks_active_limit_at_final_submission(self):
        ConfiguracaoMesa.objects.create(max_fichas_ativas=2)
        self.client.force_login(self.owner)
        self.client.get(reverse('fichas:iniciar'))
        Ficha.objects.create(dono=self.owner, nome='Criada em outra sessão', nex=5)

        response = self.client.post(reverse('fichas:criar', kwargs={'etapa': 1}), {
            'nome': 'Nova agente', 'conceito': 'Investigadora', 'aparencia': 'Casaco',
            'personalidade': 'Atenta', 'historia': 'Chegou à Ordem.', 'objetivo': 'Investigar',
            'nex_inicial': '5', 'origem': self.origem.pk, 'classe': self.classe.pk,
            'agilidade': 3, 'forca': 2, 'intelecto': 0, 'presenca': 1, 'vigor': 3,
            'pericias_escolhidas': [self.luta.pk, self.pontaria.pk],
            'confirmar': 'on',
            f'grau_pericia_{self.fortitude.pk}': 'treinado',
            f'grau_pericia_{self.luta.pk}': 'treinado',
            f'grau_pericia_{self.pontaria.pk}': 'treinado',
        })
        self.assertRedirects(response, reverse('home'))
        self.assertFalse(Ficha.objects.filter(dono=self.owner, nome='Nova agente').exists())
        self.assertNotIn('fichas.criacao', self.client.session)


class ConfiguracaoMesaViewsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='settings-owner', password=get_random_string(32))
        self.master = User.objects.create_superuser(
            username='settings-master', email='settings-master@example.com', password=get_random_string(32)
        )

    def test_configuration_is_master_only_and_accepts_supported_fields(self):
        url = reverse('fichas:configurar_mesa')
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(url).status_code, 403)

        self.client.force_login(self.master)
        self.assertRedirects(
            self.client.get(url), f'{reverse("painel_mestre")}#configuracao',
        )
        response = self.client.post(url, {
            'modo_recursos': 'sem_sanidade', 'jogador_pode_subir_nex': 'on',
            'max_fichas_ativas': 2, 'sistema_progressao': 'nivel_nex',
            'ferimentos_debilitantes': 'on', 'dono': self.owner.pk,
        })
        self.assertRedirects(
            response, f'{reverse("painel_mestre")}#configuracao',
        )
        mesa = ConfiguracaoMesa.objects.get(pk=1)
        self.assertEqual((mesa.modo_recursos, mesa.jogador_pode_subir_nex, mesa.max_fichas_ativas),
                         ('sem_sanidade', True, 2))
        self.assertEqual(mesa.sistema_progressao, 'nivel_nex')
        self.assertTrue(mesa.ferimentos_debilitantes)

    def test_enabling_debilitating_wounds_preserves_pv_over_maximum(self):
        classe = Classe.objects.create(
            nome='Combatente', slug='combatente', fonte='OPRPG', resumo='',
        )
        ficha = Ficha.objects.create(
            dono=self.owner, nome='Ferida', classe=classe, nex=5, pv_atual=21,
        )
        FerimentoDebilitante.objects.create(ficha=ficha, atributo='vigor')
        self.client.force_login(self.master)
        response = self.client.post(reverse('fichas:configurar_mesa'), {
            'modo_recursos': 'padrao',
            'sistema_progressao': 'nex',
            'max_fichas_ativas': 3,
            'ferimentos_debilitantes': 'on',
        })
        self.assertRedirects(
            response, f'{reverse("painel_mestre")}#configuracao',
        )
        ficha.refresh_from_db()
        self.assertEqual((ficha.pv_atual, ficha.versao), (21, 1))
        self.assertFalse(LogAlteracao.objects.filter(
            ficha=ficha, campo='pv_atual', valor_antigo='21', valor_novo='20',
        ).exists())


class ConfiguracaoFichaViewsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='solo-owner', password=get_random_string(32),
        )
        self.classe = Classe.objects.create(
            nome='Combatente', slug='combatente', fonte='OPRPG', resumo='',
            pv_base=20, pv_por_nex=4, pe_base=2, pe_por_nex=2,
            san_base=12, san_por_nex=3, pd_base=6, pd_por_nex=3,
        )
        self.ficha = Ficha.objects.create(
            dono=self.owner, nome='Ficha solo', classe=self.classe, nex=5,
            pv_atual=24, pe_atual=4, san_atual=15,
        )
        ConfiguracaoFicha.objects.create(ficha=self.ficha)
        Patente.objects.create(
            nome='Recruta', slug='recruta', fonte='SaH p.108', resumo='',
            credito='I', limite_pd=1, recuperacao=1,
        )
        self.client.force_login(self.owner)

    def test_owner_can_configure_an_unlinked_sheet(self):
        url = reverse('fichas:configurar_ficha', kwargs={'pk': self.ficha.pk})
        detalhe = self.client.get(reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.assertContains(detalhe, 'Configuração da ficha')
        self.assertContains(detalhe, 'href="#progressao"')
        self.assertContains(detalhe, 'id="progressao"')
        self.assertContains(detalhe, 'Sistema de progressão')
        response = self.client.post(url, {
            'versao': self.ficha.versao,
            'modo_recursos': 'sem_sanidade',
            'sistema_progressao': 'patentes',
            'ferimentos_debilitantes': 'on',
            'jogador_pode_subir_nex': 'on',
            'numero_sessao': 2,
        })
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        configuracao = ConfiguracaoFicha.objects.get(ficha=self.ficha)
        self.assertEqual(
            (configuracao.modo_recursos, configuracao.sistema_progressao,
             configuracao.numero_sessao),
            ('sem_sanidade', 'patentes', 2),
        )
        self.ficha.refresh_from_db()
        self.assertIsNone(self.ficha.nex)
        self.assertEqual(self.ficha.patente.slug, 'recruta')
        self.assertGreater(self.ficha.pd_atual, 0)

    def test_linked_sheet_configuration_is_controlled_by_its_table(self):
        mesa = Mesa.objects.create(
            mestre=self.owner, nome='Mesa da ficha', publica=True,
        )
        InscricaoMesa.objects.create(mesa=mesa, ficha=self.ficha)
        response = self.client.post(
            reverse('fichas:configurar_ficha', kwargs={'pk': self.ficha.pk}),
            {
                'versao': self.ficha.versao,
                'modo_recursos': 'sem_sanidade',
                'sistema_progressao': 'nex',
                'numero_sessao': 1,
            },
        )
        self.assertEqual(response.status_code, 403)


class ProgressaoNexViewsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='progress-owner', password=get_random_string(32))
        self.master = User.objects.create_superuser(
            username='progress-master', email='progress-master@example.com', password=get_random_string(32)
        )
        self.classe = Classe.objects.create(
            nome='Combatente', slug='combatente', fonte='OPRPG', resumo='',
        )
        self.ficha = Ficha.objects.create(dono=self.owner, nome='Agente', classe=self.classe, nex=5)

    def test_only_master_can_advance_when_player_option_is_disabled(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse('fichas:avancar_nex', kwargs={'pk': self.ficha.pk}), {
            'nex_novo': '20', 'versao': '1',
        })
        self.assertEqual(response.status_code, 403)
        self.ficha.refresh_from_db()
        self.assertEqual(self.ficha.nex, 5)
        self.assertFalse(Pendencia.objects.filter(ficha=self.ficha).exists())

    def test_master_advancement_updates_version_audit_and_milestone_choices_atomically(self):
        self.client.force_login(self.master)
        response = self.client.post(reverse('fichas:avancar_nex', kwargs={'pk': self.ficha.pk}), {
            'nex_novo': '20', 'versao': '1',
        })
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.ficha.refresh_from_db()
        self.assertEqual((self.ficha.nex, self.ficha.versao), (20, 2))
        self.assertEqual(
            list(self.ficha.pendencias.values_list('tipo', flat=True)),
            ['trilha', 'poder', 'atributo'],
        )
        self.assertTrue(LogAlteracao.objects.filter(ficha=self.ficha, campo='nex', valor_novo='20').exists())

        response = self.client.post(reverse('fichas:avancar_nex', kwargs={'pk': self.ficha.pk}), {
            'nex_novo': '25', 'versao': '1',
        })
        self.assertEqual(response.status_code, 409)
        self.ficha.refresh_from_db()
        self.assertEqual(self.ficha.nex, 20)

    def test_player_can_advance_only_when_table_allows_it(self):
        ConfiguracaoMesa.objects.create(jogador_pode_subir_nex=True)
        self.client.force_login(self.owner)
        response = self.client.post(reverse('fichas:avancar_nex', kwargs={'pk': self.ficha.pk}), {
            'nex_novo': '10', 'versao': '1',
        })
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.ficha.refresh_from_db()
        self.assertEqual(self.ficha.nex, 10)
        self.assertEqual(list(self.ficha.pendencias.values_list('tipo', flat=True)), ['trilha'])

    def test_survivor_cannot_use_nex_advancement(self):
        sobrevivente = Classe.objects.create(
            nome='Sobrevivente', slug='sobrevivente', fonte='SaH', resumo='',
        )
        ficha = Ficha.objects.create(
            dono=self.owner, nome='Sobrevivente', classe=sobrevivente, nex=None, estagio=1,
        )
        self.client.force_login(self.master)
        response = self.client.post(reverse('fichas:avancar_nex', kwargs={'pk': ficha.pk}), {
            'nex_novo': '10', 'versao': '1',
        })
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': ficha.pk}))
        ficha.refresh_from_db()
        self.assertIsNone(ficha.nex)
        self.assertEqual(ficha.estagio, 1)

    def test_nex_maximum_hides_advancement_form(self):
        self.ficha.nex = 99
        self.ficha.save(update_fields=('nex',))
        self.client.force_login(self.master)
        response = self.client.get(reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Avançar NEX')

    def test_master_advances_survivor_stage_with_audit_and_pending_choices(self):
        sobrevivente = Classe.objects.create(
            nome='Sobrevivente', slug='sobrevivente', fonte='SaH', resumo='',
        )
        ficha = Ficha.objects.create(
            dono=self.owner, nome='Sobrevivente', classe=sobrevivente, nex=None, estagio=1,
        )
        self.client.force_login(self.master)
        response = self.client.post(
            reverse('fichas:avancar_estagio', kwargs={'pk': ficha.pk}),
            {'estagio_novo': '3', 'versao': '1'},
        )
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': ficha.pk}))
        ficha.refresh_from_db()
        self.assertEqual((ficha.estagio, ficha.versao), (3, 2))
        self.assertEqual(
            list(ficha.pendencias.values_list('tipo', flat=True)),
            ['trilha', 'atributo'],
        )
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=ficha, campo='estagio', valor_antigo='1', valor_novo='3',
        ).exists())


class ProgressaoNivelViewsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(
            username='level-owner', email='level-owner@example.com', password=get_random_string(32),
        )
        self.master = User.objects.create_superuser(
            username='level-master', email='level-master@example.com', password=get_random_string(32),
        )
        self.classe = Classe.objects.create(
            nome='Combatente', slug='combatente', fonte='OPRPG', resumo='',
        )
        ConfiguracaoMesa.objects.create(sistema_progressao='nivel_nex')
        self.ficha = Ficha.objects.create(
            dono=self.owner, nome='Agente', classe=self.classe,
            nex=0, nivel_experiencia=1, vigor=1, pv_atual=21,
        )

    def test_master_advances_level_without_changing_exposure_and_creates_choices(self):
        self.client.force_login(self.master)
        response = self.client.post(
            reverse('fichas:avancar_nivel', kwargs={'pk': self.ficha.pk}),
            {'nivel_novo': '3', 'versao': '1'},
        )
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.ficha.refresh_from_db()
        self.assertEqual((self.ficha.nivel_experiencia, self.ficha.nex, self.ficha.versao), (3, 0, 2))
        self.assertEqual(
            list(self.ficha.pendencias.values_list('tipo', flat=True)),
            ['trilha', 'poder'],
        )
        self.assertEqual(self.client.get(
            reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk})
        ).context['maximos']['pv'], 31)
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=self.ficha, campo='nivel_experiencia', valor_novo='3',
        ).exists())

    def test_exposure_is_master_only_independent_and_limited_to_99_percent(self):
        url = reverse('fichas:registrar_exposicao', kwargs={'pk': self.ficha.pk})
        self.client.force_login(self.owner)
        response = self.client.post(url, {'exposicao': 'moderada', 'versao': '1'})
        self.assertEqual(response.status_code, 403)
        self.assertNotContains(
            self.client.get(reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk})),
            'Registrar exposição',
        )

        self.client.force_login(self.master)
        response = self.client.post(url, {'exposicao': 'moderada', 'versao': '1'})
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.ficha.refresh_from_db()
        self.assertEqual((self.ficha.nex, self.ficha.nivel_experiencia), (1, 1))
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=self.ficha, campo='nex_exposicao', valor_novo='1; moderada',
        ).exists())

        self.ficha.nex = 97
        self.ficha.versao += 1
        self.ficha.save(update_fields=('nex', 'versao'))
        response = self.client.post(url, {'exposicao': 'total', 'versao': self.ficha.versao})
        self.assertEqual(response.status_code, 400)
        self.ficha.refresh_from_db()
        self.assertEqual(self.ficha.nex, 97)

    def test_player_cannot_advance_level_when_table_requires_master(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('fichas:avancar_nivel', kwargs={'pk': self.ficha.pk}),
            {'nivel_novo': '2', 'versao': '1'},
        )
        self.assertEqual(response.status_code, 403)
        self.ficha.refresh_from_db()
        self.assertEqual(self.ficha.nivel_experiencia, 1)

    def test_progression_mode_change_converts_sheets_and_preserves_resource_excess(self):
        mesa = ConfiguracaoMesa.objects.get(pk=1)
        mesa.sistema_progressao = 'nex'
        mesa.save(update_fields=('sistema_progressao',))
        patente = Patente.objects.create(
            nome='Recruta independente', slug='recruta-independente', fonte='SaH',
            credito='Baixo', limite_pd=1, recuperacao=1,
        )
        self.ficha.nex = 20
        self.ficha.patente = patente
        self.ficha.pv_atual = 100
        self.ficha.save(update_fields=('nex', 'patente', 'pv_atual'))
        self.client.force_login(self.master)
        response = self.client.post(reverse('fichas:configurar_mesa'), {
            'modo_recursos': 'padrao', 'sistema_progressao': 'nivel_nex',
            'max_fichas_ativas': 3,
        })
        self.assertRedirects(
            response, f'{reverse("painel_mestre")}#configuracao',
        )
        mesa = ConfiguracaoMesa.objects.get(pk=1)
        self.assertEqual(mesa.sistema_progressao, 'nivel_nex')
        self.ficha.refresh_from_db()
        self.assertEqual(
            (self.ficha.nex, self.ficha.nivel_experiencia, self.ficha.patente,
             self.ficha.pv_atual, self.ficha.versao),
            (0, 4, patente, 100, 2),
        )
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=self.ficha, campo='configuracao.nivel_experiencia',
            valor_antigo='1', valor_novo='4',
        ).exists())

    def test_switching_to_patents_assigns_equivalent_rank_without_losing_prestige(self):
        ConfiguracaoMesa.objects.create(
            modo_recursos='padrao', sistema_progressao='nex',
        )
        recruta = Patente.objects.create(
            nome='Recruta', slug='recruta', fonte='SaH',
            pontos_prestigio=0, credito='Baixo', limite_pd=1, recuperacao=1,
        )
        operador = Patente.objects.create(
            nome='Operador', slug='operador', fonte='SaH',
            pontos_prestigio=20, credito='Médio', limite_pd=3, recuperacao=2,
        )
        self.ficha.nex = 30
        self.ficha.pontos_prestigio = 7
        self.ficha.pv_atual = 100
        self.ficha.save(update_fields=('nex', 'pontos_prestigio', 'pv_atual'))
        self.client.force_login(self.master)

        response = self.client.post(reverse('fichas:configurar_mesa'), {
            'modo_recursos': 'sem_sanidade', 'sistema_progressao': 'patentes',
            'max_fichas_ativas': 3,
        })

        self.assertRedirects(response, f'{reverse("painel_mestre")}#configuracao')
        self.ficha.refresh_from_db()
        self.assertEqual(
            (self.ficha.nex, self.ficha.nivel_experiencia, self.ficha.patente_id,
             self.ficha.pontos_prestigio, self.ficha.pv_atual),
            (None, None, operador.pk, 7, 100),
        )
        self.assertNotEqual(self.ficha.patente_id, recruta.pk)

    def test_stage_five_cicatrizado_choice_is_saved_and_used_once_per_session(self):
        sobrevivente = Classe.objects.create(
            nome='Sobrevivente', slug='sobrevivente', fonte='SaH', resumo='',
        )
        ficha = Ficha.objects.create(
            dono=self.owner, nome='Sobrevivente', classe=sobrevivente, nex=None, estagio=5,
        )
        pendencia = Pendencia.objects.create(
            ficha=ficha, tipo='cicatrizado', descricao='Escolha o perigo.',
            fonte='SaH p.31',
        )
        self.client.force_login(self.owner)
        url = reverse(
            'fichas:resolver_pendencia',
            kwargs={'pk': ficha.pk, 'pendencia_pk': pendencia.pk},
        )
        response = self.client.post(url, {
            'elemento': 'morte', 'perigo': 'Manifestação de Morte',
        })
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': ficha.pk}))
        ficha.refresh_from_db()
        self.assertEqual((ficha.cicatrizado_elemento, ficha.cicatrizado_perigo), (
            'morte', 'Manifestação de Morte',
        ))

        ConfiguracaoMesa.objects.create(modo_recursos='padrao')
        response = self.client.post(reverse('iniciar_nova_sessao'))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(ConfiguracaoMesa.objects.get().numero_sessao, 1)
        response = self.client.post(
            reverse('fichas:usar_cicatrizado', kwargs={'pk': ficha.pk}),
            {'efeito': 'ignorar_mental'},
        )
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': ficha.pk}))
        ficha.refresh_from_db()
        self.assertEqual(ficha.ajuste_pv_max, -1)
        self.assertEqual(ficha.cicatrizado_sessao_usada, 1)
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=ficha, campo='cicatrizado',
        ).exists())

        self.client.post(
            reverse('fichas:usar_cicatrizado', kwargs={'pk': ficha.pk}),
            {'efeito': 'ignorar_custo'},
        )
        ficha.refresh_from_db()
        self.assertEqual(ficha.ajuste_pv_max, -1)

        self.client.force_login(self.master)
        response = self.client.post(reverse('iniciar_nova_sessao'))
        self.assertRedirects(response, reverse('painel_mestre'))
        response = self.client.post(
            reverse('fichas:usar_cicatrizado', kwargs={'pk': ficha.pk}),
            {'efeito': 'reduzir_fisico', 'dano_fisico': 9},
        )
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': ficha.pk}))
        ficha.refresh_from_db()
        self.assertEqual(ficha.ajuste_pe_max, -1)
        self.assertEqual(ficha.cicatrizado_sessao_usada, 2)

    def test_player_cannot_advance_survivor_stage(self):
        sobrevivente = Classe.objects.create(
            nome='Sobrevivente', slug='sobrevivente', fonte='SaH', resumo='',
        )
        ficha = Ficha.objects.create(
            dono=self.owner, nome='Sobrevivente', classe=sobrevivente, nex=None, estagio=1,
        )
        ConfiguracaoMesa.objects.create(jogador_pode_subir_nex=True)
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('fichas:avancar_estagio', kwargs={'pk': ficha.pk}),
            {'estagio_novo': '2', 'versao': '1'},
        )
        self.assertEqual(response.status_code, 403)
        ficha.refresh_from_db()
        self.assertEqual(ficha.estagio, 1)
        self.assertFalse(Pendencia.objects.filter(ficha=ficha).exists())


class ProgressaoPatentesViewsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(
            username='patent-owner', password=get_random_string(32),
        )
        self.other = User.objects.create_user(
            username='patent-other', password=get_random_string(32),
        )
        self.master = User.objects.create_superuser(
            username='patent-master', email='patent-master@example.com',
            password=get_random_string(32),
        )
        self.classe = Classe.objects.create(
            nome='Combatente', slug='combatente', fonte='OPRPG', resumo='',
        )
        self.recruta = Patente.objects.create(
            nome='Recruta', slug='recruta', fonte='SaH p.108',
            pontos_prestigio=0, credito='Baixo', limite_pd=1, recuperacao=1,
        )
        self.operador = Patente.objects.create(
            nome='Operador', slug='operador', fonte='SaH p.108',
            pontos_prestigio=20, credito='Médio', limite_pd=3, recuperacao=2,
        )
        ConfiguracaoMesa.objects.create(
            modo_recursos='sem_sanidade', sistema_progressao='patentes',
        )
        self.ficha = Ficha.objects.create(
            dono=self.owner, nome='Agente', classe=self.classe,
            patente=self.recruta, nex=None, pontos_prestigio=15,
            vigor=1, presenca=1, pv_atual=21, pd_atual=7,
        )

    def test_master_scores_mission_promotes_and_awards_rank_benefits(self):
        self.client.force_login(self.master)
        payload = {
            'evento': 'solucao', 'quantidade': 1, 'versao': self.ficha.versao,
            'numero_sessao': 1,
        }
        url = reverse('fichas:registrar_prestigio', kwargs={'pk': self.ficha.pk})
        response = self.client.post(url, payload)

        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.ficha.refresh_from_db()
        self.assertEqual(
            (self.ficha.pontos_prestigio, self.ficha.patente, self.ficha.pv_atual, self.ficha.pd_atual),
            (25, self.operador, 31, 15),
        )
        self.assertEqual(
            list(self.ficha.pendencias.values_list('tipo', flat=True)),
            ['trilha', 'poder'],
        )
        registro = RegistroPrestigio.objects.get(ficha=self.ficha)
        self.assertEqual((registro.evento, registro.delta, registro.numero_sessao), ('solucao', 10, 1))
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=self.ficha, campo='patente', valor_novo='Operador',
        ).exists())

        response = self.client.post(url, {
            **payload, 'versao': self.ficha.versao,
        })
        self.assertEqual(response.status_code, 400)
        self.ficha.refresh_from_db()
        self.assertEqual(RegistroPrestigio.objects.filter(ficha=self.ficha).count(), 1)

    def test_player_cannot_record_prestige_and_ficha_remains_private(self):
        url = reverse('fichas:registrar_prestigio', kwargs={'pk': self.ficha.pk})
        payload = {
            'evento': 'inocente', 'quantidade': 1, 'versao': self.ficha.versao,
            'numero_sessao': 1,
        }
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(url, payload).status_code, 403)
        detalhe = self.client.get(reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.assertNotContains(detalhe, 'registrar-prestigio')
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url, payload).status_code, 404)
        self.assertEqual(RegistroPrestigio.objects.count(), 0)

    def test_owner_recovers_one_resource_by_current_patent(self):
        self.ficha.pv_atual = 18
        self.ficha.pd_atual = 6
        self.ficha.save(update_fields=('pv_atual', 'pd_atual'))
        self.client.force_login(self.owner)
        url = reverse('fichas:recuperar_patente', kwargs={'pk': self.ficha.pk})
        response = self.client.post(url, {
            'recurso': 'pv_atual', 'versao': self.ficha.versao,
        })

        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': self.ficha.pk}))
        self.ficha.refresh_from_db()
        self.assertEqual((self.ficha.pv_atual, self.ficha.pd_atual), (19, 6))
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=self.ficha, campo='pv_atual', valor_antigo='18', valor_novo='19',
        ).exists())

    def test_only_three_additional_clues_are_awarded_per_mission(self):
        self.client.force_login(self.master)
        url = reverse('fichas:registrar_prestigio', kwargs={'pk': self.ficha.pk})
        for _ in range(3):
            response = self.client.post(url, {
                'evento': 'pista', 'quantidade': 1, 'versao': self.ficha.versao,
                'numero_sessao': 1,
            })
            self.assertEqual(response.status_code, 302)
            self.ficha.refresh_from_db()

        response = self.client.post(url, {
            'evento': 'pista', 'quantidade': 1, 'versao': self.ficha.versao,
            'numero_sessao': 1,
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(RegistroPrestigio.objects.filter(
            ficha=self.ficha, numero_sessao=1, evento='pista',
        ).count(), 3)

    def test_creation_in_patent_mode_assigns_recruit_and_initial_pd(self):
        origem = Origem.objects.create(
            nome='Acadêmico', slug='patent-academico', fonte='OPRPG', resumo='',
            poder_nome='Saber é poder', poder_resumo='',
        )
        luta = Pericia.objects.create(
            nome='Luta', slug='luta', fonte='OPRPG', resumo='', atributo='forca',
        )
        self.client.force_login(self.owner)
        self.client.get(reverse('fichas:iniciar'))
        response = self.client.post(reverse('fichas:criar', kwargs={'etapa': 1}), {
            'nome': 'Agente recruta', 'conceito': 'Investigador',
            'aparencia': 'Roupa escura', 'personalidade': 'Observador',
            'historia': 'Entrou na Ordem recentemente.', 'objetivo': 'Investigar',
            'patente_inicial': self.recruta.pk, 'origem': origem.pk,
            'classe': self.classe.pk,
            'agilidade': 3, 'forca': 2, 'intelecto': 0, 'presenca': 1, 'vigor': 3,
            'pericias_escolhidas': [luta.pk],
            'confirmar': 'on',
            f'grau_pericia_{luta.pk}': 'treinado',
        })

        ficha = Ficha.objects.get(nome='Agente recruta')
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': ficha.pk}))
        self.assertEqual((ficha.nex, ficha.nivel_experiencia, ficha.patente), (None, None, self.recruta))
        self.assertEqual(ficha.pd_atual, 7)


class MesaAndMasterCommandTests(TestCase):
    def test_mesa_configuration_is_singleton(self):
        first = ConfiguracaoMesa.objects.create()
        second = ConfiguracaoMesa.objects.create(modo_recursos='sem_sanidade')
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ConfiguracaoMesa.objects.count(), 1)
        self.assertEqual(ConfiguracaoMesa.objects.get().modo_recursos, 'sem_sanidade')

    def test_definir_mestre_promotes_existing_user_only(self):
        user = User.objects.create_user(username='jogador', password=get_random_string(32))
        call_command('definir_mestre', 'jogador')
        user.refresh_from_db()
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_definir_mestre_errors_for_unknown_user(self):
        with self.assertRaises(CommandError):
            call_command('definir_mestre', 'inexistente')


class CarregarRegrasTests(TestCase):
    def test_loads_complete_approved_powers_and_tracks(self):
        call_command('carregar_regras', stdout=None)

        self.assertEqual(Poder.objects.count(), 143)
        self.assertEqual(Poder.objects.filter(tipo='classe').count(), 72)
        self.assertEqual(Poder.objects.filter(tipo='geral').count(), 38)
        self.assertEqual(Poder.objects.filter(tipo='paranormal').count(), 33)
        self.assertFalse(Poder.objects.filter(fonte='').exists())
        self.assertFalse(Poder.objects.filter(resumo='').exists())
        self.assertEqual(Trilha.objects.count(), 27)
        self.assertEqual(
            sum(len(trilha.habilidades) for trilha in Trilha.objects.all()), 102,
        )
        for trilha in Trilha.objects.select_related('classe'):
            esperado = 2 if trilha.classe.slug == 'sobrevivente' else 4
            self.assertEqual(len(trilha.habilidades), esperado, trilha.slug)

    def test_power_prerequisites_count_elements_and_require_matching_affinity(self):
        senha_teste = 'SenhaSegura123!'
        usuario = User.objects.create_user(username='elementos', password=senha_teste)
        classe = Classe.objects.create(
            nome='Combatente', slug='combatente', fonte='teste', resumo='',
        )
        ficha = Ficha.objects.create(
            dono=usuario, nome='Agente', classe=classe, nex=55, afinidade_elemento='morte',
        )
        poderes = [
            Poder.objects.create(
                nome=f'Poder de Morte {indice}', slug=f'poder-morte-{indice}',
                fonte='teste', resumo='', tipo='paranormal', elemento='morte',
            )
            for indice in (1, 2)
        ]
        requisito_morte = Poder.objects.create(
            nome='Poder Morte 2', slug='poder-morte-dois', fonte='teste', resumo='',
            tipo='paranormal', elemento='morte',
            pre_requisitos={'poderes_elemento_min': {'morte': 2}},
        )
        requisito_afinidade = Poder.objects.create(
            nome='Afinidade de Energia', slug='afinidade-energia', fonte='teste', resumo='',
            tipo='paranormal', elemento='energia', afinidade_resumo='Benefício aprimorado.',
        )

        ficha.afinidade_elemento = ''
        self.assertTrue(poder_atende_pre_requisitos(requisito_afinidade, ficha))
        FichaPoder.objects.create(ficha=ficha, poder=requisito_afinidade)
        self.assertFalse(poder_atende_pre_requisitos(requisito_afinidade, ficha))
        ficha.afinidade_elemento = 'energia'
        self.assertTrue(poder_atende_pre_requisitos(requisito_afinidade, ficha))
        FichaPoder.objects.create(ficha=ficha, poder=requisito_afinidade)
        self.assertFalse(poder_atende_pre_requisitos(requisito_afinidade, ficha))
        ficha.afinidade_elemento = 'morte'
        self.assertFalse(poder_atende_pre_requisitos(requisito_afinidade, ficha))

        FichaPoder.objects.create(ficha=ficha, poder=poderes[0])
        self.assertFalse(poder_atende_pre_requisitos(requisito_morte, ficha))
        FichaPoder.objects.create(ficha=ficha, poder=poderes[1])
        self.assertTrue(poder_atende_pre_requisitos(requisito_morte, ficha))

    def test_loads_priority_catalogs_and_sources(self):
        call_command('carregar_regras', stdout=None)

        self.assertEqual(Atributo.objects.count(), 5)
        self.assertEqual(Pericia.objects.count(), 28)
        self.assertEqual(Classe.objects.count(), 4)
        self.assertEqual(Condicao.objects.count(), 38)
        self.assertEqual(Patente.objects.count(), 5)
        self.assertEqual(Patente.objects.get(slug='operador').limite_pd, 3)
        self.assertEqual(Patente.objects.get(slug='agente-de-elite').recuperacao, 5)
        self.assertEqual(Origem.objects.count(), 46)
        self.assertFalse(Atributo.objects.filter(fonte='').exists())
        self.assertEqual(Origem.objects.get(slug='amnesico').escolhas_pericia, 2)
        self.assertEqual(Origem.objects.get(slug='academico').pericias_treinadas.count(), 2)
        self.assertEqual(
            Condicao.objects.get(slug='fraco').proxima_escalada.slug,
            'debilitado',
        )
        self.assertEqual(
            Condicao.objects.get(slug='abalado').efeitos,
            {'dados_teste': -1},
        )

    def test_reloading_updates_records_without_duplicates(self):
        call_command('carregar_regras', stdout=None)
        pericia = Pericia.objects.get(slug='acrobacia')
        original_pk = pericia.pk
        pericia.resumo = 'Resumo local alterado.'
        pericia.save(update_fields=('resumo',))

        call_command('carregar_regras', stdout=None)

        self.assertEqual(Pericia.objects.count(), 28)
        self.assertEqual(Pericia.objects.get(slug='acrobacia').pk, original_pk)
        self.assertIn('penalidade de carga', Pericia.objects.get(slug='acrobacia').resumo)

    def test_loads_tracks_powers_rituals_and_items_idempotently(self):
        arquivos = (
            'atributos.json', 'pericias.json', 'classes.json', 'patentes.json',
            'origens_oprgp.json', 'origens_sah.json', 'condicoes.json',
        )
        with TemporaryDirectory() as diretorio:
            pasta = Path(diretorio)
            for arquivo in arquivos:
                (pasta / arquivo).write_text('[]', encoding='utf-8')
            registros = {
                'classes.json': [{
                    'slug': 'sobrevivente', 'nome': 'Sobrevivente', 'fonte': 'teste',
                    'resumo': '', 'progressao': 'estagio',
                }],
                'trilhas.json': [{
                    'slug': 'trilha-teste', 'nome': 'Trilha de teste', 'fonte': 'teste',
                    'resumo': '', 'classe_slug': 'sobrevivente', 'habilidades': [],
                    'pre_requisitos': {'estagio_min': 2},
                }],
                'poderes.json': [{
                    'slug': 'poder-teste', 'nome': 'Poder de teste', 'fonte': 'teste',
                    'resumo': '', 'tipo': 'paranormal', 'elemento': 'morte',
                    'pre_requisitos': {
                        'classe_slug': 'sobrevivente', 'estagio_min': 2,
                        'poderes_elemento_min': {'morte': 1},
                    },
                    'custo': '',
                }],
                'rituais.json': [{
                    'slug': 'ritual-teste', 'nome': 'Ritual de teste', 'fonte': 'teste',
                    'resumo': '', 'circulo': 1, 'elemento': 'medo', 'execucao': '',
                    'alcance': '', 'alvo_area': '', 'duracao': '', 'resistencia': '', 'custo': '',
                }],
                'itens_oprgp.json': [{
                    'slug': 'item-teste', 'nome': 'Item de teste', 'fonte': 'teste',
                    'resumo': '', 'categoria': '0', 'espacos': 0, 'tipo': 'geral',
                }],
                'itens_sah.json': [],
            }
            for arquivo, dados in registros.items():
                (pasta / arquivo).write_text(json.dumps(dados), encoding='utf-8')

            with patch('fichas.management.commands.carregar_regras.DATA_DIR', pasta):
                call_command('carregar_regras', stdout=None)
                call_command('carregar_regras', stdout=None)

        self.assertEqual(Trilha.objects.get(slug='trilha-teste').classe.slug, 'sobrevivente')
        self.assertEqual(
            Trilha.objects.get(slug='trilha-teste').pre_requisitos,
            {'estagio_min': 2},
        )
        self.assertEqual(Trilha.objects.count(), 1)
        self.assertEqual(Poder.objects.count(), 1)
        self.assertEqual(
            Poder.objects.get(slug='poder-teste').pre_requisitos,
            {
                'classe_slug': 'sobrevivente', 'estagio_min': 2,
                'poderes_elemento_min': {'morte': 1},
            },
        )
        self.assertEqual(Poder.objects.get(slug='poder-teste').elemento, 'morte')
        self.assertEqual(Ritual.objects.count(), 1)
        self.assertEqual(ItemCatalogo.objects.count(), 1)

    def test_loader_rejects_unrecognized_power_prerequisite_fields_atomically(self):
        arquivos = (
            'atributos.json', 'pericias.json', 'classes.json', 'patentes.json',
            'origens_oprgp.json', 'origens_sah.json', 'condicoes.json', 'trilhas.json',
            'rituais.json', 'itens_oprgp.json', 'itens_sah.json',
        )
        with TemporaryDirectory() as diretorio:
            pasta = Path(diretorio)
            for arquivo in arquivos:
                (pasta / arquivo).write_text('[]', encoding='utf-8')
            (pasta / 'poderes.json').write_text(json.dumps([{
                'slug': 'poder-invalido',
                'nome': 'Poder inválido',
                'fonte': 'teste',
                'resumo': '',
                'tipo': 'geral',
                'pre_requisitos': {'exigencia_desconhecida': 'valor'},
            }]), encoding='utf-8')

            with patch('fichas.management.commands.carregar_regras.DATA_DIR', pasta):
                with self.assertRaises(CommandError):
                    call_command('carregar_regras', stdout=None)

        self.assertFalse(Poder.objects.exists())

    def test_loader_rejects_invalid_condition_effects_atomically(self):
        arquivos = (
            'atributos.json', 'pericias.json', 'classes.json', 'patentes.json',
            'origens_oprgp.json', 'origens_sah.json', 'trilhas.json', 'poderes.json',
            'rituais.json', 'itens_oprgp.json', 'itens_sah.json',
        )
        efeitos_invalidos = (
            {'dados_desconhecidos': -1},
            {'dados_teste': True},
            {'dados_teste': 11},
        )

        for efeitos in efeitos_invalidos:
            with self.subTest(efeitos=efeitos), TemporaryDirectory() as diretorio:
                pasta = Path(diretorio)
                for arquivo in arquivos:
                    (pasta / arquivo).write_text('[]', encoding='utf-8')
                (pasta / 'condicoes.json').write_text(json.dumps([{
                    'slug': 'condicao-invalida',
                    'nome': 'Condição inválida',
                    'fonte': 'teste',
                    'resumo': '',
                    'efeitos': efeitos,
                }]), encoding='utf-8')

                with patch('fichas.management.commands.carregar_regras.DATA_DIR', pasta):
                    with self.assertRaises(CommandError):
                        call_command('carregar_regras', stdout=None)

                self.assertFalse(Condicao.objects.exists())
