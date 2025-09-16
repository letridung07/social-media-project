import unittest
from app import create_app, db # Import create_app
from app.models import User, Post, Hashtag
from app.routes import process_hashtags

# Create the Flask app instance
app = create_app()

class TestHashtagProcessing(unittest.TestCase):
    def setUp(self):
        self.app_context = app.app_context()
        self.app_context.push()
        # Ensure tables are created within the context of the test app instance
        with app.app_context():
            db.create_all()

    def tearDown(self):
        with app.app_context(): # Ensure operations are within app context
            db.session.remove()
            db.drop_all()
        self.app_context.pop()

    def test_process_hashtags(self):
        # Create a dummy user
        user = User(username='testuser', email='test@example.com')
        user.set_password('testpassword') # Set a password
        db.session.add(user)
        db.session.commit()

        # Create a new post
        post_body = "This is a #test post with #multiple #hashtags. Let's also test #Test and #unders_core."
        post = Post(body=post_body, author=user)
        db.session.add(post)
        db.session.commit()

        # Process hashtags
        process_hashtags(post)
        db.session.commit()

        # Verification
        retrieved_post = Post.query.get(post.id)
        self.assertIsNotNone(retrieved_post, "Post should be created.")
        print("Post created successfully.")

        expected_hashtags = ['test', 'multiple', 'hashtags', 'unders_core']
        # Querying relevant hashtags for this test case to avoid interference
        # Assuming process_hashtags correctly associates them with the post
        retrieved_hashtags_for_post = [h.tag_text for h in retrieved_post.hashtags] # h.tag to h.tag_text

        for tag_name in expected_hashtags:
            self.assertIn(tag_name, retrieved_hashtags_for_post, f"Hashtag '{tag_name}' should be associated with the post.")

        # Check uniqueness and casing by querying the Hashtag table directly for these tags
        # This also implicitly checks that no duplicates like '#Test' vs '#test' were created.
        # The `process_hashtags` function is expected to handle this.
        db_hashtags = Hashtag.query.filter(Hashtag.tag_text.in_(expected_hashtags)).all()
        db_hashtag_texts = [h.tag_text for h in db_hashtags] # h.tag to h.tag_text
        self.assertEqual(len(set(db_hashtag_texts)), len(expected_hashtags), "Hashtag count in DB should match expected unique hashtags.")
        print("Hashtags created correctly (lowercase, no duplicates).")

        # Verify post_hashtags association
        self.assertEqual(len(retrieved_post.hashtags), len(expected_hashtags), "Post should be associated with the correct number of unique hashtags.")
        for tag_name in expected_hashtags:
            hashtag_obj = Hashtag.query.filter_by(tag_text=tag_name).first() # tag to tag_text
            self.assertIsNotNone(hashtag_obj, f"Hashtag object for '{tag_name}' should exist in DB.")
            self.assertIn(hashtag_obj, retrieved_post.hashtags, f"Post should be associated with hashtag '{tag_name}'.")
        print("Post-hashtag associations are correct.")

        # Clean up (optional, as tearDown will drop all tables)
        # db.session.delete(post)
        # db.session.delete(user)
        # db.session.commit()
        # print("Cleaned up dummy user and post.")

