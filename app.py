from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from ultralytics import YOLO
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import os
import math

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ma_cle_secrete_a_modifier'

# ✅ Utiliser SQLite au lieu de SQL Server
basedir = os.path.abspath(os.path.dirname(__file__))
db_file_path = os.path.join(basedir, 'render_db.sqlite3')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_file_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = os.path.join('static', 'uploads')
RESULT_FOLDER = os.path.join('static', 'results')
TOP_FOLDER = os.path.join(RESULT_FOLDER, 'face_top')
BOTTOM_FOLDER = os.path.join(RESULT_FOLDER, 'face_bottom')
MODELS_FOLDER = os.path.join('models')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TOP_FOLDER, exist_ok=True)
os.makedirs(BOTTOM_FOLDER, exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    statut = db.Column(db.String(128), nullable=False)

class PCBA(db.Model):
    __tablename__ = 'pcba'
    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(100), nullable=False)
    rf_value = db.Column(db.String(100), nullable=True)
    orf_value = db.Column(db.String(100), nullable=True)
    image_path = db.Column(db.String(255), nullable=False)
    result_image_path = db.Column(db.String(255), nullable=False)
    face = db.Column(db.String(10), nullable=False)
    defaillante = db.Column(db.Boolean, nullable=False)
    defauts = db.Column(db.String(255), nullable=True)
    date_test = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('tests', lazy=True))

class RF_ORF(db.Model):
    __tablename__ = 'rf_orf'
    id = db.Column(db.Integer, primary_key=True)
    rf_value = db.Column(db.String(100), nullable=False)
    orf_value = db.Column(db.String(100), nullable=False)
    reference = db.Column(db.String(100), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login')
def login():
    return "<h2>Page de connexion &agrave; venir...</h2>"

@app.route('/admin/db-status')
@login_required
def db_status():
    if current_user.statut != 'admin':
        flash("Acc&egrave;s refus&eacute;.")
        return redirect(url_for('index'))

    user_count = User.query.count()
    test_count = PCBA.query.count()
    rf_orf_count = RF_ORF.query.count()

    return render_template('db_status.html', user_count=user_count, test_count=test_count, rf_orf_count=rf_orf_count)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
