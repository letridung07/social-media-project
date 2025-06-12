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
    const enableRecordingCheckbox = document.getElementById('enableRecordingCheckbox');

    let localStream;
    // let peerConnections = {}; // Replaced for SFU
    let janusHandle = null; // Represents the connection/plugin handle to Janus
    let viewerCount = 0; // May still be useful for display

    const JANUS_SERVER_URL = typeof janusServerUrl !== 'undefined' ? janusServerUrl : '/janus_placeholder';

    const iceServers = {
        iceServers: [
            { urls: 'stun:stun.l.google.com:19302' }
        ]
    };
    // Conditionally add TURN server if configured and URL is not a placeholder
    if (typeof turnConfig !== 'undefined' && turnConfig.urls && !turnConfig.urls.includes('yourturnserver.example.com')) {
        iceServers.iceServers.push({
            urls: turnConfig.urls,
            username: turnConfig.username,
            credential: turnConfig.credential
        });
    }

    // function updateViewerCountDisplay() { // May adapt if Janus provides viewer counts
    //     if (webRtcStatusP.textContent.startsWith('WebRTC: Broadcasting')) {
    //         webRtcStatusP.textContent = `WebRTC: Broadcasting to ${viewerCount} viewer(s)`;
    //     }
    // }

    socket.on('connect', () => {
        console.log('Socket.IO connected for broadcaster.');
        // Broadcaster joins their own stream room upon connection if they intend to go live or are already live.
        // This is more for receiving viewer join/leave events if needed before WebRTC active.
        socket.emit('join_stream_room', { stream_username: currentUsername });
    });

    socket.on('joined_stream_room_ack', (data) => {
        console.log('Broadcaster confirmed in stream room:', data.room);
    });

    socket.on('stream_error', (data) => {
        console.error("Stream Error from server:", data.message);
        alert("Stream Error: " + data.message);
        if (webRtcStatusP) webRtcStatusP.textContent = `WebRTC Error: ${data.message}`;
    });

    socket.on('recording_status_update', (data) => {
        console.log('Recording status update:', data);
        // Update UI based on data.status and data.message
        // e.g., webRtcStatusP.textContent += ` | Recording: ${data.status}`;
        alert(`Recording status: ${data.status} - ${data.message || ''}`);
    });


    if (startCameraButton && localVideo) {
        startCameraButton.onclick = async () => {
            try {
                if (localStream) {
                    localStream.getTracks().forEach(track => track.stop());
                }
                localStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
                localVideo.srcObject = localStream;
                localVideo.muted = true; // Broadcaster does not need to hear their own audio locally
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

    // // P2P: createPeerConnection - To be replaced/removed for SFU
    // async function createPeerConnection(viewerSid, viewerUsername) { ... }

    // // P2P: makeOffer - To be replaced/removed for SFU
    // async function makeOffer(viewerSid, viewerUsername) { ... }

    if (startWebRTCBroadcastButton) {
        startWebRTCBroadcastButton.addEventListener('click', async () => {
            if (!localStream) {
                 alert("Please start your camera first.");
                 return;
            }
            if (goLiveCheckbox && !goLiveCheckbox.checked) {
                alert("Reminder: Check the 'Go Live' box and save settings if you want your stream to be publicly listed as live on the backend.");
            }

            if (webRtcStatusP) webRtcStatusP.textContent = 'WebRTC: Initializing SFU broadcast...';
            startWebRTCBroadcastButton.textContent = 'Initializing...';
            startWebRTCBroadcastButton.disabled = true;

            // TODO: Implement Janus Initialization and Publishing
            // 1. Initialize Janus library (e.g., new Janus({ server: JANUS_SERVER_URL, ... }))
            // 2. Create a Janus session (janus.attach({ plugin: "janus.plugin.videoroom", ... -> janusHandle }))
            // 3. Configure and publish localStream to janusHandle
            //    janusHandle.createOffer({
            //        media: { audioRecv: false, videoRecv: false, audioSend: true, videoSend: true },
            //        success: function(jsep) {
            //            // Send this jsep (offer) to Janus via our backend relay
            //            socket.emit('sfu_relay_message', {
            //                type: 'publish_offer', // Custom type for our backend to understand
            //                payload: jsep,
            //                stream_username: currentUsername
            //            });
            //        },
            //        error: function(error) { console.error("Janus offer error:", error); }
            //    });
            // 4. Handle Janus responses (answers, candidates) via 'sfu_message_direct' or 'sfu_message_user'

            console.log("Attempting to start WebRTC broadcast with SFU (Janus).");
            webRtcStatusP.textContent = 'WebRTC: Connecting to SFU...';
            // Simulate connection for now, actual state will depend on Janus interaction
            // On successful publishing with Janus:
            if (enableRecordingCheckbox && enableRecordingCheckbox.checked) {
                console.log("Recording enabled, sending start_stream_recording_sfu event.");
                socket.emit('start_stream_recording_sfu', { stream_username: currentUsername });
            }

            // This is a placeholder for actual Janus success
            startWebRTCBroadcastButton.textContent = 'Currently Broadcasting (SFU)';
            if (stopWebRTCBroadcastButton) stopWebRTCBroadcastButton.disabled = false;
            if (startCameraButton) startCameraButton.disabled = true;
            webRtcStatusP.textContent = 'WebRTC: Broadcasting to SFU.';
        });
    }

    if (stopWebRTCBroadcastButton) {
        stopWebRTCBroadcastButton.onclick = () => {
            if (webRtcStatusP) webRtcStatusP.textContent = 'WebRTC: Stopping SFU broadcast...';
            console.log("Stopping WebRTC SFU broadcast...");

            // TODO: Implement Janus Unpublish and Teardown
            // 1. Send "unpublish" or "hangup" to janusHandle if it exists
            //    janusHandle.send({ message: { request: "unpublish" } });
            //    janusHandle.hangup(); // Or similar command
            // 2. Detach from plugin, destroy session. janusHandle = null;

            if (localStream) {
                localStream.getTracks().forEach(track => track.stop());
                localVideo.srcObject = null;
            }
            if (cameraStatusP) cameraStatusP.textContent = 'Camera: Off';

            // If recording was active (check a state variable or the checkbox, though checkbox might not reflect actual recording state)
            // For simplicity, assume if enableRecordingCheckbox was checked, we attempt to stop.
            // A more robust solution would track actual recording state.
            if (enableRecordingCheckbox && enableRecordingCheckbox.checked) { // This is a simplification
                console.log("Recording was enabled, sending stop_stream_recording_sfu event.");
                socket.emit('stop_stream_recording_sfu', { stream_username: currentUsername });
            }

            // socket.emit('stream_ended_webrtc', { stream_username: currentUsername }); // Old P2P event, might adapt for SFU if needed for backend status

            startWebRTCBroadcastButton.textContent = 'Start WebRTC Broadcast';
            startWebRTCBroadcastButton.disabled = false;
            stopWebRTCBroadcastButton.disabled = true;
            if (goLiveSubmitButton) goLiveSubmitButton.disabled = true;
            if (startCameraButton) startCameraButton.disabled = false;
            if (webRtcStatusP) webRtcStatusP.textContent = 'WebRTC: Idle (SFU Broadcast Ended)';

            if (goLiveCheckbox && goLiveCheckbox.checked) {
                alert("WebRTC broadcast stopped. Uncheck 'Go Live' and save settings to update your stream's public status to offline if desired.");
            }
            janusHandle = null; // Reset Janus handle
        };
    }

    // // P2P: closePeerConnection - To be replaced/removed for SFU
    // function closePeerConnection(viewerSid) { ... }

    // // P2P: socket.on('webrtc_answer_received', ... ) - Replaced by sfu_message_direct/user
    // socket.on('webrtc_answer_received', async (data) => { ... });

    // // P2P: socket.on('webrtc_ice_candidate_received', ... ) - Replaced by sfu_message_direct/user
    // socket.on('webrtc_ice_candidate_received', async (data) => { ... });

    // // P2P: socket.on('viewer_joined', ... ) - Replaced by viewer_joined_sfu
    // socket.on('viewer_joined', (data) => { ... });

    // // P2P: socket.on('viewer_left', ... ) - Replaced by viewer_left_sfu
    // socket.on('viewer_left', (data) => { ... });

    // --- SFU Specific Event Handlers ---
    socket.on('viewer_joined_sfu', (data) => {
        console.log('SFU Event: Viewer joined:', data.viewer_username, 'SID:', data.viewer_sid, 'for stream:', data.stream_username);
        // TODO: Conceptual Janus Interaction for Broadcaster
        // If this broadcaster client needs to do something with Janus for this new viewer,
        // it would happen here. For example, if Janus doesn't auto-handle new viewers,
        // the broadcaster might need to signal Janus to offer a stream to data.viewer_sid.
        // This often depends on the specific Janus plugin and room configuration.
        // For a simple VideoRoom setup, Janus might handle offers to new viewers automatically
        // once they request to join the room (client-side viewer logic).
        // Or, the server might send an offer to the new viewer directly upon their join.
        viewerCount++; // Simple increment, actual count might come from Janus
        if (webRtcStatusP) webRtcStatusP.textContent = `WebRTC: Broadcasting to SFU. Viewers: ${viewerCount}`;

    });

    socket.on('viewer_left_sfu', (data) => {
        console.log('SFU Event: Viewer left:', data.viewer_username, 'SID:', data.viewer_sid, 'from stream:', data.stream_username);
        // TODO: Conceptual Janus Interaction for Broadcaster
        // Inform Janus that data.viewer_sid has left, if necessary for resource cleanup
        // on the Janus side specific to this viewer's handle.
        viewerCount = Math.max(0, viewerCount - 1); // Simple decrement
        if (webRtcStatusP) webRtcStatusP.textContent = `WebRTC: Broadcasting to SFU. Viewers: ${viewerCount}`;
    });

    socket.on('sfu_message_direct', (data) => {
        console.log(`SFU Direct Message from ${data.from_username} (SID: ${data.from_sid}) of type ${data.type} for stream ${data.stream_username}:`, data.payload);
        // This is where the broadcaster's client would receive messages from Janus
        // (potentially relayed by viewers or directly from Janus via our backend).
        if (janusHandle) {
            if (data.payload.type === 'answer') { // Assuming payload contains a JSEP answer
                // janusHandle.handleRemoteJsep({ jsep: data.payload }); // Conceptual for janus.js
                console.log("TODO: Process SFU JSEP answer with janusHandle:", data.payload);
            } else if (data.payload.candidate) { // Assuming payload is an ICE candidate
                // janusHandle.addIceCandidate(data.payload); // Conceptual for janus.js
                console.log("TODO: Process SFU ICE candidate with janusHandle:", data.payload);
            } else {
                 console.log("Received sfu_message_direct, payload type not directly handled by placeholder:", data.payload);
            }
        } else {
            console.warn("Received sfu_message_direct but janusHandle is null.");
        }
    });

    socket.on('sfu_message_user', (data) => {
        // This event is similar to 'sfu_message_direct' but was targeted via username.
        // Client-side, the handling might be identical if janusHandle is the main interaction point.
        console.log(`SFU User Message from ${data.from_username} (SID: ${data.from_sid}) of type ${data.type} for stream ${data.stream_username}:`, data.payload);
        if (janusHandle) {
            if (data.payload.type === 'answer') {
                // janusHandle.handleRemoteJsep({ jsep: data.payload });
                console.log("TODO: Process SFU JSEP answer with janusHandle (from sfu_message_user):", data.payload);
            } else if (data.payload.candidate) {
                // janusHandle.addIceCandidate(data.payload);
                console.log("TODO: Process SFU ICE candidate with janusHandle (from sfu_message_user):", data.payload);
            } else {
                 console.log("Received sfu_message_user, payload type not directly handled by placeholder:", data.payload);
            }
        } else {
            console.warn("Received sfu_message_user but janusHandle is null.");
        }
    });


    // Initial state of buttons and status messages
    if (goLiveSubmitButton) goLiveSubmitButton.disabled = true;
    if (startWebRTCBroadcastButton) startWebRTCBroadcastButton.disabled = true;
    if (stopWebRTCBroadcastButton) stopWebRTCBroadcastButton.disabled = true;
    if (cameraStatusP) cameraStatusP.textContent = 'Camera: Off';
    if (webRtcStatusP) webRtcStatusP.textContent = 'WebRTC: Idle';
});