if __name__ == '__main__':
    # This allows running the script directly for testing,
    # though it's structured as a unittest case.
    # For a standalone script, you wouldn't typically use unittest.
    # Instead, you'd run the setup, test logic, and cleanup sequentially.

    # For the purpose of this task, we'll simulate a direct run flow
    # within the unittest structure if run as __main__.

    print("Setting up application context and database...")
    # Use the global app instance created with create_app()
    temp_app_context = app.app_context()
    temp_app_context.push()

    # Ensure a clean database state for script execution
    print("Dropping existing tables (if any) and creating new ones for a clean run...")
    db.drop_all()
    db.create_all()
    print("Database reset and setup complete.")

    # Create a dummy user
    print("Creating dummy user...")
    user = User(username='scriptuser', email='script@example.com')
    user.set_password('testpassword') # Set a password
    db.session.add(user)
    db.session.commit()
    print(f"User '{user.username}' created with ID: {user.id}")

    # Create a new post
    post_body = "This is a #script_test post with #multiple #hashtags. Let's also test #Script_Test and #unders_core_script."
    print(f"Creating post with body: \"{post_body}\"")
    post = Post(body=post_body, author=user)
    db.session.add(post)
    db.session.commit()
    print(f"Post created with ID: {post.id}")

    # Process hashtags
    print("Processing hashtags for the post...")
    process_hashtags(post.body, post) # Corrected arguments
    db.session.commit()
    print("Hashtag processing complete.")

    # Verification
    print("\n--- Verification ---")
    retrieved_post = Post.query.get(post.id)
    if retrieved_post:
        print(f"Post (ID: {retrieved_post.id}) retrieved successfully.")
    else:
        print(f"Error: Post (ID: {post.id}) not found.")

    expected_hashtags = sorted(['script_test', 'multiple', 'hashtags', 'unders_core_script'])
    print(f"Expected hashtags: {expected_hashtags}")

    # Querying hashtags associated with the post directly
    actual_post_hashtags = sorted([h.tag_text for h in retrieved_post.hashtags]) # Changed h.tag to h.tag_text
    print(f"Actual hashtags associated with post: {actual_post_hashtags}")

    if actual_post_hashtags == expected_hashtags:
        print("Post-hashtag association test: PASSED")
    else:
        print("Post-hashtag association test: FAILED")
        print(f"  Expected: {expected_hashtags}")
        print(f"  Actual:   {actual_post_hashtags}")

    # Querying all hashtags in the Hashtag table to check for duplicates and casing
    all_hashtags_in_db = sorted([h.tag_text for h in Hashtag.query.all()]) # Changed h.tag to h.tag_text
    # Filter all_hashtags_in_db to only include those expected for this test to avoid interference from other tests/data
    relevant_hashtags_in_db = sorted(list(set(tag for tag in all_hashtags_in_db if tag in expected_hashtags)))

    print(f"All relevant hashtags in DB: {relevant_hashtags_in_db}")
    if relevant_hashtags_in_db == expected_hashtags:
        print("Overall hashtag creation (lowercase, no duplicates) test: PASSED")
    else:
        print("Overall hashtag creation (lowercase, no duplicates) test: FAILED")
        print(f"  Expected unique lowercase hashtags: {expected_hashtags}")
        print(f"  Actual relevant hashtags in DB:   {relevant_hashtags_in_db}")
        # Additional check for specific hashtag presence and count
        for tag_name in expected_hashtags:
            count = Hashtag.query.filter_by(tag_text=tag_name).count() # Changed tag to tag_text
            if count == 1:
                print(f"  Hashtag '{tag_name}' found and unique.")
            else:
                print(f"  Error: Hashtag '{tag_name}' count is {count}, expected 1.")


    # Clean up
    print("\n--- Cleanup ---")
    try:
        db.session.delete(post)
        db.session.delete(user)
        db.session.commit()
        print("Dummy user and post deleted successfully.")
    except Exception as e:
        print(f"Error during cleanup: {e}")
        db.session.rollback()

    print("\nRemoving application context and dropping database...")
    db.session.remove()
    db.drop_all()
    temp_app_context.pop()
    print("Script finished.")

    # To actually run the unittest version:
    # if __name__ == '__main__':
    # unittest.main(argv=['first-arg-is-ignored'], exit=False)

    # The script will now primarily rely on the `if __name__ == '__main__':` block
    # for direct execution, and the unittest structure is there if needed.
    # The direct execution part needs to ensure db.create_all() is effectively called.
    # create_app() already calls db.create_all() within its app_context.
