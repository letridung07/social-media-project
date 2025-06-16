from flask import Blueprint, request, jsonify
from app.models import Application, User # User is needed to fetch app owner
from app.oauth2 import generate_access_token, ACCESS_TOKEN_EXPIRES_IN_SECONDS
from app import db # For database session if needed directly, though models handle it
from app import limiter # Assuming limiter is the instance from app/__init__.py

api_bp = Blueprint('api', __name__)

@api_bp.route('/oauth/token', methods=['POST'])
@limiter.limit("60 per hour; 5 per minute") # Stricter: 60 per hour, 5 per minute
def oauth_token():
    """
    OAuth 2.0 Token Endpoint.
    Currently supports the client_credentials grant type.
    ---
    tags:
      - OAuth
    consumes:
      - application/x-www-form-urlencoded
    produces:
      - application/json
    parameters:
      - name: grant_type
        in: formData
        type: string
        required: true
        description: The grant type. Must be "client_credentials".
      - name: client_id
        in: formData
        type: string
        required: true
        description: The client ID of the application.
      - name: client_secret
        in: formData
        type: string
        required: true
        description: The client secret of the application.
      - name: scope
        in: formData
        type: string
        required: false
        description: Optional space-separated list of scopes. (Currently not fully implemented in token logic)
    responses:
      200:
        description: Access token granted successfully.
        schema:
          type: object
          properties:
            access_token:
              type: string
              description: The access token.
            token_type:
              type: string
              example: bearer
            expires_in:
              type: integer
              description: Token expiration time in seconds.
      400:
        description: Invalid request (e.g., missing parameters, unsupported grant type).
        schema:
          type: object
          properties:
            error:
              type: string
            error_description:
              type: string
      401:
        description: Invalid client (e.g., client not found, invalid client secret).
        schema:
          type: object
          properties:
            error:
              type: string
            error_description:
              type: string
      500:
        description: Server error (e.g., application owner not found).
    """
    grant_type = request.form.get('grant_type')
    client_id = request.form.get('client_id')
    client_secret = request.form.get('client_secret')
    # scopes = request.form.get('scope') # Optional scope

    if not grant_type or not client_id or not client_secret:
        return jsonify(error="InvalidRequest", message="Missing grant_type, client_id, or client_secret"), 400

    if grant_type == 'client_credentials':
        application = Application.query.filter_by(client_id=client_id).first()

        if not application:
            return jsonify(error="InvalidClient", message="Client not found"), 401

        # The Application model has a check_client_secret method
        if not application.check_client_secret(client_secret):
            return jsonify(error="InvalidClient", message="Invalid client secret"), 401

        # For client_credentials, the token is issued to the application itself.
        # Our AccessToken model requires a user_id. We'll use the app's owner.
        app_owner = User.query.get(application.owner_user_id)
        if not app_owner:
            # This would be an orphaned application, data integrity issue
            # This should be a 500 error, handled by the generic error handler or a specific one.
            current_app.logger.error(f"Application owner not found for app_id {application.id}")
            return jsonify(error="ServerError", message="Application owner not found."), 500

        # Generate the token (scopes can be passed if implemented)
        # For client_credentials, scopes might be more limited or predefined by the app's registration
        token_string = generate_access_token(user=app_owner, application=application, scopes=None) # Modify scopes as needed

        return jsonify({
            "access_token": token_string,
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRES_IN_SECONDS
            # "scope": scopes_string_or_null # If scopes are handled
        }), 200

    # For unsupported grant types, use a specific error type and message.
    # 501 Not Implemented for stubs, 400 Bad Request for truly unsupported.
    elif grant_type in ['authorization_code', 'refresh_token']: # Assuming these are planned but not ready
        return jsonify(error="UnsupportedGrantType", message=f"{grant_type} grant type not yet implemented."), 501

    elif grant_type == 'password': # Explicitly not supporting this
         return jsonify(error="UnsupportedGrantType", message="Password grant type is not supported."), 400

    else: # Any other grant_type string
        return jsonify(error="UnsupportedGrantType", message=f"Grant type '{grant_type}' is not supported."), 400

# Example of a protected route (to be implemented/tested later)
from app.models import Post, PRIVACY_PUBLIC, PRIVACY_PRIVATE, PRIVACY_FOLLOWERS, PRIVACY_CUSTOM_LIST
from app.oauth2 import token_required
from flask import g, abort # For g.current_user

# Helper to serialize user data (can be expanded)
def serialize_user_public_data(user):
    return {
        "id": user.id,
        "username": user.username,
        "bio": user.bio,
        "profile_picture_url": user.profile_picture_url
        # Add other public fields as needed
    }

