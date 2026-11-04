from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils.crypto import get_random_string

from fichas.models import (
    Atributo,
    Classe,
    Condicao,
    ConfiguracaoMesa,
    Ficha,
    FichaCondicao,
    FichaPericia,
    LogAlteracao,
    Origem,
    Patente,
    Pericia,
    Rolagem,
)
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
from fichas.forms import AtributosFichaForm, ConceitoFichaForm, FichaEdicaoForm

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

    def test_owner_can_complete_creation_wizard(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('fichas:iniciar'))
        self.assertRedirects(response, reverse('fichas:criar', kwargs={'etapa': 1}))

        response = self.client.post(reverse('fichas:criar', kwargs={'etapa': 1}), {
            'nome': 'Nova agente', 'conceito': 'Investigadora', 'aparencia': 'Casaco escuro',
            'personalidade': 'Atenta', 'historia': 'Chegou recentemente à Ordem.', 'objetivo': 'Investigar o caso',
        })
        self.assertRedirects(response, reverse('fichas:criar', kwargs={'etapa': 2}))
        response = self.client.post(reverse('fichas:criar', kwargs={'etapa': 2}), {
            'agilidade': 3, 'forca': 2, 'intelecto': 0, 'presenca': 1, 'vigor': 3,
        })
        self.assertRedirects(response, reverse('fichas:criar', kwargs={'etapa': 3}))
        response = self.client.post(reverse('fichas:criar', kwargs={'etapa': 3}), {'origem': self.origem.pk})
        self.assertRedirects(response, reverse('fichas:criar', kwargs={'etapa': 4}))
        response = self.client.post(reverse('fichas:criar', kwargs={'etapa': 4}), {'classe': self.classe.pk})
        self.assertRedirects(response, reverse('fichas:criar', kwargs={'etapa': 5}))
        response = self.client.post(reverse('fichas:criar', kwargs={'etapa': 5}), {
            'pericia_obrigatoria_0': self.luta.pk, 'pericias_escolhidas': [self.pontaria.pk],
        })
        self.assertRedirects(response, reverse('fichas:criar', kwargs={'etapa': 6}))
        response = self.client.post(reverse('fichas:criar', kwargs={'etapa': 6}), {'confirmar': 'on'})

        ficha = Ficha.objects.get(nome='Nova agente')
        self.assertRedirects(response, reverse('fichas:detalhe', kwargs={'pk': ficha.pk}))
        self.assertEqual((ficha.dono, ficha.pv_atual, ficha.pe_atual, ficha.san_atual), (self.owner, 23, 3, 12))
        self.assertSetEqual(
            set(ficha.pericias.values_list('pericia__slug', flat=True)),
            {'fortitude', 'luta', 'pontaria'},
        )

    def test_free_creation_mode_is_granted_only_to_master(self):
        self.client.force_login(self.other)
        self.client.get(f"{reverse('fichas:iniciar')}?livre=1")
        self.assertFalse(self.client.session['fichas.criacao']['livre'])

        self.client.force_login(self.master)
        self.client.get(f"{reverse('fichas:iniciar')}?livre=1")
        self.assertTrue(self.client.session['fichas.criacao']['livre'])
        self.client.post(reverse('fichas:criar', kwargs={'etapa': 1}), {})
        response = self.client.post(reverse('fichas:criar', kwargs={'etapa': 2}), {
            'agilidade': 4, 'forca': 4, 'intelecto': 4, 'presenca': 4, 'vigor': 4,
        })
        self.assertRedirects(response, reverse('fichas:criar', kwargs={'etapa': 3}))
        self.client.post(reverse('fichas:criar', kwargs={'etapa': 3}), {})
        self.client.post(reverse('fichas:criar', kwargs={'etapa': 4}), {})
        self.client.post(reverse('fichas:criar', kwargs={'etapa': 5}), {})
        response = self.client.post(reverse('fichas:criar', kwargs={'etapa': 6}), {})
        self.assertEqual(response.status_code, 302)
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

    def test_resource_condition_and_roll_endpoints_validate_and_persist(self):
        self.client.force_login(self.owner)
        resource = reverse('fichas:recurso', kwargs={'pk': self.ficha.pk})
        response = self.client.post(resource, data='{"recurso":"pv","delta":2}', content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.ficha.refresh_from_db()
        self.assertEqual(self.ficha.pv_atual, 12)
        self.assertEqual(self.client.post(resource, data='{"recurso":"pv","delta":999}', content_type='application/json').status_code, 400)
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
        self.assertTrue(LogAlteracao.objects.filter(ficha=self.ficha, campo='condicao', valor_novo=condicao.nome).exists())

        roll_url = reverse('fichas:rolar', kwargs={'pk': self.ficha.pk})
        response = self.client.post(
            roll_url, data='{"tipo":"pericia","alvo":%d,"bonus":0}' % self.luta.pk,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Rolagem.objects.filter(ficha=self.ficha, usuario=self.owner).count(), 1)
        self.assertEqual(response.json()['total'], response.json()['dado_escolhido'] + 0)
        self.assertEqual(self.client.post(roll_url, data='{}', content_type='application/json').status_code, 400)

    def test_json_endpoints_enforce_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        response = csrf_client.post(
            reverse('fichas:recurso', kwargs={'pk': self.ficha.pk}),
            data='{"recurso":"pv","delta":1}', content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)


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