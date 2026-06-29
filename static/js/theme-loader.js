// Theme Loader - Apply saved theme across all pages
(function() {
    // Get saved theme
    const savedTheme = localStorage.getItem('theme') || sessionStorage.getItem('theme') || 'dark';
    
    // Apply theme to HTML element immediately (works even before body loads)
    function applyTheme(theme) {
        const target = document.documentElement || document.body;
        
        // Remove all theme classes from both html and body
        if (document.documentElement) {
            document.documentElement.classList.remove('blue-theme', 'maroon-theme');
        }
        if (document.body) {
            document.body.classList.remove('blue-theme', 'maroon-theme');
        }
        
        // Apply the saved theme
        if (theme === 'blue') {
            if (document.body) document.body.classList.add('blue-theme');
            if (document.documentElement) document.documentElement.classList.add('blue-theme');
        } else if (theme === 'maroon') {
            if (document.body) document.body.classList.add('maroon-theme');
            if (document.documentElement) document.documentElement.classList.add('maroon-theme');
        }
        // Default is dark (no class needed)
    }
    
    // Apply theme as soon as possible
    applyTheme(savedTheme);
    
    // Re-apply when DOM is ready to ensure it's on body
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            applyTheme(savedTheme);
            const themeSelector = document.getElementById('themeSelector');
            if (themeSelector) {
                themeSelector.value = savedTheme;
            }
        });
    } else {
        // DOM already loaded
        applyTheme(savedTheme);
        const themeSelector = document.getElementById('themeSelector');
        if (themeSelector) {
            themeSelector.value = savedTheme;
        }
    }
    
    // Listen for theme changes from other tabs/pages
    window.addEventListener('storage', function(e) {
        if (e.key === 'theme' || e.key === 'theme_change_event') {
            const newTheme = localStorage.getItem('theme') || 'dark';
            applyTheme(newTheme);
            
            // Update theme selector if it exists on this page
            const themeSelector = document.getElementById('themeSelector');
            if (themeSelector) {
                themeSelector.value = newTheme;
            }
        }
    });
})();

