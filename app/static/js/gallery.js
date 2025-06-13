document.addEventListener('DOMContentLoaded', function() {
    const galleries = document.querySelectorAll('.media-gallery.carousel');

    galleries.forEach(gallery => {
        const track = gallery.querySelector('.carousel-track');
        if (!track) return;

        const items = track.querySelectorAll('.media-gallery-item');
        if (items.length <= 1) {
            // If only one item, hide existing nav buttons if they were rendered by template
            const navContainer = gallery.querySelector('.carousel-nav');
            if (navContainer) {
                navContainer.style.display = 'none';
            }
            return; // No need for carousel if 1 or 0 items
        }

        let currentIndex = 0;
        const totalItems = items.length;

        // Try to find existing buttons first (rendered by template)
        let prevButton = gallery.querySelector('.carousel-prev');
        let nextButton = gallery.querySelector('.carousel-next');
        let navContainer = gallery.querySelector('.carousel-nav');

        // If buttons are not in the HTML, create them
        if (!prevButton || !nextButton) {
            if (navContainer) navContainer.innerHTML = ''; // Clear existing nav if buttons are missing
            else {
                navContainer = document.createElement('div');
                navContainer.classList.add('carousel-nav');
            }

            prevButton = document.createElement('button');
            prevButton.classList.add('carousel-prev');
            prevButton.textContent = 'Previous';
            nextButton = document.createElement('button');
            nextButton.classList.add('carousel-next');
            nextButton.textContent = 'Next';
            navContainer.appendChild(prevButton);
            navContainer.appendChild(nextButton);
            gallery.appendChild(navContainer); // Append nav to the gallery
        }

        function updateCarousel() {
            track.style.transform = `translateX(-${currentIndex * 100}%)`;
            if (prevButton) prevButton.disabled = currentIndex === 0;
            if (nextButton) nextButton.disabled = currentIndex >= totalItems - 1;
        }

        if (prevButton) {
            prevButton.addEventListener('click', () => {
                if (currentIndex > 0) {
                    currentIndex--;
                    updateCarousel();
                }
            });
        }

        if (nextButton) {
            nextButton.addEventListener('click', () => {
                if (currentIndex < totalItems - 1) {
                    currentIndex++;
                    updateCarousel();
                }
            });
        }

        updateCarousel(); // Initialize
    });
});
