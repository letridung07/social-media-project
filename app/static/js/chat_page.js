document.addEventListener('DOMContentLoaded', function () {
    const conversationIdInput = document.getElementById('conversation-id');
    if (!conversationIdInput) {
        console.error('Conversation ID input field not found. Chat functionality may not work.');
        return; // Stop if critical element is missing
    }
    const conversationId = conversationIdInput.value;
    const messagesContainer = document.getElementById('chat-messages-container');
    const messageForm = document.getElementById('send-message-form');
    const messageInput = document.getElementById('message-input');
    const noMessagesYetP = document.getElementById('no-messages-yet');

    // Connect to Socket.IO
    var socket = io(); // Assumes server is on same host/port

    // Function to append a new message to the chat window
    function appendMessage(data) {
        if (noMessagesYetP) {
            noMessagesYetP.style.display = 'none'; // Hide "no messages" placeholder
        }

        const messageDiv = document.createElement('div');
        messageDiv.classList.add('chat-message', 'mb-2');

        const messageSenderUsername = document.body.dataset.currentUserUsername;

        if (data.sender_username === messageSenderUsername) {
            messageDiv.classList.add('text-right');
        } else {
            messageDiv.classList.add('text-left');
        }

        const senderSmall = document.createElement('small');
        senderSmall.classList.add('font-weight-bold');
        senderSmall.textContent = data.sender_username;

        const bodyDiv = document.createElement('div');
        bodyDiv.classList.add('message-body', 'p-2', 'd-inline-block', 'rounded');
        if (data.sender_username === messageSenderUsername) {
            bodyDiv.classList.add('bg-primary', 'text-white');
        } else {
            bodyDiv.classList.add('bg-light');
        }
        bodyDiv.textContent = data.body;

        const timeSmall = document.createElement('small');
        timeSmall.classList.add('d-block', 'text-muted');
        // Format timestamp nicely (e.g., using toLocaleString or a library like Moment.js)
        const date = new Date(data.timestamp);
        timeSmall.textContent = date.toLocaleString(); // Simple local time formatting

        messageDiv.appendChild(senderSmall);
        messageDiv.appendChild(bodyDiv);
        messageDiv.appendChild(timeSmall);

        messagesContainer.appendChild(messageDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight; // Scroll to bottom
    }

    // Socket.IO event listeners
    socket.on('connect', function () {
        console.log('Socket.IO connected for chat.');
        // Join the specific conversation room
        if (conversationId) {
            socket.emit('join_chat_room', { 'conversation_id': conversationId });
        }
    });

    socket.on('disconnect', function () {
        console.log('Socket.IO disconnected for chat.');
        // Optionally, emit leave_chat_room if server handles it for cleanup
        // if (conversationId) {
        //     socket.emit('leave_chat_room', { 'conversation_id': conversationId });
        // }
    });

    socket.on('connect_error', (err) => {
        console.error('Chat Socket.IO connection error:', err);
    });

    socket.on('new_chat_message', function (data) {
        // Ensure the message is for the current conversation
        if (data.conversation_id && data.conversation_id.toString() === conversationId) {
            appendMessage(data);
        }
    });

    socket.on('chat_error', function(data) {
        console.error('Chat Error:', data.message);
        // Display error to user, e.g., in an alert or a dedicated error div
        alert('Chat Error: ' + data.message);
    });

    // Handle message form submission
    if (messageForm) {
        messageForm.addEventListener('submit', function (e) {
            e.preventDefault();
            const messageBody = messageInput.value.trim();
            if (messageBody && conversationId) {
                socket.emit('send_chat_message', {
                    'conversation_id': conversationId,
                    'body': messageBody
                });
                messageInput.value = ''; // Clear input field
                messageInput.focus();
            }
        });
    }

    // Initial scroll to bottom if messages already exist
    if (messagesContainer) {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    // Optional: Handle leaving the room when the user navigates away or closes the tab
    // window.addEventListener('beforeunload', function() {
    //     if (conversationId) {
    //         socket.emit('leave_chat_room', { 'conversation_id': conversationId });
    //     }
    // });
});
