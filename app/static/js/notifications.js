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
    if (notificationBadge) { // Check if the element actually exists on the current page
         // Attempt to get initial count from the badge text content if it was rendered by server
        let initialCount = parseInt(notificationBadge.textContent);
        if (!isNaN(initialCount)) {
            currentNotificationCount = initialCount;
        } else {
             // If not, try to get it from a data attribute or default to 0
            const unreadCountElement = document.getElementById('initial-unread-count'); // Example
            if (unreadCountElement) {
                currentNotificationCount = parseInt(unreadCountElement.value) || 0;
            } else {
                currentNotificationCount = 0; // Default if no initial count found
            }
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
            var browserNotification = new Notification("New Notification", {
                body: data.message || "You have a new notification."
                // icon: "/static/images/favicon.ico" // Optional: path to an icon - REMOVED
            });
            // Optional: link to notifications page when notification is clicked
            browserNotification.onclick = function() {
                window.location.href = "/notifications";
            };
        } else if (Notification.permission !== "denied") {
            // Request permission if not already granted or denied
            Notification.requestPermission().then(function (permission) {
                if (permission === "granted") {
                    var browserNotification = new Notification("New Notification", {
                        body: data.message || "You have a new notification."
                        // icon: "/static/images/favicon.ico" // Optional: path to an icon - REMOVED
                    });
                    browserNotification.onclick = function() {
                        window.location.href = "/notifications";
                    };
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
