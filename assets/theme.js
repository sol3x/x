document.addEventListener('DOMContentLoaded', function () {
    const toggleBtn = document.getElementById('theme-toggle');
    const htmlRoot = document.documentElement;

    function applyTheme(theme) {
        if (theme === 'dark') {
            htmlRoot.setAttribute('data-theme', 'dark');
        } else {
            htmlRoot.removeAttribute('data-theme');
        }
        window.localStorage.setItem('theme', theme);
    }

    if (toggleBtn) {
        toggleBtn.addEventListener('click', () => {
            const currentTheme = document.documentElement.getAttribute('data-theme');
            applyTheme(currentTheme === 'dark' ? 'light' : 'dark');
        });
    }

    // Load saved theme
    const saved = window.localStorage.getItem('theme');
    if (saved === 'dark') applyTheme('dark');
});
