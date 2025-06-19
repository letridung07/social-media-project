from app import db
from app.core.models import Quest, Badge, VirtualGood # Assuming Quest is already added to models
from datetime import datetime, timedelta, timezone # For potential use in more complex quest logic later

def seed_quests():
    if Quest.query.first() is not None:
        print("Quests already seeded.")
        return

    # Example: Fetch a badge and a virtual good to link to quests if they exist
    # This part needs to be robust, as these items might not exist during initial seeding.
    # For simplicity in this subtask, we'll assume they might be None if not found.
    # A more robust version would ensure these rewards exist or log warnings.

    # Try to get a badge, e.g., "Photographer"
    # Make sure the criteria_key matches what's in your Badge seeding if it exists
    photographer_badge = Badge.query.filter_by(criteria_key='photographer').first()
    # Try to get a virtual good, e.g., "First Steps Title"
    first_steps_title = VirtualGood.query.filter_by(name="First Steps Title", type="title").first()

    initial_quests = [
        {
            "title": "Daily Login: Day 1", # Clarified title
            "description": "Log in to the platform. The first step to a great day!",
            "type": "daily",
            "criteria_type": "daily_login", # Assumes 'daily_login' is an ActivityLog type
            "criteria_target_count": 1,
            "reward_points": 5,
            "is_active": True,
            "repeatable_after_hours": 24
        },
        {
            "title": "First Photo Shared", # Clarified title
            "description": "Share your first post containing at least one image or video.",
            "type": "achievement",
            "criteria_type": "create_post_with_media", # This will be a new custom criteria_type
            "criteria_target_count": 1,
            "reward_points": 20,
            "reward_badge_id": photographer_badge.id if photographer_badge else None,
            "is_active": True
        },
        {
            "title": "Active Commentator", # Clarified title
            "description": "Make 5 comments on any posts.",
            "type": "achievement",
            "criteria_type": "create_comment", # Assumes 'create_comment' is an ActivityLog type
            "criteria_target_count": 5,
            "reward_points": 15,
            "is_active": True
        },
        {
            "title": "Weekly Engagement Challenge", # Clarified title
            "description": "Make at least 10 posts or comments in a week.",
            "type": "weekly", # This type implies custom logic for weekly reset/tracking
            "criteria_type": "general_engagement_weekly", # Custom criteria_type
            "criteria_target_count": 10, # e.g., 10 combined posts/comments
            "reward_points": 50,
            "reward_virtual_good_id": first_steps_title.id if first_steps_title else None,
            "is_active": True,
            "repeatable_after_hours": 24 * 7
        },
        {
            "title": "Profile Completionist", # Clarified title
            "description": "Complete your profile by adding a bio and a profile picture.",
            "type": "achievement",
            "criteria_type": "complete_profile", # Assumes 'complete_profile' is an ActivityLog type
            "criteria_target_count": 1,
            "reward_points": 25,
            "is_active": True
        }
    ]

    for quest_data in initial_quests:
        # Ensure nullable foreign keys are handled if the reward item doesn't exist
        if 'reward_badge_id' in quest_data and quest_data['reward_badge_id'] is None:
            del quest_data['reward_badge_id'] # Don't try to set None if column expects valid ID or NULL
        if 'reward_virtual_good_id' in quest_data and quest_data['reward_virtual_good_id'] is None:
            del quest_data['reward_virtual_good_id']

        quest = Quest(**quest_data)
        db.session.add(quest)

    try:
        db.session.commit()
        print("Initial quests seeded successfully.")
    except Exception as e:
        db.session.rollback()
        print(f"Error seeding quests: {e}")

# Example of how to call this, typically from a CLI command or initial setup script
# if __name__ == '__main__':
    # This part is for direct execution testing and assumes app context can be created.
    # In a real Flask app, you'd use a CLI command.
    # from app import create_app # This would be needed if running standalone
    # app = create_app()
    # with app.app_context():
    # print("Attempting to seed quests (if run directly and app context is available)...")
    # seed_quests()
    # pass # Keep this part commented out or conditional for actual app integration


# Added User for type hinting, though user_obj is passed directly.
from app.core.models import User, UserQuestProgress, Notification
# Quest, Badge, VirtualGood, datetime, timedelta, timezone already imported at the top

