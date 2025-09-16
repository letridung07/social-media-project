document.addEventListener('DOMContentLoaded', function() {
    // Use event delegation to handle clicks on all reaction buttons
    document.body.addEventListener('click', function(event) {
        if (event.target.matches('.reaction-button')) {
            handleReactionClick(event.target);
        }
    });

    function handleReactionClick(button) {
        const reactionButtonsDiv = button.closest('.reaction-buttons');
        const postId = reactionButtonsDiv.dataset.postId;
        const reactionType = button.dataset.reactionType;
        const csrfToken = reactionButtonsDiv.querySelector('.csrf_token').value;

        const url = `/react/${postId}/${reactionType}`;

        fetch(url, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
        })
        .then(response => {
            if (!response.ok) {
                return response.json().then(err => Promise.reject(err));
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                updateReactionUI(postId, data.reaction_counts, data.new_reaction_type);
            } else {
                console.error('Failed to apply reaction:', data.error);
                // Optionally, display an error message to the user
            }
        })
        .catch(error => {
            console.error('Error processing reaction:', error);
        });
    }

    function updateReactionUI(postId, reactionCounts, newReactionType) {
        const countsWrapper = document.querySelector(`.reaction-counts-wrapper[data-post-id="${postId}"]`);
        const reactionButtonsDiv = document.querySelector(`.reaction-buttons[data-post-id="${postId}"]`);

        if (!countsWrapper || !reactionButtonsDiv) {
            return; // Exit if the post elements are not on the page
        }

        // Update all reaction counts based on the server's response
        for (const [type, count] of Object.entries(reactionCounts)) {
            const pill = countsWrapper.querySelector(`.reaction-count-pill[data-reaction-type="${type}"]`);
            if (pill) {
                const countSpan = pill.querySelector('.reaction-count-number');
                countSpan.textContent = count;
                if (count > 0) {
                    pill.style.display = '';
                } else {
                    pill.style.display = 'none';
                }
            }
        }

        // Update all button styles
        const allButtonsInGroup = reactionButtonsDiv.querySelectorAll('.reaction-button');
        allButtonsInGroup.forEach(btn => {
            const btnReactionType = btn.dataset.reactionType;
            if (btnReactionType === newReactionType) {
                btn.classList.remove('btn-outline-secondary');
                btn.classList.add('btn-primary');
            } else {
                btn.classList.remove('btn-primary');
                btn.classList.add('btn-outline-secondary');
            }
        });
    }
});
