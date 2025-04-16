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
app.config['SQLALCHEMY_DATABASE_URI'] = 'mssql+pyodbc://DESKTOP-OEKM2KN\\SQLEXPRESS01/pcba_db?trusted_connection=yes&driver=ODBC+Driver+17+for+SQL+Server'
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

# --------------------------- MODELS ---------------------------

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

# --------------------------- AUTH ---------------------------

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        statut = request.form['statut']

        if User.query.filter_by(username=username).first():
            flash("Nom d'utilisateur déjà utilisé.")
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)
        new_user = User(username=username, password_hash=hashed_password, statut=statut)
        db.session.add(new_user)
        db.session.commit()
        flash("Inscription réussie.")
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if not user or not check_password_hash(user.password_hash, request.form['password']):
            flash("Identifiants incorrects.")
            return redirect(url_for('login'))
        login_user(user)
        return redirect(url_for('inspect'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Déconnecté avec succès.")
    return redirect(url_for('login'))

# --------------------------- INSPECTION ---------------------------

def rotate_point(x, y, cx, cy, angle_deg):
    angle_rad = math.radians(angle_deg)
    cos_val = math.cos(angle_rad)
    sin_val = math.sin(angle_rad)
    dx = x - cx
    dy = y - cy
    return (cx + dx * cos_val - dy * sin_val, cy + dx * sin_val + dy * cos_val)

def get_obb_corners(xc, yc, w, h, angle_deg):
    half_w, half_h = w / 2, h / 2
    corners = [
        (xc - half_w, yc - half_h),
        (xc + half_w, yc - half_h),
        (xc + half_w, yc + half_h),
        (xc - half_w, yc + half_h),
    ]
    return [rotate_point(x, y, xc, yc, angle_deg) for (x, y) in corners]

def detect_defauts(image_path: str, output_path: str, face: str):
    model_path = os.path.join(MODELS_FOLDER, 'model_top.pt') if face.lower() == 'top' else os.path.join(MODELS_FOLDER, 'model_bot.pt')
    model = YOLO(model_path)
    results = model(image_path)
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("arial.ttf", size=28) if os.path.exists("arial.ttf") else ImageFont.load_default()

    CLASS_COLORS = {
        0: (255, 0, 0), 1: (0, 255, 0), 2: (0, 0, 255),
        3: (255, 255, 0), 4: (0, 255, 255), 5: (255, 0, 255),
        6: (128, 0, 128), 7: (255, 165, 0), 8: (255, 192, 203), 9: (0, 0, 0),
    }

    liste_defauts_colores = []
    defaillante = False

    if results and hasattr(results[0], 'obb') and results[0].obb is not None:
        obb = results[0].obb
        if hasattr(obb, 'data') and obb.data is not None and obb.data.size(0) > 0:
            defaillante = True
            for row in obb.data:
                xc, yc, w, h, angle, conf, cls = row.tolist()
                class_id = int(cls)
                class_name = results[0].names.get(class_id, f"Classe {class_id}")
                color = CLASS_COLORS.get(class_id, (255, 0, 0))
                corners = get_obb_corners(xc, yc, w, h, angle)
                draw.line(corners + [corners[0]], fill=color, width=5)
                liste_defauts_colores.append({
                    "nom": class_name,
                    "confiance": f"{conf:.2%}",
                    "couleur": '#%02x%02x%02x' % color
                })

    image.save(output_path)
    return defaillante, liste_defauts_colores

@app.route('/inspect', methods=['GET', 'POST'])
@login_required
def inspect():
    top_result = bottom_result = ''
    top_defauts = bottom_defauts = ''
    reference = rf_value = orf_value = ''
    liste_defauts_colores = []
    image_inspectee = False

    if request.method == 'POST':
        reference = request.form['reference']
        rf_value = request.form['rf_value']
        orf_value = request.form['orf_value']
        face = request.form['face'].capitalize()
        image = request.files['image']

        combinaison_valide = RF_ORF.query.filter_by(rf_value=rf_value, orf_value=orf_value, reference=reference).first()
        if not combinaison_valide:
            flash("La combinaison RF/ORF/REFERENCE est invalide.")
            return redirect(url_for('inspect'))

        filename = secure_filename(image.filename)
        image_path = os.path.join(UPLOAD_FOLDER, filename)
        image.save(image_path)

        result_filename = f"result_{filename}"
        result_subfolder = 'face_top' if face == 'Top' else 'face_bottom'
        result_path = os.path.join(RESULT_FOLDER, result_subfolder, result_filename)
        relative_result_path = f"results/{result_subfolder}/{result_filename}"

        defaillante, liste_defauts_colores = detect_defauts(image_path, result_path, face)

        test = PCBA(
            reference=reference,
            rf_value=rf_value,
            orf_value=orf_value,
            face=face,
            image_path=image_path,
            result_image_path=result_path,
            defaillante=defaillante,
            defauts='Aucun' if not defaillante else ', '.join([d['nom'] for d in liste_defauts_colores]),
            date_test=datetime.utcnow(),
            user_id=current_user.id
        )
        db.session.add(test)
        db.session.commit()

        if face == "Top":
            top_result = relative_result_path
            top_defauts = test.defauts
        else:
            bottom_result = relative_result_path
            bottom_defauts = test.defauts

        image_inspectee = True

    return render_template(
        'inspect.html',
        user=current_user,
        reference=reference,
        rf_value=rf_value,
        orf_value=orf_value,
        top_result=top_result,
        top_defauts=top_defauts,
        bottom_result=bottom_result,
        bottom_defauts=bottom_defauts,
        liste_defauts_colores=liste_defauts_colores,
        image_inspectee=image_inspectee,
        face=face if image_inspectee else None
    )

# --------------------------- RF_ORF Management ---------------------------

@app.route('/rf_orf', methods=['GET', 'POST'])
@login_required
def manage_rf_orf():
    if request.method == 'POST':
        rf_value = request.form['rf_value']
        orf_value = request.form['orf_value']
        reference = request.form['reference']

        existing = RF_ORF.query.filter_by(rf_value=rf_value, orf_value=orf_value, reference=reference).first()
        if existing:
            flash("Cette combinaison existe déjà.")
        else:
            new_entry = RF_ORF(rf_value=rf_value, orf_value=orf_value, reference=reference, user_id=current_user.id)
            db.session.add(new_entry)
            db.session.commit()
            flash("Combinaison ajoutée avec succès.")
        return redirect(url_for('manage_rf_orf'))

    rf_orf_list = RF_ORF.query.all()
    return render_template('rf_orf.html', rf_orf_list=rf_orf_list, user=current_user)

# --------------------------- History ---------------------------

@app.route('/history')
@login_required
def history():
    tests = PCBA.query.all() if current_user.statut == 'admin' else PCBA.query.filter_by(user_id=current_user.id).all()

    rf_orf_entries = RF_ORF.query.all()
    rf_orf_map = {
        entry.reference: {
            'rf': entry.rf_value,
            'orf': entry.orf_value
        } for entry in rf_orf_entries
    }

    return render_template('history.html', tests=tests, user=current_user, rf_orf_map=rf_orf_map)

# --------------------------- Run App ---------------------------

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)