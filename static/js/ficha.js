(() => {
    const token = document.querySelector('meta[name="csrf-token"]')?.content;
    const feedback = document.querySelector('[data-feedback]');
    const fichaPath = window.location.pathname.replace(/\/$/, '');
    let operacoesPendentes = 0;
    let atualizarInstrucaoRolagem = () => {};
    let bloqueioTela = null;

    document.querySelectorAll(
        'details.skill-adjustment, details.ability-manager, details.ability-edit, '
        + 'details.delete-confirm',
    ).forEach((details) => {
        details.dataset.closeable = '';
        const close = document.createElement('button');
        close.type = 'button';
        close.className = 'subpanel-close';
        close.dataset.closeDetails = '';
        close.setAttribute('aria-label', 'Fechar painel');
        close.textContent = '×';
        details.append(close);
    });

    function fecharDetalhe(details) {
        if (!details?.open || details.classList.contains('is-closing')) return;
        details.classList.add('is-closing');
        window.setTimeout(() => {
            details.open = false;
            details.classList.remove('is-closing');
        }, 180);
    }

    document.addEventListener('click', (event) => {
        const summary = event.target.closest(
            'details.skill-adjustment > summary, details.ability-manager > summary, '
            + 'details.ability-edit > summary, details.track-upcoming > summary, '
            + 'details.delete-confirm > summary, details.roll-advanced > summary',
        );
        if (summary?.parentElement.open) {
            event.preventDefault();
            fecharDetalhe(summary.parentElement);
            return;
        }
        const close = event.target.closest('[data-close-details]');
        if (close) {
            event.preventDefault();
            fecharDetalhe(close.closest('details'));
            return;
        }
        const dismissPending = event.target.closest('[data-dismiss-pending]');
        if (dismissPending) {
            const pendencias = dismissPending.closest('.sheet-pending');
            if (pendencias) {
                try {
                    window.sessionStorage.setItem(
                        `monotofobia:pendencias:${pendencias.dataset.fichaId}`,
                        pendencias.dataset.pendingSignature,
                    );
                } catch {
                    // Storage may be disabled; dismissal still applies to this page.
                }
                pendencias.classList.add('is-leaving');
                window.setTimeout(() => { pendencias.hidden = true; }, 180);
            }
        }
    });

    const painelPendencias = document.querySelector('[data-pending-panel]');
    if (painelPendencias) {
        try {
            const assinaturaSalva = window.sessionStorage.getItem(
                `monotofobia:pendencias:${painelPendencias.dataset.fichaId}`,
            );
            if (assinaturaSalva === painelPendencias.dataset.pendingSignature) {
                painelPendencias.hidden = true;
            }
        } catch {
            // Storage may be disabled; keep the pending panel visible.
        }
    }

    function preencherCamposCatalogo(select, nomeCampo, descricaoCampo) {
        if (!select || !nomeCampo || !descricaoCampo) return;
        const opcao = select.selectedOptions[0];
        if (!opcao) {
            nomeCampo.value = '';
            descricaoCampo.value = '';
            return;
        }
        const nome = opcao.dataset.powerName || opcao.dataset.ritualName || '';
        const descricao = opcao.dataset.powerDescription || opcao.dataset.ritualDescription || '';
        nomeCampo.value = nome;
        descricaoCampo.value = descricao;
    }

    document.addEventListener('change', (event) => {
        const select = event.target.closest('[name="poder"], [name="ritual"]');
        if (!select) return;
        const form = select.closest('form');
        const nomeCampo = form?.querySelector('[name="nome_personalizado"]');
        const descricaoCampo = form?.querySelector('[name="resumo_personalizado"]');
        if (!nomeCampo || !descricaoCampo) return;
        if (select.value) {
            preencherCamposCatalogo(select, nomeCampo, descricaoCampo);
        }
    });

    function atualizarExcedente(recurso, atual, maximo) {
        const indicador = document.querySelector(`[data-overflow="${recurso}"]`);
        if (!indicador) return;
        const quantidade = Math.max(0, Number(atual) - Number(maximo));
        indicador.hidden = quantidade === 0;
        indicador.textContent = quantidade
            ? `${quantidade} temporário${quantidade === 1 ? '' : 's'}`
            : '';
    }

    function atualizarRecurso(resultado) {
        const atual = document.querySelector(`[data-current="${resultado.recurso}"]`);
        const maximo = document.querySelector(`[data-max="${resultado.recurso}"]`);
        if (atual) atual.textContent = resultado.atual;
        if (maximo && resultado.maximo !== null) maximo.textContent = resultado.maximo;
        atualizarExcedente(resultado.recurso, resultado.atual, resultado.maximo);
    }

    document.querySelectorAll('[data-overflow]').forEach((indicador) => {
        const recurso = indicador.dataset.overflow;
        const atual = document.querySelector(`[data-current="${recurso}"]`);
        const maximo = document.querySelector(`[data-max="${recurso}"]`);
        if (atual && maximo) atualizarExcedente(recurso, atual.textContent, maximo.textContent);
    });

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
        if (condicao.turnos_restantes !== null && condicao.turnos_restantes !== undefined) {
            const duracao = document.createElement('span');
            duracao.className = 'muted';
            duracao.dataset.conditionDuration = condicao.id;
            duracao.textContent = `Turnos restantes: ${condicao.turnos_restantes}.`;
            linha.append(duracao);
        }
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
                atualizarRecurso(resultado);
            } else if (adicionar || escalar || remover) {
                const seletor = document.querySelector('#condition-select');
                const campoDuracao = document.querySelector('#condition-turns');
                const lista = document.querySelector('[data-condition-list]');
                const acao = adicionar ? 'adicionar' : (escalar ? 'escalar' : 'remover');
                const id = adicionar
                    ? Number(seletor.value)
                    : Number((escalar || remover).dataset.conditionEscalate
                        || (escalar || remover).dataset.conditionRemove);
                if (!id) return;
                const dados = { acao, condicao: id };
                if (adicionar) {
                    if (campoDuracao?.value) {
                        const duracao = Number(campoDuracao.value);
                        if (!Number.isInteger(duracao) || duracao < 1 || duracao > 99) {
                            throw new Error('A duração deve ser de 1 a 99 turnos.');
                        }
                        dados.turnos_restantes = duracao;
                    } else {
                        dados.turnos_restantes = null;
                    }
                }
                const resultado = await enviar('condicoes', dados);
                if (adicionar && campoDuracao) campoDuracao.value = '';
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
                        turnos_restantes: resultado.turnos_restantes,
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

    const seletorFaces = document.querySelector('#damage-dice-faces');
    function atualizarDadoSelecionado() {
        if (!seletorFaces) return;
        document.querySelectorAll('[data-die-face]').forEach((botao) => {
            botao.setAttribute(
                'aria-pressed',
                String(botao.dataset.dieFace === seletorFaces.value),
            );
        });
    }

    document.addEventListener('click', (event) => {
        const dado = event.target.closest('[data-die-face]');
        if (!dado || !seletorFaces) return;
        seletorFaces.value = dado.dataset.dieFace;
        atualizarDadoSelecionado();
    });
    seletorFaces?.addEventListener('input', atualizarDadoSelecionado);
    seletorFaces?.addEventListener('change', atualizarDadoSelecionado);

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
            atualizarRecurso(resultado);
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
    const totalRolagem = document.querySelector('[data-roll-toast-total]');
    const equacaoRolagem = document.querySelector('[data-roll-toast-equation]');
    const bonusExtra = document.querySelector('#roll-bonus');
    const dadosExtras = document.querySelector('#roll-extra-dice');
    const dtInput = document.querySelector('#roll-dt');
    const instrucoes = document.querySelector('[data-roll-instructions]');
    const botaoRolagem = document.querySelector('[data-roll-submit]');
    const kitField = document.querySelector('[data-kit-field]');
    const kitCheckbox = document.querySelector('#roll-kit-available');
    const cicatrizadoField = document.querySelector('[data-cicatrizado-field]');
    const cicatrizadoCheckbox = document.querySelector('#roll-cicatrizado-perigo');
    let temporizadorToast = null;
    function ocultarToast() {
        if (!resultadoRolagem || resultadoRolagem.hidden) return;
        resultadoRolagem.classList.add('is-leaving');
        window.clearTimeout(temporizadorToast);
        temporizadorToast = window.setTimeout(() => {
            resultadoRolagem.hidden = true;
            resultadoRolagem.classList.remove('is-leaving');
        }, 180);
    }
    function mostrarToast(total, equacao, erro = false) {
        if (!resultadoRolagem || !totalRolagem || !equacaoRolagem) return;
        window.clearTimeout(temporizadorToast);
        resultadoRolagem.classList.remove('is-leaving');
        totalRolagem.textContent = total;
        equacaoRolagem.textContent = equacao;
        resultadoRolagem.dataset.error = String(erro);
        resultadoRolagem.hidden = false;
        temporizadorToast = window.setTimeout(() => {
            ocultarToast();
        }, 4800);
    }
    document.addEventListener('click', (event) => {
        const fechar = event.target.closest('[data-close-roll-toast]');
        if (!fechar || !resultadoRolagem) return;
        ocultarToast();
    });
    if (tipo && alvo && rolagem && bonusExtra && dadosExtras && instrucoes) {
        function ehTesteResistencia(opcao) {
            return tipo.value === 'pericia'
                && ['fortitude', 'reflexos', 'vontade'].includes(opcao.dataset.rollSlug);
        }

        function calcularPool() {
            const opcao = alvo.selectedOptions[0];
            if (!opcao) return { quantidade: 0, menor: false };

            if (tipo.value === 'livre') {
                const quantidade = Number(alvo.value) || 1;
                return { quantidade, menor: false };
            }

            const atributo = Number(opcao.dataset.attributeValue) || 0;
            const bonusDados = Number(dadosExtras.value) || 0;
            const dadosPericia = Number(opcao.dataset.skillExtraDice) || 0;
            const dadosCondicao = Number(opcao.dataset.conditionDice) || 0;
            const dadosFerimento = Number(opcao.dataset.woundDice) || 0;
            const extras = bonusDados + dadosPericia + dadosCondicao + dadosFerimento;

            if (atributo === 0) {
                const quantidade = 2 + extras;
                return {
                    quantidade: quantidade < 1 ? 2 + Math.abs(extras) : quantidade,
                    menor: true,
                };
            }

            const quantidade = atributo + extras;
            if (quantidade < 1) {
                return {
                    quantidade: atributo + Math.abs(extras),
                    menor: true,
                };
            }
            return { quantidade, menor: false };
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
            const bonusPericia = tipo.value === 'pericia'
                ? Number(opcao.dataset.skillModifier) || 0
                : 0;
            const kitRequired = tipo.value === 'pericia' && opcao.dataset.kitRequired === 'true';
            const penalidadeKit = kitRequired && !kitCheckbox.checked ? -5 : 0;
            const penalidadeCarga = tipo.value === 'pericia'
                ? Number(opcao.dataset.loadPenalty) || 0
                : 0;
            const bonus = bonusTreinamento + bonusPericia + penalidadeCarga + penalidadeKit
                + (Number(bonusExtra.value) || 0);
            const operador = bonus > 0 ? '+' : '';
            const instrucaoDados = menor ? 'use o menor' : 'use o maior';
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
            const detalhePericia = tipo.value === 'pericia'
                ? ` Treinamento ${bonusTreinamento >= 0 ? '+' : ''}${bonusTreinamento}; modificador da perícia ${bonusPericia >= 0 ? '+' : ''}${bonusPericia}.`
                : '';
            const resistencia = ehTesteResistencia(opcao);
            const modificadorCicatrizado = resistencia && cicatrizadoCheckbox?.checked
                ? ' Cicatrizado contra o perigo marcado: −1 dado.'
                : '';
            instrucoes.textContent = `${quantidade}d20; use o ${instrucaoDados}; some ${operador}${bonus}.${detalhePericia}${modificadorCondicao}${modificadorFerimento}${modificadorKit}${modificadorCarga}${modificadorCicatrizado}`;
            if (kitField) kitField.hidden = !kitRequired;
            if (cicatrizadoField) {
                cicatrizadoField.hidden = !resistencia;
                if (!resistencia && cicatrizadoCheckbox) cicatrizadoCheckbox.checked = false;
            }
            if (botaoRolagem) {
                botaoRolagem.textContent = `Rolar teste de ${opcao.textContent.trim().split(' (')[0]}`;
            }
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
        document.addEventListener('click', (event) => {
            const disparador = event.target.closest('[data-roll-trigger]');
            if (!disparador || disparador.disabled) return;
            tipo.value = disparador.dataset.rollType;
            tipo.dispatchEvent(new Event('change', { bubbles: true }));
            alvo.value = disparador.dataset.rollTarget;
            alvo.dispatchEvent(new Event('change', { bubbles: true }));
            rolagem.requestSubmit();
        });
        atualizarInstrucaoRolagem = atualizarInstrucao;
        tipo.addEventListener('change', () => {
            if (kitCheckbox) kitCheckbox.checked = true;
            filtrarAlvos();
        });
        alvo.addEventListener('change', () => {
            if (kitCheckbox) {
                kitCheckbox.checked = alvo.selectedOptions[0]?.dataset.kitRequired === 'true';
            }
            atualizarInstrucao();
        });
        bonusExtra.addEventListener('input', atualizarInstrucao);
        dadosExtras.addEventListener('input', atualizarInstrucao);
        kitCheckbox?.addEventListener('change', atualizarInstrucao);
        cicatrizadoCheckbox?.addEventListener('change', atualizarInstrucao);
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
                const dt = dtInput?.value.trim();
                if (dt) dados.dt = Number(dt);
                const conteudo = await enviar('rolar', dados);
                const opcaoAlvo = alvo.selectedOptions[0];
                const nomeAlvo = (tipo.value === 'atributo'
                    ? opcaoAlvo?.dataset.attributeName
                    : opcaoAlvo?.textContent.trim().split(' (')[0])
                    || 'Teste';
                const textoBonus = conteudo.bonus
                    ? ` ${conteudo.bonus >= 0 ? '+' : '−'} ${Math.abs(conteudo.bonus)}`
                    : '';
                const textoDt = conteudo.dt !== null
                    ? (conteudo.sucesso ? ` · Sucesso DT ${conteudo.dt}` : ` · Falha DT ${conteudo.dt}`)
                    : '';
                const equacao = `${nomeAlvo} · ${conteudo.quantidade_dados}d20${textoBonus} → `
                    + `${conteudo.dados.join(', ')} → ${conteudo.dado_escolhido}${textoBonus} = ${conteudo.total}${textoDt}`;
                mostrarToast(String(conteudo.total), equacao, Boolean(conteudo.dt !== null && !conteudo.sucesso));
            } catch (erro) {
                mostrarToast('Não rolou', erro.message, true);
            }
        });
    }

    const formularioDano = document.querySelector('[data-damage-form]');
    if (formularioDano) {
        formularioDano.addEventListener('submit', async (event) => {
            event.preventDefault();
            try {
                const dadosFormulario = new FormData(formularioDano);
                const dados = {
                    quantidade_dados: Number(dadosFormulario.get('quantidade_dados')),
                    faces: Number(dadosFormulario.get('faces')),
                    bonus: Number(dadosFormulario.get('bonus')),
                    multiplicador_critico: 1,
                };
                const conteudo = await enviar('dano', dados);
                const textoBonus = conteudo.bonus
                    ? ` ${conteudo.bonus >= 0 ? '+' : '−'} ${Math.abs(conteudo.bonus)}`
                    : '';
                mostrarToast(
                    String(conteudo.total),
                    `${conteudo.descricao}: [${conteudo.dados.join(', ')}]${textoBonus} = ${conteudo.total}`,
                );
            } catch (erro) {
                mostrarToast('Não rolou', erro.message, true);
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
                    if (Object.prototype.hasOwnProperty.call(estado.recursos, recurso)) {
                        atualizarExcedente(recurso, estado.recursos[recurso], maximo);
                    }
                }
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