import atexit
from datetime import datetime, timezone, timedelta # Added timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import func

# Removed: from app import db
# Imported Post and Story models
from app.core.models import User, Post, Story, Reaction, Comment, HistoricalAnalytics, UserAnalytics, followers, Notification, Mention, Group, GroupMembership # Added Notification, Mention, Group, GroupMembership, Replaced Like with Reaction
from app.utils.helpers import process_mentions # Added process_mentions

def collect_daily_analytics():
    from app import db # Added here
    """Collects daily analytics for all users and stores them."""
    print("Starting daily analytics collection...")
    users = User.query.all()
    if not users:
        print("No users found to process.")
        return

    for user in users:
        print(f"Processing analytics for user ID: {user.id} ({user.username})")
        # Calculate total likes received on user's posts (specifically 'like' reactions)
        total_likes_received = db.session.query(func.count(Reaction.id))\
            .join(Post, Post.id == Reaction.post_id)\
            .filter(Post.user_id == user.id, Reaction.reaction_type == 'like')\
            .scalar() or 0

        # Calculate total comments received on user's posts
        total_comments_received = db.session.query(func.count(Comment.id))\
            .join(Post, Post.id == Comment.post_id)\
            .filter(Post.user_id == user.id)\
            .scalar() or 0

        # Calculate followers count
        # Using the relationship user.followers.count() is generally fine.
        # For very large numbers of followers, a direct query might be marginally more performant,
        # but user.followers.count() is idiomatic SQLAlchemy.
        followers_count = user.followers.count()
        # Alternative direct query:
        # followers_count = db.session.query(func.count(followers.c.follower_id))\
        #     .filter(followers.c.followed_id == user.id)\
        #     .scalar() or 0

        print(f"User {user.id}: Likes={total_likes_received}, Comments={total_comments_received}, Followers={followers_count}")

        # Create new HistoricalAnalytics record
        historical_record = HistoricalAnalytics(
            user_id=user.id,
            timestamp=datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow(),
            likes_received=total_likes_received,
            comments_received=total_comments_received,
            followers_count=followers_count
        )
        db.session.add(historical_record)
        print(f"Created HistoricalAnalytics record for user {user.id}")

        # Update or create UserAnalytics record
        user_analytics = UserAnalytics.query.filter_by(user_id=user.id).first()
        if not user_analytics:
            user_analytics = UserAnalytics(user_id=user.id)
            db.session.add(user_analytics)
            print(f"Created new UserAnalytics record for user {user.id}")

        user_analytics.total_likes_received = total_likes_received
        user_analytics.total_comments_received = total_comments_received
        # Note: followers_count is not part of UserAnalytics in the provided model structure.
        # last_updated should be handled by onupdate in the model definition.
        # If not, uncomment:
        # user_analytics.last_updated = datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow()
        print(f"Updated UserAnalytics record for user {user.id}")

    try:
        db.session.commit()
        print("Daily analytics collection complete. Database changes committed.")
    except Exception as e:
        db.session.rollback()
        print(f"Error during daily analytics collection commit: {e}")

scheduler = None

def init_scheduler(app):
    global scheduler
    if scheduler is not None and scheduler.running:
        print("Scheduler already initialized and running.")
        return

    scheduler = BackgroundScheduler(daemon=True)
    # Schedule to run daily at midnight UTC
    scheduler.add_job(collect_daily_analytics, trigger='cron', hour=0, minute=5) # Run at 00:05 UTC

    # Add job for publishing scheduled content (runs every minute)
    scheduler.add_job(publish_scheduled_content, trigger='interval', minutes=1)

    # For testing, you might want a shorter interval:
    # scheduler.add_job(collect_daily_analytics, trigger='interval', seconds=60)
    # scheduler.add_job(publish_scheduled_content, trigger='interval', seconds=30) # Example for faster testing

    try:
        scheduler.start()
        print("Scheduler started successfully.")
    except Exception as e:
        print(f"Error starting scheduler: {e}")
        # Optionally, re-raise or handle more gracefully
        return

    # Shut down the scheduler when exiting the app
    atexit.register(lambda: shutdown_scheduler())
    print("Scheduler shutdown registered with atexit.")

def shutdown_scheduler():
    global scheduler
    if scheduler is not None and scheduler.running:
        try:
            scheduler.shutdown()
            print("Scheduler shutdown successfully.")
        except Exception as e:
            print(f"Error shutting down scheduler: {e}")
    else:
        print("Scheduler not running or not initialized, no shutdown needed.")

# Example of how to manually trigger for testing (not part of the app flow)
# if __name__ == '__main__':
#     # This part would require a Flask app context to run if db operations are involved.
#     # For standalone testing of collect_daily_analytics without a running Flask app,
#     # you'd need to set up an app context manually.
#     print("This script is intended to be imported, not run directly for full functionality.")
#     # To test collect_daily_analytics in isolation (e.g. with a test db setup):
#     # from app import create_app
#     # app = create_app()
#     # with app.app_context():
#     #     collect_daily_analytics()

