// Establish SocketIO connection globally or within DOMContentLoaded
const socket = io();

document.addEventListener('DOMContentLoaded', function() {
    console.log("Polls JS loaded");

    // Join rooms for all polls on the page
    const pollContainers = document.querySelectorAll('.poll-container');
    pollContainers.forEach(pollContainer => {
        const pollId = pollContainer.dataset.pollId;
        if (pollId) {
            socket.emit('join_poll_room', { 'poll_id': pollId });
            console.log(`Joined room for poll ${pollId}`);
        }
    });

    // Listen for poll_update events
    socket.on('poll_update', function(data) {
        console.log('Received poll_update:', data);
        const pollContainer = document.querySelector(`.poll-container[data-poll-id="${data.poll_id}"]`);

        if (pollContainer) {
            // Update individual option counts and progress bars
            for (const optionId in data.vote_counts) {
                if (data.vote_counts.hasOwnProperty(optionId)) {
                    const count = data.vote_counts[optionId];

                    // Update count display
                    const optionCountElement = pollContainer.querySelector(`.poll-option-count[data-option-id="${optionId}"]`);
                    if (optionCountElement) {
                        // Check if the count actually changed to avoid unnecessary animation
                        if (optionCountElement.textContent !== String(count)) {
                            optionCountElement.textContent = count;
                            optionCountElement.classList.add('vote-updated-animation');
                            setTimeout(() => {
                                optionCountElement.classList.remove('vote-updated-animation');
                            }, 700); // Duration matches typical short animation
                        }
                    }

                    // Update progress bar
                    const progressBarElement = pollContainer.querySelector(`.poll-option-progress-bar[data-option-id="${optionId}"]`);
                    if (progressBarElement) {
                        const percentage = (data.total_votes > 0) ? (count / data.total_votes) * 100 : 0;
                        progressBarElement.style.width = percentage + '%';
                        progressBarElement.setAttribute('aria-valuenow', percentage);
                        // If you also display percentage text on the bar, update it here too
                        // Example: progressBarElement.textContent = Math.round(percentage) + '%';
                    }
                }
            }

            // Update total votes display
            const totalVotesElement = pollContainer.querySelector('.poll-total-votes');
            if (totalVotesElement) {
                totalVotesElement.textContent = data.total_votes;
            }
        } else {
            console.warn(`Poll container not found for poll_id: ${data.poll_id}`);
        }
    });

    const pollVoteForms = document.querySelectorAll('.poll-vote-form');

    pollVoteForms.forEach(form => {
        form.addEventListener('submit', function(event) {
            event.preventDefault(); // Prevent default form submission

            const pollId = this.dataset.pollId;
            const selectedOptionInput = this.querySelector('input[name="option_id"]:checked');
            const submitButton = this.querySelector('button[type="submit"]'); // Define submitButton here

            if (!selectedOptionInput) {
                alert('Please select an option to vote.');
                return;
            }
            const optionId = selectedOptionInput.value;

            const csrfTokenInput = this.querySelector('input[name="csrf_token"]');
            if (!csrfTokenInput) {
                console.error('CSRF token field not found in form.');
                alert('A configuration error occurred. Please try again later.');
                return;
            }
            const csrfToken = csrfTokenInput.value;

            if (submitButton) {
                submitButton.disabled = true;
                submitButton.textContent = 'Voting...';
            }

            fetch(`/poll/${pollId}/vote`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': csrfToken
                },
                body: new URLSearchParams({
                    'option_id': optionId
                })
            })
            .then(response => {
                const contentType = response.headers.get("content-type");
                if (contentType && contentType.indexOf("application/json") !== -1) {
                    return response.json();
                } else {
                    console.error('Response was not JSON.', response);
                    // Try to get text content for better error diagnosis if possible
                    return response.text().then(text => {
                        throw new Error(`Server returned an unexpected response: ${text || response.statusText}`);
                    });
                }
            })
            .then(data => {
                if (data.success) {
                    if (data.message) {
                        // Consider using a more sophisticated notification system
                        // For example, a small, non-blocking toast message
                        console.log('Vote success:', data.message);
                        // alert(data.message); // Kept for now, can be replaced
                    }
                    // Page will not reload; UI updates via SocketIO.
                    // Re-enable the button and reset text.
                    if (submitButton) {
                        submitButton.disabled = false;
                        submitButton.textContent = 'Vote';
                    }
                } else {
                    alert(data.error || 'An error occurred while voting.');
                     if (submitButton) { // Also re-enable on known error from server
                        submitButton.disabled = false;
                        submitButton.textContent = 'Vote';
                    }
                }
            })
            .catch(error => {
                console.error('Fetch Error:', error);
                alert(error.message || 'An error occurred while submitting your vote.');
                if (submitButton) {
                    submitButton.disabled = false;
                    submitButton.textContent = 'Vote';
                }
            });
        });
    });
});
