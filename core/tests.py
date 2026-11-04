from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils.crypto import get_random_string

from core.models import AmeacaMesa, CenaMesa, PistaCena, RegistroAmeaca, RegistroCena
from fichas.models import Classe, Condicao, ConfiguracaoMesa, Ficha, FichaCondicao, LogAlteracao, Rolagem

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
		self.assertContains(login, 'href="/static/css/style.css"')
		self.assertContains(login, 'src="/static/js/pwa.js"')

	def test_password_change_requires_current_password(self):
		current_password = get_random_string(32)
		new_password = get_random_string(32)
		user = User.objects.create_user(
			username='member',
			password=current_password,
		)
		self.client.force_login(user)
		change_url = reverse('password_change')

		response = self.client.post(
			change_url,
			{
				'old_password': get_random_string(32),
				'new_password1': new_password,
				'new_password2': new_password,
			},
		)
		self.assertEqual(response.status_code, 200)
		user.refresh_from_db()
		self.assertTrue(user.check_password(current_password))

		response = self.client.post(
			change_url,
			{
				'old_password': current_password,
				'new_password1': new_password,
				'new_password2': new_password,
			},
		)
		self.assertRedirects(response, reverse('password_change_done'))
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
            nome='Combatente', slug='combatente-dashboard', fonte='OPRPG p. 25', resumo='',
        )
        self.ficha = Ficha.objects.create(
            dono=self.owner, nome='Agente do Painel', classe=classe, nex=5,
            anotacoes_mestre='Nota reservada ao mestre',
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
        self.assertNotContains(home, 'Nota reservada ao mestre')

        self.client.force_login(self.master)
        response = self.client.get(reverse('painel_mestre'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Agente do Painel')
        self.assertContains(response, '[7, 12] + 5 = 17')
        self.assertContains(response, 'Ativa: 1')
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
        self.assertRedirects(response, reverse('detalhe_cena', args=[created_scene.pk]))
        self.assertFalse(created_scene.ativa)
        self.assertTrue(RegistroCena.objects.filter(cena=created_scene, acao='criada').exists())

        add_clue_url = reverse('adicionar_pista', args=[self.scene.pk])
        response = self.client.post(add_clue_url, {
            'titulo': 'Chave',
            'conteudo': 'Está sob o tapete.',
        })
        self.assertRedirects(response, reverse('detalhe_cena', args=[self.scene.pk]))
        clue = PistaCena.objects.get(cena=self.scene, titulo='Chave')
        self.assertEqual(clue.estado, 'oculta')
        self.assertTrue(RegistroCena.objects.filter(
            cena=self.scene, acao=f'pista_criada:{clue.pk}',
        ).exists())

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
