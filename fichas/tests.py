from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase
from django.utils.crypto import get_random_string

from fichas.models import Atributo, Classe, Condicao, ConfiguracaoMesa, Ficha, Origem, Patente, Pericia
from fichas.permissions import fichas_visiveis_para, is_mestre, pode_editar_ficha, pode_ver_ficha
from fichas.regras import (
    bonus_pericia,
    calcular_defesa,
    calcular_pd_max,
    calcular_pe_max,
    calcular_pv_max,
    calcular_san_max,
    capacidade_carga,
    espacos_usados,
    limite_pe_por_turno,
    pericias_treinadas_disponiveis,
    pendencias_ao_subir_nex,
    rolar_dano,
    rolar_teste,
    validar_atributos_iniciais,
)

User = get_user_model()


class FixedDice:
    def __init__(self, values):
        self.values = iter(values)

    def randint(self, _minimum, _maximum):
        return next(self.values)


class RegrasTests(SimpleTestCase):
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

    def test_turn_limits_and_level_up_pending_choices(self):
        self.assertEqual(limite_pe_por_turno(5), 1)
        self.assertEqual(limite_pe_por_turno(99), 20)
        self.assertEqual(limite_pe_por_turno(99, classe='sobrevivente'), 1)
        pendencias = pendencias_ao_subir_nex('especialista', 5, 20, intelecto=3)
        self.assertEqual([item['tipo'] for item in pendencias], ['trilha', 'poder', 'atributo'])

    def test_rolls_follow_attribute_zero_and_negative_pool_rules(self):
        zero = rolar_teste(0, rng=FixedDice([19, 3]))
        self.assertEqual((zero['dados'], zero['dado_escolhido'], zero['ordem']), ([19, 3], 3, 'menor'))
        zero_penalizado = rolar_teste(0, dados_extras=-2, rng=FixedDice([19, 18, 14, 2]))
        self.assertEqual((zero_penalizado['dados'], zero_penalizado['dado_escolhido']), ([19, 18, 14, 2], 2))
        ordinary = rolar_teste(3, bonus_pericia=5, rng=FixedDice([3, 18, 8]))
        self.assertEqual((ordinary['dado_escolhido'], ordinary['total']), (18, 23))
        negative = rolar_teste(1, dados_extras=-2, rng=FixedDice([18, 12, 4]))
        self.assertEqual((negative['dados'], negative['dado_escolhido'], negative['ordem']), ([18, 12, 4], 4, 'menor'))

    def test_critical_damage_multiplies_dice_not_numeric_bonus(self):
        damage = rolar_dano(2, 6, bonus=3, multiplicador_critico=2, rng=FixedDice([2, 3, 4, 5]))
        self.assertEqual(damage['total'], 17)


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
    def test_loads_priority_catalogs_and_sources(self):
        call_command('carregar_regras', stdout=None)

        self.assertEqual(Atributo.objects.count(), 5)
        self.assertEqual(Pericia.objects.count(), 28)
        self.assertEqual(Classe.objects.count(), 4)
        self.assertEqual(Condicao.objects.count(), 38)
        self.assertEqual(Patente.objects.count(), 5)
        self.assertEqual(Origem.objects.count(), 46)
        self.assertFalse(Atributo.objects.filter(fonte='').exists())
        self.assertEqual(Origem.objects.get(slug='amnesico').escolhas_pericia, 2)
        self.assertEqual(Origem.objects.get(slug='academico').pericias_treinadas.count(), 2)
        self.assertEqual(
            Condicao.objects.get(slug='fraco').proxima_escalada.slug,
            'debilitado',
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