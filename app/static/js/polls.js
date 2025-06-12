document.addEventListener('DOMContentLoaded', function() {
    console.log("Polls JS loaded");

    const pollVoteForms = document.querySelectorAll('.poll-vote-form');

    pollVoteForms.forEach(form => {
        form.addEventListener('submit', function(event) {
            event.preventDefault(); // Prevent default form submission

            const pollId = this.dataset.pollId;
            const selectedOptionInput = this.querySelector('input[name="option_id"]:checked');

            if (!selectedOptionInput) {
                // Consider using a more user-friendly notification system than alert if available
                alert('Please select an option to vote.');
                return;
            }
            const optionId = selectedOptionInput.value;

            // Assuming the CSRF token input field has name="csrf_token"
            const csrfTokenInput = this.querySelector('input[name="csrf_token"]');
            if (!csrfTokenInput) {
                console.error('CSRF token field not found in form.');
                alert('A configuration error occurred. Please try again later.');
                return;
            }
            const csrfToken = csrfTokenInput.value;

            // Show some visual feedback that voting is in progress (optional)
            const submitButton = this.querySelector('button[type="submit"]');
            if (submitButton) {
                submitButton.disabled = true;
                submitButton.textContent = 'Voting...';
            }

            fetch(`/poll/${pollId}/vote`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': csrfToken // Send CSRF token as a header
                },
                // FormData could also be used, but for a single option_id, this is simple.
                body: new URLSearchParams({
                    'option_id': optionId
                    // 'csrf_token': csrfToken // Can also be sent in body if route expects it there for non-AJAX
                })
            })
            .then(response => {
                // Check if response is JSON before trying to parse it
                const contentType = response.headers.get("content-type");
                if (contentType && contentType.indexOf("application/json") !== -1) {
                    return response.json();
                } else {
                    // If not JSON, maybe an error page was returned
                    console.error('Response was not JSON.', response);
                    throw new Error('Server returned an unexpected response. Please try again.');
                }
            })
            .then(data => {
                if (data.success) {
                    if (data.message) {
                        alert(data.message); // Or use a nicer notification
                    }
                    // Reload the page to show updated poll results or form state
                    // A more advanced implementation would update the DOM dynamically.
                    window.location.reload();
                } else {
                    alert(data.error || 'An error occurred while voting.');
                }
            })
            .catch(error => {
                console.error('Fetch Error:', error);
                alert(error.message || 'An error occurred while submitting your vote via AJAX.');
                if (submitButton) { // Re-enable button on error
                    submitButton.disabled = false;
                    submitButton.textContent = 'Vote';
                }
            });
        });
    });
});
