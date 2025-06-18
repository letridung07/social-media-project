LEVEL_THRESHOLDS = {
    1: (0, 99),
    2: (100, 249),
    3: (250, 499),
    4: (500, 999),
    5: (1000, 1999),
    6: (2000, 3999),
    7: (4000, 7999),
    8: (8000, 14999),
    9: (15000, 24999),
    10: (25000, float('inf')) # Using float('inf') for the upper bound of the last level
}

"""
Utilities for the gamification system, including badge seeding and awarding logic.
"""
from flask import current_app # Added for logger
from app import db, socketio, cache # Import cache
from app.core.models import User, UserPoints, Badge, ActivityLog, Post, Story, Poll, Article, AudioPost, Comment, Reaction, Group, Event, Notification, VirtualGood, UserVirtualGood
from sqlalchemy import func, desc # For distinct, date, count, desc
from datetime import datetime, date, timedelta, timezone # For Dedicated Member badge and leaderboard

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
    {
        'name': 'Gamer',
        'description': 'Achieved Level 5!',
        'icon_url': 'static/badges/gamer.png', # Placeholder icon
        'criteria_key': 'level_5_reached'
    },
    {
        'name': 'Veteran',
        'description': 'Achieved Level 10! You are a true platform veteran.',
        'icon_url': 'static/badges/veteran.png', # Placeholder icon
        'criteria_key': 'level_10_reached'
    },
    # { # Placeholder for leaderboard badge - implementation note below
    #     'name': 'Weekly Contender',
    #     'description': 'Made it to the Top 10 on the weekly leaderboard!',
    #     'icon_url': 'static/badges/weekly_contender.png', # Placeholder icon
    #     'criteria_key': 'weekly_top_10'
    # },
    # { # Placeholder for leaderboard badge - implementation note below
    #     'name': 'Monthly Champion',
    #     'description': 'Secured a Top 3 spot on the monthly leaderboard!',
    #     'icon_url': 'static/badges/monthly_champion.png', # Placeholder icon
    #     'criteria_key': 'monthly_top_3'
    # }
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
            current_app.logger.info("Badges seeded successfully.")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error seeding badges: {e}", exc_info=True)

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
        current_app.logger.warning("No badges found in the database to check against during check_and_award_badges.")
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
                                current_app.logger.info(f"Awarded title '{title_good.name}' to user {user.username}")
                                # The commit will happen with the badge award commit
                            else:
                                current_app.logger.info(f"User {user.username} already owns title '{title_good.name}'")
                        else:
                            current_app.logger.warning(f"VirtualGood 'First Steps Title' of type 'title' not found. Cannot award title.")
                    except Exception as e:
                        current_app.logger.error(f"Error awarding title for 'First Steps' badge to user {user.username}: {e}", exc_info=True)
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
        elif badge_obj.criteria_key == 'level_5_reached':
            if user_points_obj and user_points_obj.level >= 5:
                awarded = True
        elif badge_obj.criteria_key == 'level_10_reached':
            if user_points_obj and user_points_obj.level >= 10:
                awarded = True
        # elif badge_obj.criteria_key == 'weekly_top_10':
        #     # NOTE: Checking leaderboard badges here can be inefficient.
        #     # This would ideally be handled by a separate, less frequent task.
        #     # For demonstration, a simplified check (if implemented):
        #     # weekly_lb = get_leaderboard(time_period='weekly', limit=10)
        #     # if any(entry['user_id'] == user.id for entry in weekly_lb):
        #     #     awarded = True
        #     pass # Not implementing the check here due to complexity/performance
        # elif badge_obj.criteria_key == 'monthly_top_3':
        #     # Similar note as above for monthly leaderboard badges.
        #     # monthly_lb = get_leaderboard(time_period='monthly', limit=3)
        #     # if any(entry['user_id'] == user.id for entry in monthly_lb):
        #     #     awarded = True
        #     pass # Not implementing the check here

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
            current_app.logger.info(f"User {user.username} awarded badge: {badge_obj.name}")

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
            db.session.commit() # This will commit user.badges, activity_log, notifications, and any new UserVirtualGood titles
            current_app.logger.info(f"Committed new badges/titles and related notifications for user {user.username}")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error committing new badges/titles/notifications for user {user.username}: {e}", exc_info=True)


