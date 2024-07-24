from app import app
import init_db

if __name__ == "__main__":
    # Initialize the database
    init_db.init_db()

    # Start the Flask application
    app.run(host='0.0.0.0', port=8080)
