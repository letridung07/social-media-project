document.addEventListener('DOMContentLoaded', function() {
    console.log("Stories JS loaded");

    // Future: Logic for story timer, navigation, full-screen view, etc.
    const storyItems = document.querySelectorAll('.story-item'); // This class should be on each story block in stories.html

    if (storyItems.length > 0) {
        console.log(`Found ${storyItems.length} story items on the page.`);

        // Example: Add a click listener to each story item
        storyItems.forEach((item, index) => {
            item.addEventListener('click', function() {
                console.log(`Clicked on story item ${index + 1}`);
                // Placeholder for future action, e.g., open in full-screen view
            });
        });

        // Placeholder for auto-advancing logic (more complex, for future enhancement)
        // let currentStoryIndex = 0;
        // function showStory(index) {
        //     storyItems.forEach((item, i) => {
        //         // This simple display toggle is more for a carousel where only one is visible.
        //         // For a feed, you might highlight or scroll to it.
        //         item.style.display = i === index ? 'block' : 'none';
        //     });
        //     console.log(`Showing story ${index + 1}`);
        // }

        // function nextStory() {
        //     currentStoryIndex = (currentStoryIndex + 1) % storyItems.length;
        //     showStory(currentStoryIndex);
        // }

        // if (storyItems.length > 1 && false) { // Disabled for now
        //     // Example: Auto-advance every 5 seconds (Illustrative)
        //     // setInterval(nextStory, 5000);
        //     // showStory(currentStoryIndex); // Show the first story
        //     console.log("Auto-advancing placeholder is present but inactive.");
        // }
    } else {
        console.log("No story items found on this page.");
    }
});
