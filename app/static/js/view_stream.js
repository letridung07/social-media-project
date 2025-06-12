// app/static/js/view_stream.js
document.addEventListener('DOMContentLoaded', () => {
    console.log('View Stream JS Loaded');

    const remoteVideo = document.getElementById('remoteVideo');
    const connectionStatusP = document.getElementById('connectionStatus');
    const socket = io();

    let peerConnection;
    const iceServers = {
        iceServers: [
            { urls: 'stun:stun.l.google.com:19302' }
        ]
    };

    function initializeViewerConnection() {
        if (!streamData || !streamData.streamerUsername) {
            console.error("Stream data (streamerUsername) is not available.");
            if(connectionStatusP) connectionStatusP.textContent = 'Status: Error - Stream information missing.';
            return false;
        }

        if (!streamData.isLive) {
            if(connectionStatusP) connectionStatusP.textContent = 'Status: Stream is currently offline.';
            console.log(`Streamer ${streamData.streamerUsername} is not live.`);
            return false;
        }

        if(connectionStatusP) connectionStatusP.textContent = 'Status: Initializing WebRTC connection...';
        console.log("Initializing PeerConnection for viewer.");

        peerConnection = new RTCPeerConnection(iceServers);

        peerConnection.onicecandidate = event => {
            if (event.candidate) {
                console.log('Viewer sending ICE candidate to broadcaster:', event.candidate);
                socket.emit('webrtc_ice_candidate', {
                    candidate: event.candidate,
                    stream_username: streamData.streamerUsername,
                    target_sid: null // Server relays to broadcaster in stream_username's room
                });
            }
        };

        peerConnection.ontrack = event => {
            console.log('Track received from broadcaster.');
            if (remoteVideo && event.streams && event.streams[0]) {
                if (remoteVideo.srcObject !== event.streams[0]) {
                    remoteVideo.srcObject = event.streams[0];
                    console.log('Remote stream added to video element and attempting to play.');
                    remoteVideo.play().catch(e => console.error("Error playing remote stream:", e));
                    // Status update will be handled by onconnectionstatechange 'connected' or video.onplaying
                }
            } else {
                console.warn("Track event received, but no stream or video element to attach to.", event);
            }
        };

        peerConnection.onconnectionstatechange = () => {
            if (peerConnection) {
                console.log('Viewer Peer Connection State:', peerConnection.connectionState);
                if(connectionStatusP) connectionStatusP.textContent = `Status: ${peerConnection.connectionState}`;

                switch(peerConnection.connectionState) {
                    case 'connected':
                        if(connectionStatusP) connectionStatusP.textContent = 'Status: Live!';
                        if (remoteVideo && remoteVideo.paused && remoteVideo.srcObject) {
                           remoteVideo.play().catch(e => console.error("Error auto-playing remote stream post-connection:", e));
                        }
                        break;
                    case 'disconnected':
                        if(connectionStatusP) connectionStatusP.textContent = 'Status: Disconnected. Trying to reconnect...';
                        // Some browsers might attempt to reconnect automatically.
                        break;
                    case 'failed':
                        if(connectionStatusP) connectionStatusP.textContent = 'Status: Connection failed. Stream may have ended.';
                        if(remoteVideo) remoteVideo.srcObject = null;
                        break;
                    case 'closed':
                        if(connectionStatusP) connectionStatusP.textContent = 'Status: Stream closed.';
                        if(remoteVideo) remoteVideo.srcObject = null;
                        break;
                }
            }
        };

        console.log("PeerConnection created for viewer. Ready for SDP offer from broadcaster.");
        if(connectionStatusP) connectionStatusP.textContent = 'Status: Ready to receive stream data...';
        return true;
    }

    async function handleOfferAndCreateAnswer(offerSdp, fromUsername) {
        if (!peerConnection) {
            console.error("PeerConnection not initialized for viewer. Cannot handle offer.");
            if(connectionStatusP) connectionStatusP.textContent = 'Status: Error - Connection not ready to handle offer.';
            return;
        }
        if (fromUsername !== streamData.streamerUsername) {
            console.warn(`Offer received from unexpected user ${fromUsername}. Expected ${streamData.streamerUsername}. Ignoring.`);
            return;
        }

        console.log('Received SDP Offer from broadcaster:', offerSdp);
        if(connectionStatusP) connectionStatusP.textContent = 'Status: Stream data received, preparing...';

        try {
            await peerConnection.setRemoteDescription(new RTCSessionDescription({ type: 'offer', sdp: offerSdp }));
            console.log("Remote description (offer) set successfully.");

            const answer = await peerConnection.createAnswer();
            console.log("Answer created successfully.");

            await peerConnection.setLocalDescription(answer);
            console.log("Local description (answer) set successfully.");
            console.log('Viewer SDP Answer:', answer.sdp);

            socket.emit('webrtc_answer', {
                answer_sdp: answer.sdp,
                stream_username: streamData.streamerUsername,
            });
            if(connectionStatusP) connectionStatusP.textContent = 'Status: Connecting to broadcaster...';

        } catch (error) {
            console.error('Error handling WebRTC offer or creating/setting answer:', error);
            if(connectionStatusP) connectionStatusP.textContent = 'Status: Error processing stream offer.';
        }
    }

    async function handleReceivedIceCandidate(candidate, fromUsername) {
        if (!peerConnection) {
            console.error("PeerConnection not initialized for viewer. Cannot handle ICE candidate.");
            return;
        }
        if (fromUsername !== streamData.streamerUsername) {
            console.warn(`ICE candidate received from unexpected user ${fromUsername}. Expected ${streamData.streamerUsername}. Ignoring.`);
            return;
        }

        try {
            await peerConnection.addIceCandidate(new RTCIceCandidate(candidate));
            console.log('Added ICE candidate from broadcaster:', candidate);
        } catch (error) {
            console.error('Error adding received ICE candidate (viewer):', error);
        }
    }

    socket.on('connect', () => {
        console.log('Socket.IO connected for viewer.');
        if (streamData && streamData.streamerUsername) { // streamData.isLive check is now inside initializeViewerConnection
            const initialized = initializeViewerConnection(); // This also checks isLive
            if (initialized) { // if isLive and PC is set up
                console.log(`Emitting join_stream_room for ${streamData.streamerUsername}`);
                socket.emit('join_stream_room', { stream_username: streamData.streamerUsername });
            }
        } else {
            console.log("Streamer info missing on connect.");
            if(connectionStatusP) connectionStatusP.textContent = 'Status: Stream information missing.';
        }
    });

    socket.on('joined_stream_room_ack', (data) => {
        console.log('Viewer joined stream room:', data.room);
        if(connectionStatusP && peerConnection && peerConnection.connectionState !== 'connected') {
             connectionStatusP.textContent = 'Status: Joined stream room. Waiting for broadcast...';
        }
    });

    socket.on('webrtc_offer_received', async (data) => {
        console.log("Socket event: webrtc_offer_received", data);
        if (data.from_username === streamData.streamerUsername) {
            if (!peerConnection) {
                console.log("PeerConnection not ready, but received offer. Initializing now.");
                const initialized = initializeViewerConnection();
                 if (!initialized || !peerConnection) {
                    console.error("Failed to initialize PeerConnection on offer receipt.");
                    return;
                }
            }
            await handleOfferAndCreateAnswer(data.offer_sdp, data.from_username);
        } else {
            console.warn("Offer received from non-streamer user:", data.from_username);
        }
    });

    socket.on('webrtc_ice_candidate_received', async (data) => {
        console.log("Socket event: webrtc_ice_candidate_received", data);
        if (data.from_username === streamData.streamerUsername) {
             if (!peerConnection) {
                console.warn("Received ICE candidate but PeerConnection is not initialized.");
                return;
            }
            await handleReceivedIceCandidate(data.candidate, data.from_username);
        } else {
             console.warn("ICE Candidate received from non-streamer user:", data.from_username);
        }
    });

    socket.on('stream_error', (data) => {
        console.error("Stream Error from server:", data.message);
        if(connectionStatusP) connectionStatusP.textContent = "Status: Error - " + data.message;
    });

    socket.on('stream_really_ended', (data) => {
        console.log("Stream has officially ended by broadcaster.", data.message);
        if(connectionStatusP) connectionStatusP.textContent = 'Status: Stream has ended by broadcaster.';
        if (peerConnection) {
            peerConnection.close();
            peerConnection = null;
        }
        if (remoteVideo) remoteVideo.srcObject = null;
    });

    socket.on('disconnect', () => {
        console.log('Socket.IO disconnected for viewer.');
        // Avoid aggressive "Disconnected" message if stream already ended gracefully
        if (connectionStatusP && !connectionStatusP.textContent.includes("ended") && !connectionStatusP.textContent.includes("offline")) {
            connectionStatusP.textContent = 'Status: Disconnected from signaling server.';
        }
    });

    // Initial status based on streamData passed from template
    if (typeof streamData === 'undefined') {
        console.error("streamData is not defined. Check template.");
        if(connectionStatusP) connectionStatusP.textContent = 'Status: Error - Stream information unavailable.';
    } else if (!streamData.isLive) {
         if(connectionStatusP) connectionStatusP.textContent = 'Status: Stream is currently offline.';
    } else {
        // If streamData.isLive is true, socket 'connect' handler will call initializeViewerConnection
        // and then emit join_stream_room. Initial status set there.
        if(connectionStatusP) connectionStatusP.textContent = 'Status: Connecting to signaling server...';
    }
});