@api_bp.route('/users/<int:user_id>', methods=['GET'])
@token_required
def get_user(user_id):
    """
    Get a user's public profile information.
    Requires Bearer token authentication.
    ---
    tags:
      - Users
    parameters:
      - name: user_id
        in: path
        type: integer
        required: true
        description: The ID of the user to retrieve.
    security:
      - BearerAuth: []
    responses:
      200:
        description: User profile data.
        schema:
          type: object
          properties:
            id:
              type: integer
            username:
              type: string
            bio:
              type: string
              nullable: true
            profile_picture_url:
              type: string
              nullable: true
      401:
        description: Unauthorized (token missing or invalid).
      403:
        description: Forbidden (access to user profile denied due to privacy settings).
      404:
        description: User not found.
    """
    target_user = User.query.get_or_404(user_id)
    requesting_user = g.current_user

    # Profile visibility checks
    if target_user.id == requesting_user.id: # Owner can always view
        pass
    elif target_user.profile_visibility == PRIVACY_PRIVATE:
        return jsonify(error="Forbidden", message="This profile is private."), 403
    elif target_user.profile_visibility == PRIVACY_FOLLOWERS:
        if not requesting_user.is_following(target_user):
            return jsonify(error="Forbidden", message="This profile is only visible to followers."), 403
    elif target_user.profile_visibility == PRIVACY_PUBLIC:
        pass # Public profile, accessible to all authenticated users
    elif target_user.profile_visibility == PRIVACY_CUSTOM_LIST:
        # Simplified: if it's custom list and not the owner, deny for now
        return jsonify(error="Forbidden", message="Access to this profile is restricted by a custom list."), 403
    else: # Default deny for unknown privacy levels
        return jsonify(error="Forbidden", message="Profile visibility settings prevent access."), 403

    return jsonify(serialize_user_public_data(target_user)), 200

# Helper to serialize post data (can be expanded)
def serialize_post_data(post):
    return {
        "id": post.id,
        "body": post.body,
        "timestamp": post.timestamp.isoformat() + 'Z', # ISO 8601 format
        "author_id": post.user_id,
        "like_count": post.like_count(), # Assuming Post model has like_count()
        "comment_count": post.comments.count(), # Assuming Post model has comments relationship
        "privacy_level": post.privacy_level
        # Add other fields as needed, e.g., media_items
    }

