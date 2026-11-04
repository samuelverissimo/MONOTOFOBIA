from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from fichas.permissions import fichas_visiveis_para


# Views privadas novas devem usar @login_required ou LoginRequiredMixin.
@login_required
def home(request):
    return render(request, 'home.html', {'fichas': fichas_visiveis_para(request.user)})
