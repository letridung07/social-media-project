// app/static/js/view_stream.js
document.addEventListener('DOMContentLoaded', () => {
    console.log('View Stream JS Loaded');

    const remoteVideo = document.getElementById('remoteVideo');
    const connectionStatusP = document.getElementById('connectionStatus');
    const socket = io();

    let peerConnection; // For SFU, this will be the connection to Janus
    const JANUS_SERVER_URL = typeof janusServerUrlGlobal !== 'undefined' ? janusServerUrlGlobal : '/janus_placeholder';

    const iceServers = {
        iceServers: [
            { urls: 'stun:stun.l.google.com:19302' }
        ]
    };
    if (typeof turnConfigGlobal !== 'undefined' && turnConfigGlobal.urls && !turnConfigGlobal.urls.includes('yourturnserver.example.com')) {
        iceServers.iceServers.push({
            urls: turnConfigGlobal.urls,
            username: turnConfigGlobal.username,
            credential: turnConfigGlobal.credential
        });
    }

    function updateConnectionStatus(message) {
        if (connectionStatusP) {
            connectionStatusP.textContent = `Status: ${message}`;
        }
        console.log(`Connection Status: ${message}`);
    }

    function initializeStreamChat() {
        if (!streamData.conversationId) {
            console.log("No conversation ID for stream chat.");
            return;
        }
        console.log("Initializing stream chat for conversation ID:", streamData.conversationId);

        const chatMessagesContainer = document.getElementById('chat-messages-container');
        const sendMessageForm = document.getElementById('send-message-form-stream');
        const messageInput = document.getElementById('message-input-stream');
        const typingIndicatorContainer = document.getElementById('typing-indicator-container');
        const noMessagesYetP = document.getElementById('no-messages-yet');


        socket.emit('join_chat_room', { conversation_id: streamData.conversationId });

        if (sendMessageForm && messageInput) {
            sendMessageForm.addEventListener('submit', function(event) {
                event.preventDefault();
                const messageBody = messageInput.value.trim();
                if (messageBody) {
                    socket.emit('send_chat_message', {
                        conversation_id: streamData.conversationId,
                        body: messageBody
                    });
                    messageInput.value = '';
                    socket.emit('typing_stopped', { conversation_id: streamData.conversationId });
                }
            });

            let typingTimeout;
            messageInput.addEventListener('input', () => {
                clearTimeout(typingTimeout);
                socket.emit('typing_started', { conversation_id: streamData.conversationId });
                typingTimeout = setTimeout(() => {
                    socket.emit('typing_stopped', { conversation_id: streamData.conversationId });
                }, 2000);
            });
        }

        socket.on('new_chat_message', function(data) {
            if (data.conversation_id.toString() === streamData.conversationId.toString()) {
                if (noMessagesYetP) {
                    noMessagesYetP.style.display = 'none';
                }
                appendMessageToChat(data, chatMessagesContainer);
            }
        });

        socket.on('user_typing', function(data) {
            if (data.conversation_id.toString() === streamData.conversationId.toString() && data.user_id.toString() !== streamData.currentUserId.toString()) {
                let indicator = document.getElementById(`typing-${data.user_id}`);
                if (!indicator) {
                    indicator = document.createElement('small');
                    indicator.id = `typing-${data.user_id}`;
                    indicator.classList.add('text-muted', 'd-block');
                    indicator.textContent = `${data.username} is typing...`;
                    typingIndicatorContainer.appendChild(indicator);
                }
            }
        });

        socket.on('user_stopped_typing', function(data) {
            if (data.conversation_id.toString() === streamData.conversationId.toString()) {
                const indicator = document.getElementById(`typing-${data.user_id}`);
                if (indicator) {
                    indicator.remove();
                }
            }
        });
        scrollToBottom(chatMessagesContainer); // Scroll on initial load
    }

    function appendMessageToChat(msgData, container) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('chat-message', 'mb-2');
        messageDiv.dataset.messageId = msgData.message_id || msgData.id; // Adapt to potential differences in field name
        messageDiv.dataset.senderId = msgData.sender_id;
        messageDiv.dataset.timestamp = msgData.timestamp;

        const senderUsername = msgData.sender_username || 'User'; // Fallback if username not provided
        const messageBodyText = msgData.body;
        const messageTimestamp = new Date(msgData.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        if (msgData.sender_id.toString() === streamData.currentUserId.toString()) {
            messageDiv.classList.add('text-right');
        } else {
            messageDiv.classList.add('text-left');
        }

        messageDiv.innerHTML = `
            <small class="font-weight-bold">${senderUsername}</small>
            <div class="message-body p-2 d-inline-block rounded ${msgData.sender_id.toString() === streamData.currentUserId.toString() ? 'bg-primary text-white' : 'bg-secondary text-white'}">
                ${messageBodyText}
            </div>
            <small class="d-block text-muted message-timestamp" data-utc-timestamp="${msgData.timestamp}">
                ${messageTimestamp}
            </small>
        `;
        container.appendChild(messageDiv);
        scrollToBottom(container);
    }

    function scrollToBottom(element) {
        if (element) {
            element.scrollTop = element.scrollHeight;
        }
    }


    function initializeViewerConnection() {
        if (!streamData || !streamData.streamerUsername) {
            console.error("Stream data (streamerUsername) is not available.");
            updateConnectionStatus('Error - Stream information missing.');
            return false;
        }

        if (!streamData.isLive) {
            updateConnectionStatus('Stream is currently offline.');
            console.log(`Streamer ${streamData.streamerUsername} is not live.`);
            return false;
        }

        updateConnectionStatus('Initializing WebRTC connection (SFU)...');
        console.log("Initializing PeerConnection for viewer to connect to SFU.");

        peerConnection = new RTCPeerConnection(iceServers);

        peerConnection.onicecandidate = event => {
            if (event.candidate) {
                console.log('Viewer sending ICE candidate to SFU (via server):', event.candidate);
                socket.emit('sfu_relay_message', {
                    type: 'candidate',
                    payload: event.candidate,
                    stream_username: streamData.streamerUsername,
                    // target_sid: null, // Not needed if Janus handles candidates at stream level
                    // recipient_username: streamData.streamerUsername // Or to SFU directly if server handles that
                });
            }
        };

        peerConnection.ontrack = event => {
            console.log('Track received from SFU.');
            if (remoteVideo && event.streams && event.streams[0]) {
                if (remoteVideo.srcObject !== event.streams[0]) {
                    remoteVideo.srcObject = event.streams[0];
                    console.log('Remote stream from SFU added to video element and attempting to play.');
                    remoteVideo.play().catch(e => console.error("Error playing remote SFU stream:", e));
                }
            } else {
                console.warn("SFU Track event received, but no stream or video element to attach to.", event);
            }
        };

        peerConnection.onconnectionstatechange = () => {
            if (peerConnection) {
                console.log('Viewer SFU Peer Connection State:', peerConnection.connectionState);
                updateConnectionStatus(peerConnection.connectionState);

                switch(peerConnection.connectionState) {
                    case 'connected':
                        updateConnectionStatus('Live!');
                        if (remoteVideo && remoteVideo.paused && remoteVideo.srcObject) {
                           remoteVideo.play().catch(e => console.error("Error auto-playing remote SFU stream post-connection:", e));
                        }
                        break;
                    case 'disconnected':
                        updateConnectionStatus('Disconnected from SFU. Trying to reconnect...');
                        // TODO: Implement SFU reconnection logic if needed
                        break;
                    case 'failed':
                        updateConnectionStatus('SFU Connection failed. Stream may have ended.');
                        if(remoteVideo) remoteVideo.srcObject = null;
                        break;
                    case 'closed':
                        updateConnectionStatus('SFU Stream closed.');
                        if(remoteVideo) remoteVideo.srcObject = null;
                        break;
                }
            }
        };

        // TODO: Conceptual Janus Interaction for viewer
        // 1. Initialize Janus library, create session, attach to VideoRoom plugin.
        // 2. Send a "join and subscribe" request to Janus for streamData.streamerUsername's stream.
        //    This might involve janusHandle.send({ message: { request: "join", room: <room_id_for_stream>, ptype: "subscriber", feed: <feed_id_of_streamer> }})
        //    The room_id and feed_id would typically be managed by your application or a convention.
        // 3. Janus will then likely send an SDP offer (JSEP) for this subscription.
        //    This offer will come via 'sfu_message_direct' (or similar) from the server.

        console.log("PeerConnection for SFU created. Waiting for offer from SFU.");
        updateConnectionStatus('Ready to receive stream data from SFU...');
        return true;
    }

    async function handleOfferAndCreateAnswer(offerSdp, fromUsername) { // fromUsername is likely SFU/Janus via server
        if (!peerConnection) {
            console.error("PeerConnection not initialized for viewer. Cannot handle SFU offer.");
            updateConnectionStatus('Error - Connection not ready to handle SFU offer.');
            return;
        }
        // For SFU, offer typically comes from Janus, not directly from another user in same way as P2P.
        // The 'fromUsername' might be the streamer's if the server relays it that way, or a generic SFU identifier.
        console.log('Received SDP Offer from SFU (via server from', fromUsername, '):', offerSdp);
        updateConnectionStatus('SFU stream data received, preparing answer...');

        try {
            await peerConnection.setRemoteDescription(new RTCSessionDescription({ type: 'offer', sdp: offerSdp }));
            console.log("Remote description (SFU offer) set successfully.");

            const answer = await peerConnection.createAnswer();
            console.log("Answer to SFU offer created successfully.");

            await peerConnection.setLocalDescription(answer);
            console.log("Local description (SFU answer) set successfully.");

            socket.emit('sfu_relay_message', {
                type: 'answer', // Viewer is sending an answer
                payload: { sdp: answer.sdp }, // The answer JSEP
                stream_username: streamData.streamerUsername, // Context of the stream
                // target_sid: null, // Or specific SID if known for Janus component
                // recipient_username: streamData.streamerUsername // Or to SFU directly
            });
            updateConnectionStatus('Connecting to SFU...');

        } catch (error) {
            console.error('Error handling SFU WebRTC offer or creating/setting answer:', error);
            updateConnectionStatus('Error processing SFU stream offer.');
        }
    }

    async function handleReceivedIceCandidate(candidate, fromUsername) { // fromUsername is likely SFU/Janus
        if (!peerConnection) {
            console.error("PeerConnection not initialized for viewer. Cannot handle SFU ICE candidate.");
            return;
        }

        try {
            await peerConnection.addIceCandidate(new RTCIceCandidate(candidate));
            console.log('Added ICE candidate from SFU (via server from', fromUsername, '):', candidate);
        } catch (error) {
            console.error('Error adding received SFU ICE candidate (viewer):', error);
        }
    }

    socket.on('connect', () => {
        console.log('Socket.IO connected for viewer.');
        if (streamData && streamData.streamerUsername) {
            const initialized = initializeViewerConnection();
            if (initialized) {
                console.log(`Emitting join_stream_room for ${streamData.streamerUsername}`);
                socket.emit('join_stream_room', { stream_username: streamData.streamerUsername });
            }
            // Initialize chat if conversationId is present
            if (streamData.conversationId) {
                initializeStreamChat();
            }
        } else {
            console.log("Streamer info missing on connect.");
            updateConnectionStatus('Stream information missing.');
        }
    });

    socket.on('joined_stream_room_ack', (data) => {
        console.log('Viewer joined stream room:', data.room);
        if (peerConnection && peerConnection.connectionState !== 'connected') {
             updateConnectionStatus('Joined stream room. Waiting for SFU broadcast...');
        }
    });

    // Listen for SFU messages (offer, candidate) relayed by the server
    socket.on('sfu_message_direct', async (data) => { // Or 'sfu_message_user' or 'sfu_message_room' depending on server logic
        console.log("Socket event: sfu_message_direct received", data);
        if (data.stream_username === streamData.streamerUsername) {
            if (!peerConnection && data.type !== 'offer') { // Allow offer to initialize PC
                console.warn("Received SFU message but PeerConnection is not initialized, and it's not an offer.");
                return;
            }

            if (data.type === 'offer') {
                if (!peerConnection) {
                    console.log("PeerConnection not ready, but received SFU offer. Initializing now.");
                    const initialized = initializeViewerConnection();
                     if (!initialized || !peerConnection) {
                        console.error("Failed to initialize PeerConnection on SFU offer receipt.");
                        return;
                    }
                }
                await handleOfferAndCreateAnswer(data.payload.sdp || data.payload, data.from_username); // data.payload might be the jsep itself
            } else if (data.type === 'candidate') {
                await handleReceivedIceCandidate(data.payload, data.from_username);
            } else {
                console.log("Received other SFU message type:", data.type, data.payload);
                // Handle other Janus-specific messages if necessary
            }
        } else {
            console.warn("SFU message received for a different stream or from an unexpected source:", data);
        }
    });

    // socket.on('webrtc_offer_received', ...); // Old P2P: Remove or adapt
    // socket.on('webrtc_ice_candidate_received', ...); // Old P2P: Remove or adapt

    socket.on('stream_error', (data) => {
        console.error("Stream Error from server:", data.message);
        updateConnectionStatus("Error - " + data.message);
    });

    socket.on('stream_really_ended', (data) => {
        console.log("Stream has officially ended by broadcaster.", data.message);
        updateConnectionStatus('Stream has ended by broadcaster.');
        if (peerConnection) {
            peerConnection.close();
            peerConnection = null;
        }
        if (remoteVideo) remoteVideo.srcObject = null;
    });

    socket.on('disconnect', () => {
        console.log('Socket.IO disconnected for viewer.');
        if (connectionStatusP && !connectionStatusP.textContent.includes("ended") && !connectionStatusP.textContent.includes("offline")) {
            updateConnectionStatus('Disconnected from signaling server.');
        }
    });

    // Initial status based on streamData passed from template
    if (typeof streamData === 'undefined') {
        console.error("streamData is not defined. Check template.");
        updateConnectionStatus('Error - Stream information unavailable.');
    } else if (!streamData.isLive) {
         updateConnectionStatus('Stream is currently offline.');
    } else {
        updateConnectionStatus('Connecting to signaling server...');
    }
});
