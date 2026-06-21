from flask import Flask
from flask_cors import CORS
from database import init_db
from api.routes import api
from config import Config

def create_app():
    app = Flask(__name__)
    print("Registering blueprint...")
    app.config['SECRET_KEY'] = Config.SECRET_KEY
    app.config['MAX_CONTENT_LENGTH'] = Config.MAX_FILE_SIZE_MB * 1024 * 1024

    CORS(app, origins="*")

    init_db()

    app.register_blueprint(api, url_prefix='/api')

    @app.route('/health')
    def health():
        return {'status': 'ok', 'app': 'MindVault'}

    return app

if __name__ == '__main__':
    app = create_app()
    print("Routes:", list(app.url_map.iter_rules()))
    print("🧠 MindVault backend starting on http://localhost:5000")
    app.run(debug=Config.DEBUG, port=8080, use_reloader=False)