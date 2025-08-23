function initializeUploadProgress(formElement) {
    if (!formElement) {
        return;
    }

    const progressBar = formElement.querySelector('.progress');
    const progressBarInner = formElement.querySelector('.progress-bar');
    const fileInput = formElement.querySelector('input[type="file"]');

    if (!progressBar || !progressBarInner || !fileInput) {
        return;
    }

    formElement.addEventListener('submit', function(e) {
        if (fileInput.files.length === 0) {
            return;
        }

        e.preventDefault();

        const formData = new FormData(formElement);
        const xhr = new XMLHttpRequest();

        xhr.open('POST', formElement.action, true);

        xhr.upload.addEventListener('progress', function(e) {
            if (e.lengthComputable) {
                const percentComplete = (e.loaded / e.total) * 100;
                progressBar.style.display = 'block';
                progressBarInner.style.width = percentComplete + '%';
                progressBarInner.textContent = Math.round(percentComplete) + '%';
            }
        });

        xhr.addEventListener('load', function() {
            if (xhr.status >= 200 && xhr.status < 400) {
                if (xhr.responseURL) {
                    window.location.href = xhr.responseURL;
                } else {
                    window.location.reload();
                }
            } else {
                alert('An error occurred during the upload. Please try again.');
                progressBar.style.display = 'none';
            }
        });

        xhr.addEventListener('error', function() {
            alert('An unexpected error occurred. Please check your connection and try again.');
            progressBar.style.display = 'none';
        });

        xhr.send(formData);
    });
}
