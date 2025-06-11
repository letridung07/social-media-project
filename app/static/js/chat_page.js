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
    const currentUserId = parseInt(document.body.dataset.currentUserId); // Access currentUserId

    // Emoji picker elements
    const emojiToggleButton = document.getElementById('emoji-toggle-button');
    const emojiPanel = document.getElementById('emoji-panel');
    const sampleEmojis = ['😊', '😂', '❤️', '👍', '🤔', '🎉', '😢', '😠', '😮', '🙏'];

    // Global variables for typing
    let typingTimer; // Timer identifier
    const doneTypingInterval = 1500; // Time in ms (1.5 seconds)
    const typingUsers = new Map(); // To keep track of users currently typing {userId: username}
    const typingIndicatorContainer = document.getElementById('typing-indicator-container');

    // Connect to Socket.IO
    var socket = io(); // Assumes server is on same host/port

    // Function to update typing indicator UI
    function updateTypingIndicatorUI() {
        if (!typingIndicatorContainer) return;
        if (typingUsers.size === 0) {
            typingIndicatorContainer.innerHTML = '';
        } else {
            const users = Array.from(typingUsers.values());
            let text = users.join(', ');
            if (users.length > 2) {
                text = `${users.slice(0, 2).join(', ')} and ${users.length - 2} others`;
            }
            typingIndicatorContainer.innerHTML = `<small class="text-muted"><em>${text} ${users.length === 1 ? 'is' : 'are'} typing...</em></small>`;
        }
    }

    // Function to append a new message to the chat window
    function appendMessage(data) {
        if (noMessagesYetP) {
            noMessagesYetP.style.display = 'none'; // Hide "no messages" placeholder
        }

        const lastMessageElement = messagesContainer.lastElementChild;
        let showSender = true;
        if (lastMessageElement && lastMessageElement.classList.contains('chat-message')) {
            const lastSenderId = parseInt(lastMessageElement.dataset.senderId);
            const lastTimestampStr = lastMessageElement.dataset.timestamp; // ISO format

            if (lastSenderId === data.sender_id) {
                showSender = false; // Basic grouping by sender
                if (lastTimestampStr) {
                    const lastTimestamp = new Date(lastTimestampStr);
                    const currentTimestamp = new Date(data.timestamp); // data.timestamp is ISO string from server
                    const timeDiffMinutes = (currentTimestamp - lastTimestamp) / (1000 * 60);
                    if (timeDiffMinutes > 5) { // Group if within 5 minutes
                        showSender = true;
                    }
                }
            }
        }

        const messageDiv = document.createElement('div');
        messageDiv.classList.add('chat-message', 'mb-2');
        messageDiv.dataset.messageId = data.message_id;
        messageDiv.dataset.senderId = data.sender_id;
        messageDiv.dataset.timestamp = data.timestamp; // Store ISO timestamp

        if (data.sender_id === currentUserId) {
            messageDiv.classList.add('text-right');
        } else {
            messageDiv.classList.add('text-left');
        }

        if (showSender) {
            const senderSmall = document.createElement('small');
            senderSmall.classList.add('font-weight-bold');
            senderSmall.textContent = data.sender_username;
            messageDiv.appendChild(senderSmall);
        } else {
            const spacerDiv = document.createElement('div');
            spacerDiv.classList.add('grouped-message-spacer'); // Use CSS class
            messageDiv.appendChild(spacerDiv);
        }

        const bodyDiv = document.createElement('div');
        bodyDiv.classList.add('message-body', 'p-2', 'd-inline-block', 'rounded');
        if (data.sender_id === currentUserId) {
            bodyDiv.classList.add('bg-primary', 'text-white');
        } else {
            bodyDiv.classList.add('bg-light');
        }
        bodyDiv.textContent = data.body;

        const timeSmall = document.createElement('small');
        timeSmall.classList.add('d-block', 'text-muted', 'message-timestamp');
        timeSmall.dataset.utcTimestamp = data.timestamp; // Store ISO for potential re-formatting
        const date = new Date(data.timestamp);
        // Consistent local time formatting
        timeSmall.textContent = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' | ' + date.toLocaleDateString();

        messageDiv.appendChild(bodyDiv); // Body first, then sender (if shown), then time
        // Re-order: Sender (if shown), then Body, then Time
        // Correct order will be handled by structure: if(showSender) appends child, then body, then time.
        // The current appendChild order for senderSmall/spacerDiv is inside the if/else, so it's fine.
        // Then bodyDiv and timeSmall are appended after that block.
        // This means bodyDiv should be appended after senderSmall/spacerDiv in the DOM flow.
        // The actual order of appending:
        // 1. senderSmall OR spacerDiv
        // 2. bodyDiv (needs to be after sender/spacer)
        // 3. timeSmall (after body)
        // Let's ensure this. The current code is:
        // if (showSender) { messageDiv.appendChild(senderSmall); } else { messageDiv.appendChild(spacerDiv); }
        // messageDiv.appendChild(bodyDiv); // This is fine
        // messageDiv.appendChild(timeSmall); // This is fine

        // Add read receipt span for outgoing messages
        if (data.sender_id === currentUserId) {
            const receiptSpan = document.createElement('span');
            receiptSpan.classList.add('read-receipt-status');
            receiptSpan.dataset.messageId = data.message_id;
            // New messages are initially "Sent". If server confirms read later, it will update.
            // If this message is from self and is part of a batch of old messages that were already read,
            // this initial status might be "Sent" then immediately updated by a separate 'messages_read_update'.
            // For simplicity, new outgoing messages start as "Sent".
            receiptSpan.innerHTML = '<small class="text-muted">✓ Sent</small>';
            messageDiv.appendChild(receiptSpan);
        }

        messagesContainer.appendChild(messageDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight; // Scroll to bottom

        // If the new message is incoming, try to mark it as read
        if (data.sender_id !== currentUserId) {
            markVisibleMessagesAsRead(); // Or more targeted: emit mark for [data.message_id]
        }
    }

    // Function to update read receipt UI for a specific message
    function updateReadReceiptUI(messageId, readerUserId) {
        const messageStatusElement = document.querySelector(`.read-receipt-status[data-message-id="${messageId}"]`);
        if (messageStatusElement) {
            // This function is called when 'messages_read_update' is received.
            // This means *another* user (readerUserId) has read a message.
            // We only want to change the status of messages sent by the *current* user.
            const messageDiv = messageStatusElement.closest('.chat-message');
            // data-sender-id was added in appendMessage and should be on the template-rendered messages too.
            const senderId = parseInt(messageDiv.dataset.senderId);

            if (senderId === currentUserId) {
                // If it's my message that got read by someone else (readerUserId)
                messageStatusElement.innerHTML = '<small class="text-muted">✓ Read</small>';
            }
        }
    }

    // Function to identify and mark visible unread messages
    function markVisibleMessagesAsRead() {
        if (!messagesContainer || !currentUserId) return; // Ensure currentUserId is available
        const unreadMessageIds = [];
        const messages = messagesContainer.querySelectorAll('.chat-message'); // Select all chat messages

        messages.forEach(msgElement => {
            const messageId = parseInt(msgElement.dataset.messageId);
            const senderId = parseInt(msgElement.dataset.senderId);

            // Check if it's an incoming message (sender is not current user)
            if (senderId !== currentUserId && messageId) {
                // Check if it's not already marked as read by the current user.
                // For simplicity, we'll assume the server handles if a message is already read.
                // The client just sends IDs of potentially unread incoming messages.
                // A more sophisticated client-side check could see if a 'read' visual cue already exists.
                unreadMessageIds.push(messageId);
            }
        });

        if (unreadMessageIds.length > 0 && conversationId) {
            socket.emit('mark_messages_as_read', {
                'message_ids': unreadMessageIds,
                'conversation_id': conversationId
            });
            // console.log('Emitted mark_messages_as_read for:', unreadMessageIds);
        }
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

    // Listen for typing events from server
    socket.on('user_typing', function(data) {
        if (data.conversation_id && data.conversation_id.toString() === conversationId) {
            // Don't show for self - this is handled by skip_sid on server.
            typingUsers.set(data.user_id, data.username);
            updateTypingIndicatorUI();
        }
    });

    socket.on('user_stopped_typing', function(data) {
        if (data.conversation_id && data.conversation_id.toString() === conversationId) {
            typingUsers.delete(data.user_id);
            updateTypingIndicatorUI();
        }
    });

    socket.on('messages_read_update', function(data) {
        if (data.conversation_id && data.conversation_id.toString() === conversationId) {
            data.message_ids.forEach(messageId => {
                // Pass data.reader_user_id to know who read it, if needed for more complex UI
                updateReadReceiptUI(messageId, data.reader_user_id);
            });
        }
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
                // Also send typing_stopped as message submission implies typing has stopped.
                clearTimeout(typingTimer);
                socket.emit('typing_stopped', { 'conversation_id': conversationId });
                messageInput.value = ''; // Clear input field
                messageInput.focus();
            }
        });
    }

    // Add event listeners for typing on messageInput
    if (messageInput) {
        messageInput.addEventListener('input', () => {
            clearTimeout(typingTimer);
            socket.emit('typing_started', { 'conversation_id': conversationId });
            typingTimer = setTimeout(() => {
                socket.emit('typing_stopped', { 'conversation_id': conversationId });
            }, doneTypingInterval);
        });

        messageInput.addEventListener('blur', () => {
            clearTimeout(typingTimer); // Clear existing timer
            socket.emit('typing_stopped', { 'conversation_id': conversationId });
        });
    }

    // Initial scroll to bottom if messages already exist
    if (messagesContainer) {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
    // Call updateTypingIndicatorUI initially
    updateTypingIndicatorUI();
    // Call markVisibleMessagesAsRead on initial load
    markVisibleMessagesAsRead();

    // Format all timestamps on initial load
    document.querySelectorAll('.message-timestamp').forEach(tsElement => {
        const utcTimestamp = tsElement.dataset.utcTimestamp;
        if (utcTimestamp) {
            const date = new Date(utcTimestamp);
            tsElement.textContent = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' | ' + date.toLocaleDateString();
        }
    });

    // Function to populate emoji panel
    function populateEmojiPanel() {
        if (!emojiPanel) return;
        sampleEmojis.forEach(emoji => {
            const emojiSpan = document.createElement('span');
            emojiSpan.textContent = emoji;
            emojiSpan.classList.add('emoji-option', 'p-1', 'm-1');
            emojiSpan.style.cursor = 'pointer';
            emojiSpan.addEventListener('click', () => {
                messageInput.value += emoji;
                messageInput.focus();
                // Optionally hide panel: emojiPanel.style.display = 'none';
            });
            emojiPanel.appendChild(emojiSpan);
        });
    }

    // Event listener for emoji toggle button
    if (emojiToggleButton && emojiPanel) {
        emojiToggleButton.addEventListener('click', () => {
            emojiPanel.style.display = emojiPanel.style.display === 'none' ? 'block' : 'none';
        });
    }

    // Populate emoji panel on load
    populateEmojiPanel();

    // Optional: Handle leaving the room when the user navigates away or closes the tab
    // window.addEventListener('beforeunload', function() {
    //     if (conversationId) {
    //         socket.emit('leave_chat_room', { 'conversation_id': conversationId });
    //     }
    // });
});
