# Flask Social Platform

A social media platform built with Flask, featuring user authentication, profiles, content posting, user following, likes, comments, and real-time chat. The application also features a refreshed, modern user interface for an enhanced experience.

## Features

*   User registration (username, email, password)
*   User login and logout functionality
*   Secure password hashing (using passlib with sha256_crypt)
*   User profile pages displaying username, email, bio, and profile picture
*   User profile editing:
    *   Update biography
    *   Upload new profile picture (supports JPG, PNG, JPEG)
*   **User Interface & Experience:**
    *   Modern, responsive UI built with Bootstrap 4.5.2 and a custom theme.
    *   Improved visual styling for enhanced readability and aesthetics.
    *   Intuitive navigation and user flows.
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
*   **Real-time Chat:** (See dedicated section below for more details)
    *   One-on-one conversations.
    *   Real-time messaging with Socket.IO.
    *   Typing indicators.
    *   Read receipts.
    *   Basic emoji support.
*   CSRF Protection for forms.
*   Default profile picture for new users.
*   Basic unit tests for authentication, profile management, posts, following, engagement (likes/comments), and chat.

## Real-time Chat

The platform includes a real-time chat feature allowing users to engage in one-on-one conversations.

**Key Chat Features:**

*   **One-on-one Conversations:** Users can initiate private chats with other users.
*   **Real-time Messaging:** Messages are sent and received instantly without needing to refresh the page, powered by Flask-SocketIO.
*   **Typing Indicators:** Users can see when the other person in the conversation is typing a message.
*   **Read Receipts:** Sent messages display "✓ Sent" status, which updates to "✓ Read" when the recipient has viewed the message.
*   **Emoji Support (Basic):** A simple emoji picker allows users to insert common emojis into their messages.
*   **Message History:** Past messages in a conversation are loaded and displayed.
*   **Notifications:** New chat messages trigger real-time notifications for the recipient (integrated with the existing notification system).

**Chat Screenshots:**

*   **Conversation List View:**
    `[Screenshot of Conversation List]`
    *Description: Shows a list of active conversations for the logged-in user, typically ordered by the most recent activity.*

*   **Chat View:**
    `[Screenshot of Chat View]`
    *Description: Displays the message history with another user. Features include dynamically grouped messages, typing indicators when the other user is active, and read receipts for sent messages.*

*   **Chat View with Emoji Panel Open:**
    `[Screenshot of Chat View with Emoji Panel]`
    *Description: Shows the emoji panel open, allowing users to easily select and insert emojis into their chat messages.*

## Frontend Technologies & Styling

The frontend of this platform is built using:

*   **Flask Templates (Jinja2):** For dynamic HTML rendering.
*   **Bootstrap 4.5.2:** As the core CSS framework for layout, components, and responsiveness. Bootstrap is integrated via CDN.
*   **Custom Modern Theme:** Applied via `app/static/css/style.css`, this theme includes:
    *   A unique color palette.
    *   The "Lato" Google Font for typography.
    *   Customized styling for Bootstrap components (cards, buttons, forms) to create a distinct look and feel.
*   **JavaScript & Socket.IO Client:** For real-time features like chat, notifications, typing indicators, and read receipts.

## Screenshots

*(Coming Soon: The following screenshots will demonstrate key features of the application.)*

*   User Registration and Login
*   User Profile Page
*   Content Feed
*   Creating a Post
*   Post Engagement
*   *(Chat screenshots are now in the dedicated "Real-time Chat" section)*

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
│   │   ├── js/           # JavaScript files (e.g., chat_page.js, notifications.js)
│   │   └── images/
│   ├── templates/        # HTML templates
│   │   └── chat/         # Chat specific templates
│   ├── __init__.py       # Application factory, initializes Flask app and extensions
│   ├── forms.py          # WTForms definitions
│   ├── models.py         # SQLAlchemy database models
│   ├── routes.py         # Application routes (views)
│   ├── events.py         # Socket.IO event handlers
│   └── utils.py          # Utility functions (e.g., saving pictures)
├── tests/                # Unit tests
│   ├── __init__.py
│   ├── test_auth.py      # Authentication tests
│   ├── test_profile.py   # Profile management tests
│   ├── test_posts.py     # Tests for creating and viewing posts
│   ├── test_follow.py    # Tests for following/unfollowing users and feed generation
│   ├── test_engagement.py # Tests for liking/unliking posts and adding/viewing comments
│   └── test_chat.py      # Chat functionality tests
├── venv/                 # Python virtual environment (if created with this name)
├── .gitignore            # Specifies intentionally untracked files that Git should ignore
├── config.py             # Configuration settings (e.g., SECRET_KEY, database URI)
├── README.md             # This file
├── requirements.txt      # Python package dependencies
└── run.py                # Script to run the Flask development server
```
*(Note: Project structure updated to reflect chat-related files like `events.py`, `js/chat_page.js`, and `templates/chat/`)*

## Contributing

We welcome contributions to the Flask Social Platform! Here are some ways you can contribute:

*   **Reporting Bugs:** If you find a bug, please open an issue on our issue tracker. Include as much detail as possible:
    *   Steps to reproduce the bug.
    *   Expected behavior.
    *   Actual behavior.
    *   Your environment (e.g., browser, OS).
*   **Suggesting Enhancements:** If you have an idea for a new feature or an improvement to an existing one, please open an issue to discuss it.
*   **Pull Requests:** We are happy to review pull requests. To make the process smoother:
    1.  Fork the repository.
    2.  Create a new branch for your feature or bug fix (`git checkout -b feature/your-feature-name` or `git checkout -b fix/your-bug-fix`).
    3.  Make your changes.
    4.  Ensure your code adheres to any existing style guidelines (if we establish them).
    5.  Write tests for your changes if applicable.
    6.  Ensure all tests pass (`python3 -m unittest discover tests`).
    7.  Commit your changes with a clear and descriptive commit message.
    8.  Push your branch to your fork (`git push origin feature/your-feature-name`).
    9.  Open a pull request against our `main` (or `develop`) branch.

We'll do our best to review contributions in a timely manner.