#     # To test scheduler (would typically be done within the Flask app runtime)
#     # app = Flask(__name__) # Dummy app for scheduler testing
#     # init_scheduler(app)
#     # try:
#     #     while True:
#     #         time.sleep(2)
#     # except (KeyboardInterrupt, SystemExit):
#     #     if scheduler.running:
#     #         scheduler.shutdown()
#     pass


def publish_scheduled_content():
    from app import db # Import db locally
    print("Scheduler: Checking for scheduled content to publish...")
    now = datetime.now(timezone.utc)

    # Publish scheduled posts
    try:
        scheduled_posts = Post.query.filter(Post.scheduled_for <= now, Post.is_published == False).all()
        if not scheduled_posts:
            print("Scheduler: No scheduled posts to publish at this time.")
        for post in scheduled_posts:
            try:
                post.is_published = True
                db.session.add(post) # Add to session before commit
                db.session.commit()
                print(f"Scheduler: Published post ID {post.id} scheduled for {post.scheduled_for}")

                # --- Start Notification Logic for Published Post ---
                # Ensure post.author is loaded if needed by process_mentions or notification logic
                # Typically, relationships are available if the 'post' object is session-bound.

                # 1. Process Mentions
                try:
                    mentioned_users_in_post = process_mentions(text_content=post.body, owner_object=post, actor_user=post.author)
                    if mentioned_users_in_post:
                        for tagged_user in mentioned_users_in_post:
                            if tagged_user.id != post.author.id: # Don't notify self
                                mention_obj = Mention.query.filter_by(
                                    user_id=tagged_user.id,
                                    post_id=post.id,
                                    actor_id=post.author.id
                                ).order_by(Mention.timestamp.desc()).first()
                                if mention_obj:
                                    notification = Notification(
                                        recipient_id=tagged_user.id,
                                        actor_id=post.author.id,
                                        type='mention',
                                        related_post_id=post.id,
                                        related_mention_id=mention_obj.id
                                    )
                                    db.session.add(notification)
                        db.session.commit() # Commit mention notifications
                        print(f"Scheduler: Processed mentions for published post ID {post.id}")
                except Exception as e_mention:
                    db.session.rollback()
                    print(f"Scheduler: Error processing mentions for post ID {post.id}. Error: {e_mention}")

                # 2. Group Post Notifications
                if post.group_id:
                    try:
                        group = Group.query.get(post.group_id)
                        if group:
                            for membership_assoc in group.memberships:
                                member_user = membership_assoc.user
                                if member_user.id != post.author.id:
                                    notification = Notification(
                                        recipient_id=member_user.id,
                                        actor_id=post.author.id,
                                        type='new_group_post',
                                        related_post_id=post.id,
                                        related_group_id=group.id
                                    )
                                    db.session.add(notification)
                            db.session.commit() # Commit group post notifications
                            print(f"Scheduler: Processed group notifications for published post ID {post.id}")
                    except Exception as e_group_notif:
                        db.session.rollback()
                        print(f"Scheduler: Error processing group notifications for post ID {post.id}. Error: {e_group_notif}")
                # --- End Notification Logic for Published Post ---
            except Exception as e:
                db.session.rollback()
                print(f"Scheduler: Error publishing post ID {post.id}. Error: {e}")
    except Exception as e:
        print(f"Scheduler: Error querying scheduled posts. Error: {e}")
        # db.session.rollback() # Ensure session is clean if query itself failed, though less likely for .all()

    # Publish scheduled stories
    try:
        scheduled_stories = Story.query.filter(Story.scheduled_for <= now, Story.is_published == False).all()
        if not scheduled_stories:
            print("Scheduler: No scheduled stories to publish at this time.")
        for story in scheduled_stories:
            try:
                story.is_published = True
                story.expires_at = now + timedelta(hours=24) # Set expiration relative to publish time
                db.session.add(story) # Add to session before commit
                db.session.commit()
                print(f"Scheduler: Published story ID {story.id} scheduled for {story.scheduled_for}")
                # TODO: Add notification logic for newly published story if applicable
            except Exception as e:
                db.session.rollback()
                print(f"Scheduler: Error publishing story ID {story.id}. Error: {e}")
    except Exception as e:
        print(f"Scheduler: Error querying scheduled stories. Error: {e}")
        # db.session.rollback()

    if (not scheduled_posts and not scheduled_stories) or (len(scheduled_posts) == 0 and len(scheduled_stories) == 0) : # Check if lists are empty if query succeeded
        pass # No items were fetched, so no "finished" message needed beyond the "no items" messages
    else:
        print("Scheduler: Finished publishing cycle.")
