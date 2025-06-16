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
        console.log('Attempting to save theme preference:', theme);

        // Attempt to get CSRF token from meta tag
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');

        const headers = {
            'Content-Type': 'application/json'
        };
        if (csrfToken) {
            headers['X-CSRFToken'] = csrfToken;
        }

        fetch('/set-theme-preference', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify({ theme: theme })
        })
        .then(response => {
            if (!response.ok) {
                // If response is not OK, throw an error to be caught by .catch()
                return response.json().then(errData => {
                    throw new Error(errData.message || `Request failed with status ${response.status}`);
                });
            }
            return response.json();
        })
        .then(data => {
            if (data.status === 'success') {
                console.log('Theme preference saved successfully.');
            } else {
                console.error('Failed to save theme preference:', data.message);
            }
        })
        .catch(error => {
            console.error('Error saving theme preference:', error);
        });
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