@api_bp.route('/users/<int:user_id>/posts', methods=['GET'])
@token_required
def get_user_posts(user_id):
    """
    Get posts by a specific user.
    Requires Bearer token authentication. Respects user profile and post privacy settings.
    ---
    tags:
      - Users
      - Posts
    parameters:
      - name: user_id
        in: path
        type: integer
        required: true
        description: The ID of the user whose posts are to be retrieved.
      - name: page
        in: query
        type: integer
        required: false
        default: 1
        description: Page number for pagination.
      - name: per_page
        in: query
        type: integer
        required: false
        default: 10
        description: Number of posts per page.
    security:
      - BearerAuth: []
    responses:
      200:
        description: A paginated list of the user's visible posts.
        schema:
          type: object
          properties:
            posts:
              type: array
              items:
                # Assuming serialize_post_data structure
                type: object
                properties:
                  id: { type: integer }
                  body: { type: string }
                  timestamp: { type: string, format: date-time }
                  author_id: { type: integer }
                  like_count: { type: integer }
                  comment_count: { type: integer }
                  privacy_level: { type: string }
            page: { type: integer }
            per_page: { type: integer }
            total_pages: { type: integer }
            total_items: { type: integer }
      401:
        description: Unauthorized (token missing or invalid).
      403:
        description: Forbidden (access to user's profile or posts denied).
      404:
        description: User not found.
    """
    target_user = User.query.get_or_404(user_id)
    requesting_user = g.current_user

    # 1. Check profile visibility first (same logic as get_user endpoint)
    if target_user.id != requesting_user.id:
        if target_user.profile_visibility == PRIVACY_PRIVATE:
            return jsonify({"error": "forbidden", "message": "This user's profile is private."}), 403
        elif target_user.profile_visibility == PRIVACY_FOLLOWERS:
            if not requesting_user.is_following(target_user):
                return jsonify({"error": "forbidden", "message": "This user's profile is only visible to followers."}), 403
        elif target_user.profile_visibility == PRIVACY_CUSTOM_LIST:
            # Simplified: Deny if not owner. Real check needed for custom lists.
            return jsonify({"error": "forbidden", "message": "Access to this user's profile is restricted by a custom list."}), 403
        elif target_user.profile_visibility != PRIVACY_PUBLIC: # Default deny for unknown or other restricted
            return jsonify({"error": "forbidden", "message": "Profile visibility settings prevent access to posts."}), 403

    # 2. Fetch and filter posts
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
    except ValueError: # Should be caught by Werkzeug's type conversion, but good to be safe if direct conversion was used.
                       # However, request.args.get with type=int handles this by returning default.
                       # This try-except might not be strictly needed with current Flask versions.
                       # For robustness, we can ensure positive values.
        # This path is less likely with current request.args.get usage.
        # abort(400, description="Page and per_page must be integers.") might be better if direct conversion was used.
        # For now, let the default values and checks below handle it.
        pass # Or log a warning, but direct error response here might be preempted by checks below.

    if page <= 0:
        # page = 1 # Defaulting is one option, or return error for invalid explicit values
        return jsonify(error="InvalidRequest", message="Page number must be positive."), 400
    if per_page <= 0 :
        # per_page = 10
        return jsonify(error="InvalidRequest", message="Items per page must be positive."), 400
    if per_page > 100: # Max per_page
        # per_page = 100
        return jsonify(error="InvalidRequest", message="Items per page cannot exceed 100."), 400

    # Base query for published posts by the target user
    posts_query = Post.query.filter_by(user_id=target_user.id, is_published=True)

    # Apply privacy filtering for each post
    # This can be inefficient if done purely in Python for many posts.
    # For a more optimized approach, complex SQL queries or pre-filtering might be needed.
    # Here, we fetch then filter in Python for clarity of logic.

    # A more performant way would be to build up the query with OR conditions based on privacy.
    # For example:
    # conditions = [Post.privacy_level == PRIVACY_PUBLIC]
    # if requesting_user.id == target_user.id:
    #     conditions.append(Post.privacy_level.in_([PRIVACY_PRIVATE, PRIVACY_FOLLOWERS, PRIVACY_CUSTOM_LIST]))
    # elif requesting_user.is_following(target_user):
    #     conditions.append(Post.privacy_level == PRIVACY_FOLLOWERS)
    # # Custom list check would be more complex: check if requesting_user is in Post.custom_friend_list.members
    # posts_query = posts_query.filter(db.or_(*conditions))
    # This is still simplified, especially for PRIVACY_CUSTOM_LIST.

    # For now, let's paginate first, then filter the paginated items in Python (less ideal for large datasets).
    pagination = posts_query.order_by(Post.timestamp.desc()).paginate(page=page, per_page=per_page, error_out=False)
    all_posts_on_page = pagination.items

    visible_posts = []
    if target_user.id == requesting_user.id: # Owner sees all their own posts
        visible_posts = all_posts_on_page
    else:
        for post in all_posts_on_page:
            if post.privacy_level == PRIVACY_PUBLIC:
                visible_posts.append(post)
            elif post.privacy_level == PRIVACY_FOLLOWERS:
                if requesting_user.is_following(target_user):
                    visible_posts.append(post)
            elif post.privacy_level == PRIVACY_CUSTOM_LIST:
                # This requires checking if requesting_user is in post.custom_friend_list.members
                # Assuming Post model has 'custom_friend_list' relationship and FriendList has 'members'
                if post.custom_friend_list and requesting_user in post.custom_friend_list.members.all():
                     visible_posts.append(post)
            # PRIVACY_PRIVATE posts are only visible to the owner, already handled by the first `if`

    return jsonify({
        "posts": [serialize_post_data(post) for post in visible_posts],
        "page": pagination.page,
        "per_page": pagination.per_page,
        "total_pages": pagination.pages,
        "total_items": pagination.total # This total is for pre-filtered posts by user_id and is_published
                                        # A more accurate total for visible posts would require counting after filtering.
    }), 200

@api_bp.route('/posts/<int:post_id>', methods=['GET'])
@token_required
def get_post(post_id):
    """
    Get a single post by its ID.
    Requires Bearer token authentication. Respects post privacy settings.
    ---
    tags:
      - Posts
    parameters:
      - name: post_id
        in: path
        type: integer
        required: true
        description: The ID of the post to retrieve.
    security:
      - BearerAuth: []
    responses:
      200:
        description: Post data.
        schema:
          # Assuming serialize_post_data structure
          type: object
          properties:
            id: { type: integer }
            body: { type: string }
            timestamp: { type: string, format: date-time }
            author_id: { type: integer }
            like_count: { type: integer }
            comment_count: { type: integer }
            privacy_level: { type: string }
      401:
        description: Unauthorized (token missing or invalid).
      403:
        description: Forbidden (access to post denied due to privacy settings).
      404:
        description: Post not found or not published.
    """
    post = Post.query.get_or_404(post_id)
    requesting_user = g.current_user

    # Check if post is published, unless requester is the author
    if not post.is_published and post.user_id != requesting_user.id:
        # This specific 404 is fine as is, or can use the generic handler via abort(404, description="...")
        return jsonify(error="NotFound", message="Post not found or not published."), 404

    # Privacy checks
    if post.user_id == requesting_user.id: # Author can always view their own post
        pass
    elif post.privacy_level == PRIVACY_PUBLIC:
        pass
    elif post.privacy_level == PRIVACY_FOLLOWERS:
        if not post.author or not requesting_user.is_following(post.author):
            return jsonify(error="Forbidden", message="This post is only visible to followers of the author."), 403
    elif post.privacy_level == PRIVACY_CUSTOM_LIST:
        if not post.custom_friend_list or requesting_user not in post.custom_friend_list.members.all():
            return jsonify(error="Forbidden", message="Access to this post is restricted to a custom list."), 403
    elif post.privacy_level == PRIVACY_PRIVATE:
        return jsonify(error="Forbidden", message="This post is private."), 403 # Should be caught by first check if not author
    else:
        return jsonify(error="Forbidden", message="Post visibility settings prevent access."), 403

    return jsonify(serialize_post_data(post)), 200

