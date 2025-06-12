document.addEventListener('DOMContentLoaded', function () {
    console.log('Mention autocomplete script loaded.');

    const textareas = document.querySelectorAll('.mentionable-textarea');
    let suggestionsDropdown = null;
    let currentTextarea = null;
    let mentionQueryStartPosition = -1;

    function createSuggestionsDropdown() {
        if (!suggestionsDropdown) {
            suggestionsDropdown = document.createElement('ul');
            suggestionsDropdown.classList.add('mention-suggestions');
            document.body.appendChild(suggestionsDropdown); // Append to body to avoid positioning issues
        }
        suggestionsDropdown.style.display = 'none';
        return suggestionsDropdown;
    }

    function hideSuggestions() {
        if (suggestionsDropdown) {
            suggestionsDropdown.style.display = 'none';
            suggestionsDropdown.innerHTML = '';
        }
    }

    function showSuggestions(textarea, suggestions) {
        if (!suggestionsDropdown) createSuggestionsDropdown();

        suggestionsDropdown.innerHTML = ''; // Clear previous suggestions
        if (suggestions.length === 0) {
            hideSuggestions();
            return;
        }

        suggestions.forEach(user => {
            const li = document.createElement('li');
            li.innerHTML = `<img src="${user.profile_picture_url}" alt="${user.username}" class="mr-2" width="20" height="20"> ${user.username}`;
            li.addEventListener('click', function () {
                insertMention(textarea, user.username);
                hideSuggestions();
            });
            suggestionsDropdown.appendChild(li);
        });

        // Position dropdown near the textarea (simple version, can be improved)
        const rect = textarea.getBoundingClientRect();
        suggestionsDropdown.style.position = 'absolute';
        suggestionsDropdown.style.left = `${rect.left}px`;
        // Position below the textarea, considering scroll offset
        suggestionsDropdown.style.top = `${window.scrollY + rect.bottom}px`;
        suggestionsDropdown.style.display = 'block';
        suggestionsDropdown.style.zIndex = '1000'; // Ensure it's on top
    }

    function insertMention(textarea, username) {
        const currentText = textarea.value;
        const cursorPosition = textarea.selectionStart;

        // Find the start of the mention query (e.g., after the '@')
        // This needs to be robust, for now, we use the stored mentionQueryStartPosition
        if (mentionQueryStartPosition === -1) return;

        const textBeforeQuery = currentText.substring(0, mentionQueryStartPosition -1); // -1 to exclude '@'
        const textAfterQuery = currentText.substring(cursorPosition);

        textarea.value = textBeforeQuery + `@${username} ` + textAfterQuery; // Add space after mention

        // Adjust cursor position after insertion
        const newCursorPosition = (textBeforeQuery + `@${username} `).length;
        textarea.focus();
        textarea.setSelectionRange(newCursorPosition, newCursorPosition);

        mentionQueryStartPosition = -1; // Reset
    }

    textareas.forEach(textarea => {
        textarea.addEventListener('input', function (e) {
            currentTextarea = this; // Store current textarea
            const text = this.value;
            const cursorPos = this.selectionStart;
            let query = null;

            // Basic logic to find current mention query (e.g., text after last '@' before cursor)
            let atPos = text.lastIndexOf('@', cursorPos - 1);
            if (atPos !== -1) {
                // Check if there's a space or newline between @ and cursor, or if it's just after @
                const potentialQuery = text.substring(atPos + 1, cursorPos);
                if (!/\s/.test(potentialQuery) && potentialQuery.length >= 1) { // No spaces in query, length >= 1
                    query = potentialQuery;
                    mentionQueryStartPosition = atPos + 1; // Store start of the actual query text
                } else {
                     mentionQueryStartPosition = -1; // Invalid query
                }
            } else {
                mentionQueryStartPosition = -1; // No @ found before cursor
            }

            if (query) {
                fetch(`/users/search_mentions?q=${encodeURIComponent(query)}`)
                    .then(response => response.json())
                    .then(data => {
                        if (data.users && data.users.length > 0) {
                            showSuggestions(this, data.users);
                        } else {
                            hideSuggestions();
                        }
                    })
                    .catch(error => {
                        console.error('Error fetching mention suggestions:', error);
                        hideSuggestions();
                    });
            } else {
                hideSuggestions();
            }
        });

        textarea.addEventListener('keydown', function(e) {
            if (suggestionsDropdown && suggestionsDropdown.style.display === 'block') {
                const items = suggestionsDropdown.querySelectorAll('li');
                let currentIndex = Array.from(items).findIndex(item => item.classList.contains('selected'));

                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    if (currentIndex < items.length - 1) {
                        if (currentIndex !== -1) items[currentIndex].classList.remove('selected');
                        items[++currentIndex].classList.add('selected');
                    }
                } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    if (currentIndex > 0) {
                        items[currentIndex].classList.remove('selected');
                        items[--currentIndex].classList.add('selected');
                    }
                } else if (e.key === 'Enter' && currentIndex !== -1) {
                    e.preventDefault();
                    items[currentIndex].click(); // Trigger click to insert
                } else if (e.key === 'Escape') {
                    hideSuggestions();
                }
            }
        });
    });

    // Hide suggestions if clicking outside
    document.addEventListener('click', function (e) {
        if (currentTextarea && !currentTextarea.contains(e.target) && suggestionsDropdown && !suggestionsDropdown.contains(e.target)) {
            hideSuggestions();
        }
    });

    // Add some basic styling for the dropdown - this should ideally be in a CSS file
    const style = document.createElement('style');
    style.innerHTML = `
        .mention-suggestions {
            list-style: none;
            padding: 0;
            margin: 0;
            border: 1px solid #ccc;
            background-color: white;
            max-height: 150px;
            overflow-y: auto;
            min-width: 150px; /* Ensure it's wide enough */
        }
        .mention-suggestions li {
            padding: 5px 10px;
            cursor: pointer;
            display: flex;
            align-items: center;
        }
        .mention-suggestions li:hover, .mention-suggestions li.selected {
            background-color: #f0f0f0;
        }
        .mention-suggestions li img {
            border-radius: 50%; /* Circular images */
        }
    `;
    document.head.appendChild(style);
});
