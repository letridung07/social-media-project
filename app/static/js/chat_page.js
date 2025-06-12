document.addEventListener('DOMContentLoaded', function () {
    const conversationIdInput = document.getElementById('conversation-id');
    if (!conversationIdInput) {
        console.error('Conversation ID input field not found. Chat functionality may not work.');
        return;
    }
    const conversationId = conversationIdInput.value;
    const messagesContainer = document.getElementById('chat-messages-container');
    const messageForm = document.getElementById('send-message-form');
    const messageInput = document.getElementById('message-input');
    const noMessagesYetP = document.getElementById('no-messages-yet');
    const currentUserId = parseInt(document.body.dataset.currentUserId);

    const emojiToggleButton = document.getElementById('emoji-toggle-button');
    const emojiPanel = document.getElementById('emoji-panel');
    const sampleEmojis = ['😊', '😂', '❤️', '👍', '🤔', '🎉', '😢', '😠', '😮', '🙏'];

    let typingTimer;
    const doneTypingInterval = 2000; // User stops typing if no input for 2s
    let isCurrentlyTyping = false; // Tracks if 'typing_started' was emitted
    const typingUsers = new Map();
    const typingIndicatorContainer = document.getElementById('typing-indicator-container'); // Ensure this ID exists in HTML

    var socket = io();

    let messageObserver;
    const observedMessages = new Set(); // Tracks message IDs currently being observed

    function initMessageObserver() {
        if (!('IntersectionObserver' in window)) {
            console.warn("IntersectionObserver not supported. Read receipts on scroll will not function.");
            return;
        }
        messageObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const messageElement = entry.target;
                    const messageId = parseInt(messageElement.dataset.messageId);
                    const senderId = parseInt(messageElement.dataset.senderId);

                    if (senderId !== currentUserId && messageId && !messageElement.dataset.readEmitted) {
                        socket.emit('mark_messages_as_read', {
                            'message_ids': [messageId],
                            'conversation_id': conversationId
                        });
                        messageElement.dataset.readEmitted = 'true'; // Mark as processed
                        observer.unobserve(messageElement); // Stop observing once processed
                        observedMessages.delete(messageId);
                        // console.log(`Emitted mark_messages_as_read for incoming message: ${messageId}`);
                    }
                }
            });
        }, {
            root: messagesContainer, // Observing intersections within the messages container
            rootMargin: '0px',
            threshold: 0.8 // % of message visible to trigger
        });
    }

    function observeMessageForRead(messageElement) {
        if (!messageObserver || !messageElement) return;
        const messageId = parseInt(messageElement.dataset.messageId);
        // Observe only incoming messages that haven't had their read status emitted by this observer yet
        if (messageId && parseInt(messageElement.dataset.senderId) !== currentUserId && !messageElement.dataset.readEmitted) {
            if (!observedMessages.has(messageId)) {
                 messageObserver.observe(messageElement);
                 observedMessages.add(messageId);
            }
        }
    }

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

    function appendMessage(data) { // data is the new message object from server
        if (noMessagesYetP) noMessagesYetP.style.display = 'none';

        const messageDiv = document.createElement('div');
        messageDiv.classList.add('chat-message', 'mb-2');
        messageDiv.dataset.messageId = data.message_id;
        messageDiv.dataset.senderId = data.sender_id;
        messageDiv.dataset.timestamp = data.timestamp; // ISO string
        if (data.read_at) { // General read_at (first read by anyone/recipient in 1-1)
            messageDiv.dataset.readAt = data.read_at;
        }
        // Note: is_read_by_current_user and read_at_by_current_user are not typically sent for brand new messages via socket.
        // They are more relevant for initially loaded messages.

        const lastMessageElement = messagesContainer.lastElementChild;
        let showSender = true;
        if (lastMessageElement && lastMessageElement.classList.contains('chat-message')) {
            const lastSenderId = parseInt(lastMessageElement.dataset.senderId);
            const lastTimestampStr = lastMessageElement.dataset.timestamp;
            if (lastSenderId === data.sender_id) {
                showSender = false;
                if (lastTimestampStr) {
                    const timeDiffMinutes = (new Date(data.timestamp) - new Date(lastTimestampStr)) / (1000 * 60);
                    if (timeDiffMinutes > 5) showSender = true;
                }
            }
        }

        if (data.sender_id === currentUserId) messageDiv.classList.add('text-right');
        else messageDiv.classList.add('text-left');

        if (showSender) {
            const senderSmall = document.createElement('small');
            senderSmall.classList.add('font-weight-bold');
            senderSmall.textContent = data.sender_username;
            messageDiv.appendChild(senderSmall);
        } else {
            messageDiv.appendChild(document.createElement('div')).classList.add('grouped-message-spacer');
        }

        const bodyDiv = document.createElement('div');
        bodyDiv.classList.add('message-body', 'p-2', 'd-inline-block', 'rounded');
        bodyDiv.classList.toggle('bg-primary', data.sender_id === currentUserId);
        bodyDiv.classList.toggle('text-white', data.sender_id === currentUserId);
        bodyDiv.classList.toggle('bg-light', data.sender_id !== currentUserId);
        bodyDiv.textContent = data.body;
        messageDiv.appendChild(bodyDiv);

        const timeSmall = document.createElement('small');
        timeSmall.classList.add('d-block', 'text-muted', 'message-timestamp');
        const date = new Date(data.timestamp);
        timeSmall.textContent = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' | ' + date.toLocaleDateString();
        messageDiv.appendChild(timeSmall);

        if (data.sender_id === currentUserId) {
            const receiptSpan = document.createElement('span');
            receiptSpan.classList.add('read-receipt-status', 'ml-1');
            receiptSpan.dataset.messageId = data.message_id;
            // For new messages via socket: data.read_at is the general read_at from ChatMessage model.
            // It will be null if no one has read it yet.
            let initialStatus = data.read_at ? "✓✓ Read" : "✓ Sent";
            receiptSpan.innerHTML = `<small class="text-muted">${initialStatus}</small>`;
            messageDiv.appendChild(receiptSpan);
        }

        messagesContainer.appendChild(messageDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;

        if (data.sender_id !== currentUserId) {
            observeMessageForRead(messageDiv); // Observe new incoming messages
        }
    }

    function updateMessageReadStatusUI(messageId, readerUserId, conversationIdFromServer) {
        if (conversationIdFromServer !== conversationId) return;

        const messageDiv = document.querySelector(`.chat-message[data-message-id="${messageId}"]`);
        if (!messageDiv) return;

        const senderId = parseInt(messageDiv.dataset.senderId);
        if (senderId === currentUserId) { // Outgoing message was read
            const receiptSpan = messageDiv.querySelector('.read-receipt-status');
            if (receiptSpan) {
                // Update to "Read", readerUserId can be used for more detailed status if needed in future.
                receiptSpan.innerHTML = `<small class="text-muted">✓✓ Read</small>`;
            }
        }
        // No specific UI update for incoming messages when current user reads them (handled by observer sending event)
    }

    function initializeMessageStatuses() {
        document.querySelectorAll('.chat-message').forEach(msgElement => {
            const senderId = parseInt(msgElement.dataset.senderId);
            const messageId = parseInt(msgElement.dataset.messageId);

            // data attributes set by Jinja template from augmented_messages
            const readAtGeneral = msgElement.dataset.readAt; // General ChatMessage.read_at
            const isReadByCurrentUser = msgElement.dataset.isReadByCurrentUser === 'true';
            // const readAtByCurrentUser = msgElement.dataset.readAtByCurrentUser; // Specific time current user read it

            if (senderId === currentUserId) { // Outgoing message
                const receiptSpan = msgElement.querySelector('.read-receipt-status');
                if (receiptSpan) {
                    // If there's a general read_at timestamp OR specifically marked as read by current user
                    if (readAtGeneral || isReadByCurrentUser) {
                        receiptSpan.innerHTML = '<small class="text-muted">✓✓ Read</small>';
                    } else {
                        receiptSpan.innerHTML = '<small class="text-muted">✓ Sent</small>';
                    }
                }
            } else { // Incoming message
                // If not already marked as read by current user (via server-rendered data), observe it.
                if (!isReadByCurrentUser && !msgElement.dataset.readEmitted) {
                    observeMessageForRead(msgElement);
                }
            }
        });
    }

    socket.on('connect', () => {
        console.log('Socket.IO connected for chat.');
        if (conversationId) socket.emit('join_chat_room', { 'conversation_id': conversationId });
    });
    socket.on('disconnect', () => console.log('Socket.IO disconnected.'));
    socket.on('connect_error', (err) => console.error('Chat Socket.IO connection error:', err));

    socket.on('new_chat_message', (data) => {
        if (data.conversation_id && data.conversation_id.toString() === conversationId) {
            appendMessage(data);
        }
    });
    socket.on('chat_error', (data) => alert('Chat Error: ' + data.message));

    socket.on('user_typing', (data) => {
        if (data.conversation_id && data.conversation_id.toString() === conversationId && data.user_id !== currentUserId) {
            typingUsers.set(data.user_id, data.username);
            updateTypingIndicatorUI();
        }
    });
    socket.on('user_stopped_typing', (data) => {
        if (data.conversation_id && data.conversation_id.toString() === conversationId && data.user_id !== currentUserId) {
            typingUsers.delete(data.user_id);
            updateTypingIndicatorUI();
        }
    });

    socket.on('messages_read_update', (data) => {
        if (data.conversation_id && data.conversation_id.toString() === conversationId) {
            data.message_ids.forEach(msgId => updateMessageReadStatusUI(msgId, data.reader_user_id, data.conversation_id));
        }
    });

    if (messageForm) {
        messageForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const messageBody = messageInput.value.trim();
            if (messageBody && conversationId) {
                socket.emit('send_chat_message', { 'conversation_id': conversationId, 'body': messageBody });
                clearTimeout(typingTimer);
                if (isCurrentlyTyping) {
                    socket.emit('typing_stopped', { 'conversation_id': conversationId });
                    isCurrentlyTyping = false;
                }
                messageInput.value = '';
                messageInput.focus();
            }
        });
    }

    if (messageInput) {
        messageInput.addEventListener('input', () => {
            if (!isCurrentlyTyping && messageInput.value.trim().length > 0) {
                isCurrentlyTyping = true;
                socket.emit('typing_started', { 'conversation_id': conversationId });
            }
            clearTimeout(typingTimer);
            typingTimer = setTimeout(() => {
                if (isCurrentlyTyping) {
                    socket.emit('typing_stopped', { 'conversation_id': conversationId });
                    isCurrentlyTyping = false;
                }
            }, doneTypingInterval);
        });
        messageInput.addEventListener('blur', () => {
            clearTimeout(typingTimer);
            if (isCurrentlyTyping) {
                socket.emit('typing_stopped', { 'conversation_id': conversationId });
                isCurrentlyTyping = false;
            }
        });
        messageInput.addEventListener('keyup', (event) => { // Send stopped if input cleared
            if (messageInput.value.trim().length === 0 && isCurrentlyTyping) {
                clearTimeout(typingTimer);
                socket.emit('typing_stopped', { 'conversation_id': conversationId });
                isCurrentlyTyping = false;
            }
        });
    }

    if (messagesContainer) messagesContainer.scrollTop = messagesContainer.scrollHeight;
    updateTypingIndicatorUI();

    initMessageObserver(); // Initialize the IntersectionObserver
    initializeMessageStatuses(); // Process messages loaded by template

    document.querySelectorAll('.message-timestamp').forEach(tsElement => {
        const utcTimestamp = tsElement.dataset.utcTimestamp || tsElement.textContent; // Fallback for initial template
        if (utcTimestamp) {
            const date = new Date(utcTimestamp);
            tsElement.textContent = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' | ' + date.toLocaleDateString();
        }
    });

    function populateEmojiPanel() {
        if (!emojiPanel) return;
        emojiPanel.innerHTML = ''; // Clear previous if any
        sampleEmojis.forEach(emoji => {
            const emojiSpan = document.createElement('span');
            emojiSpan.textContent = emoji;
            emojiSpan.classList.add('emoji-option', 'p-1', 'm-1');
            emojiSpan.style.cursor = 'pointer';
            emojiSpan.addEventListener('click', () => {
                messageInput.value += emoji;
                messageInput.focus();
            });
            emojiPanel.appendChild(emojiSpan);
        });
    }

    if (emojiToggleButton && emojiPanel) {
        emojiToggleButton.addEventListener('click', ()_ => {
            emojiPanel.style.display = emojiPanel.style.display === 'none' ? 'block' : 'none';
        });
    }
    populateEmojiPanel();
});
