from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils.crypto import get_random_string

from core.models import (
    AmeacaMesa,
    CenaMesa,
    InscricaoMesa,
    Mesa,
    PistaCena,
    RegistroAmeaca,
    RegistroCena,
)
from fichas.models import (
    Classe,
    Condicao,
    ConfiguracaoFicha,
    ConfiguracaoMesa,
    Ficha,
    FichaCondicao,
    LogAlteracao,
    RegistroPrestigio,
    Rolagem,
)

User = get_user_model()


class AuthenticationSecurityTests(TestCase):
	def test_home_requires_login(self):
		response = self.client.get(reverse('home'))

		self.assertRedirects(response, '/accounts/login/?next=/')

	def test_logout_requires_post(self):
		password = get_random_string(32)
		user = User.objects.create_user(
			username='member',
			password=password,
		)
		self.client.force_login(user)

		response = self.client.get(reverse('logout'))

		self.assertEqual(response.status_code, 405)
		self.assertEqual(self.client.get(reverse('home')).status_code, 200)

		response = self.client.post(reverse('logout'))

		self.assertRedirects(response, reverse('login'))
		self.assertRedirects(self.client.get(reverse('home')), '/accounts/login/?next=/')

	def test_external_next_is_not_followed(self):
		password = get_random_string(32)
		user = User.objects.create_user(
			username='member',
			password=password,
		)

		response = self.client.post(
			reverse('login'),
			{
				'username': user.username,
				'password': password,
				'next': '//evil.com',
			},
		)

		self.assertRedirects(response, reverse('home'))
		self.assertNotIn('evil.com', response.url)

	def test_security_headers_are_present(self):
		response = self.client.get(reverse('login'))

		self.assertEqual(response.headers['X-Frame-Options'], 'DENY')
		self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
		policy = response.headers['Content-Security-Policy']
		self.assertIn("default-src 'self'", policy)
		self.assertNotIn('unsafe-inline', policy)

	def test_service_worker_uses_root_scope_without_caching_private_pages(self):
		response = self.client.get(reverse('service_worker'))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response['Service-Worker-Allowed'], '/')
		self.assertEqual(response['Cache-Control'], 'no-cache')
		self.assertContains(response, "url.pathname.startsWith('/static/')")
		self.assertContains(response, "request.mode === 'navigate'")
		self.assertContains(response, 'As páginas da mesa exigem conexão e autenticação.')
		self.assertNotContains(response, 'anotacoes_mestre')
		self.assertEqual(self.client.post(reverse('service_worker')).status_code, 405)
		login = self.client.get(reverse('login'))
		self.assertContains(login, 'href="/static/manifest.webmanifest"')
		self.assertContains(login, 'href="/static/css/style.css?v=21"')
		self.assertContains(login, 'src="/static/js/pwa.js"')
		self.assertContains(login, 'src="/static/js/aparencia.js?v=3"')
		self.assertNotContains(login, 'id="die-d20"')

	def test_password_change_requires_current_password(self):
		current_password = get_random_string(32)
		new_password = get_random_string(32)
		user = User.objects.create_user(
			username='member',
			password=current_password,
		)
		self.client.force_login(user)
		change_url = reverse('account_profile')

		response = self.client.post(
			change_url,
			{
				'acao': 'senha',
				'old_password': get_random_string(32),
				'new_password1': new_password,
				'new_password2': new_password,
			},
		)
		self.assertEqual(response.status_code, 400)
		user.refresh_from_db()
		self.assertTrue(user.check_password(current_password))

		response = self.client.post(
			change_url,
			{
				'acao': 'senha',
				'old_password': current_password,
				'new_password1': new_password,
				'new_password2': new_password,
			},
		)
		self.assertRedirects(response, reverse('account_profile'))
		user.refresh_from_db()
		self.assertTrue(user.check_password(new_password))


class MasterDashboardTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='dashboard-owner', password=get_random_string(32),
        )
        self.master = User.objects.create_superuser(
            username='dashboard-master',
            email='dashboard-master@example.com',
            password=get_random_string(32),
        )
        classe = Classe.objects.create(
            nome='Combatente', slug='combatente', fonte='OPRPG p. 25', resumo='',
        )
        self.ficha = Ficha.objects.create(
            dono=self.owner, nome='Agente do Painel', classe=classe, nex=5,
            anotacoes_mestre='Nota reservada ao mestre',
        )
        self.table = Mesa.objects.create(
            mestre=self.master, nome='Mesa do Painel', publica=True,
        )
        InscricaoMesa.objects.create(mesa=self.table, ficha=self.ficha)
        self.scene = CenaMesa.objects.create(
            criado_por=self.master, nome='Cena do Painel', ativa=False,
        )
        Rolagem.objects.create(
            ficha=self.ficha, usuario=self.owner, tipo='pericia', descricao='Luta',
            dados=[7, 12], dado_escolhido=12, bonus=5, total=17,
        )

    def test_dashboard_is_master_only_and_lists_roll_activity(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('painel_mestre'))
        self.assertEqual(response.status_code, 403)
        updates_url = reverse('painel_mestre_atualizacoes')
        self.assertEqual(self.client.get(updates_url).status_code, 403)
        home = self.client.get(reverse('home'))
        self.assertNotContains(home, 'Painel do mestre')
        self.assertContains(home, 'Encontrar mesas')
        self.assertNotContains(home, 'Cenas da mesa')
        self.assertNotContains(home, 'Histórico de rolagens')
        self.assertNotContains(home, 'Nota reservada ao mestre')

        self.client.force_login(self.master)
        response = self.client.get(reverse('painel_mestre'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Agente do Painel')
        self.assertContains(response, '[7, 12] + 5 = 17')
        self.assertContains(response, 'Ativa: 1')
        self.assertContains(response, self.table.nome)
        self.assertContains(response, self.scene.nome)
        self.assertContains(response, 'Histórico de rolagens')
        self.assertContains(response, 'Configuração da mesa')
        self.assertContains(response, 'class="master-sheet-name"')
        self.assertContains(response, 'class="checklist-control"')
        self.assertContains(response, 'js/mesa.js?v=13')
        self.assertNotContains(response, 'Nota reservada ao mestre')

        cursor = Rolagem.objects.filter(ficha=self.ficha).latest('pk').pk
        Rolagem.objects.create(
            ficha=self.ficha, usuario=self.owner, tipo='pericia', descricao='Atualização',
            dados=[15], dado_escolhido=15, bonus=0, total=15, secreta=True,
        )
        response = self.client.get(f'{updates_url}?desde={cursor}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item['descricao'] for item in response.json()['rolagens']], ['Atualização'])
        self.assertTrue(response.json()['rolagens'][0]['secreta'])
        self.assertNotIn('anotacoes_mestre', response.json())
        self.assertEqual(response.json()['cursor'], Rolagem.objects.latest('pk').pk)

    def test_only_master_can_start_a_session_and_missing_configuration_is_created(self):
        url = reverse('iniciar_nova_sessao')
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.master)
        self.assertEqual(csrf_client.post(url).status_code, 403)
        self.assertFalse(ConfiguracaoMesa.objects.exists())

        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.assertFalse(ConfiguracaoMesa.objects.exists())

        self.client.force_login(self.master)
        response = self.client.post(url)
        self.assertRedirects(response, reverse('painel_mestre'))
        self.assertEqual(ConfiguracaoMesa.objects.get().numero_sessao, 2)

    def test_dashboard_resources_are_per_sheet_and_can_be_adjusted_without_opening_sheet(self):
        alternative = Ficha.objects.create(
            dono=self.owner, nome='Z Agente alternativa', classe=self.ficha.classe, nex=5,
        )
        ConfiguracaoFicha.objects.create(
            ficha=alternative, modo_recursos='sem_sanidade',
        )
        self.client.force_login(self.master)

        page = self.client.get(reverse('painel_mestre'))
        self.assertContains(page, 'data-resource="pe"')
        self.assertContains(page, 'data-resource="san"')
        updates = self.client.get(reverse('painel_mestre_atualizacoes')).json()
        fichas_por_id = {item['id']: item for item in updates['fichas']}
        self.assertTrue(fichas_por_id[self.ficha.pk]['selecionavel'])
        self.assertTrue(fichas_por_id[alternative.pk]['selecionavel'])
        self.assertEqual(
            {item['chave'] for item in fichas_por_id[self.ficha.pk]['recursos']},
            {'pv', 'pe', 'san'},
        )
        self.assertEqual(
            {item['chave'] for item in fichas_por_id[alternative.pk]['recursos']},
            {'pv', 'pd'},
        )

        response = self.client.post(
            reverse('fichas:recurso', kwargs={'pk': self.ficha.pk}),
            data='{"recurso":"pe","delta":1}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.ficha.refresh_from_db()
        self.assertEqual(self.ficha.pe_atual, response.json()['atual'])
        self.assertTrue(LogAlteracao.objects.filter(
            ficha=self.ficha, usuario=self.master, campo='pe_atual',
        ).exists())

    def test_dashboard_updates_work_when_there_are_no_sheets(self):
        self.ficha.delete()
        self.client.force_login(self.master)

        response = self.client.get(reverse('painel_mestre_atualizacoes'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['fichas'], [])

    def test_master_can_reset_session_count_without_deleting_history(self):
        ConfiguracaoMesa.objects.create(numero_sessao=8)
        ConfiguracaoFicha.objects.create(
            ficha=self.ficha, numero_sessao=8,
        )
        self.ficha.cicatrizado_sessao_usada = 8
        self.ficha.save(update_fields=('cicatrizado_sessao_usada',))
        registro = RegistroPrestigio.objects.create(
            ficha=self.ficha, usuario=self.owner, numero_sessao=8,
            evento='pista', quantidade=1, delta=2,
        )
        url = reverse('limpar_contagem_sessoes')

        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.master)
        response = self.client.post(url)

        self.assertRedirects(response, reverse('painel_mestre'))
        self.assertEqual(ConfiguracaoMesa.objects.get().numero_sessao, 0)
        self.assertEqual(
            ConfiguracaoFicha.objects.get(ficha=self.ficha).numero_sessao, 0,
        )
        self.assertIsNone(Ficha.objects.get(pk=self.ficha.pk).cicatrizado_sessao_usada)
        registro.refresh_from_db()
        self.assertEqual(registro.numero_sessao, 0)

        self.client.post(reverse('iniciar_nova_sessao'))
        self.assertEqual(ConfiguracaoMesa.objects.get().numero_sessao, 1)
        self.assertEqual(
            ConfiguracaoFicha.objects.get(ficha=self.ficha).numero_sessao, 1,
        )

    def test_master_can_apply_audited_condition_to_selected_active_sheets_only(self):
        condition = Condicao.objects.create(
            nome='Abalado em grupo', slug='abalado-grupo', fonte='OPRPG p.310', resumo='',
        )
        another = Ficha.objects.create(
            dono=self.owner, nome='Agente reserva', classe=self.ficha.classe, nex=5,
        )
        archived = Ficha.objects.create(
            dono=self.owner, nome='Ficha arquivada', classe=self.ficha.classe,
            nex=5, status='arquivada',
        )
        url = reverse('aplicar_condicao_grupo')
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(url, {
            'condicao': condition.pk, 'fichas': [self.ficha.pk],
        }).status_code, 403)

        self.client.force_login(self.master)
        response = self.client.post(url, {
            'condicao': condition.pk,
            'fichas': [self.ficha.pk, another.pk],
        })
        self.assertRedirects(response, reverse('painel_mestre'))
        self.assertEqual(
            FichaCondicao.objects.filter(condicao=condition).count(), 2,
        )
        self.assertEqual(
            LogAlteracao.objects.filter(campo='condicao', valor_novo=condition.nome).count(), 2,
        )
        response = self.client.post(url, {
            'condicao': condition.pk,
            'fichas': [self.ficha.pk, archived.pk],
        })
        self.assertRedirects(response, reverse('painel_mestre'))
        self.assertFalse(FichaCondicao.objects.filter(ficha=archived, condicao=condition).exists())
        response = self.client.get(reverse('painel_mestre'))
        self.assertContains(response, 'Aplicar condição a fichas ativas')
        self.assertContains(response, 'Abalado em grupo')

    def test_roll_history_scopes_sheets_and_hides_secret_rolls_from_players(self):
        Rolagem.objects.create(
            ficha=self.ficha, usuario=self.master, tipo='pericia', descricao='Análise reservada',
            dados=[3], dado_escolhido=3, bonus=0, total=3, secreta=True,
        )
        other = User.objects.create_user(username='other-history', password=get_random_string(32))
        ficha_alheia = Ficha.objects.create(dono=other, nome='Ficha alheia', nex=5)

        self.client.force_login(self.owner)
        url = reverse('fichas:historico_rolagens')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Luta')
        self.assertNotContains(response, 'Análise reservada')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(f'{url}?ficha={ficha_alheia.pk}').status_code, 404)

        self.client.force_login(self.master)
        response = self.client.get(url)
        self.assertRedirects(response, f'{reverse("painel_mestre")}#historico')
        response = self.client.get(reverse('painel_mestre'))
        self.assertContains(response, 'Análise reservada')
        self.assertContains(response, 'Ficha alheia')


class SceneManagementTests(TestCase):
    def setUp(self):
        self.player = User.objects.create_user(
            username='scene-player', password=get_random_string(32),
        )
        self.master = User.objects.create_superuser(
            username='scene-master',
            email='scene-master@example.com',
            password=get_random_string(32),
        )
        self.scene = CenaMesa.objects.create(
            criado_por=self.master,
            nome='Arquivo abandonado',
            tipo='investigacao',
            descricao_jogadores='A porta está entreaberta.',
            anotacoes_mestre='O cultista está escondido no porão.',
            ativa=False,
        )
        self.hidden_clue = PistaCena.objects.create(
            cena=self.scene, titulo='Bilhete selado',
            conteudo='A senha secreta é eclipse.', estado='oculta',
        )
        self.revealed_clue = PistaCena.objects.create(
            cena=self.scene, titulo='Marca na parede',
            conteudo='Há um símbolo recém-riscado.', estado='revelada',
        )

    def test_hidden_scenes_and_clues_are_not_disclosed_to_players(self):
        self.client.force_login(self.player)
        scenes_url = reverse('lista_cenas')
        detail_url = reverse('detalhe_cena', args=[self.scene.pk])
        self.assertNotContains(self.client.get(scenes_url), self.scene.nome)
        self.assertEqual(self.client.get(detail_url).status_code, 404)

        self.scene.ativa = True
        self.scene.save(update_fields=('ativa',))
        response = self.client.get(detail_url)
        self.assertContains(response, self.scene.descricao_jogadores)
        self.assertContains(response, self.revealed_clue.titulo)
        self.assertNotContains(response, self.scene.anotacoes_mestre)
        self.assertNotContains(response, self.hidden_clue.titulo)
        self.assertNotContains(response, self.hidden_clue.conteudo)

    def test_only_master_can_create_scenes_and_manage_clues(self):
        create_url = reverse('criar_cena')
        self.client.force_login(self.player)
        payload = {
            'nome': 'Cena não autorizada',
            'tipo': 'investigacao',
            'descricao_jogadores': 'Texto',
            'anotacoes_mestre': 'Segredo',
        }
        self.assertEqual(self.client.post(create_url, payload).status_code, 403)
        self.assertEqual(self.client.post(
            reverse('adicionar_pista', args=[self.scene.pk]),
            {'titulo': 'Tentativa', 'conteudo': 'Não autorizada'},
        ).status_code, 403)
        self.assertFalse(CenaMesa.objects.filter(nome='Cena não autorizada').exists())

        self.client.force_login(self.master)
        response = self.client.post(create_url, {
            'nome': 'Porão',
            'tipo': 'medo',
            'descricao_jogadores': 'Um ruído vem de baixo.',
            'anotacoes_mestre': 'A criatura ainda está viva.',
        })
        created_scene = CenaMesa.objects.get(nome='Porão')
        self.assertRedirects(response, f'{reverse("painel_mestre")}#cenas')
        self.assertFalse(created_scene.ativa)
        self.assertTrue(RegistroCena.objects.filter(cena=created_scene, acao='criada').exists())

        add_clue_url = reverse('adicionar_pista', args=[self.scene.pk])
        response = self.client.post(add_clue_url, {
            'titulo': 'Chave',
            'conteudo': 'Está sob o tapete.',
        })
        self.assertRedirects(response, f'{reverse("painel_mestre")}#cenas')
        clue = PistaCena.objects.get(cena=self.scene, titulo='Chave')
        self.assertEqual(clue.estado, 'oculta')
        self.assertTrue(RegistroCena.objects.filter(
            cena=self.scene, acao=f'pista_criada:{clue.pk}',
        ).exists())

    def test_only_master_can_delete_scene_and_deletion_cascades_to_clues_and_history(self):
        clue = PistaCena.objects.create(
            cena=self.scene, titulo='Chave', conteudo='Debaixo do tapete.',
        )
        history = RegistroCena.objects.create(
            cena=self.scene, usuario=self.master, acao='publicada',
        )
        url = reverse('excluir_cena', args=[self.scene.pk])

        self.client.force_login(self.player)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.master)
        self.assertEqual(self.client.get(url).status_code, 405)
        response = self.client.post(url)

        self.assertRedirects(response, f'{reverse("painel_mestre")}#cenas')
        self.assertFalse(CenaMesa.objects.filter(pk=self.scene.pk).exists())
        self.assertFalse(PistaCena.objects.filter(pk=clue.pk).exists())
        self.assertFalse(RegistroCena.objects.filter(pk=history.pk).exists())

    def test_master_bestiary_is_private_editable_and_audited(self):
        create_url = reverse('criar_ameaca')
        self.client.force_login(self.player)
        self.assertEqual(self.client.get(reverse('lista_ameacas')).status_code, 403)
        self.assertEqual(self.client.post(create_url, {
            'nome': 'Ameaça privada',
            'categoria': 'anomalia',
        }).status_code, 403)

        self.client.force_login(self.master)
        payload = {
            'nome': 'Figura sem rosto',
            'categoria': 'anomalia',
            'defesa': '18',
            'pv': '42',
            'deslocamento': '9m',
            'resistencias': 'Impacto 5',
            'vulnerabilidades': 'Fogo',
            'imunidades': '',
            'acoes': 'Ataque de exemplo.',
            'anotacoes_mestre': 'Aparece apenas em espelhos.',
        }
        response = self.client.post(create_url, payload)
        self.assertRedirects(response, reverse('lista_ameacas'))
        ameaca = AmeacaMesa.objects.get(nome='Figura sem rosto')
        self.assertTrue(RegistroAmeaca.objects.filter(ameaca=ameaca, acao='criada').exists())
        response = self.client.get(reverse('lista_ameacas'))
        self.assertContains(response, ameaca.nome)
        self.assertContains(response, 'Aparece apenas em espelhos.')

        payload.update({'nome': 'Figura sem rosto alterada', 'pv': '45'})
        response = self.client.post(reverse('editar_ameaca', args=[ameaca.pk]), payload)
        self.assertRedirects(response, reverse('lista_ameacas'))
        ameaca.refresh_from_db()
        self.assertEqual(ameaca.nome, 'Figura sem rosto alterada')
        self.assertEqual(ameaca.pv, 45)
        self.assertTrue(RegistroAmeaca.objects.filter(ameaca=ameaca, acao='editada').exists())

        self.client.force_login(self.player)
        self.assertEqual(self.client.get(reverse('lista_ameacas')).status_code, 403)


