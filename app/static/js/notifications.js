document.addEventListener('DOMContentLoaded', function () {
    // Connect to the Socket.IO server.
    // The URL should match your server configuration.
    // If running on the same host and port, '/" is usually fine.
    var socket = io();

    // Get the notification badge element
    var notificationBadge = document.getElementById('notification-count-badge');
    var currentNotificationCount = 0;

    // Function to update the badge
    function updateNotificationBadge(count) {
        if (notificationBadge) {
            notificationBadge.textContent = count;
            if (count > 0) {
                notificationBadge.style.display = ''; // Show badge if count > 0
            } else {
                notificationBadge.style.display = 'none'; // Hide badge if count is 0
            }
        }
    }

    // Initialize badge (e.g., fetch initial unread count via an API endpoint, or start at 0)
    // For simplicity, we'll start at 0 and only increment with new real-time notifications.
    // A more robust solution would fetch the current unread count on page load.
    if (notificationBadge) {
        let initialCount = parseInt(notificationBadge.textContent);
        if (!isNaN(initialCount)) {
            currentNotificationCount = initialCount;
        } else {
            // Fallback if textContent is not a number for some reason, though it should be.
            currentNotificationCount = 0;
        }
        updateNotificationBadge(currentNotificationCount);
    }


    // Listen for 'new_notification' events from the server
    socket.on('new_notification', function (data) {
        console.log('New notification received:', data);
        currentNotificationCount++;
        updateNotificationBadge(currentNotificationCount);

        // Optional: Display a browser notification (requires user permission)
        if (Notification.permission === "granted") {
            let browserNotification;
            if (data.type === 'new_chat_message' && data.conversation_id) {
                browserNotification = new Notification("New Chat Message", {
                    body: data.message || `New message from ${data.actor_username}`,
                    // icon: "..." // Optional: chat icon
                });
                browserNotification.onclick = function() {
                    window.location.href = '/chat/' + data.conversation_id;
                };
            } else { // For other types of notifications like 'like', 'comment', 'follow'
                browserNotification = new Notification("New Notification", {
                    body: data.message || "You have a new notification."
                    // icon: "..." // Optional: general notification icon
                });
                browserNotification.onclick = function() {
                    window.location.href = "/notifications";
                };
            }
        } else if (Notification.permission !== "denied") {
            // Request permission if not already granted or denied
            Notification.requestPermission().then(function (permission) {
                if (permission === "granted") {
                    let browserNotification;
                    // Duplicate the logic from above for when permission is granted immediately
                    if (data.type === 'new_chat_message' && data.conversation_id) {
                        browserNotification = new Notification("New Chat Message", {
                            body: data.message || `New message from ${data.actor_username}`,
                            // icon: "..."
                        });
                        browserNotification.onclick = function() {
                            window.location.href = '/chat/' + data.conversation_id;
                        };
                    } else {
                        browserNotification = new Notification("New Notification", {
                            body: data.message || "You have a new notification."
                            // icon: "..."
                        });
                        browserNotification.onclick = function() {
                            window.location.href = "/notifications";
                        };
                    }
                }
            });
        }

        // Optional: If on the notifications page, dynamically add to list (more complex)
        // if (window.location.pathname === '/notifications') {
        //     // Code to prepend the new notification to the list
        // }
    });

    // Handle connection events (optional, for debugging)
    socket.on('connect', function() {
        console.log('Socket.IO connected');
    });

    socket.on('disconnect', function() {
        console.log('Socket.IO disconnected');
    });

    socket.on('connect_error', (err) => {
        console.error('Socket.IO connection error:', err);
    });

});
