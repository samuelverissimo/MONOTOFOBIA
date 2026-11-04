from django.urls import path

from . import views

app_name = 'fichas'

urlpatterns = [
    path('criar/', views.iniciar_criacao, name='iniciar'),
    path('criar/<int:etapa>/', views.criar_ficha, name='criar'),
    path('<int:pk>/recursos/', views.alterar_recurso, name='recurso'),
    path('<int:pk>/condicoes/', views.alterar_condicao, name='condicao'),
    path('<int:pk>/rolar/', views.rolar_ficha, name='rolar'),
    path('<int:pk>/', views.detalhe_ficha, name='detalhe'),
    path('<int:pk>/editar/', views.editar_ficha, name='editar'),
]