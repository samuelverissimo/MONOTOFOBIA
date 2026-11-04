from django.urls import path

from . import views

app_name = 'fichas'

urlpatterns = [
    path('criar/', views.iniciar_criacao, name='iniciar'),
    path('criar/<int:etapa>/', views.criar_ficha, name='criar'),
    path('<int:pk>/recursos/', views.alterar_recurso, name='recurso'),
    path('<int:pk>/condicoes/', views.alterar_condicao, name='condicao'),
    path('<int:pk>/rolar/', views.rolar_ficha, name='rolar'),
    path('<int:pk>/avancar-nex/', views.avancar_nex, name='avancar_nex'),
    path('<int:pk>/inventario/adicionar/', views.adicionar_item, name='adicionar_item'),
    path('<int:pk>/inventario/<int:item_pk>/atualizar/', views.atualizar_item, name='atualizar_item'),
    path('<int:pk>/inventario/<int:item_pk>/remover/', views.remover_item, name='remover_item'),
    path('<int:pk>/', views.detalhe_ficha, name='detalhe'),
    path('<int:pk>/editar/', views.editar_ficha, name='editar'),
]