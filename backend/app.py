import logging
from flask import Flask
from flask_cors import CORS
from database import init_db
from api.routes import api
from config import Config


def create_app():
    app = Flask(__name__)
    logging.basicConfig(
        level=logging.DEBUG if Config.DEBUG else logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s'
    )

    app.config['SECRET_KEY'] = Config.SECRET_KEY
    app.config['MAX_CONTENT_LENGTH'] = Config.MAX_FILE_SIZE_MB * 1024 * 1024

    # FIX: was CORS(app, origins="*") unconditionally, meaning any website could
    # call this API from a user's browser. Wide open is fine for local dev, but
    # it should not be the production default.
    CORS(app, origins=Config.CORS_ORIGINS)

    init_db()
    app.register_blueprint(api, url_prefix='/api')

    @app.errorhandler(413)
    def too_large(_):
        # FIX: exceeding MAX_CONTENT_LENGTH returned Flask's HTML error page to
        # a JSON client, which then failed to parse the response.
        return {'error': f'File exceeds {Config.MAX_FILE_SIZE_MB}MB limit'}, 413

    @app.route('/health')
    def health():
        return {'status': 'ok', 'app': 'MindVault'}

    return app


if __name__ == '__main__':
    app = create_app()
    # FIX: printed port 5000 while actually binding 8080.
    print(f"MindVault backend starting on http://localhost:{Config.PORT}")
    app.run(debug=Config.DEBUG, port=Config.PORT, use_reloader=False)
