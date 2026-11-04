def is_mestre(user):
    return bool(user and user.is_authenticated and user.is_superuser)


def pode_ver_ficha(user, ficha):
    return bool(user and user.is_authenticated and (is_mestre(user) or ficha.dono_id == user.pk))


def pode_editar_ficha(user, ficha):
    return bool(user and user.is_authenticated and (is_mestre(user) or ficha.dono_id == user.pk))


def fichas_visiveis_para(user):
    from .models import Ficha

    if not user or not user.is_authenticated:
        return Ficha.objects.none()
    if is_mestre(user):
        return Ficha.objects.all()
    return Ficha.objects.filter(dono=user)