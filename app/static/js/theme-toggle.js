document.addEventListener('DOMContentLoaded', function () {
    const themeToggle = document.getElementById('themeToggleSwitch');
    const body = document.body;
    // The label text part is removed as per the simpler toggle implementation in HTML
    // const themeToggleLabel = document.getElementById('themeToggleLabelText');

    // Function to apply the saved theme or default to light
    function applyTheme() {
        // Check localStorage first
        let preferredTheme = localStorage.getItem('theme');

        // If no localStorage preference, check for server-set class (for logged-in users)
        // This assumes the body tag might have 'dark-mode' class set by the server
        if (!preferredTheme && body.classList.contains('dark-mode')) {
            preferredTheme = 'dark';
        } else if (!preferredTheme) {
            preferredTheme = 'light'; // Default to light if nothing is set
        }

        if (preferredTheme === 'dark') {
            body.classList.add('dark-mode');
            if (themeToggle) {
                themeToggle.checked = true;
            }
            // if (themeToggleLabel) themeToggleLabel.textContent = 'Dark Mode';
        } else {
            body.classList.remove('dark-mode');
            if (themeToggle) {
                themeToggle.checked = false;
            }
            // if (themeToggleLabel) themeToggleLabel.textContent = 'Light Mode';
        }
    }

    // Function to send theme preference to the backend
    function saveThemePreference(theme) {
        // Ensure current_user is available (passed via data attribute or other means)
        // For now, we'll just log it. The actual fetch will be implemented
        // once the backend endpoint (step 4) is ready.
        console.log('Attempting to save theme preference:', theme);

        // Placeholder for fetch request:
        // fetch('/set-theme-preference', {
        //     method: 'POST',
        //     headers: {
        //         'Content-Type': 'application/json',
        //         // Include CSRF token if required by Flask-WTF
        //         // 'X-CSRFToken': getCsrfToken() // You'd need a function to get this
        //     },
        //     body: JSON.stringify({ theme: theme })
        // })
        // .then(response => response.json())
        // .then(data => {
        //     if (data.status === 'success') {
        //         console.log('Theme preference saved successfully.');
        //     } else {
        //         console.error('Failed to save theme preference.');
        //     }
        // })
        // .catch(error => {
        //     console.error('Error saving theme preference:', error);
        // });
    }

    if (themeToggle) {
        themeToggle.addEventListener('change', function () {
            if (this.checked) {
                body.classList.add('dark-mode');
                localStorage.setItem('theme', 'dark');
                // if (themeToggleLabel) themeToggleLabel.textContent = 'Dark Mode';
                saveThemePreference('dark');
            } else {
                body.classList.remove('dark-mode');
                localStorage.setItem('theme', 'light');
                // if (themeToggleLabel) themeToggleLabel.textContent = 'Light Mode';
                saveThemePreference('light');
            }
        });
    }

    // Apply theme on initial load
    applyTheme();
});