def update_user_level(user_points_object):
    """
    Checks a user's points against LEVEL_THRESHOLDS and updates their level if necessary.
    Awards a notification and emits a socket event on level up.

    Args:
        user_points_object (UserPoints): The UserPoints object for the user.

    Returns:
        bool: True if the user leveled up, False otherwise.
    """
    if not user_points_object:
        return False

    current_level = user_points_object.level
    new_level = current_level # Initialize new_level with current_level
    user_total_points = user_points_object.points

    # Iterate through defined levels to find the new correct level based on points
    # This loop correctly finds the highest level bracket the user's points fall into.
    for level, (min_points, max_points) in LEVEL_THRESHOLDS.items():
        if min_points <= user_total_points <= max_points:
            new_level = level # Update new_level if points fall into this level's range
            # Continue checking as user might qualify for a higher level within the loop (e.g. if LEVEL_THRESHOLDS is not sorted)
        elif user_total_points > max_points and level == max(LEVEL_THRESHOLDS.keys()):
            # Handles cases where points exceed the max defined threshold for the highest level
            new_level = level
            break # Found the highest possible level or exceeded it

    # Determine the actual highest level the user qualifies for based on their points.
    # This is crucial if LEVEL_THRESHOLDS might not be perfectly ordered or if points can skip levels.
    potential_new_level = 1 # Start with the lowest possible level
    for level_num, (min_pts, _max_pts) in sorted(LEVEL_THRESHOLDS.items()): # Ensure items are sorted by level number
        if user_total_points >= min_pts:
            potential_new_level = level_num
        else:
            # As soon as user's points are less than min_pts for a level,
            # the previously assigned potential_new_level is the correct one.
            break

    new_level = potential_new_level

    if new_level > current_level:
        user_points_object.level = new_level
        # Assuming user_points_object.user_profile is the correct backref to the User model
        user = user_points_object.user_profile
        if not user: # Safeguard if the user_profile relationship isn't loaded or set
            user = User.query.get(user_points_object.user_id)
            if not user:
                current_app.logger.error(f"Could not find User with id {user_points_object.user_id} for UserPoints id {user_points_object.id}")
                return False # Cannot proceed without user object

        current_app.logger.info(f"User {user.username} leveled up to Level {new_level}!")

        # Create Notification
        notification = Notification(
            recipient_id=user.id,
            actor_id=user.id, # Self-action for leveling up
            type='level_up',
            # related_id and related_item_type could be added if Notification model supports it
            # e.g., related_id=user_points_object.id, related_item_type='user_level'
        )
        db.session.add(notification)

        # Emit SocketIO event
        socketio.emit('new_notification', {
            'type': 'level_up',
            'message': f"Congratulations! You've reached Level {new_level}!",
            'level': new_level,
            # 'level_name': f"Level {new_level}", # Optional: for more detailed display
            # 'level_icon_url': f"static/levels/level_{new_level}.png" # Optional: for visual flair
        }, room=str(user.id))

        # The commit of the session including the level update and notification
        # should ideally be handled by the calling function (e.g., award_points)
        # to ensure atomicity of the entire point awarding and leveling process.
        # However, if this function is called standalone, a commit might be needed here.
        # For this subtask, assuming award_points will handle the commit.

        return True # User leveled up
    return False # User did not level up


@cache.memoize(timeout=300) # Cache for 5 minutes
def get_leaderboard(time_period='all', limit=10):
    """
    Fetches leaderboard data based on points.

    Args:
        time_period (str): 'all', 'daily', 'weekly', 'monthly'.
        limit (int): Number of users to return.

    Returns:
        list: List of dictionaries, each representing a user on the leaderboard.
              Each dict contains: 'rank', 'user_id', 'username',
                                 'profile_picture_url', 'level', 'score'.
    """
    leaderboard_results = []

    if time_period == 'all':
        # Query UserPoints directly for all-time leaderboard
        top_users_points = UserPoints.query.join(User, UserPoints.user_id == User.id) \
                                           .add_columns(User.username, User.profile_picture_url, UserPoints.points, UserPoints.level, User.id.label('user_id')) \
                                           .order_by(desc(UserPoints.points)) \
                                           .limit(limit) \
                                           .all()

        for i, result in enumerate(top_users_points):
            # result is a row-like object. Access columns by attribute name given in add_columns or model attribute
            leaderboard_results.append({
                'rank': i + 1,
                'user_id': result.user_id,
                'username': result.username,
                'profile_picture_url': result.profile_picture_url,
                'level': result.level,
                'score': result.points # For 'all' time, score is total points
            })

    else:
        # For daily, weekly, monthly - aggregate from ActivityLog
        now = datetime.now(timezone.utc)
        if time_period == 'daily':
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif time_period == 'weekly':
            start_date = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        elif time_period == 'monthly':
            start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else: # Should not happen if called correctly, but default to daily
            current_app.logger.warning(f"get_leaderboard called with invalid time_period '{time_period}', defaulting to 'daily'.")
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

        end_date = now # Aggregate up to the current moment for these periods

        # Query to sum points from ActivityLog within the period
        summed_points_subquery = db.session.query(
            ActivityLog.user_id,
            func.sum(ActivityLog.points_earned).label('period_score')
        ).filter(ActivityLog.timestamp >= start_date) \
         .filter(ActivityLog.timestamp <= end_date) \
         .group_by(ActivityLog.user_id) \
         .subquery()

        # Join with User and UserPoints to get details
        top_users_period = db.session.query(
            User.id.label('user_id'),
            User.username,
            User.profile_picture_url,
            UserPoints.level, # Get current level from UserPoints
            summed_points_subquery.c.period_score
        ).join(summed_points_subquery, User.id == summed_points_subquery.c.user_id) \
         .join(UserPoints, User.id == UserPoints.user_id) \
         .order_by(desc(summed_points_subquery.c.period_score)) \
         .limit(limit) \
         .all()

        for i, result in enumerate(top_users_period):
            leaderboard_results.append({
                'rank': i + 1,
                'user_id': result.user_id,
                'username': result.username,
                'profile_picture_url': result.profile_picture_url,
                'level': result.level,
                'score': result.period_score if result.period_score is not None else 0
            })

    return leaderboard_results
