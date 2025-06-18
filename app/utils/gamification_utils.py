from app import db
from app.core.models import User, UserPoints, Badge, ActivityLog, Post, Story, Poll, Article, AudioPost, Comment, Reaction, Group, Event
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
    Seeds the database with initial badges if the Badge table is empty.
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
    Checks and awards badges to a user based on predefined criteria.
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
            if Post.query.filter_by(user_id=user.id).count() >= 1:
                awarded = True
        elif badge_obj.criteria_key == 'photographer':
            # Assuming MediaItem model is related to Post as 'media_items'
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
            like_reactions_count = db.session.query(func.count(Reaction.id)).join(Post, Reaction.post_id == Post.id).filter(Post.user_id == user.id, Reaction.reaction_type == 'like').scalar()
            if like_reactions_count >= 25:
                awarded = True
        elif badge_obj.criteria_key == 'very_popular':
            like_reactions_count = db.session.query(func.count(Reaction.id)).join(Post, Reaction.post_id == Post.id).filter(Post.user_id == user.id, Reaction.reaction_type == 'like').scalar()
            if like_reactions_count >= 100:
                awarded = True
        elif badge_obj.criteria_key == 'influencer':
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
            # Count distinct days of 'daily_login' ActivityLog entries
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

    if newly_awarded_badges_info:
        try:
            db.session.commit()
            # Here you could trigger notifications for newly awarded badges
            # For example, iterate through newly_awarded_badges_info and send SocketIO events or create Notification objects
            print(f"Committed new badges for user {user.username}")
        except Exception as e:
            db.session.rollback()
            print(f"Error committing new badges for user {user.username}: {e}")