class TableEnrollmentTests(TestCase):
    def setUp(self):
        password = get_random_string(32)
        self.master = User.objects.create_superuser(
            username='table-master', email='table-master@example.com', password=password,
        )
        self.player = User.objects.create_user(
            username='table-player', password=password,
        )
        self.other = User.objects.create_user(
            username='table-other', password=password,
        )
        self.ficha = Ficha.objects.create(dono=self.player, nome='Agente de teste', nex=5)

    def test_master_creates_public_and_private_tables_with_private_numeric_code(self):
        self.client.force_login(self.master)
        response = self.client.post(reverse('criar_mesa'), {'nome': 'Mesa aberta', 'publica': 'on'})
        self.assertRedirects(response, f'{reverse("painel_mestre")}#mesas')
        public = Mesa.objects.get(nome='Mesa aberta')
        self.assertTrue(public.publica)
        self.assertIsNone(public.codigo_acesso)

        response = self.client.post(reverse('criar_mesa'), {'nome': 'Mesa fechada'})
        self.assertRedirects(response, f'{reverse("painel_mestre")}#mesas')
        private = Mesa.objects.get(nome='Mesa fechada')
        self.assertFalse(private.publica)
        self.assertRegex(private.codigo_acesso, r'^[0-9]{8}$')
        self.assertEqual(Mesa.objects.filter(codigo_acesso=private.codigo_acesso).count(), 1)
        self.assertContains(self.client.get(reverse('painel_mestre')), private.codigo_acesso)

    def test_public_enrollment_and_private_code_are_scoped_and_removable(self):
        public = Mesa.objects.create(mestre=self.master, nome='Mesa pública', publica=True)
        private = Mesa.objects.create(mestre=self.master, nome='Mesa privada')
        self.client.force_login(self.player)

        page = self.client.get(reverse('lista_mesas'))
        self.assertContains(page, public.nome)
        self.assertNotContains(page, private.nome)
        self.assertNotContains(page, private.codigo_acesso)

        enroll_url = reverse('inscrever_ficha_mesa')
        response = self.client.post(enroll_url, {
            'ficha': self.ficha.pk, 'mesa': public.pk, 'codigo_acesso': '',
        })
        self.assertRedirects(response, reverse('lista_mesas'))
        self.assertTrue(InscricaoMesa.objects.filter(mesa=public, ficha=self.ficha).exists())
        response = self.client.post(enroll_url, {
            'ficha': self.ficha.pk, 'mesa': '', 'codigo_acesso': '123',
        })
        self.assertRedirects(response, reverse('lista_mesas'))
        self.assertFalse(InscricaoMesa.objects.filter(mesa=private, ficha=self.ficha).exists())

        response = self.client.post(enroll_url, {
            'ficha': self.ficha.pk, 'mesa': '', 'codigo_acesso': private.codigo_acesso,
        })
        self.assertRedirects(response, reverse('lista_mesas'))
        self.assertTrue(InscricaoMesa.objects.filter(mesa=private, ficha=self.ficha).exists())

        remove_url = reverse(
            'remover_inscricao_mesa', kwargs={'mesa_pk': public.pk, 'ficha_pk': self.ficha.pk},
        )
        self.assertEqual(self.client.get(remove_url).status_code, 405)
        self.assertEqual(self.client.post(remove_url).status_code, 302)
        self.assertFalse(InscricaoMesa.objects.filter(mesa=public, ficha=self.ficha).exists())
        self.assertEqual(self.client.post(
            reverse('excluir_mesa', kwargs={'pk': private.pk}),
        ).status_code, 404)

    def test_non_master_cannot_create_tables_or_enroll_another_players_sheet(self):
        self.client.force_login(self.player)
        self.assertEqual(self.client.post(
            reverse('criar_mesa'), {'nome': 'Não autorizada'},
        ).status_code, 403)
        public = Mesa.objects.create(mestre=self.master, nome='Mesa aberta', publica=True)
        outra_ficha = Ficha.objects.create(dono=self.other, nome='Privada', nex=5)
        self.assertEqual(self.client.post(reverse('inscrever_ficha_mesa'), {
            'ficha': outra_ficha.pk, 'mesa': public.pk,
        }).status_code, 302)
        self.assertFalse(InscricaoMesa.objects.filter(ficha=outra_ficha).exists())

    def test_deleting_table_keeps_character_sheet(self):
        public = Mesa.objects.create(mestre=self.master, nome='Mesa aberta', publica=True)
        InscricaoMesa.objects.create(mesa=public, ficha=self.ficha)
        self.client.force_login(self.master)
        response = self.client.post(reverse('excluir_mesa', kwargs={'pk': public.pk}))
        self.assertRedirects(response, f'{reverse("painel_mestre")}#mesas')
        self.assertFalse(Mesa.objects.filter(pk=public.pk).exists())
        self.assertTrue(Ficha.objects.filter(pk=self.ficha.pk).exists())
        self.assertFalse(InscricaoMesa.objects.filter(ficha=self.ficha).exists())
