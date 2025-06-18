"""
Utilities for the gamification system, including badge seeding and awarding logic.
"""
from app import db, socketio
from app.core.models import User, UserPoints, Badge, ActivityLog, Post, Story, Poll, Article, AudioPost, Comment, Reaction, Group, Event, Notification, VirtualGood, UserVirtualGood
from sqlalchemy import func # For distinct, date, count
from datetime import datetime, date # For Dedicated Member badge

# Placeholder for INITIAL_BADGES and functions to be defined
INITIAL_BADGES = [
    {'name': 'Welcome Wagon', 'description': 'Joined the community and started exploring with a bio and profile picture!', 'icon_url': 'static/badges/welcome_wagon.png', 'criteria_key': 'welcome_wagon'},
    {'name': 'First Steps', 'description': 'Shared your first post with the community.', 'icon_url': 'static/badges/first_steps.png', 'criteria_key': 'first_steps'},
    {'name': 'Photographer', 'description': 'Shared a post containing at least one image or video.', 'icon_url': 'static/badges/photographer.png', 'criteria_key': 'photographer'},
    {'name': 'Storyteller', 'description': 'Shared your first story.', 'icon_url': 'static/badges/storyteller.png', 'criteria_key': 'storyteller'},
    {'name': 'Opinionator', 'description': 'Created your first poll to gather opinions.', 'icon_url': 'static/badges/opinionator.png', 'criteria_key': 'opinionator'},
    {'name': 'Wordsmith', 'description': 'Published your first article.', 'icon_url': 'static/badges/wordsmith.png', 'criteria_key': 'wordsmith'},
    {'name': 'Podcaster', 'description': 'Uploaded your first audio post.', 'icon_url': 'static/badges/podcaster.png', 'criteria_key': 'podcaster'},
    {'name': 'Engager', 'description': 'Made 10 or more comments on posts.', 'icon_url': 'static/badges/engager.png', 'criteria_key': 'engager'},
    {'name': 'Popular', 'description': 'Received 25 "like" reactions across all your posts.', 'icon_url': 'static/badges/popular.png', 'criteria_key': 'popular'},
    {'name': 'Very Popular', 'description': 'Received 100 "like" reactions across all your posts.', 'icon_url': 'static/badges/very_popular.png', 'criteria_key': 'very_popular'},
    {'name': 'Influencer', 'description': 'Gained 10 or more followers.', 'icon_url': 'static/badges/influencer.png', 'criteria_key': 'influencer'},
    {'name': 'Community Builder', 'description': 'Created your first group.', 'icon_url': 'static/badges/community_builder.png', 'criteria_key': 'community_builder'},
    {'name': 'Event Organizer', 'description': 'Organized your first event.', 'icon_url': 'static/badges/event_organizer.png', 'criteria_key': 'event_organizer'},
    {'name': 'Social Butterfly', 'description': 'Followed 5 or more users.', 'icon_url': 'static/badges/social_butterfly.png', 'criteria_key': 'social_butterfly'},
    {'name': 'Dedicated Member', 'description': 'Logged in on 7 distinct days.', 'icon_url': 'static/badges/dedicated_member.png', 'criteria_key': 'dedicated_member'},
    {'name': 'Point Collector', 'description': 'Earned 100 points.', 'icon_url': 'static/badges/point_collector.png', 'criteria_key': 'point_collector'},
    {'name': 'Point Hoarder', 'description': 'Earned 500 points.', 'icon_url': 'static/badges/point_hoarder.png', 'criteria_key': 'point_hoarder'},
]

def seed_badges():
    """
    Seeds the database with initial badges defined in `INITIAL_BADGES`.

    This function checks if the Badge table is empty. If it is, it iterates
    through the `INITIAL_BADGES` list, creates new `Badge` model instances,
    and commits them to the database. This ensures that all predefined badges
    are available in the system.
    """
    if Badge.query.first() is None: # Check if any badges exist
        for badge_data in INITIAL_BADGES:
            badge = Badge(
                name=badge_data['name'],
                description=badge_data['description'],
                icon_url=badge_data['icon_url'],
                criteria_key=badge_data['criteria_key']
                # criteria field from model is for human-readable text, not used here.
            )
            db.session.add(badge)
        try:
            db.session.commit()
            print("Badges seeded successfully.") # Or use current_app.logger
        except Exception as e:
            db.session.rollback()
            print(f"Error seeding badges: {e}") # Or use current_app.logger

