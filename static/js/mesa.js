(() => {
    const painel = document.querySelector('[data-master-dashboard]');
    if (!painel) return;

    const resumo = painel.querySelector('[data-master-summary]');
    const fichas = painel.querySelector('[data-master-sheet-list]');
    const rolagens = painel.querySelector('[data-master-roll-list]');
    const feedback = painel.querySelector('[data-master-feedback]');
    let cursor = Number(painel.dataset.rollCursor) || 0;
    let atualizacaoEmAndamento = false;

    function atualizarContagens(contagens) {
        resumo.replaceChildren();
        for (const contagem of contagens) {
            const item = document.createElement('li');
            item.dataset.statusCount = contagem.valor;
            item.textContent = `${contagem.rotulo}: ${contagem.total}`;
            resumo.append(item);
        }
    }

    function atualizarFichas(lista) {
        fichas.replaceChildren();
        if (!lista.length) {
            const vazio = document.createElement('li');
            vazio.textContent = 'Nenhuma ficha cadastrada.';
            fichas.append(vazio);
            return;
        }
        for (const ficha of lista) {
            const item = document.createElement('li');
            item.dataset.masterSheet = ficha.id;
            if (ficha.status === 'Ativa') {
                const rotulo = document.createElement('label');
                const caixa = document.createElement('input');
                caixa.type = 'checkbox';
                caixa.name = 'fichas';
                caixa.value = ficha.id;
                rotulo.append(caixa, document.createTextNode(' Selecionar'));
                item.append(rotulo);
            }
            const link = document.createElement('a');
            link.href = `/fichas/${ficha.id}/`;
            link.textContent = ficha.nome;
            const detalhe = document.createElement('span');
            detalhe.textContent = `${ficha.jogador} · ${ficha.classe} · ${ficha.status}`;
            item.append(link, detalhe);
            fichas.append(item);
        }
    }

    function criarLinhaRolagem(rolagem) {
        const item = document.createElement('li');
        item.dataset.masterRoll = rolagem.id;
        const resultado = document.createElement('span');
        resultado.textContent = `${rolagem.ficha} · ${rolagem.descricao} · [${rolagem.dados.join(', ')}] ${rolagem.bonus >= 0 ? '+' : ''}${rolagem.bonus} = ${rolagem.total}`;
        const detalhe = document.createElement('span');
        detalhe.className = 'muted';
        const data = new Date(rolagem.criada_em).toLocaleString('pt-BR');
        detalhe.textContent = `${rolagem.usuario} · ${data}${rolagem.secreta ? ' · Secreta' : ''}`;
        item.append(resultado, detalhe);
        return item;
    }

    function anexarRolagens(lista) {
        if (lista.length) rolagens.querySelector('[data-empty-rolls]')?.remove();
        const idsExistentes = new Set(
            [...rolagens.querySelectorAll('[data-master-roll]')].map((item) => item.dataset.masterRoll),
        );
        for (const rolagem of lista) {
            if (!idsExistentes.has(String(rolagem.id))) {
                rolagens.prepend(criarLinhaRolagem(rolagem));
            }
        }
        while (rolagens.children.length > 25) rolagens.lastElementChild.remove();
    }

    async function atualizarPainel() {
        if (atualizacaoEmAndamento || document.visibilityState === 'hidden') return;
        atualizacaoEmAndamento = true;
        try {
            const url = new URL(painel.dataset.pollUrl, window.location.origin);
            url.searchParams.set('desde', String(cursor));
            const resposta = await fetch(url, {
                credentials: 'same-origin',
                headers: { Accept: 'application/json' },
            });
            const conteudo = await resposta.json();
            if (!resposta.ok) throw new Error(conteudo.erro || 'Não foi possível atualizar o painel do mestre.');
            atualizarContagens(conteudo.contagens_status);
            atualizarFichas(conteudo.fichas);
            anexarRolagens(conteudo.rolagens);
            cursor = conteudo.cursor;
            painel.dataset.rollCursor = String(cursor);
            feedback.textContent = '';
        } catch (erro) {
            feedback.textContent = erro.message;
        } finally {
            atualizacaoEmAndamento = false;
        }
    }

    if (painel.dataset.pollEnabled === 'true') {
        window.setInterval(atualizarPainel, 5000);
    }
})();
