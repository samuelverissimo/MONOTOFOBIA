from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('service-worker.js', views.service_worker, name='service_worker'),
    path('mesas/', views.lista_mesas, name='lista_mesas'),
    path('mesas/criar/', views.criar_mesa, name='criar_mesa'),
    path('mesas/inscrever/', views.inscrever_ficha_mesa, name='inscrever_ficha_mesa'),
    path(
        'mesas/<int:mesa_pk>/fichas/<int:ficha_pk>/remover/',
        views.remover_inscricao_mesa,
        name='remover_inscricao_mesa',
    ),
    path('mesas/<int:pk>/excluir/', views.excluir_mesa, name='excluir_mesa'),
    path('mesa/cenas/', views.lista_cenas, name='lista_cenas'),
    path('mesa/cenas/criar/', views.criar_cena, name='criar_cena'),
    path('mesa/cenas/<int:pk>/', views.detalhe_cena, name='detalhe_cena'),
    path('mesa/cenas/<int:pk>/excluir/', views.excluir_cena, name='excluir_cena'),
    path('mesa/cenas/<int:pk>/estado/', views.alterar_estado_cena, name='alterar_estado_cena'),
    path('mesa/cenas/<int:pk>/pistas/', views.adicionar_pista, name='adicionar_pista'),
    path(
        'mesa/cenas/<int:pk>/pistas/<int:pista_pk>/estado/',
        views.alterar_estado_pista,
        name='alterar_estado_pista',
    ),
    path('mesa/bestiario/', views.lista_ameacas, name='lista_ameacas'),
    path('mesa/bestiario/criar/', views.criar_ameaca, name='criar_ameaca'),
    path('mesa/bestiario/<int:pk>/editar/', views.editar_ameaca, name='editar_ameaca'),
    path('mesa/bestiario/<int:pk>/estado/', views.alterar_estado_ameaca, name='alterar_estado_ameaca'),
    path('mesa/mestre/nova-sessao/', views.iniciar_nova_sessao, name='iniciar_nova_sessao'),
    path('mesa/mestre/limpar-sessoes/', views.limpar_contagem_sessoes, name='limpar_contagem_sessoes'),
    path('mesa/mestre/atualizacoes/', views.atualizacoes_painel_mestre, name='painel_mestre_atualizacoes'),
    path('mesa/mestre/condicao-grupo/', views.aplicar_condicao_em_grupo, name='aplicar_condicao_grupo'),
    path('mesa/mestre/', views.painel_mestre, name='painel_mestre'),
]