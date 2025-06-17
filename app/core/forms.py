from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField, TextAreaField, FieldList, FormField, HiddenField, SelectField, DecimalField
from wtforms.fields import FileField, MultipleFileField, DateTimeField # Added DateTimeField
from flask_babel import lazy_gettext as _l
from flask_wtf.file import FileAllowed # For validation
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError, Optional, InputRequired, NumberRange, URL
from app.core.models import User, PRIVACY_PUBLIC, PRIVACY_FOLLOWERS, PRIVACY_CUSTOM_LIST, PRIVACY_PRIVATE
from datetime import datetime # Added datetime

PRIVACY_CHOICES = [
    (PRIVACY_PUBLIC, _l('Public (visible to everyone)')),
    (PRIVACY_FOLLOWERS, _l('Followers Only (visible to your followers)')),
    (PRIVACY_CUSTOM_LIST, _l('Custom List (visible to a specific list of friends)')),
    (PRIVACY_PRIVATE, _l('Private (visible only to you)'))
]

PROFILE_VISIBILITY_CHOICES = [
    (PRIVACY_PUBLIC, _l('Public Profile')),
    (PRIVACY_FOLLOWERS, _l('Followers Only Profile')),
    (PRIVACY_PRIVATE, _l('Private Profile (Only you)'))
]

DEFAULT_CONTENT_PRIVACY_CHOICES = [
    (PRIVACY_PUBLIC, _l('Public')),
    (PRIVACY_FOLLOWERS, _l('Followers Only')),
    (PRIVACY_PRIVATE, _l('Private'))
]

