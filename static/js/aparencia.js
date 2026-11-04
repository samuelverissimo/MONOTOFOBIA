(() => {
    const storageKey = 'monotofobia.aparencia';
    const defaultPreferences = { theme: 'dark', accent: 'jade', textScale: 100 };
    const accents = ['jade', 'blue', 'violet', 'ruby', 'amber'];
    const textScales = [90, 95, 100, 105, 110, 115, 120];
    const root = document.documentElement;
    let preferences = { ...defaultPreferences };
    let storageFeedback = '';

    function normalizePreferences(saved) {
        return {
            theme: saved?.theme === 'light' ? 'light' : 'dark',
            accent: accents.includes(saved?.accent) ? saved.accent : 'jade',
            textScale: textScales.includes(Number(saved?.textScale))
                ? Number(saved.textScale)
                : 100,
        };
    }

    try {
        const saved = window.localStorage.getItem(storageKey);
        if (saved) {
            try {
                preferences = normalizePreferences(JSON.parse(saved));
            } catch (error) {
                if (!(error instanceof SyntaxError)) throw error;
                window.localStorage.removeItem(storageKey);
                storageFeedback = 'As preferências salvas estavam inválidas; os padrões foram restaurados.';
            }
        }
    } catch (error) {
        storageFeedback = `Não foi possível ler as preferências salvas: ${error.message}`;
    }

    function applyPreferences() {
        root.dataset.theme = preferences.theme;
        root.dataset.accent = preferences.accent;
        root.dataset.textScale = String(preferences.textScale);
        const themeColor = document.querySelector('meta[name="theme-color"]');
        if (themeColor) themeColor.content = preferences.theme === 'light' ? '#edf7f0' : '#07140f';
    }

    applyPreferences();

    function initializeControls() {
        const panel = document.querySelector('[data-appearance-panel]');
        if (!panel) return;

        const feedback = panel.querySelector('[data-appearance-feedback]');
        const colorChoice = panel.querySelector('[data-accent-choice]');
        const textScale = panel.querySelector('[data-text-scale-control]');
        const textScaleValue = panel.querySelector('[data-text-scale-value]');

        function synchronizeControls() {
            panel.querySelectorAll('[data-theme-choice]').forEach((choice) => {
                choice.checked = choice.value === preferences.theme;
            });
            colorChoice.value = preferences.accent;
            textScale.value = preferences.textScale;
            textScaleValue.value = `${preferences.textScale}%`;
            textScaleValue.textContent = `${preferences.textScale}%`;
        }

        function savePreferences() {
            applyPreferences();
            synchronizeControls();
            try {
                window.localStorage.setItem(storageKey, JSON.stringify(preferences));
                feedback.textContent = 'Preferências salvas neste dispositivo.';
                return true;
            } catch (error) {
                feedback.textContent = `Preferências aplicadas apenas nesta sessão: ${error.message}`;
                return false;
            }
        }

        panel.querySelectorAll('[data-theme-choice]').forEach((choice) => {
            choice.addEventListener('change', () => {
                if (!choice.checked) return;
                preferences.theme = choice.value;
                savePreferences();
            });
        });
        colorChoice.addEventListener('change', () => {
            preferences.accent = colorChoice.value;
            savePreferences();
        });
        textScale.addEventListener('input', () => {
            preferences.textScale = Number(textScale.value);
            savePreferences();
        });
        panel.querySelector('[data-reset-appearance]').addEventListener('click', () => {
            preferences = { ...defaultPreferences };
            if (savePreferences()) feedback.textContent = 'Aparência padrão restaurada.';
        });

        synchronizeControls();
        if (storageFeedback) feedback.textContent = storageFeedback;
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeControls, { once: true });
    } else {
        initializeControls();
    }
})();
