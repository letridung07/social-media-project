from app import db
from flask_login import UserMixin
from passlib.hash import sha256_crypt
from datetime import datetime, timezone

# Define the association table for followers
followers = db.Table('followers',
    db.Column('follower_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('followed_id', db.Integer, db.ForeignKey('user.id'), primary_key=True)
)

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    email = db.Column(db.String(120), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    bio = db.Column(db.String(250), nullable=True)
    profile_picture_url = db.Column(db.String(200), nullable=True, default='default_profile_pic.png')

    # Relationship to Post
    posts = db.relationship('Post', backref='author', lazy='dynamic')

    # 'followed' is the list of users this user is following.
    # 'followers' is the list of users who are following this user.
    followed = db.relationship(
        'User', secondary=followers,
        primaryjoin=(followers.c.follower_id == id), # Condition for whom this user is following
        secondaryjoin=(followers.c.followed_id == id), # Condition for whom is following this user
        backref=db.backref('followers', lazy='dynamic'), # How to access users following this one
        lazy='dynamic'
    )

    def __repr__(self):
        return f'<User {self.username}>'

    def set_password(self, password):
        self.password_hash = sha256_crypt.hash(password)

    def check_password(self, password):
        return sha256_crypt.verify(password, self.password_hash)

    # Helper methods for follow mechanism
    def follow(self, user):
        if not self.is_following(user):
            self.followed.append(user)

    def unfollow(self, user):
        if self.is_following(user):
            self.followed.remove(user)

    def is_following(self, user):
        # Ensure user.id is not None for new, uncommitted users if that's a possibility
        if user.id is None:
            return False
        return self.followed.filter(
            followers.c.followed_id == user.id).count() > 0

    # Method to get posts from followed users (for the feed)
    def followed_posts(self):
        followed_posts_query = Post.query.join(
            followers, (followers.c.followed_id == Post.user_id)).filter(
                followers.c.follower_id == self.id)
        own_posts_query = Post.query.filter_by(user_id=self.id)
        return followed_posts_query.union(own_posts_query).order_by(Post.timestamp.desc())

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False)
    # Use lambda for default to ensure it's called at insertion time
    timestamp = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f'<Post {self.body[:50]}...>'