# from app.utils import process_hashtags, process_mentions # For creating/updating posts
from app.models import FriendList # For custom list validation

@api_bp.route('/posts', methods=['POST'])
@token_required
def create_post():
    """
    Create a new post.
    Requires Bearer token authentication.
    ---
    tags:
      - Posts
    security:
      - BearerAuth: []
    consumes:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        description: The content of the post and privacy settings.
        schema:
          type: object
          required:
            - body
          properties:
            body:
              type: string
              description: The text content of the post.
            privacy_level:
              type: string
              description: "Privacy level for the post (e.g., PUBLIC, FOLLOWERS, CUSTOM_LIST, PRIVATE). Defaults to user's default or PUBLIC."
              enum: ["PUBLIC", "FOLLOWERS", "CUSTOM_LIST", "PRIVATE"] # Example enum
            custom_friend_list_id:
              type: integer
              description: "Required if privacy_level is CUSTOM_LIST. The ID of the FriendList."
    produces:
      - application/json
    responses:
      201:
        description: Post created successfully. Returns the new post data.
        schema:
          # Assuming serialize_post_data structure
          type: object
          properties:
            id: { type: integer }
            body: { type: string }
            timestamp: { type: string, format: date-time }
            author_id: { type: integer }
            like_count: { type: integer }
            comment_count: { type: integer }
            privacy_level: { type: string }
      400:
        description: Invalid request (e.g., missing body, validation error).
      401:
        description: Unauthorized (token missing or invalid).
    """
    data = request.get_json()
    if not data:
        return jsonify(error="InvalidRequest", message="No input data provided or not valid JSON."), 400

    body = data.get('body')
    if not body or not body.strip():
        return jsonify(error="ValidationError", message="Post body cannot be empty."), 400
    if len(body) > 5000: # Max length for post body
        return jsonify(error="ValidationError", message="Post body exceeds maximum length of 5000 characters."), 400

    requesting_user = g.current_user

    valid_privacy_levels = [PRIVACY_PUBLIC, PRIVACY_FOLLOWERS, PRIVACY_CUSTOM_LIST, PRIVACY_PRIVATE]
    privacy_level = data.get('privacy_level', requesting_user.default_post_privacy or PRIVACY_PUBLIC)
    if privacy_level not in valid_privacy_levels:
        return jsonify(error="ValidationError", message=f"Invalid privacy_level. Must be one of: {', '.join(valid_privacy_levels)}"), 400

    custom_friend_list_id = data.get('custom_friend_list_id')
    friend_list = None
    if privacy_level == PRIVACY_CUSTOM_LIST:
        if not custom_friend_list_id:
            return jsonify(error="ValidationError", message="custom_friend_list_id is required for PRIVACY_CUSTOM_LIST."), 400
        friend_list = FriendList.query.filter_by(id=custom_friend_list_id, user_id=requesting_user.id).first()
        if not friend_list:
            return jsonify(error="ValidationError", message="Invalid custom_friend_list_id or list not owned by user."), 400
    elif custom_friend_list_id: # If privacy is not custom, but ID is given, it's a bad request
        return jsonify(error="ValidationError", message="custom_friend_list_id should only be provided if privacy_level is PRIVACY_CUSTOM_LIST."), 400


    new_post = Post(
        body=body,
        user_id=requesting_user.id,
        author=requesting_user, # Set relationship directly
        privacy_level=privacy_level,
        custom_friend_list_id=friend_list.id if friend_list else None,
        custom_friend_list=friend_list if friend_list else None, # Set relationship
        is_published=True # API posts are immediately published
    )
    db.session.add(new_post)
    db.session.commit() # Commit to get new_post.id for hashtag/mention processing

    # Process hashtags and mentions
    process_hashtags(new_post.body, new_post)
    # process_mentions(new_post.body, new_post, requesting_user) # actor is requesting_user
    # For process_mentions, the original function signature might be (text, post_id, actor_id, comment_id=None)
    # Assuming process_mentions can handle a Post object and actor object, or adjust call accordingly.
    # Let's assume a simplified call for now, focusing on data integrity of hashtags.
    # Full mention notification logic might be complex for API response.
    # The original process_mentions in app/utils.py is:
    # def process_mentions(text_body, post_id, actor_id, comment_id=None, db_session=None):
    # So, we need post_id and actor_id.
    process_mentions(text_body=new_post.body, post_id=new_post.id, actor_id=requesting_user.id, db_session=db.session)


    db.session.commit() # Commit again if hashtags/mentions modify the session (e.g. new tags)

    return jsonify(serialize_post_data(new_post)), 201

