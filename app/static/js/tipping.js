document.addEventListener('DOMContentLoaded', function() {
    // Check if Stripe key is available
    if (typeof STRIPE_PUBLISHABLE_KEY === 'undefined' || STRIPE_PUBLISHABLE_KEY === 'your_stripe_publishable_key' || !STRIPE_PUBLISHABLE_KEY) {
        console.error('Stripe publishable key is not set.');
        // Disable tip button if Stripe is not configured
        const tipButton = document.getElementById('tip-button');
        if (tipButton) {
            tipButton.disabled = true;
            tipButton.title = 'Tipping is currently disabled.';
        }
        return;
    }

    const stripe = Stripe(STRIPE_PUBLISHABLE_KEY);
    let elements;
    let clientSecret;

    const tipButton = document.getElementById('tip-button');
    const tipModal = new bootstrap.Modal(document.getElementById('tipModal'));
    const tipForm = document.getElementById('tip-form');
    const cardElementContainer = document.getElementById('card-element');
    const cardErrors = document.getElementById('card-errors');
    const recipientId = tipButton.dataset.recipientId;

    // Style for the Stripe Element
    const style = {
        base: {
            color: '#32325d',
            fontFamily: '"Helvetica Neue", Helvetica, sans-serif',
            fontSmoothing: 'antialiased',
            fontSize: '16px',
            '::placeholder': {
                color: '#aab7c4'
            }
        },
        invalid: {
            color: '#fa755a',
            iconColor: '#fa755a'
        }
    };

    // Create and mount the card element
    const card = stripe.elements().create('card', { style: style });
    card.mount(cardElementContainer);

    // Handle real-time validation errors from the card Element.
    card.on('change', function(event) {
        if (event.error) {
            cardErrors.textContent = event.error.message;
        } else {
            cardErrors.textContent = '';
        }
    });

    // Show the modal when the tip button is clicked
    tipButton.addEventListener('click', function() {
        tipModal.show();
    });

    // Handle form submission
    tipForm.addEventListener('submit', async function(event) {
        event.preventDefault();

        const amount = document.getElementById('tip-amount').value;
        const message = document.getElementById('tip-message').value;
        const amountInCents = Math.round(parseFloat(amount) * 100);

        // Basic client-side validation
        if (isNaN(amountInCents) || amountInCents < 100) {
            cardErrors.textContent = 'Please enter an amount of at least $1.00.';
            return;
        }

        // 1. Create PaymentIntent on the server
        try {
            // Get CSRF token from the page (e.g., from the follow/unfollow form)
            const csrfToken = document.querySelector('input[name="csrf_token"]').value;

            const response = await fetch('/api/v1/tip/create-payment-intent', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({
                    amount: amountInCents,
                    recipient_id: recipientId,
                    message: message
                })
            });

            const data = await response.json();

            if (response.ok) {
                clientSecret = data.clientSecret;
            } else {
                cardErrors.textContent = data.message || 'Failed to initialize payment.';
                return;
            }
        } catch (error) {
            console.error('Error creating payment intent:', error);
            cardErrors.textContent = 'An error occurred while setting up the payment. Please try again.';
            return;
        }

        // 2. Confirm the card payment
        const { error, paymentIntent } = await stripe.confirmCardPayment(clientSecret, {
            payment_method: {
                card: card,
                billing_details: {
                    // We can add more billing details here if needed
                    name: 'Tipping User' // This could be pre-filled with the current user's name
                }
            }
        });

        if (error) {
            // Show error to your customer
            cardErrors.textContent = error.message;
        } else {
            // The payment has been processed!
            if (paymentIntent.status === 'succeeded') {
                // Show a success message to your customer
                alert('Tip successful! Thank you for your support.');
                tipModal.hide();
                tipForm.reset();
                card.clear();
            }
        }
    });
});
