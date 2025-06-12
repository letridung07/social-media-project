import atexit
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import func

from app import db
from app.models import User, Post, Like, Comment, HistoricalAnalytics, UserAnalytics, followers # Assuming 'followers' is the association table

def collect_daily_analytics():
    """Collects daily analytics for all users and stores them."""
    print("Starting daily analytics collection...")
    users = User.query.all()
    if not users:
        print("No users found to process.")
        return

    for user in users:
        print(f"Processing analytics for user ID: {user.id} ({user.username})")
        # Calculate total likes received on user's posts
        total_likes_received = db.session.query(func.count(Like.id))\
            .join(Post, Post.id == Like.post_id)\
            .filter(Post.user_id == user.id)\
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
    # For testing, you might want a shorter interval:
    # scheduler.add_job(collect_daily_analytics, trigger='interval', seconds=60)

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