# Make sure socketio is imported if it's not already available globally in this file
# For standalone utils, explicit import is safer.
try:
    from app import socketio as app_socketio # Try to import the app's socketio instance
except ImportError:
    app_socketio = None # Fallback if not available (e.g. script run outside app context)
    print("Warning: app.socketio could not be imported. SocketIO events for quests will not be emitted.")


def update_quest_progress(user_obj, activity_type_key, related_item=None, count_increment=1):
    # Fetch all active quests that match the criteria_type

    now = datetime.now(timezone.utc)

    candidate_quests = Quest.query.filter_by(
        is_active=True,
        criteria_type=activity_type_key
    ).all()

    if not candidate_quests:
        return

    for quest in candidate_quests:
        # Check if quest is timed and outside its active window
        if quest.start_date and now < quest.start_date:
            continue # Quest hasn't started
        if quest.end_date and now > quest.end_date:
            continue # Quest has ended

        progress = UserQuestProgress.query.filter_by(
            user_id=user_obj.id,
            quest_id=quest.id
        ).first()

        if not progress:
            progress = UserQuestProgress(
                user_id=user_obj.id,
                quest_id=quest.id,
                current_count=0,
                status='in_progress',
                last_progress_at=now
            )
            db.session.add(progress)

        if quest.repeatable_after_hours is not None:
            if progress.status == 'claimed' or \
               (progress.status == 'completed' and progress.last_completed_instance_at is not None): # Check if it was a completed instance
                if progress.last_completed_instance_at and \
                   (now < progress.last_completed_instance_at + timedelta(hours=quest.repeatable_after_hours)):
                    continue # Still in cooldown
                else:
                    print(f"Quest '{quest.title}' cooldown passed for user {user_obj.username}. Resetting progress.")
                    progress.current_count = 0
                    progress.status = 'in_progress'
                    progress.completed_at = None
                    # last_completed_instance_at will be updated upon next completion
        elif progress.status == 'completed' or progress.status == 'claimed':
            # Non-repeatable quest already completed/claimed
            continue

        # Specific criteria checks
        if activity_type_key == 'create_post_with_media':
            if not (related_item and hasattr(related_item, 'media_items') and related_item.media_items.count() > 0):
                print(f"Skipping quest '{quest.title}' for user {user_obj.username}: 'create_post_with_media' criteria not met by related_item.")
                continue # This post doesn't have media, so don't count for this quest type

        if progress.status == 'in_progress':
            progress.current_count += count_increment
            progress.last_progress_at = now
            print(f"Quest '{quest.title}' progress for {user_obj.username}: {progress.current_count}/{quest.criteria_target_count}")

            if progress.current_count >= quest.criteria_target_count:
                progress.status = 'completed'
                progress.completed_at = now
                if quest.repeatable_after_hours is not None:
                     progress.last_completed_instance_at = now # Mark completion time for cooldown calculation

                print(f"Quest '{quest.title}' COMPLETED for {user_obj.username}!")

                notification = Notification(
                    recipient_id=user_obj.id,
                    actor_id=user_obj.id,
                    type='quest_completed',
                    # related_id=quest.id, # Assuming Notification model can store this
                    # related_item_type='quest'
                )
                db.session.add(notification)

                if app_socketio:
                    try:
                        # url_for might not be available if called from a script without full app context for routing
                        # from flask import url_for
                        # quests_url = url_for('main.view_user_quests', _external=True) # Example, replace with actual route
                        quests_url = f"/user/{user_obj.username}/quests" # Fallback or simplified URL
                    except Exception:
                        quests_url = None # Or a default non-dynamic URL

                    app_socketio.emit('new_notification', {
                        'type': 'quest_completed',
                        'message': f"Quest Completed: {quest.title}! You can now claim your reward.",
                        'quest_title': quest.title,
                        'quest_id': quest.id,
                        'quests_url': quests_url
                    }, room=str(user_obj.id))
                else:
                    print("SocketIO object (app_socketio) not available in quest_utils. Not emitting event.")

    # Removed db.session.commit() from here.
    # The calling route will be responsible for the commit.
    # try:
    #     db.session.commit()
    # except Exception as e:
    #     db.session.rollback()
    #     print(f"Error committing quest progress for user {user_obj.username}: {e}")
    #     # Consider logging this to current_app.logger if available/appropriate
