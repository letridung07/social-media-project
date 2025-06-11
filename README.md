# Flask Social Platform

A social media platform built with Flask, featuring user authentication, profiles, content posting, user following, likes, and comments.

## Features

*   User registration (username, email, password)
*   User login and logout functionality
*   Secure password hashing (using passlib with sha256_crypt)
*   User profile pages displaying username, email, bio, and profile picture
*   User profile editing:
    *   Update biography
    *   Upload new profile picture (supports JPG, PNG, JPEG)
*   **Content Posting:**
    *   Users can create and share text-based posts.
*   **Following System:**
    *   Users can follow and unfollow other users.
    *   Personalized feed on the homepage displaying posts from followed users and own posts.
*   **Post Engagement:**
    *   Users can like and unlike posts.
    *   Like counts are displayed for each post.
    *   Users can add comments to posts.
    *   Comments are displayed chronologically under each post, showing the author and timestamp.
*   CSRF Protection for forms.
*   Default profile picture for new users.
*   Basic unit tests for authentication, profile management, posts, following, and engagement (likes/comments).

## Getting Started

Follow these instructions to get a copy of the project up and running on your local machine for development and testing purposes.

### Prerequisites

*   Python 3.8 or higher
*   pip (Python package installer)
*   git (for cloning the repository)

### Setup

1.  **Clone the repository**:
    ```bash
    git clone <your_repository_url_here>
    cd <repository_directory_name>
    ```
    *(Replace `<your_repository_url_here>` and `<repository_directory_name>` with the actual URL and directory name if you are cloning this from a remote repository. If working locally, you can skip this step or adjust as needed.)*

2.  **Create and activate a virtual environment**:
    ```bash
    python3 -m venv venv
    ```
    On Linux/macOS:
    ```bash
    source venv/bin/activate
    ```
    On Windows:
    ```bash
    venv\Scripts\activate
    ```

3.  **Install dependencies**:
    Make sure your virtual environment is activated, then run:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configuration (Optional)**:
    *   The application uses configurations defined in `config.py`.
    *   A default `SECRET_KEY` is provided for development. For production, this should be set to a secure, random value, preferably via an environment variable.
    *   The database is configured to use SQLite (`app.db`) by default. The `SQLALCHEMY_DATABASE_URI` in `config.py` can be modified to use other databases like PostgreSQL or MySQL.
    *   The `UPLOAD_FOLDER` for profile pictures is set to `app/static/images/`.

### Running the Application

1.  Ensure your virtual environment is activated.
2.  From the project root directory, run the application:
    ```bash
    python3 run.py
    ```
3.  The application will typically be available at `http://127.0.0.1:5000/`. Open this URL in your web browser.

### Running Tests

1.  Ensure your virtual environment is activated and development dependencies are installed.
2.  From the project root directory, run the tests:
    ```bash
    python3 -m unittest discover tests
    ```
    This command will discover and run all tests located in the `tests` directory.

## Project Structure
```
/
├── app/                  # Main application package
│   ├── static/           # Static files (CSS, JS, images)
│   │   ├── css/
│   │   └── images/
│   ├── templates/        # HTML templates
│   ├── __init__.py       # Application factory, initializes Flask app and extensions
│   ├── forms.py          # WTForms definitions
│   ├── models.py         # SQLAlchemy database models
│   ├── routes.py         # Application routes (views)
│   └── utils.py          # Utility functions (e.g., saving pictures)
├── tests/                # Unit tests
│   ├── __init__.py
│   ├── test_auth.py      # Authentication tests
│   ├── test_profile.py   # Profile management tests
│   ├── test_posts.py     # Tests for creating and viewing posts
│   ├── test_follow.py    # Tests for following/unfollowing users and feed generation
│   └── test_engagement.py # Tests for liking/unliking posts and adding/viewing comments
├── venv/                 # Python virtual environment (if created with this name)
├── .gitignore            # Specifies intentionally untracked files that Git should ignore
├── config.py             # Configuration settings (e.g., SECRET_KEY, database URI)
├── README.md             # This file
├── requirements.txt      # Python package dependencies
└── run.py                # Script to run the Flask development server
```

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue.
(Further details on contributing can be added here if desired).
```
