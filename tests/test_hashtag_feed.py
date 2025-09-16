from app import create_app, db
from app.models import User, Post, Hashtag
from app.routes import process_hashtags # For creating hashtag data

# Create the Flask app instance for the script
app = create_app()
# app.config['TESTING'] = True # Enable testing mode
# app.config['WTF_CSRF_ENABLED'] = False # Disable CSRF for testing forms if any, not strictly needed for GETs
# app.config['SERVER_NAME'] = 'localhost:5000' # Important for url_for with test_client

def run_hashtag_feed_test():
    print("Setting up application context and database for hashtag feed test...")
    ctx = app.app_context()
    ctx.push()

    print("Dropping existing tables (if any) and creating new ones for a clean run...")
    db.drop_all()
    db.create_all()
    print("Database reset and setup complete.")

    client = app.test_client() # Use the test client

    # 1. Create a dummy user
    print("Creating dummy user...")
    user = User(username='feedtester', email='feedtester@example.com')
    user.set_password('testpassword')
    db.session.add(user)
    db.session.commit()
    print(f"User '{user.username}' created with ID: {user.id}")

    # 2. Create two posts
    print("Creating posts...")
    post1_body = "This is the first post about #Flask and #Python."
    post1 = Post(body=post1_body, author=user)
    db.session.add(post1)

    post2_body = "Another post talking about #Python programming."
    post2 = Post(body=post2_body, author=user)
    db.session.add(post2)
    db.session.commit() # Commit posts to get IDs
    print(f"Post 1 created with ID: {post1.id}, Body: \"{post1_body}\"")
    print(f"Post 2 created with ID: {post2.id}, Body: \"{post2_body}\"")

    # 3. Process and store hashtags
    print("Processing hashtags for Post 1...")
    process_hashtags(post1.body, post1)
    print("Processing hashtags for Post 2...")
    process_hashtags(post2.body, post2)
    db.session.commit()
    print("Hashtag processing complete.")

    # Verification
    print("\n--- Verification ---")

    # 4. Simulate request for #python
    print("\nTesting feed for #python (case-insensitive)...")
    response_python = client.get('/hashtag/python') # Test client uses relative paths
    response_python_data = response_python.get_data(as_text=True)

    # 5. Verify #python feed
    python_feed_ok = True
    if response_python.status_code != 200:
        print(f"  Error: #python feed request failed with status {response_python.status_code}")
        python_feed_ok = False

    if post1_body not in response_python_data:
        print(f"  Error: Post 1 ('{post1_body}') not found in #python feed.")
        python_feed_ok = False

    if post2_body not in response_python_data:
        print(f"  Error: Post 2 ('{post2_body}') not found in #python feed.")
        python_feed_ok = False

    if python_feed_ok:
        print("  Feed for #python PASSED: Contains both Post 1 and Post 2.")
    else:
        print("  Feed for #python FAILED.")
        # print("Response data for #python:\n", response_python_data[:500] + "...")


    # 6. Simulate request for #flask
    print("\nTesting feed for #flask...")
    response_flask = client.get('/hashtag/flask')
    response_flask_data = response_flask.get_data(as_text=True)

    # 7. Verify #flask feed
    flask_feed_ok = True
    if response_flask.status_code != 200:
        print(f"  Error: #flask feed request failed with status {response_flask.status_code}")
        flask_feed_ok = False

    if post1_body not in response_flask_data:
        print(f"  Error: Post 1 ('{post1_body}') not found in #flask feed.")
        flask_feed_ok = False

    if post2_body in response_flask_data:
        print(f"  Error: Post 2 ('{post2_body}') FOUND in #flask feed, but should not be.")
        flask_feed_ok = False

    if flask_feed_ok:
        print("  Feed for #flask PASSED: Contains Post 1 and does not contain Post 2.")
    else:
        print("  Feed for #flask FAILED.")
        # print("Response data for #flask:\n", response_flask_data[:500] + "...")

    # 9. Clean up
    print("\n--- Cleanup ---")
    try:
        db.session.delete(post1)
        db.session.delete(post2)
        db.session.delete(user)
        db.session.commit()
        print("Dummy user and posts deleted successfully.")
    except Exception as e:
        print(f"Error during cleanup: {e}")
        db.session.rollback()

    print("\nRemoving application context and dropping database...")
    db.session.remove()
    db.drop_all()
    ctx.pop()
    print("Script finished.")

if __name__ == '__main__':
    run_hashtag_feed_test()
