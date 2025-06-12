// app/static/js/manage_stream.js
document.addEventListener('DOMContentLoaded', () => {
    console.log('Manage Stream JS Loaded');

    if (typeof currentUsername === 'undefined') {
        console.error('currentUsername is not defined. Check template.');
        alert('Error: User context not available for streaming.');
        return;
    }

    const socket = io();

    const localVideo = document.getElementById('localVideo');
    const startCameraButton = document.getElementById('startCameraButton');
    const goLiveSubmitButton = document.getElementById('goLiveButton');
    const goLiveCheckbox = document.getElementById('goLiveCheckbox');
    const startWebRTCBroadcastButton = document.getElementById('startWebRTCBroadcastButton');
    const stopWebRTCBroadcastButton = document.getElementById('stopWebRTCBroadcastButton');

    const cameraStatusP = document.getElementById('cameraStatus');
    const webRtcStatusP = document.getElementById('webRtcStatus');

    let localStream;
    let peerConnections = {};
    let viewerCount = 0;

    const iceServers = {
        iceServers: [ { urls: 'stun:stun.l.google.com:19302' } ]
    };

    function updateViewerCountDisplay() {
        if (webRtcStatusP.textContent.startsWith('WebRTC: Broadcasting')) {
            webRtcStatusP.textContent = `WebRTC: Broadcasting to ${viewerCount} viewer(s)`;
        }
    }

    socket.on('connect', () => {
        console.log('Socket.IO connected for broadcaster.');
        if (goLiveCheckbox && goLiveCheckbox.checked) {
            socket.emit('join_stream_room', { stream_username: currentUsername });
        }
    });

    socket.on('joined_stream_room_ack', (data) => {
        console.log('Broadcaster joined stream room:', data.room);
    });

    socket.on('stream_error', (data) => {
        console.error("Stream Error from server:", data.message);
        alert("Stream Error: " + data.message);
        if (webRtcStatusP) webRtcStatusP.textContent = `WebRTC Error: ${data.message}`;
    });

    if (startCameraButton && localVideo) {
        startCameraButton.onclick = async () => {
            try {
                if (localStream) {
                    localStream.getTracks().forEach(track => track.stop());
                }
                localStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
                localVideo.srcObject = localStream;
                localVideo.muted = true;
                localVideo.play();

                if (goLiveSubmitButton) goLiveSubmitButton.disabled = false;
                if (startWebRTCBroadcastButton) startWebRTCBroadcastButton.disabled = false;
                if (stopWebRTCBroadcastButton) stopWebRTCBroadcastButton.disabled = true;
                if (cameraStatusP) cameraStatusP.textContent = 'Camera: On';
                console.log('Local camera and microphone accessed.');
            } catch (error) {
                console.error('Error accessing media devices.', error);
                alert('Error accessing media devices: ' + error.message);
                if (goLiveSubmitButton) goLiveSubmitButton.disabled = true;
                if (startWebRTCBroadcastButton) startWebRTCBroadcastButton.disabled = true;
                if (cameraStatusP) cameraStatusP.textContent = 'Camera: Error accessing devices';
            }
        };
    }

    async function createPeerConnection(viewerSid, viewerUsername) {
        if (!localStream) {
            console.warn("Local stream not ready, cannot create peer connection for", viewerUsername);
            return null;
        }

        const pc = new RTCPeerConnection(iceServers);
        peerConnections[viewerSid] = pc;
        viewerCount = Object.keys(peerConnections).length;
        console.log(`PeerConnection created for viewer: ${viewerUsername} (SID: ${viewerSid}). Total viewers: ${viewerCount}`);
        if (webRtcStatusP.textContent.startsWith('WebRTC: Broadcasting')) { // Check if currently broadcasting
             updateViewerCountDisplay();
        }


        pc.onicecandidate = event => {
            if (event.candidate) {
                console.log(`Broadcaster sending ICE candidate to ${viewerUsername} (SID: ${viewerSid}):`, event.candidate);
                socket.emit('webrtc_ice_candidate', {
                    candidate: event.candidate,
                    stream_username: currentUsername,
                    target_sid: viewerSid
                });
            }
        };

        pc.onconnectionstatechange = () => {
            console.log(`PeerConnection state for ${viewerUsername} (SID: ${viewerSid}): ${pc.connectionState}`);
            if (webRtcStatusP && (startWebRTCBroadcastButton.disabled)) { // Only update if broadcasting
                 webRtcStatusP.textContent = `WebRTC: Broadcasting to ${viewerCount} viewer(s). Last event: ${viewerUsername} is ${pc.connectionState}.`;
            }
            if (pc.connectionState === 'disconnected' || pc.connectionState === 'closed' || pc.connectionState === 'failed') {
                closePeerConnection(viewerSid);
            }
        };

        localStream.getTracks().forEach(track => {
            try {
                pc.addTrack(track, localStream);
            } catch (e) {
                console.error("Error adding track:", track, e);
            }
        });
        console.log(`Local tracks added to PeerConnection for ${viewerUsername}`);
        return pc;
    }

    async function makeOffer(viewerSid, viewerUsername) {
        let pc = peerConnections[viewerSid];
        if (!pc) {
            pc = await createPeerConnection(viewerSid, viewerUsername);
            if (!pc) return;
        }

        if (webRtcStatusP) webRtcStatusP.textContent = `WebRTC: Sending offer to ${viewerUsername}...`;
        try {
            const offer = await pc.createOffer();
            await pc.setLocalDescription(offer);
            console.log(`SDP Offer created for ${viewerUsername} (SID: ${viewerSid}). Sending...`);
            socket.emit('webrtc_offer', {
                offer_sdp: offer.sdp,
                stream_username: currentUsername,
                target_viewer_sid: viewerSid
            });
        } catch (error) {
            console.error(`Error creating WebRTC offer for ${viewerUsername}:`, error);
            if (webRtcStatusP) webRtcStatusP.textContent = `WebRTC: Error offering to ${viewerUsername}.`;
        }
    }

    if (startWebRTCBroadcastButton) {
        startWebRTCBroadcastButton.addEventListener('click', async () => {
            if (!localStream) {
                 alert("Please start your camera first.");
                 return;
            }
            if (goLiveCheckbox && !goLiveCheckbox.checked) {
                alert("Reminder: Check the 'Go Live' box and save settings if you want your stream to be publicly listed as live on the backend.");
            }

            if (webRtcStatusP) webRtcStatusP.textContent = 'WebRTC: Initializing broadcast...';
            startWebRTCBroadcastButton.textContent = 'Initializing...';
            startWebRTCBroadcastButton.disabled = true;

            // Join room explicitly if not already joined (e.g. if goLiveCheckbox wasn't checked on load)
            socket.emit('join_stream_room', { stream_username: currentUsername });

            // The actual offers will be sent when viewers join and 'viewer_joined' is received.
            // This button just sets the state that the broadcaster is ready.
            console.log("WebRTC broadcasting prepared by broadcaster. Waiting for viewers.");
            webRtcStatusP.textContent = 'WebRTC: Ready for viewers. Broadcasting to 0 viewer(s).';
            startWebRTCBroadcastButton.textContent = 'Currently Broadcasting'; // Remains disabled while active
            if (stopWebRTCBroadcastButton) stopWebRTCBroadcastButton.disabled = false;
            if (startCameraButton) startCameraButton.disabled = true;
        });
    }

    if (stopWebRTCBroadcastButton) {
        stopWebRTCBroadcastButton.onclick = () => {
            if (webRtcStatusP) webRtcStatusP.textContent = 'WebRTC: Stopping...';
            console.log("Stopping WebRTC broadcast...");

            if (localStream) { // Only stop tracks if localStream exists
                localStream.getTracks().forEach(track => track.stop());
                localVideo.srcObject = null;
            }
            if (cameraStatusP) cameraStatusP.textContent = 'Camera: Off';


            Object.keys(peerConnections).forEach(viewerSid => {
                closePeerConnection(viewerSid);
            });
            peerConnections = {}; // Reset
            viewerCount = 0;

            socket.emit('stream_ended_webrtc', { stream_username: currentUsername });

            startWebRTCBroadcastButton.textContent = 'Start WebRTC Broadcast';
            startWebRTCBroadcastButton.disabled = false; // Allow restarting
            stopWebRTCBroadcastButton.disabled = true;
            if (goLiveSubmitButton) goLiveSubmitButton.disabled = true; // Require camera restart
            if (startCameraButton) startCameraButton.disabled = false;
            if (webRtcStatusP) webRtcStatusP.textContent = 'WebRTC: Idle (Broadcast Ended)';

            if (goLiveCheckbox && goLiveCheckbox.checked) {
                alert("WebRTC broadcast stopped. Uncheck 'Go Live' and save settings to update your stream's public status to offline if desired.");
            }
        };
    }

    function closePeerConnection(viewerSid) {
        if (peerConnections[viewerSid]) {
            peerConnections[viewerSid].close();
            delete peerConnections[viewerSid];
            viewerCount = Object.keys(peerConnections).length;
            console.log(`PeerConnection closed for viewer SID: ${viewerSid}. Total viewers: ${viewerCount}`);
            updateViewerCountDisplay();
        }
    }

    socket.on('webrtc_answer_received', async (data) => {
        const viewerSid = data.viewer_sid;
        const pc = peerConnections[viewerSid];

        if (pc && pc.signalingState === 'have-local-offer') {
            console.log(`Received SDP Answer from viewer ${data.from_username} (SID: ${viewerSid}):`, data.answer_sdp);
            if (webRtcStatusP) webRtcStatusP.textContent = `WebRTC: Received answer from ${data.from_username}. Connecting...`;
            try {
                await pc.setRemoteDescription(new RTCSessionDescription({ type: 'answer', sdp: data.answer_sdp }));
                console.log(`Remote description (answer) set for viewer ${data.from_username}`);
                // Connection state change will update status further
            } catch (error) {
                console.error(`Error setting remote description for answer from ${data.from_username}:`, error);
                if (webRtcStatusP) webRtcStatusP.textContent = `WebRTC: Error with ${data.from_username}'s answer.`;
            }
        } else {
            console.warn(`Received answer from ${data.from_username}, but no suitable PC or state. State: ${pc ? pc.signalingState : 'No PC'}`);
        }
    });

    socket.on('webrtc_ice_candidate_received', async (data) => {
        // For broadcaster, candidates come from viewers. The server should include viewer's SID.
        const viewerSid = data.from_sid; // Assuming server adds 'from_sid' for candidates from viewers
        const pc = peerConnections[viewerSid];

        if (pc && data.candidate) {
             console.log(`Broadcaster received ICE candidate from viewer ${data.from_username} (SID: ${viewerSid}):`, data.candidate);
            try {
                await pc.addIceCandidate(new RTCIceCandidate(data.candidate));
            } catch (error) {
                console.error(`Error adding received ICE candidate from ${data.from_username} (SID: ${viewerSid}):`, error);
            }
        } else if (data.from_username === currentUsername) {
            // This should not happen if server uses skip_sid and we target candidates with target_sid
        } else {
             console.warn(`Received ICE candidate from ${data.from_username} but no PC found for SID ${viewerSid} or candidate missing.`);
        }
    });

    socket.on('viewer_joined', (data) => {
        console.log('Viewer joined:', data.viewer_username, 'SID:', data.viewer_sid);
        if (localStream && startWebRTCBroadcastButton.disabled) { // If "Start WebRTC Broadcast" is disabled, it implies we are in "broadcasting" mode
            console.log(`New viewer ${data.viewer_username} joined. Creating offer for them.`);
            if (webRtcStatusP) webRtcStatusP.textContent = `WebRTC: New viewer ${data.viewer_username}. Sending offer...`;
            makeOffer(data.viewer_sid, data.viewer_username);
        } else {
            console.log("New viewer joined, but broadcaster is not actively in WebRTC broadcast mode yet.");
        }
    });

    socket.on('viewer_left', (data) => {
        console.log('Viewer left:', data.viewer_username, 'SID:', data.viewer_sid);
        closePeerConnection(data.viewer_sid);
        if (webRtcStatusP && startWebRTCBroadcastButton.disabled) { // If broadcasting
            updateViewerCountDisplay();
        }
    });

    // Initial state of buttons and status messages
    if (goLiveSubmitButton) goLiveSubmitButton.disabled = true;
    if (startWebRTCBroadcastButton) startWebRTCBroadcastButton.disabled = true;
    if (stopWebRTCBroadcastButton) stopWebRTCBroadcastButton.disabled = true;
    if (cameraStatusP) cameraStatusP.textContent = 'Camera: Off';
    if (webRtcStatusP) webRtcStatusP.textContent = 'WebRTC: Idle';
});