def check_and_award_badges(user):
    """
    Checks if a given user qualifies for any new badges and awards them.

    The general flow is:
    1. Ensure badges are seeded in the database (calls `seed_badges()` if needed).
    2. Fetch all available badges and the user's currently earned badges.
    3. For each available badge not already earned by the user:
        a. Evaluate the specific criteria for that badge (based on `badge.criteria_key`).
        b. If criteria are met:
            i. Append the badge to the user's `badges` collection.
            ii. Create an `ActivityLog` entry for earning the badge.
            iii. Create a `Notification` for the user.
            iv. Emit a SocketIO event to notify the user in real-time.
    4. If any new badges were awarded, commit the changes to the database.

    Args:
        user (User): The user object for whom to check and award badges.
                 The function will evaluate badge criteria based on this user's
                 activities, posts, points, etc.

    Side Effects:
        - If new badges are awarded, this function will commit the changes to the
          database session (`db.session.commit()`). This includes associating the
          new badge(s) with the user, creating `ActivityLog` entries, and
          `Notification` objects.
        - Emits a 'new_notification' SocketIO event to the user if a badge is awarded.
    """
    if not Badge.query.first(): # Check if badges are seeded, if not, seed them.
        seed_badges() # This also commits the session if badges are added.

    all_badges = Badge.query.all()
    if not all_badges: # If still no badges after trying to seed (e.g. DB error in seed_badges)
        print("No badges found in the database to check against.") # Or logger
        return

    # Eagerly load user's points if not already loaded by the caller of award_points
    # This ensures user.points_data (or user.points as per model) is accessible.
    # Assuming UserPoints relationship is named 'points' on User model, and backref is 'user_profile'.
    # If UserPoints is accessed via user.points_data_ref.points, ensure that's loaded.
    # For simplicity, let's assume user.points.points is how it's accessed.
    # The UserPoints model has `user = db.relationship('User', backref=db.backref('points_data_ref', uselist=False))`
    # And User model has `points = db.relationship('UserPoints', backref='user_profile', uselist=False, cascade='all, delete-orphan')`
    # So, user.points will give the UserPoints object.

    user_points_obj = user.points # This should trigger a load if not already loaded.
    if not user_points_obj: # Should not happen if award_points created it, but as a safeguard
        user_points_obj = UserPoints(user_id=user.id, points=0)
        db.session.add(user_points_obj)
        # No commit here, let the main logic commit at the end.

    earned_badge_ids = {badge.id for badge in user.badges}
    newly_awarded_badges_info = [] # To collect info about newly awarded badges

    for badge_obj in all_badges:
        if badge_obj.id in earned_badge_ids:
            continue # User already has this badge

        awarded = False
        if badge_obj.criteria_key == 'welcome_wagon':
            if user.bio and user.bio.strip() and \
               user.profile_picture_url and user.profile_picture_url != 'default_profile_pic.png':
                awarded = True
        elif badge_obj.criteria_key == 'first_steps':
            # Criteria: User has made at least one post.
            if Post.query.filter_by(user_id=user.id).count() >= 1:
                awarded = True
                if awarded: # If badge is awarded, try to award corresponding title
                    try:
                        title_good = VirtualGood.query.filter_by(name="First Steps Title", type="title").first()
                        if title_good:
                            # Check if user already owns this title
                            existing_user_title = UserVirtualGood.query.filter_by(user_id=user.id, virtual_good_id=title_good.id).first()
                            if not existing_user_title:
                                new_user_title = UserVirtualGood(
                                    user_id=user.id,
                                    virtual_good_id=title_good.id,
                                    quantity=1,
                                    is_equipped=False # User can equip it later
                                )
                                db.session.add(new_user_title)
                                print(f"Awarded title '{title_good.name}' to user {user.username}") # Or logger
                                # The commit will happen with the badge award commit
                            else:
                                print(f"User {user.username} already owns title '{title_good.name}'") # Or logger
                        else:
                            print(f"VirtualGood 'First Steps Title' of type 'title' not found. Cannot award title.") # Or logger
                    except Exception as e:
                        print(f"Error awarding title for 'First Steps' badge to user {user.username}: {e}") # Or logger
                        # Potentially db.session.rollback() if this error is critical, but for now, let the main commit handle it or fail.
        elif badge_obj.criteria_key == 'photographer':
            # Criteria: User has made at least one post that contains any media items (images/videos).
            # This is checked by looking for posts authored by the user that have a non-empty 'media_items' relationship.
            if Post.query.filter(Post.user_id == user.id, Post.media_items.any()).count() >= 1:
                awarded = True
        elif badge_obj.criteria_key == 'storyteller':
            if Story.query.filter_by(user_id=user.id).count() >= 1:
                awarded = True
        elif badge_obj.criteria_key == 'opinionator':
            if Poll.query.filter_by(user_id=user.id).count() >= 1:
                awarded = True
        elif badge_obj.criteria_key == 'wordsmith':
            if Article.query.filter_by(user_id=user.id).count() >= 1:
                awarded = True
        elif badge_obj.criteria_key == 'podcaster':
            if AudioPost.query.filter_by(user_id=user.id).count() >= 1:
                awarded = True
        elif badge_obj.criteria_key == 'engager':
            if Comment.query.filter_by(user_id=user.id).count() >= 10:
                awarded = True
        elif badge_obj.criteria_key == 'popular':
            # Criteria: User's posts have received at least 25 'like' reactions in total.
            # This query counts Reaction objects of type 'like' associated with posts authored by the user.
            like_reactions_count = db.session.query(func.count(Reaction.id)).join(Post, Reaction.post_id == Post.id).filter(Post.user_id == user.id, Reaction.reaction_type == 'like').scalar()
            if like_reactions_count >= 25:
                awarded = True
        elif badge_obj.criteria_key == 'very_popular':
            # Criteria: User's posts have received at least 100 'like' reactions in total.
            like_reactions_count = db.session.query(func.count(Reaction.id)).join(Post, Reaction.post_id == Post.id).filter(Post.user_id == user.id, Reaction.reaction_type == 'like').scalar()
            if like_reactions_count >= 100:
                awarded = True
        elif badge_obj.criteria_key == 'influencer':
            # Criteria: User has 10 or more followers.
            # This uses the 'followers' backref relationship on the User model, which counts users following this user.
            if user.followers.count() >= 10: # Assuming user.followers is the relationship
                awarded = True
        elif badge_obj.criteria_key == 'community_builder':
            if Group.query.filter_by(creator_id=user.id).count() >= 1:
                awarded = True
        elif badge_obj.criteria_key == 'event_organizer':
            if Event.query.filter_by(organizer_id=user.id).count() >= 1:
                awarded = True
        elif badge_obj.criteria_key == 'social_butterfly':
            if user.followed.count() >= 5: # Assuming user.followed is the relationship
                awarded = True
        elif badge_obj.criteria_key == 'dedicated_member':
            # Criteria: User has logged in on 7 distinct calendar days.
            # This is checked by counting distinct dates from 'daily_login' entries in the ActivityLog for the user.
            distinct_login_days = db.session.query(func.count(func.distinct(func.date(ActivityLog.timestamp)))) \
                                      .filter(ActivityLog.user_id == user.id, ActivityLog.activity_type == 'daily_login') \
                                      .scalar()
            if distinct_login_days >= 7:
                awarded = True
        elif badge_obj.criteria_key == 'point_collector':
            if user_points_obj and user_points_obj.points >= 100:
                awarded = True
        elif badge_obj.criteria_key == 'point_hoarder':
            if user_points_obj and user_points_obj.points >= 500:
                awarded = True

        if awarded:
            user.badges.append(badge_obj) # Add badge to user's collection
            # Log this achievement
            activity_log = ActivityLog(
                user_id=user.id,
                activity_type='earn_badge',
                points_earned=0, # Or some bonus points for earning a badge
                related_id=badge_obj.id,
                related_item_type='badge'
            )
            db.session.add(activity_log)
            newly_awarded_badges_info.append({'name': badge_obj.name, 'icon_url': badge_obj.icon_url})
            print(f"User {user.username} awarded badge: {badge_obj.name}") # Or logger

            # Create Notification object
            notification = Notification(
                recipient_id=user.id,
                actor_id=user.id, # Self-awarded for earning a badge
                type='new_badge',
                # related_id could be badge_obj.id if Notification model supports generic related_id/type
                # For now, details are in the socketio message.
            )
            db.session.add(notification)

            # Emit SocketIO event
            socketio.emit('new_notification', {
                'type': 'new_badge',
                'message': f"Congratulations! You've earned the '{badge_obj.name}' badge!",
                'badge_name': badge_obj.name,
                'badge_description': badge_obj.description,
                'badge_icon_url': badge_obj.icon_url
                # Client side will handle constructing full URL for static icon if needed
            }, room=str(user.id))

    if newly_awarded_badges_info:
        try:
            db.session.commit() # This will commit user.badges, activity_log, and notification
            print(f"Committed new badges and notifications for user {user.username}")
        except Exception as e:
            db.session.rollback()
            print(f"Error committing new badges/notifications for user {user.username}: {e}")