@api_bp.route('/posts/<int:post_id>', methods=['PUT'])
@token_required
def update_post(post_id):
    """
    Update an existing post.
    Requires Bearer token authentication. User must be the author of the post.
    ---
    tags:
      - Posts
    security:
      - BearerAuth: []
    parameters:
      - name: post_id
        in: path
        type: integer
        required: true
        description: The ID of the post to update.
      - name: body
        in: body
        required: true
        description: The fields to update for the post. All fields are optional.
        schema:
          type: object
          properties:
            body:
              type: string
              description: The new text content of the post.
            privacy_level:
              type: string
              description: "New privacy level for the post (e.g., PUBLIC, FOLLOWERS, CUSTOM_LIST, PRIVATE)."
              enum: ["PUBLIC", "FOLLOWERS", "CUSTOM_LIST", "PRIVATE"]
            custom_friend_list_id:
              type: integer
              description: "Required if privacy_level is changed to CUSTOM_LIST. The ID of the FriendList."
    produces:
      - application/json
    responses:
      200:
        description: Post updated successfully. Returns the updated post data.
        schema:
          # Assuming serialize_post_data structure
          type: object
          properties:
            id: { type: integer }
            body: { type: string }
            timestamp: { type: string, format: date-time }
            author_id: { type: integer }
            like_count: { type: integer }
            comment_count: { type: integer }
            privacy_level: { type: string }
      400:
        description: Invalid request (e.g., empty body, validation error).
      401:
        description: Unauthorized (token missing or invalid).
      403:
        description: Forbidden (user is not the author of the post).
      404:
        description: Post not found.
    """
    post = Post.query.get_or_404(post_id)
    requesting_user = g.current_user

    if post.user_id != requesting_user.id:
        return jsonify(error="Forbidden", message="You are not authorized to edit this post."), 403

    data = request.get_json()
    if not data:
        return jsonify(error="InvalidRequest", message="No input data provided or not valid JSON."), 400

    # Update fields if provided
    body_changed = False
    if 'body' in data:
        new_body = data['body']
        if new_body is not None:
            if not new_body.strip():
                return jsonify(error="ValidationError", message="Post body cannot be empty if provided."), 400
            if len(new_body) > 5000:
                return jsonify(error="ValidationError", message="Post body exceeds maximum length of 5000 characters."), 400
            if post.body != new_body:
                post.body = new_body
                body_changed = True
        else:
            return jsonify(error="ValidationError", message="Post body cannot be null if 'body' key is provided."), 400

    valid_privacy_levels = [PRIVACY_PUBLIC, PRIVACY_FOLLOWERS, PRIVACY_CUSTOM_LIST, PRIVACY_PRIVATE]
    if 'privacy_level' in data:
        new_privacy_level = data['privacy_level']
        if new_privacy_level not in valid_privacy_levels:
            return jsonify(error="ValidationError", message=f"Invalid privacy_level. Must be one of: {', '.join(valid_privacy_levels)}"), 400
        post.privacy_level = new_privacy_level

        if post.privacy_level == PRIVACY_CUSTOM_LIST:
            custom_friend_list_id = data.get('custom_friend_list_id', post.custom_friend_list_id)
            if not custom_friend_list_id:
                return jsonify(error="ValidationError", message="custom_friend_list_id is required when privacy_level is PRIVACY_CUSTOM_LIST."), 400
            friend_list = FriendList.query.filter_by(id=custom_friend_list_id, user_id=requesting_user.id).first()
            if not friend_list:
                return jsonify(error="ValidationError", message="Invalid custom_friend_list_id or list not owned by user."), 400
            post.custom_friend_list_id = friend_list.id
            post.custom_friend_list = friend_list
        elif data.get('custom_friend_list_id') is not None:
             return jsonify(error="ValidationError", message="custom_friend_list_id should only be provided if privacy_level is PRIVACY_CUSTOM_LIST."), 400
        else:
            post.custom_friend_list_id = None
            post.custom_friend_list = None

    elif 'custom_friend_list_id' in data and data['custom_friend_list_id'] is not None:
        if post.privacy_level != PRIVACY_CUSTOM_LIST: # Cannot set custom_friend_list_id if not in CUSTOM_LIST privacy mode
             return jsonify(error="ValidationError", message="custom_friend_list_id can only be set if privacy_level is PRIVACY_CUSTOM_LIST. Please set privacy_level first or simultaneously."), 400
        friend_list = FriendList.query.filter_by(id=data['custom_friend_list_id'], user_id=requesting_user.id).first()
        if not friend_list:
            return jsonify(error="ValidationError", message="Invalid custom_friend_list_id or list not owned by user."), 400
        post.custom_friend_list_id = friend_list.id
        post.custom_friend_list = friend_list


    if body_changed:
        # Clear old hashtags/mentions and reprocess
        # For hashtags, process_hashtags usually handles additions/removals correctly if it clears existing tags first
        # For mentions, it's more complex if we want to remove old ones that are no longer in body
        # A simple approach: delete all existing mentions for this post and re-create.
        from app.models import Mention, Hashtag # Import here to avoid circular if not already at top
        Mention.query.filter_by(post_id=post.id).delete()
        # For hashtags, if process_hashtags doesn't clear them:
        post.hashtags.clear() # Clear existing many-to-many hashtag associations
        db.session.flush() # Ensure deletions and clears are processed before adding new ones

        process_hashtags(post.body, post)
        process_mentions(text_body=post.body, post_id=post.id, actor_id=requesting_user.id, db_session=db.session)

    db.session.commit()
    return jsonify(serialize_post_data(post)), 200

