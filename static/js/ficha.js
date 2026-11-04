(() => {
    const token = document.querySelector('meta[name="csrf-token"]')?.content;
    const feedback = document.querySelector('[data-feedback]');
    const fichaPath = window.location.pathname.replace(/\/$/, '');
    let operacoesPendentes = 0;
    let atualizarInstrucaoRolagem = () => {};
    let bloqueioTela = null;

    async function enviar(endpoint, dados) {
        operacoesPendentes += 1;
        try {
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
        } finally {
            operacoesPendentes -= 1;
        }
    }

    function linhaCondicao(condicao, lista) {
        const linha = document.createElement('li');
        linha.dataset.activeCondition = condicao.id;
        const nome = document.createElement('strong');
        nome.textContent = condicao.nome;
        const resumo = document.createElement('span');
        resumo.className = 'muted';
        resumo.textContent = condicao.resumo;
        linha.append(nome, resumo);
        if (lista.dataset.canEdit === 'true') {
            if (condicao.proxima_escalada) {
                const escalar = document.createElement('button');
                escalar.type = 'button';
                escalar.className = 'button button-secondary';
                escalar.dataset.conditionEscalate = condicao.id;
                escalar.textContent = `Escalar para ${condicao.proxima_escalada.nome}`;
                linha.append(escalar);
            }
            const remover = document.createElement('button');
            remover.type = 'button';
            remover.className = 'button button-secondary';
            remover.dataset.conditionRemove = condicao.id;
            remover.textContent = 'Remover';
            linha.append(remover);
        }
        return linha;
    }

    function adicionarOpcaoCondicao(select, condicao) {
        if (!select || [...select.options].some((opcao) => opcao.value === String(condicao.id))) return;
        const opcao = document.createElement('option');
        opcao.value = condicao.id;
        opcao.textContent = condicao.nome;
        select.append(opcao);
    }

    document.addEventListener('click', async (event) => {
        const recurso = event.target.closest('[data-resource]');
        const adicionar = event.target.closest('[data-condition-add]');
        const escalar = event.target.closest('[data-condition-escalate]');
        const remover = event.target.closest('[data-condition-remove]');
        try {
            if (recurso) {
                const resultado = await enviar('recursos', {
                    recurso: recurso.dataset.resource,
                    delta: Number(recurso.dataset.delta),
                });
                const atual = document.querySelector(`[data-current="${resultado.recurso}"]`);
                const maximo = document.querySelector(`[data-max="${resultado.recurso}"]`);
                if (atual) atual.textContent = resultado.atual;
                if (maximo && resultado.maximo !== null) maximo.textContent = resultado.maximo;
                if (resultado.pv_temporario !== null) {
                    const temporario = document.querySelector('[data-current="pv_temporario"]');
                    if (temporario) temporario.textContent = resultado.pv_temporario;
                }
            } else if (adicionar || escalar || remover) {
                const seletor = document.querySelector('#condition-select');
                const lista = document.querySelector('[data-condition-list]');
                const acao = adicionar ? 'adicionar' : (escalar ? 'escalar' : 'remover');
                const id = adicionar
                    ? Number(seletor.value)
                    : Number((escalar || remover).dataset.conditionEscalate
                        || (escalar || remover).dataset.conditionRemove);
                if (!id) return;
                const resultado = await enviar('condicoes', { acao, condicao: id });
                if (resultado.removida) {
                    document.querySelector(`[data-active-condition="${resultado.removida.id}"]`)?.remove();
                    adicionarOpcaoCondicao(seletor, resultado.removida);
                } else if (acao === 'remover') {
                    const linha = document.querySelector(`[data-active-condition="${resultado.condicao}"]`);
                    adicionarOpcaoCondicao(seletor, {
                        id: resultado.condicao,
                        nome: linha.querySelector('strong').textContent,
                    });
                    linha.remove();
                }
                if (resultado.ativa
                    && !document.querySelector(`[data-active-condition="${resultado.condicao}"]`)) {
                    document.querySelector('[data-empty-conditions]')?.remove();
                    lista.append(linhaCondicao({
                        id: resultado.condicao,
                        nome: resultado.nome,
                        resumo: resultado.resumo,
                        proxima_escalada: resultado.proxima_escalada,
                    }, lista));
                    seletor?.querySelector(`option[value="${resultado.condicao}"]`)?.remove();
                }
            }
            if (feedback) feedback.textContent = '';
        } catch (erro) {
            if (feedback) feedback.textContent = erro.message;
        }
    });

    document.addEventListener('submit', async (event) => {
        const formulario = event.target.closest('[data-resource-adjustment]');
        if (!formulario) return;
        event.preventDefault();
        const campo = formulario.elements.namedItem('delta');
        const delta = Number(campo.value);
        const recurso = formulario.dataset.resourceAdjustment;
        if (!Number.isInteger(delta) || Math.abs(delta) > 1000) {
            if (feedback) feedback.textContent = 'Informe um ajuste inteiro entre −1000 e 1000.';
            return;
        }
        try {
            const resultado = await enviar('recursos', { recurso, delta });
            const atual = document.querySelector(`[data-current="${resultado.recurso}"]`);
            const maximo = document.querySelector(`[data-max="${resultado.recurso}"]`);
            if (atual) atual.textContent = resultado.atual;
            if (maximo && resultado.maximo !== null) maximo.textContent = resultado.maximo;
            if (resultado.pv_temporario !== null) {
                const temporario = document.querySelector('[data-current="pv_temporario"]');
                if (temporario) temporario.textContent = resultado.pv_temporario;
            }
            campo.value = '';
            if (feedback) feedback.textContent = '';
        } catch (erro) {
            if (feedback) feedback.textContent = erro.message;
        }
    });

    const modoSessao = document.querySelector('[data-session-mode-toggle]');
    if (modoSessao) {
        modoSessao.addEventListener('change', () => {
            document.documentElement.classList.toggle('session-mode', modoSessao.checked);
        });
    }

    const alternarTelaAcesa = document.querySelector('[data-wake-lock-toggle]');
    const retornoSessao = document.querySelector('[data-session-feedback]');
    if (alternarTelaAcesa) {
        async function solicitarBloqueioTela() {
            if (!('wakeLock' in navigator)) {
                alternarTelaAcesa.checked = false;
                retornoSessao.textContent = 'Este navegador não oferece a função de manter a tela acesa.';
                return;
            }
            try {
                bloqueioTela = await navigator.wakeLock.request('screen');
                retornoSessao.textContent = 'A tela ficará ativa enquanto esta página estiver visível.';
                bloqueioTela.addEventListener('release', () => {
                    bloqueioTela = null;
                    if (document.visibilityState === 'visible' && alternarTelaAcesa.checked) {
                        solicitarBloqueioTela();
                    }
                }, { once: true });
            } catch (erro) {
                alternarTelaAcesa.checked = false;
                retornoSessao.textContent = `Não foi possível manter a tela ativa: ${erro.message}`;
            }
        }

        alternarTelaAcesa.addEventListener('change', async () => {
            if (alternarTelaAcesa.checked) {
                await solicitarBloqueioTela();
            } else {
                if (bloqueioTela) await bloqueioTela.release();
                bloqueioTela = null;
                retornoSessao.textContent = 'Manter a tela acesa está desligado.';
            }
        });
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible'
                && alternarTelaAcesa.checked && !bloqueioTela) {
                solicitarBloqueioTela();
            }
        });
    }

    const tipo = document.querySelector('#roll-type');
    const alvo = document.querySelector('#roll-target');
    const rolagem = document.querySelector('[data-roll-form]');
    const resultadoRolagem = document.querySelector('[data-roll-result]');
    const modo = document.querySelector('#roll-mode');
    const bonusExtra = document.querySelector('#roll-bonus');
    const dadosExtras = document.querySelector('#roll-extra-dice');
    const dadosFisicos = document.querySelector('#roll-physical-dice');
    const dtInput = document.querySelector('#roll-dt');
    const instrucoes = document.querySelector('[data-roll-instructions]');
    const camposFisicos = document.querySelector('[data-physical-fields]');
    const botaoRolagem = document.querySelector('[data-roll-submit]');
    const kitField = document.querySelector('[data-kit-field]');
    const kitCheckbox = document.querySelector('#roll-kit-available');
    const cicatrizadoField = document.querySelector('[data-cicatrizado-field]');
    const cicatrizadoCheckbox = document.querySelector('#roll-cicatrizado-perigo');
    if (tipo && alvo && rolagem && modo && bonusExtra && dadosExtras && instrucoes) {
        function ehTesteResistencia(opcao) {
            return tipo.value === 'pericia'
                && ['fortitude', 'reflexos', 'vontade'].includes(opcao.dataset.rollSlug);
        }

        function calcularPool() {
            const opcao = alvo.selectedOptions[0];
            const bonusDados = Number(dadosExtras.value) || 0;
            const dadosCondicao = tipo.value === 'livre' ? 0 : Number(opcao.dataset.conditionDice) || 0;
            const dadosFerimento = tipo.value === 'livre' ? 0 : Number(opcao.dataset.woundDice) || 0;
            const atributo = tipo.value === 'livre' ? 1 : Number(opcao.dataset.attributeValue);
            const penalidadeCicatrizado = ehTesteResistencia(opcao) && cicatrizadoCheckbox?.checked
                ? -1
                : 0;
            const extras = tipo.value === 'livre'
                ? Number(alvo.value) - 1 + bonusDados + dadosCondicao
                : bonusDados + dadosCondicao + dadosFerimento + penalidadeCicatrizado;
            let quantidade;
            let menor;
            if (atributo === 0) {
                quantidade = 2 + extras;
                quantidade = quantidade < 1 ? 2 + Math.abs(extras) : quantidade;
                menor = true;
            } else {
                quantidade = atributo + extras;
                if (quantidade < 1) {
                    quantidade = atributo + Math.abs(extras);
                    menor = true;
                } else {
                    menor = false;
                }
            }
            return { quantidade, menor };
        }

        function atualizarInstrucao() {
            const opcao = alvo.selectedOptions[0];
            if (!opcao || opcao.disabled) {
                instrucoes.textContent = 'Escolha uma perícia que possa ser usada.';
                return;
            }
            const { quantidade, menor } = calcularPool();
            const bonusTreinamento = tipo.value === 'pericia'
                ? Number(opcao.dataset.trainingBonus)
                : 0;
            const kitRequired = tipo.value === 'pericia' && opcao.dataset.kitRequired === 'true';
            const penalidadeKit = kitRequired && !kitCheckbox.checked ? -5 : 0;
            const penalidadeCarga = tipo.value === 'pericia'
                ? Number(opcao.dataset.loadPenalty) || 0
                : 0;
            const bonus = bonusTreinamento + penalidadeCarga + penalidadeKit
                + (Number(bonusExtra.value) || 0);
            const operador = bonus > 0 ? '+' : '';
            const instrucaoDados = menor ? 'use o menor' : 'use o maior';
            const atributoTexto = tipo.value === 'livre'
                ? 'dados livres'
                : `atributo-base ${opcao.dataset.attributeName}`;
            const condicao = Number(opcao.dataset.conditionDice) || 0;
            const ferimento = Number(opcao.dataset.woundDice) || 0;
            const modificadorCondicao = tipo.value !== 'livre' && condicao
                ? ` Condições: ${condicao > 0 ? '+' : ''}${condicao} dado(s).`
                : '';
            const modificadorFerimento = tipo.value !== 'livre' && ferimento
                ? ` Ferimentos debilitantes: ${ferimento} dado(s).`
                : '';
            const modificadorKit = penalidadeKit ? ' Sem kit adequado: −5.' : '';
            const modificadorCarga = penalidadeCarga ? ' Sobrecarga: −5.' : '';
            const resistencia = ehTesteResistencia(opcao);
            const modificadorCicatrizado = resistencia && cicatrizadoCheckbox?.checked
                ? ' Cicatrizado contra o perigo marcado: −1 dado.'
                : '';
            instrucoes.textContent = `Role ${quantidade}d20; ${instrucaoDados}; ${atributoTexto}; depois some ${operador}${bonus}.${modificadorCondicao}${modificadorFerimento}${modificadorKit}${modificadorCarga}${modificadorCicatrizado}`;
            if (kitField) kitField.hidden = !kitRequired;
            if (cicatrizadoField) {
                cicatrizadoField.hidden = !resistencia;
                if (!resistencia && cicatrizadoCheckbox) cicatrizadoCheckbox.checked = false;
            }
            if (botaoRolagem) {
                botaoRolagem.textContent = modo.value === 'fisico'
                    ? 'Avaliar dados físicos'
                    : 'Rolar no site';
            }
            if (camposFisicos) camposFisicos.hidden = modo.value !== 'fisico';
        }

        function filtrarAlvos() {
            for (const opcao of alvo.options) {
                opcao.hidden = opcao.dataset.rollFor !== tipo.value;
            }
            const primeira = [...alvo.options].find((opcao) => !opcao.hidden && !opcao.disabled);
            if (primeira) alvo.value = primeira.value;
            else alvo.selectedIndex = -1;
            atualizarInstrucao();
        }
        atualizarInstrucaoRolagem = atualizarInstrucao;
        tipo.addEventListener('change', () => {
            if (kitCheckbox) kitCheckbox.checked = false;
            filtrarAlvos();
        });
        alvo.addEventListener('change', () => {
            if (kitCheckbox) kitCheckbox.checked = false;
            atualizarInstrucao();
        });
        bonusExtra.addEventListener('input', atualizarInstrucao);
        dadosExtras.addEventListener('input', atualizarInstrucao);
        kitCheckbox?.addEventListener('change', atualizarInstrucao);
        cicatrizadoCheckbox?.addEventListener('change', atualizarInstrucao);
        modo.addEventListener('change', atualizarInstrucao);
        filtrarAlvos();
        rolagem.addEventListener('submit', async (event) => {
            event.preventDefault();
            try {
                const dados = {
                    tipo: tipo.value,
                    alvo: tipo.value === 'atributo' ? alvo.value : Number(alvo.value),
                    bonus: Number(new FormData(rolagem).get('bonus')),
                    dados_extras: Number(dadosExtras.value),
                };
                if (tipo.value === 'pericia' && alvo.selectedOptions[0].dataset.kitRequired === 'true') {
                    dados.kit_disponivel = kitCheckbox.checked;
                }
                if (cicatrizadoCheckbox?.checked) {
                    dados.perigo_cicatrizado = cicatrizadoCheckbox.dataset.cicatrizadoDanger;
                }
                if (modo.value === 'fisico') {
                    const valores = dadosFisicos.value.trim().split(/[,\s]+/).filter(Boolean);
                    if (!valores.length || valores.some((valor) => !/^\d+$/.test(valor))) {
                        throw new Error('Digite os resultados dos d20 físicos, separados por espaço ou vírgula.');
                    }
                    dados.dados_fisicos = valores.map(Number);
                    const dt = dtInput.value.trim();
                    dados.dt = dt ? Number(dt) : null;
                    const { quantidade } = calcularPool();
                    if (dados.dados_fisicos.length !== quantidade) {
                        throw new Error(`Este teste exige exatamente ${quantidade} resultado(s) de d20.`);
                    }
                }
                const conteudo = await enviar('rolar', dados);
                const ordem = conteudo.ordem === 'menor' ? 'menor' : 'maior';
                let resultado = `${conteudo.descricao}: [${conteudo.dados.join(', ')}]; ${ordem} ${conteudo.dado_escolhido} ${conteudo.bonus >= 0 ? '+' : ''}${conteudo.bonus} = ${conteudo.total}.`;
                if (Array.isArray(conteudo.detalhamento)) {
                    resultado += ` ${conteudo.detalhamento.join('; ')}.`;
                }
                if (conteudo.dt !== null) {
                    resultado += conteudo.sucesso ? ` Sucesso contra DT ${conteudo.dt}.` : ` Não alcançou a DT ${conteudo.dt}.`;
                }
                resultadoRolagem.textContent = resultado;
            } catch (erro) {
                resultadoRolagem.textContent = erro.message;
            }
        });
    }

    const formularioDano = document.querySelector('[data-damage-form]');
    const resultadoDano = document.querySelector('[data-damage-result]');
    if (formularioDano && resultadoDano) {
        formularioDano.addEventListener('submit', async (event) => {
            event.preventDefault();
            try {
                const dadosFormulario = new FormData(formularioDano);
                const dados = {
                    quantidade_dados: Number(dadosFormulario.get('quantidade_dados')),
                    faces: Number(dadosFormulario.get('faces')),
                    bonus: Number(dadosFormulario.get('bonus')),
                    multiplicador_critico: Number(dadosFormulario.get('multiplicador_critico')),
                };
                const modoDano = dadosFormulario.get('modo');
                if (modoDano === 'fisico') {
                    const valores = String(dadosFormulario.get('dados_fisicos') || '')
                        .trim().split(/[,\s]+/).filter(Boolean);
                    if (!valores.length || valores.some((valor) => !/^\d+$/.test(valor))) {
                        throw new Error('Digite os resultados físicos separados por espaço ou vírgula.');
                    }
                    dados.dados_fisicos = valores.map(Number);
                }
                const conteudo = await enviar('dano', dados);
                resultadoDano.textContent = `${conteudo.descricao}: [${conteudo.dados.join(', ')}]; `
                    + `${conteudo.bonus >= 0 ? '+' : ''}${conteudo.bonus} = ${conteudo.total}.`;
            } catch (erro) {
                resultadoDano.textContent = erro.message;
            }
        });
    }

    const listaCondicoes = document.querySelector('[data-condition-list]');
    if (listaCondicoes) {
        async function atualizarEstadoFicha() {
            if (document.visibilityState === 'hidden' || operacoesPendentes) return;
            try {
                const resposta = await fetch(`${fichaPath}/atualizacoes/`, {
                    credentials: 'same-origin',
                    headers: { Accept: 'application/json' },
                });
                if (!resposta.ok) throw new Error('Não foi possível atualizar o estado da ficha.');
                const estado = await resposta.json();
                if (operacoesPendentes) return;
                const painelRecursos = document.querySelector('[data-resource-mode]');
                if (painelRecursos && painelRecursos.dataset.resourceMode !== estado.modo_recursos) {
                    window.location.reload();
                    return;
                }
                for (const [recurso, atual] of Object.entries(estado.recursos)) {
                    const saida = document.querySelector(`[data-current="${recurso}"]`);
                    if (saida) saida.textContent = atual;
                }
                for (const [recurso, maximo] of Object.entries(estado.maximos)) {
                    const saida = document.querySelector(`[data-max="${recurso}"]`);
                    if (saida) saida.textContent = maximo;
                }
                const pvTemporario = document.querySelector('[data-current="pv_temporario"]');
                if (pvTemporario) pvTemporario.textContent = estado.pv_temporario;
                const defesa = document.querySelector('[data-defense]');
                if (defesa) defesa.textContent = estado.defesa;
                for (const modificador of estado.alvos_rolagem) {
                    const opcao = [...(alvo?.options || [])].find((item) =>
                        item.dataset.rollFor === modificador.tipo
                        && item.value === String(modificador.id));
                    if (opcao) {
                        opcao.dataset.conditionDice = modificador.dados_condicao;
                        opcao.dataset.loadPenalty = modificador.penalidade_carga;
                        opcao.dataset.woundDice = modificador.dados_ferimentos;
                    }
                }
                if (alvo?.selectedOptions.length) atualizarInstrucaoRolagem();

                listaCondicoes.replaceChildren();
                if (!estado.condicoes.length) {
                    const vazio = document.createElement('li');
                    vazio.dataset.emptyConditions = '';
                    vazio.textContent = 'Nenhuma condição ativa.';
                    listaCondicoes.append(vazio);
                }
                for (const condicao of estado.condicoes) {
                    listaCondicoes.append(linhaCondicao(condicao, listaCondicoes));
                }

                const seletor = document.querySelector('#condition-select');
                if (seletor) {
                    const selecionada = seletor.value;
                    seletor.replaceChildren();
                    for (const condicao of estado.condicoes_disponiveis) {
                        const opcao = document.createElement('option');
                        opcao.value = condicao.pk;
                        opcao.textContent = condicao.nome;
                        seletor.append(opcao);
                    }
                    if ([...seletor.options].some((opcao) => opcao.value === selecionada)) {
                        seletor.value = selecionada;
                    }
                }
            } catch (erro) {
                if (feedback) feedback.textContent = erro.message;
            }
        }
        window.setInterval(atualizarEstadoFicha, 30000);
    }
})();