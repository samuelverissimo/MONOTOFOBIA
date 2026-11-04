(() => {
    const token = document.querySelector('input[name="csrfmiddlewaretoken"]')?.value;
    const feedback = document.querySelector('[data-feedback]');
    const fichaPath = window.location.pathname.replace(/\/$/, '');

    async function enviar(endpoint, dados) {
        const resposta = await fetch(`${fichaPath}/${endpoint}/`, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': token,
            },
            body: JSON.stringify(dados),
        });
        const conteudo = await resposta.json();
        if (!resposta.ok) throw new Error(conteudo.erro || 'Não foi possível concluir a operação.');
        return conteudo;
    }

    document.addEventListener('click', async (event) => {
        const recurso = event.target.closest('[data-resource]');
        const adicionar = event.target.closest('[data-condition-add]');
        const remover = event.target.closest('[data-condition-remove]');
        try {
            if (recurso) {
                const resultado = await enviar('recursos', {
                    recurso: recurso.dataset.resource,
                    delta: Number(recurso.dataset.delta),
                });
                document.querySelector(`[data-current="${resultado.recurso}"]`).textContent = resultado.atual;
                document.querySelector(`[data-max="${resultado.recurso}"]`).textContent = resultado.maximo;
            } else if (adicionar) {
                const seletor = document.querySelector('#condition-select');
                if (!seletor.value) return;
                const resultado = await enviar('condicoes', {
                    acao: 'adicionar', condicao: Number(seletor.value),
                });
                const nome = seletor.selectedOptions[0].textContent;
                const linha = document.createElement('li');
                linha.dataset.activeCondition = resultado.condicao;
                linha.append(document.createTextNode(`${nome} `));
                const botao = document.createElement('button');
                botao.type = 'button';
                botao.className = 'button button-secondary';
                botao.dataset.conditionRemove = resultado.condicao;
                botao.textContent = 'Remover';
                linha.append(botao);
                document.querySelector('[data-empty-conditions]')?.remove();
                document.querySelector('[data-condition-list]').append(linha);
                seletor.selectedOptions[0].remove();
            } else if (remover) {
                const resultado = await enviar('condicoes', {
                    acao: 'remover', condicao: Number(remover.dataset.conditionRemove),
                });
                const linha = document.querySelector(`[data-active-condition="${resultado.condicao}"]`);
                const opcao = document.createElement('option');
                opcao.value = resultado.condicao;
                opcao.textContent = linha.firstChild.textContent.trim();
                document.querySelector('#condition-select').append(opcao);
                linha.remove();
            }
            if (feedback) feedback.textContent = '';
        } catch (erro) {
            if (feedback) feedback.textContent = erro.message;
        }
    });

    const tipo = document.querySelector('#roll-type');
    const alvo = document.querySelector('#roll-target');
    const rolagem = document.querySelector('[data-roll-form]');
    const resultadoRolagem = document.querySelector('[data-roll-result]');
    if (tipo && alvo && rolagem) {
        function filtrarAlvos() {
            for (const opcao of alvo.options) {
                opcao.hidden = opcao.dataset.rollFor !== tipo.value;
            }
            const primeira = [...alvo.options].find((opcao) => !opcao.hidden);
            if (primeira) alvo.value = primeira.value;
        }
        tipo.addEventListener('change', filtrarAlvos);
        filtrarAlvos();
        rolagem.addEventListener('submit', async (event) => {
            event.preventDefault();
            try {
                const conteudo = await enviar('rolar', {
                    tipo: tipo.value,
                    alvo: tipo.value === 'atributo' ? alvo.value : Number(alvo.value),
                    bonus: Number(new FormData(rolagem).get('bonus')),
                });
                resultadoRolagem.textContent = `${conteudo.descricao}: [${conteudo.dados.join(', ')}] = ${conteudo.total}`;
            } catch (erro) {
                resultadoRolagem.textContent = erro.message;
            }
        });
    }
})();