@api_bp.route('/posts/<int:post_id>', methods=['DELETE'])
@token_required
def delete_post_api(post_id): # Renamed to avoid conflict if a web route `delete_post` exists
    """
    Delete an existing post.
    Requires Bearer token authentication. User must be the author of the post.
    ---
    tags:
      - Posts
    security:
      - BearerAuth: []
    parameters:
      - name: post_id
        in: path
        type: integer
        required: true
        description: The ID of the post to delete.
    produces:
      - application/json
    responses:
      200:
        description: Post deleted successfully.
        schema:
          type: object
          properties:
            message:
              type: string
              example: Post deleted successfully
      401:
        description: Unauthorized (token missing or invalid).
      403:
        description: Forbidden (user is not the author of the post).
      404:
        description: Post not found.
    """
    post = Post.query.get_or_404(post_id)
    requesting_user = g.current_user

    if post.user_id != requesting_user.id:
        return jsonify(error="Forbidden", message="You are not authorized to delete this post."), 403

    # Cascading deletes for related items like likes, comments, mentions, media_items (db rows)
    # are expected to be handled by SQLAlchemy's cascade options in model definitions.
    # Filesystem file deletions for media_items are not handled here.

    # Also, need to remove associations in post_hashtags table.
    # If `post.hashtags` relationship has `cascade="all, delete"` or similar for the association,
    # it might be handled. Otherwise, explicit clear is safer.
    post.hashtags.clear() # Clear many-to-many for hashtags before deleting post.

    # Manually delete associated mentions if not cascaded perfectly by DB or ORM config.
    from app.models import Mention # Import here if not at top
    Mention.query.filter_by(post_id=post.id).delete()

    # Note: If there are other related items that don't cascade (e.g., notifications referencing this post),
    # they might need manual cleanup or be set to nullify the foreign key.
    # For this subtask, focusing on direct post deletion and its ORM-managed cascades.

    db.session.delete(post)
    db.session.commit()

    return jsonify({"message": "Post deleted successfully"}), 200 # Or 204 No Content, but 200 with message is also common.

from app.models import Like, Comment # For interactions
from werkzeug.exceptions import HTTPException
from flask import json, current_app, request, g # Added request, g for logging
import time # For logging request duration
import logging # For setting log level if needed

# Standardized JSON Error Handling for API Blueprint
@api_bp.errorhandler(HTTPException)
def handle_http_exception_api(e):
    """Return JSON instead of HTML for HTTP errors within the API blueprint."""
    response = e.get_response()
    # Replace the HTML response with JSON content
    response.data = json.dumps({
        "error": e.name.replace(" ", ""), # e.g., "NotFound", "BadRequest"
        "message": e.description,
    })
    response.content_type = "application/json"
    return response

# Specific handlers to ensure consistent format if needed,
# or to add more details/logging. The generic one above might suffice.
@api_bp.errorhandler(400) # Bad Request
def handle_bad_request_api(e):
    # If e.description is already set by abort(400, description="..."), use it.
    # Otherwise, provide a generic message.
    message = e.description or "The browser (or proxy) sent a request that this server could not understand."
    return jsonify(error="BadRequest", message=message), 400