class RegistrationForm(FlaskForm):
    username = StringField(_l('Username'), validators=[DataRequired(), Length(min=2, max=20)])
    email = StringField(_l('Email'), validators=[DataRequired(), Email()])
    password = PasswordField(_l('Password'), validators=[DataRequired()])
    confirm_password = PasswordField(_l('Confirm Password'), validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField(_l('Sign Up'))

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError(_l('That username is taken. Please choose a different one.'))

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError(_l('That email is already in use. Please choose a different one.'))

class LoginForm(FlaskForm):
    email = StringField(_l('Email'), validators=[DataRequired(), Email()])
    password = PasswordField(_l('Password'), validators=[DataRequired()])
    remember_me = BooleanField(_l('Remember Me'))
    submit = SubmitField(_l('Login'))

class EditProfileForm(FlaskForm):
    bio = TextAreaField(_l('Bio'), validators=[Optional(), Length(min=0, max=250)])
    profile_picture = FileField(_l('Update Profile Picture'), validators=[Optional(), FileAllowed(['jpg', 'png', 'jpeg'], _l('Images only!'))])
    theme = SelectField(_l('Site Theme'), choices=[
        ('default', _l('Default Theme')),
        ('dark', _l('Dark Theme')),
        ('blue', _l('Blue Lagoon Theme'))
    ], default='default', validators=[InputRequired()])

    profile_visibility = SelectField(_l('Profile Visibility'), choices=PROFILE_VISIBILITY_CHOICES, default=PRIVACY_PUBLIC, validators=[DataRequired()])
    default_post_privacy = SelectField(_l('Default Post Visibility'), choices=DEFAULT_CONTENT_PRIVACY_CHOICES, default=PRIVACY_PUBLIC, validators=[DataRequired()])
    default_story_privacy = SelectField(_l('Default Story Visibility'), choices=DEFAULT_CONTENT_PRIVACY_CHOICES, default=PRIVACY_PUBLIC, validators=[DataRequired()])

    submit = SubmitField(_l('Submit Changes'))

class PostForm(FlaskForm):
    body = TextAreaField(_l('What\'s on your mind?'), validators=[DataRequired(), Length(min=1, max=500)])
    media_files = MultipleFileField(_l('Upload Images or Videos (Select multiple files)'), validators=[
        Optional(),
        FileAllowed(['jpg', 'png', 'jpeg', 'gif', 'mp4', 'mov', 'avi', 'mkv'], _l('Images or videos only!'))
    ])
    privacy_level = SelectField(_l('Visibility'), choices=PRIVACY_CHOICES, default=PRIVACY_PUBLIC, validators=[DataRequired()])
    custom_friend_list_id = SelectField(_l('Select Friend List'), choices=[], coerce=int, validators=[Optional()])
    schedule_time = DateTimeField(_l('Schedule For (optional)'), format='%Y-%m-%d %H:%M', validators=[Optional()])
    submit = SubmitField(_l('Post'))

    def validate_schedule_time(self, field):
        if field.data:
            if field.data < datetime.now():
                raise ValidationError(_l('Scheduled time must be in the future.'))

class CommentForm(FlaskForm):
    body = TextAreaField(_l('Your Comment'), validators=[DataRequired(), Length(min=1, max=280)])
    submit = SubmitField(_l('Add Comment'))

class ForgotPasswordForm(FlaskForm):
    email = StringField(_l('Email'),
                        validators=[DataRequired(), Email()])
    submit = SubmitField(_l('Request Password Reset'))

class ResetPasswordForm(FlaskForm):
    password = PasswordField(_l('New Password'), validators=[DataRequired()])
    confirm_password = PasswordField(_l('Confirm New Password'),
                                     validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField(_l('Reset Password'))

class SearchForm(FlaskForm):
    query = StringField(_l('Search'), validators=[DataRequired()])
    submit = SubmitField(_l('Go'))

class GroupCreationForm(FlaskForm):
    name = StringField(_l('Group Name'), validators=[DataRequired(), Length(min=2, max=100)])
    description = TextAreaField(_l('Description'), validators=[Optional(), Length(max=255)])
    image_file = FileField(_l('Group Image (Optional)'), validators=[
        Optional(),
        FileAllowed(['jpg', 'png', 'jpeg', 'gif'], _l('Images only!'))
    ])
    submit = SubmitField(_l('Create Group'))

class StoryForm(FlaskForm):
    media_file = FileField(_l('Upload Image or Video'), validators=[
        DataRequired(),
        FileAllowed(['jpg', 'png', 'jpeg', 'gif', 'mp4', 'mov', 'avi'], _l('Image or video files only (jpg, png, jpeg, gif, mp4, mov, avi)!'))
    ])
    caption = TextAreaField(_l('Caption (Optional)'), validators=[Optional(), Length(max=280)])
    privacy_level = SelectField(_l('Visibility'), choices=PRIVACY_CHOICES, default=PRIVACY_PUBLIC, validators=[DataRequired()])
    custom_friend_list_id = SelectField(_l('Select Friend List'), choices=[], coerce=int, validators=[Optional()])
    schedule_time = DateTimeField(_l('Schedule For (optional)'), format='%Y-%m-%d %H:%M', validators=[Optional()])
    submit = SubmitField(_l('Post Story'))

    def validate_schedule_time(self, field):
        if field.data:
            if field.data < datetime.now():
                raise ValidationError(_l('Scheduled time must be in the future.'))

class PollOptionEntryForm(FlaskForm):
    option_text = StringField(_l('Option Text'), validators=[DataRequired(), Length(min=1, max=255)])


class PollForm(FlaskForm):
    question = TextAreaField(_l('Poll Question'), validators=[DataRequired(), Length(min=5, max=500)])
    options = FieldList(FormField(PollOptionEntryForm), min_entries=2, max_entries=10)
    post_id = HiddenField(_l('Post ID'), validators=[Optional()])
    group_id = HiddenField(_l('Group ID'), validators=[Optional()])
    submit = SubmitField(_l('Create Poll'))

    def validate_options(self, field):
        valid_options_submitted = 0
        option_texts_seen = []
        for entry_field in self.options.entries:
            option_text_data = entry_field.form.option_text.data
            if option_text_data and option_text_data.strip():
                valid_options_submitted += 1
                option_texts_seen.append(option_text_data.strip().lower())
        if valid_options_submitted < 2:
            raise ValidationError(_l('Please provide at least two valid options for the poll.'))
        if len(option_texts_seen) != len(set(option_texts_seen)):
            raise ValidationError(_l('Poll options must be unique (case-insensitive).'))

class EventForm(FlaskForm):
    name = StringField(_l('Event Name'), validators=[DataRequired(), Length(min=3, max=100)])
    description = TextAreaField(_l('Description'), validators=[Optional(), Length(max=500)])
    start_datetime = DateTimeField(_l('Start Time'), format='%Y-%m-%dT%H:%M', validators=[DataRequired()])
    end_datetime = DateTimeField(_l('End Time'), format='%Y-%m-%dT%H:%M', validators=[DataRequired()])
    location = StringField(_l('Location'), validators=[Optional(), Length(max=255)])
    submit = SubmitField(_l('Create Event'))

    def validate_end_datetime(self, field):
        if self.start_datetime.data and field.data:
            if field.data <= self.start_datetime.data:
                raise ValidationError(_l('End time must be after start time.'))

class StreamSetupForm(FlaskForm):
    title = StringField(_l('Stream Title'), validators=[Optional(), Length(max=150)])
    description = TextAreaField(_l('Stream Description'), validators=[Optional()])
    go_live = BooleanField(_l('Go Live Now / Update Live Status'))
    enable_recording = BooleanField(_l('Enable Recording'))
    submit = SubmitField(_l('Update Stream Settings'))

class ArticleForm(FlaskForm):
    title = StringField(_l('Title'), validators=[DataRequired(), Length(min=3, max=150)])
    body = TextAreaField(_l('Body'), validators=[DataRequired()])
    submit = SubmitField(_l('Publish Article'))

class AudioPostForm(FlaskForm):
    title = StringField(_l('Title'), validators=[DataRequired(), Length(min=3, max=150)])
    description = TextAreaField(_l('Description'), validators=[Optional(), Length(max=500)])
    audio_file = FileField(_l('Audio File'), validators=[
        DataRequired(),
        FileAllowed(['mp3', 'wav', 'ogg', 'aac'], _l('Audio files only! (mp3, wav, ogg, aac)'))
    ])
    submit = SubmitField(_l('Upload Audio'))

class FriendListForm(FlaskForm):
    name = StringField(_l('List Name'), validators=[DataRequired(), Length(min=1, max=100)])
    submit = SubmitField(_l('Save List'))

class AddUserToFriendListForm(FlaskForm):
    username = StringField(_l('Username to Add'), validators=[DataRequired()])
    submit = SubmitField(_l('Add User'))

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if not user:
            raise ValidationError(_l('User with that username does not exist.'))

class VirtualGoodForm(FlaskForm):
    name = StringField(_l('Name'), validators=[DataRequired(), Length(min=2, max=100)])
    description = TextAreaField(_l('Description'), validators=[Optional(), Length(max=500)])
    price = DecimalField(_l('Price'), validators=[DataRequired()], places=2)
    currency = StringField(_l('Currency'), validators=[DataRequired(), Length(min=3, max=10)], default='USD')
    type = SelectField(_l('Type'), choices=[
        ('badge', _l('Badge')),
        ('emoji', _l('Emoji')),
        ('profile_frame', _l('Profile Frame')),
        ('other', _l('Other'))
    ], validators=[DataRequired()])
    image_url = StringField(_l('Image URL'), validators=[Optional(), URL(), Length(max=255)])
    is_active = BooleanField(_l('Is Active'), default=True)
    submit = SubmitField(_l('Save Virtual Good'))

class SubscriptionPlanForm(FlaskForm):
    name = StringField(_l('Plan Name'), validators=[DataRequired(), Length(min=3, max=100)])
    description = TextAreaField(_l('Description'), validators=[Optional(), Length(max=500)])
    price = DecimalField(_l('Price (e.g., 9.99)'), places=2, validators=[DataRequired(), NumberRange(min=0.01, message=_l("Price must be greater than 0."))])
    currency = StringField(_l('Currency Code (e.g., USD)'), validators=[DataRequired(), Length(min=3, max=3)])
    duration = SelectField(_l('Billing Interval'), choices=[
        ('day', _l('Daily')),
        ('week', _l('Weekly')),
        ('month', _l('Monthly')),
        ('year', _l('Yearly'))
    ], validators=[DataRequired()])
    features = TextAreaField(_l('Features (one per line)'), validators=[Optional()])
    submit = SubmitField(_l('Save Plan'))

class ApplicationRegistrationForm(FlaskForm):
    name = StringField(_l('Application Name'), validators=[DataRequired(), Length(min=3, max=100)])
    description = TextAreaField(_l('Description'), validators=[Optional(), Length(max=500)])
    redirect_uris = TextAreaField(_l('Redirect URIs (one per line)'),
                                  validators=[DataRequired()],
                                  description=_l("Enter one URI per line. These are the locations your application can redirect to after authorization."))
    submit = SubmitField(_l('Register Application'))

class ApplicationEditForm(FlaskForm):
    name = StringField(_l('Application Name'), validators=[DataRequired(), Length(min=3, max=100)])
    description = TextAreaField(_l('Description'), validators=[Optional(), Length(max=500)])
    redirect_uris = TextAreaField(_l('Redirect URIs (one per line)'),
                                  validators=[DataRequired()],
                                  description=_l("Enter one URI per line."))
    submit = SubmitField(_l('Save Changes'))

class TOTPSetupForm(FlaskForm):
    totp_code = StringField(_l('Authenticator Code'), validators=[DataRequired(), Length(min=6, max=6, message=_l("Code must be 6 digits."))])
    submit = SubmitField(_l('Verify and Enable 2FA'))

class Verify2FAForm(FlaskForm):
    code = StringField(_l('Authenticator Code or Backup Code'), validators=[DataRequired(), Length(min=6, max=16, message=_l("Enter a valid 6-digit TOTP code or a backup code."))])
    submit = SubmitField(_l('Verify'))

class Disable2FAForm(FlaskForm):
    password = PasswordField(_l('Current Password'), validators=[DataRequired()])
    totp_code = StringField(_l('Authenticator Code'), validators=[DataRequired(), Length(min=6, max=6)])
    submit = SubmitField(_l('Disable 2FA'))

class ConfirmPasswordAndTOTPForm(FlaskForm): # For actions like viewing/regenerating backup codes
    password = PasswordField(_l('Current Password'), validators=[DataRequired()])
    totp_code = StringField(_l('Authenticator Code'), validators=[DataRequired(), Length(min=6, max=6)])
    submit = SubmitField(_l('Confirm Identity'))
