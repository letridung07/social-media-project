from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField, TextAreaField, FieldList, FormField, HiddenField, SelectField
from wtforms.fields import FileField # Correct import for FileField
from flask_wtf.file import FileAllowed # For validation
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError, Optional, InputRequired
from app.models import User

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=2, max=20)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Sign Up')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('That username is taken. Please choose a different one.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('That email is already in use. Please choose a different one.')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Login')

class EditProfileForm(FlaskForm):
    bio = TextAreaField('Bio', validators=[Optional(), Length(min=0, max=250)])
    profile_picture = FileField('Update Profile Picture', validators=[Optional(), FileAllowed(['jpg', 'png', 'jpeg'], 'Images only!')])
    theme = SelectField('Site Theme', choices=[
        ('default', 'Default Theme'),
        ('dark', 'Dark Theme'),
        ('blue', 'Blue Lagoon Theme')
    ], default='default', validators=[InputRequired()])
    submit = SubmitField('Submit Changes')

class PostForm(FlaskForm):
    body = TextAreaField('What\'s on your mind?', validators=[DataRequired(), Length(min=1, max=500)])
    image_file = FileField('Upload Image (Optional)', validators=[
        FileAllowed(['jpg', 'png', 'jpeg', 'gif'], 'Images only!')
    ]) # New field
    video_file = FileField('Upload Video (Optional)', validators=[FileAllowed(['mp4', 'mov', 'avi', 'mkv'], 'Videos only!')])
    alt_text = TextAreaField(
        'Alternative Text (for accessibility)',
        description='Describe your image or video for users who cannot see it. This is optional but highly recommended.',
        validators=[Length(max=500), Optional()] # Added Optional() validator
    )
    submit = SubmitField('Post')

class CommentForm(FlaskForm):
    body = TextAreaField('Your Comment', validators=[DataRequired(), Length(min=1, max=280)]) # Max length can be adjusted
    submit = SubmitField('Add Comment')

class ForgotPasswordForm(FlaskForm):
    email = StringField('Email',
                        validators=[DataRequired(), Email()])
    submit = SubmitField('Request Password Reset')

class ResetPasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm New Password',
                                     validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Reset Password')

class SearchForm(FlaskForm):
    query = StringField('Search', validators=[DataRequired()])
    submit = SubmitField('Go')

class GroupCreationForm(FlaskForm):
    name = StringField('Group Name', validators=[DataRequired(), Length(min=2, max=100)])
    description = TextAreaField('Description', validators=[Optional(), Length(max=255)])
    image_file = FileField('Group Image (Optional)', validators=[
        Optional(),
        FileAllowed(['jpg', 'png', 'jpeg', 'gif'], 'Images only!')
    ])
    submit = SubmitField('Create Group')

class StoryForm(FlaskForm):
    media_file = FileField('Upload Image or Video', validators=[
        DataRequired(),
        FileAllowed(['jpg', 'png', 'jpeg', 'gif', 'mp4', 'mov', 'avi'], 'Image or video files only (jpg, png, jpeg, gif, mp4, mov, avi)!')
    ])
    caption = TextAreaField('Caption (Optional)', validators=[Optional(), Length(max=280)])
    submit = SubmitField('Post Story')

# Auxiliary form for individual poll options
class PollOptionEntryForm(FlaskForm):
    # No CSRF protection needed for subforms handled by FieldList by default
    # if it were a standalone form rendered via its own <form> tag, it would need it.
    # For WTForms 3.x, CSRF is generally handled by the parent FlaskForm.
    option_text = StringField('Option Text', validators=[DataRequired(), Length(min=1, max=255)])

class PollForm(FlaskForm):
    question = TextAreaField('Poll Question', validators=[DataRequired(), Length(min=5, max=500)])
    # Using min_entries=2 to ensure at least two fields are rendered by default in the template.
    # The actual data validation for >=2 options with text is handled by validate_options.
    options = FieldList(FormField(PollOptionEntryForm), min_entries=2, max_entries=10)
    post_id = HiddenField('Post ID', validators=[Optional()])
    group_id = HiddenField('Group ID', validators=[Optional()])
    submit = SubmitField('Create Poll')

    def validate_options(self, field):
        # field here refers to the 'options' FieldList itself.
        # self.options.entries gives access to the list of FormField entries.

        # Count how many options have actual text data
        valid_options_submitted = 0
        option_texts_seen = []

        for entry_field in self.options.entries:
            # entry_field is an UnboundField instance wrapping PollOptionEntryForm
            # entry_field.form gives access to the actual PollOptionEntryForm instance
            option_text_data = entry_field.form.option_text.data
            if option_text_data and option_text_data.strip():
                valid_options_submitted += 1
                option_texts_seen.append(option_text_data.strip().lower())

        if valid_options_submitted < 2:
            # Add error to the 'options' field itself, or raise general ValidationError
            # Raising ValidationError is more direct for custom validators.
            raise ValidationError('Please provide at least two valid options for the poll.')

        if len(option_texts_seen) != len(set(option_texts_seen)):
            raise ValidationError('Poll options must be unique (case-insensitive).')

from wtforms.fields import DateTimeLocalField

class EventForm(FlaskForm):
    name = StringField('Event Name', validators=[DataRequired(), Length(min=3, max=100)])
    description = TextAreaField('Description', validators=[Optional(), Length(max=500)])
    start_datetime = DateTimeLocalField('Start Time', format='%Y-%m-%dT%H:%M', validators=[DataRequired()])
    end_datetime = DateTimeLocalField('End Time', format='%Y-%m-%dT%H:%M', validators=[DataRequired()])
    location = StringField('Location', validators=[Optional(), Length(max=255)])
    submit = SubmitField('Create Event')

    def validate_end_datetime(self, field):
        if self.start_datetime.data and field.data:
            if field.data <= self.start_datetime.data:
                raise ValidationError('End time must be after start time.')

class StreamSetupForm(FlaskForm):
    title = StringField('Stream Title', validators=[Optional(), Length(max=150)])
    description = TextAreaField('Stream Description', validators=[Optional()])
    go_live = BooleanField('Go Live Now / Update Live Status')
    enable_recording = BooleanField('Enable Recording')
    submit = SubmitField('Update Stream Settings')