@api_bp.errorhandler(401) # Unauthorized
def handle_unauthorized_api(e):
    message = e.description or "Authentication is required to access this resource."
    return jsonify(error="Unauthorized", message=message), 401

@api_bp.errorhandler(403) # Forbidden
def handle_forbidden_api(e):
    message = e.description or "You do not have permission to access this resource."
    return jsonify(error="Forbidden", message=message), 403

@api_bp.errorhandler(404) # Not Found
def handle_not_found_api(e):
    message = e.description or "The requested resource was not found on the server."
    return jsonify(error="NotFound", message=message), 404

@api_bp.errorhandler(405) # Method Not Allowed
def handle_method_not_allowed_api(e):
    message = e.description or "The method is not allowed for the requested URL."
    return jsonify(error="MethodNotAllowed", message=message), 405

@api_bp.errorhandler(500) # Internal Server Error
def handle_internal_server_error_api(e):
    # Log the exception for server-side review
    current_app.logger.error(f"API Internal Server Error: {e}", exc_info=True)
    # Return a generic error message to the client
    return jsonify(error="InternalServerError", message="An unexpected error occurred on the server. Please try again later."), 500


# Request and Response Logging for API Blueprint
@api_bp.before_request
def log_api_request_before():
    g.api_start_time = time.time()
    # Ensure logger is at least INFO level if not in DEBUG mode.
    # This might be better placed in app creation, but can be checked here.
    if not current_app.debug and current_app.logger.level > logging.INFO:
        current_app.logger.setLevel(logging.INFO) # Or directly in config.py

    log_message = (
        f"API Request START: {request.remote_addr} {request.method} {request.scheme} {request.host}{request.full_path} "
        f"Agent: {request.user_agent.string}"
    )
    current_app.logger.info(log_message)

@api_bp.after_request
def log_api_response_after(response):
    duration_ms = (time.time() - g.api_start_time) * 1000 if hasattr(g, 'api_start_time') else -1

    user_info = "User: Anonymous/App" # Default for client_credentials or if token_required hasn't run/set g.current_user
    if hasattr(g, 'current_user') and g.current_user:
        user_info = f"User: {g.current_user.id}"

    app_info = ""
    if hasattr(g, 'current_application') and g.current_application:
        app_info = f"App: {g.current_application.name} (ID: {g.current_application.id})"

    log_message = (
        f"API Response END: {request.remote_addr} {request.method} {request.scheme} {request.host}{request.full_path} "
        f"Status: {response.status_code} Duration: {duration_ms:.2f}ms {user_info} {app_info}"
    )

    if 400 <= response.status_code < 500:
        current_app.logger.warning(log_message)
        try:
            data_sample = response.get_data(as_text=True)
            current_app.logger.warning(f"Client Error Response Body: {data_sample[:500]}") # Log more for client errors
        except Exception:
            pass
    elif response.status_code >= 500: # Server errors already logged in detail by their handler
        current_app.logger.error(log_message) # Log summary here as well
    else: # Successful responses
        current_app.logger.info(log_message)

    # Example: Selective logging of response data for debugging (be cautious with sensitive data)
    # if response.content_type == 'application/json' and current_app.debug:
    #     try:
    #         data_sample = response.get_data(as_text=True)
    #         current_app.logger.debug(f"DEBUG Response JSON sample: {data_sample[:200]}")
    #     except Exception:
    #         pass

    return response

@api_bp.route('/posts/<int:post_id>/like', methods=['POST'])
@token_required
def toggle_like_post(post_id):
    """
    Toggle like/unlike on a post.
    Requires Bearer token authentication. User must have permission to view/interact with the post.
    ---
    tags:
      - Interactions
      - Posts
    security:
      - BearerAuth: []
    parameters:
      - name: post_id
        in: path
        type: integer
        required: true
        description: The ID of the post to like/unlike.
    produces:
      - application/json
    responses:
      200:
        description: Like status updated successfully.
        schema:
          type: object
          properties:
            status:
              type: string
              example: liked # or unliked
            like_count:
              type: integer
      401:
        description: Unauthorized (token missing or invalid).
      403:
        description: Forbidden (user cannot interact with the post).
      404:
        description: Post not found or not published.
    """
    post = Post.query.get_or_404(post_id)
    requesting_user = g.current_user

    # Check if post is published, unless requester is the author
    if not post.is_published and post.user_id != requesting_user.id:
        return jsonify(error="NotFound", message="Post not found or not published."), 404

    # Privacy checks for interaction (similar to GET /posts/<id>)
    can_interact = False
    if post.user_id == requesting_user.id:
        can_interact = True
    elif post.privacy_level == PRIVACY_PUBLIC:
        can_interact = True
    elif post.privacy_level == PRIVACY_FOLLOWERS:
        if post.author and requesting_user.is_following(post.author):
            can_interact = True
    elif post.privacy_level == PRIVACY_CUSTOM_LIST:
        if post.custom_friend_list and requesting_user in post.custom_friend_list.members.all():
            can_interact = True
    # PRIVACY_PRIVATE posts are only interactable by the author, covered by the first check.

    if not can_interact:
        return jsonify(error="Forbidden", message="You do not have permission to interact with this post."), 403

    existing_like = Like.query.filter_by(user_id=requesting_user.id, post_id=post.id).first()
    action_taken = None

    if existing_like:
        db.session.delete(existing_like)
        action_taken = "unliked"
    else:
        new_like = Like(user_id=requesting_user.id, post_id=post.id)
        db.session.add(new_like)
        action_taken = "liked"

    db.session.commit()

    return jsonify({
        "status": action_taken,
        "like_count": post.like_count() # Assumes like_count() method on Post model correctly reflects changes
    }), 200

