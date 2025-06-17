from app import create_app, db, socketio
# from app.core.models import User, Post # Assuming you have these models

app = create_app()

@app.shell_context_processor
def make_shell_context():
    return {'db': db} # 'User': User, 'Post': Post}

if __name__ == '__main__':
    socketio.run(app, debug=True)
