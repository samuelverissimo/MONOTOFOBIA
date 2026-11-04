from django.contrib import admin

from .models import (
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
)


class CatalogoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'slug', 'fonte', 'personalizado')
    search_fields = ('nome', 'slug', 'fonte')
    list_filter = ('personalizado',)

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


for modelo in (Atributo, Classe, Condicao, ItemCatalogo, Origem, Patente, Pericia, Poder, Ritual, Trilha):
    admin.site.register(modelo, CatalogoAdmin)