# Helper to serialize comment data
def serialize_comment_data(comment):
    return {
        "id": comment.id,
        "body": comment.body,
        "timestamp": comment.timestamp.isoformat() + 'Z', # ISO 8601 format
        "author_id": comment.user_id,
        "post_id": comment.post_id
        # Add other fields as needed
    }

@api_bp.route('/posts/<int:post_id>/comments', methods=['POST'])
@token_required
def create_comment_on_post(post_id):
    """
    Create a new comment on a post.
    Requires Bearer token authentication. User must have permission to view/interact with the post.
    ---
    tags:
      - Interactions
      - Posts
    security:
      - BearerAuth: []
    parameters:
      - name: post_id
        in: path
        type: integer
        required: true
        description: The ID of the post to comment on.
      - name: body
        in: body
        required: true
        description: The content of the comment.
        schema:
          type: object
          required:
            - body
          properties:
            body:
              type: string
              description: The text content of the comment.
    produces:
      - application/json
    responses:
      201:
        description: Comment created successfully. Returns the new comment data.
        schema:
          # Assuming serialize_comment_data structure
          type: object
          properties:
            id: { type: integer }
            body: { type: string }
            timestamp: { type: string, format: date-time }
            author_id: { type: integer }
            post_id: { type: integer }
      400:
        description: Invalid request (e.g., missing body).
      401:
        description: Unauthorized (token missing or invalid).
      403:
        description: Forbidden (user cannot interact with the post).
      404:
        description: Post not found or not published.
    """
    post = Post.query.get_or_404(post_id)
    requesting_user = g.current_user

    # Check if post is published, unless requester is the author
    if not post.is_published and post.user_id != requesting_user.id:
        return jsonify(error="NotFound", message="Post not found or not published."), 404

    # Privacy checks for interaction
    can_interact = False
    if post.user_id == requesting_user.id:
        can_interact = True
    elif post.privacy_level == PRIVACY_PUBLIC:
        can_interact = True
    elif post.privacy_level == PRIVACY_FOLLOWERS:
        if post.author and requesting_user.is_following(post.author):
            can_interact = True
    elif post.privacy_level == PRIVACY_CUSTOM_LIST:
        if post.custom_friend_list and requesting_user in post.custom_friend_list.members.all():
            can_interact = True

    if not can_interact:
        return jsonify(error="Forbidden", message="You do not have permission to comment on this post."), 403

    data = request.get_json()
    if not data:
        return jsonify(error="InvalidRequest", message="No input data provided or not valid JSON."), 400

    body = data.get('body')
    if not body or not body.strip():
        return jsonify(error="ValidationError", message="Comment body cannot be empty."), 400
    if len(body) > 2000: # Max length for comment body, e.g., 2000 characters
        return jsonify(error="ValidationError", message="Comment body exceeds maximum length of 2000 characters."), 400

    new_comment = Comment(
        body=body,
        user_id=requesting_user.id,
        author=requesting_user, # Set relationship
        post_id=post.id,
        commented_post=post # Set relationship
    )
    db.session.add(new_comment)
    db.session.commit() # Commit to get new_comment.id for mention processing

    # Process mentions in the comment
    # def process_mentions(text_body, post_id, actor_id, comment_id=None, db_session=None):
    process_mentions(text_body=new_comment.body, post_id=post.id, actor_id=requesting_user.id, comment_id=new_comment.id, db_session=db.session)
    db.session.commit() # Commit again if mentions created new DB objects or modified session

    return jsonify(serialize_comment_data(new_comment)), 201

# @api_bp.route('/me', methods=['GET'])
# @token_required # Decorator to be created
# def me():
#     from flask import g
#     # Assuming current_user is populated by @token_required
#     return jsonify({"username": g.current_user.username, "app": g.current_application.name})
