(() => {
    const classe = document.querySelector('[name="classe"]');
    if (!classe) return;

    const progressao = document.querySelector('[data-wizard-progression]');
    const trilha = document.querySelector('[name="trilha"]');
    const estagio = document.querySelector('[name="estagio_inicial"]');
    const origem = document.querySelector('[name="origem"]');
    const intelecto = document.querySelector('[name="intelecto"]');
    const periciasAdicionais = document.querySelector('[data-additional-skills]');
    const quantidadePericias = document.querySelector('[data-pericia-choice-count]');
    const survivorFields = document.querySelector('[data-wizard-survivor]');
    const stageFiveFields = document.querySelector('[data-wizard-stage-five]');

    function definirDisponibilidade(container, visivel) {
        if (!container) return;
        container.hidden = !visivel;
        container.querySelectorAll('input, select, textarea').forEach((campo) => {
            campo.disabled = !visivel;
        });
    }

    function atualizarPericias() {
        const classeOpcao = classe.selectedOptions[0];
        const classeSlug = classeOpcao?.dataset.slug || '';
        const origemOpcao = origem?.selectedOptions[0];
        const origemIds = new Set(
            (origemOpcao?.dataset.originPericias || '').split(',').filter(Boolean),
        );
        const escolhas = periciasAdicionais?.querySelectorAll('input[type="checkbox"]') || [];
        escolhas.forEach((checkbox) => {
            const bloqueada = origemIds.has(checkbox.value);
            const label = checkbox.closest('label');
            if (bloqueada && checkbox.checked) checkbox.checked = false;
            checkbox.disabled = bloqueada;
            if (label) label.hidden = bloqueada;
        });

        if (quantidadePericias) {
            if (quantidadePericias.dataset.freeCreation === 'true') {
                quantidadePericias.textContent = (
                    'Criação livre: escolha as perícias que quiser; todas começam Treinadas.'
                );
            } else if (!classeSlug || !origemOpcao?.value) {
                quantidadePericias.textContent = 'Escolha classe e origem para ver quantas perícias selecionar.';
            } else {
                const base = Number(classeOpcao.dataset.periciasBase) || 0;
                const intelectoBase = Number(intelecto?.value) || 0;
                const escolhasOrigem = Number(origemOpcao?.dataset.originEscolhas) || 0;
                const total = base + intelectoBase + escolhasOrigem;
                quantidadePericias.textContent = `Escolha ${total} perícia${total === 1 ? '' : 's'} treinada${total === 1 ? '' : 's'}. As da origem já contam.`;
            }
        }
    }

    function atualizarCampos() {
        const slug = classe.selectedOptions[0]?.dataset.slug || '';
        const sobrevivente = slug === 'sobrevivente';

        definirDisponibilidade(progressao, !sobrevivente);
        definirDisponibilidade(survivorFields, sobrevivente);
        definirDisponibilidade(stageFiveFields, sobrevivente && estagio?.value === '5');

        if (trilha) {
            [...trilha.options].forEach((opcao) => {
                const disponivel = !opcao.value || opcao.dataset.classe === slug;
                opcao.hidden = !disponivel;
                opcao.disabled = !disponivel;
            });
            if (trilha.selectedOptions[0]?.disabled) trilha.value = '';
        }
        atualizarPericias();
    }

    classe.addEventListener('change', atualizarCampos);
    origem?.addEventListener('change', atualizarPericias);
    intelecto?.addEventListener('input', atualizarPericias);
    periciasAdicionais?.addEventListener('change', atualizarPericias);
    estagio?.addEventListener('change', atualizarCampos);
    atualizarCampos();
})();