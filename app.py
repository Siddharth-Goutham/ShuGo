import os
import razorpay
from dotenv import load_dotenv
from flask import Flask, render_template, redirect, url_for, session, request, flash
from flask_bcrypt import Bcrypt
from flask_bootstrap import Bootstrap5
from flask_login import UserMixin, login_user, LoginManager, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, FloatField, SelectField, BooleanField, PasswordField
from wtforms.validators import DataRequired, URL, Email, Length, ValidationError

load_dotenv()

app = Flask(__name__)
# Securely fallback locally, but reads from Render Environment panel in production
app.secret_key = os.getenv("SECRET_KEY", "dev_fallback_string_key_12345")
bootstrap = Bootstrap5(app)

# --- DYNAMIC DATABASE ROUTING (FIXED FOR RENDER & SQLALCHEMY 2.x) ---
# Check for DATABASE_URL to match your Render Environment dashboard key precisely
db_url = os.environ.get("DATABASE_URL")

if db_url:
    # Auto-correct legacy 'postgres://' schemes to match SQLAlchemy strict requirements
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
else:
    # Local clean fallback file path format
    db_url = "sqlite:///products.db"

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
# --------------------------------------------------------------------

db = SQLAlchemy()
db.init_app(app)
bcrypt = Bcrypt(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

razorpay_client = razorpay.Client(
    auth=(os.getenv("RAZORPAY_KEY_ID"), os.getenv("RAZORPAY_KEY_SECRET"))
)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ==========================================
# DATABASE MODELS
# ==========================================

class ProductInfo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(100), nullable=False)
    img_url = db.Column(db.String(100), nullable=False)
    size = db.Column(db.String(5), nullable=False)
    featured = db.Column(db.Boolean, default=False)
    category = db.Column(db.String(20), nullable=False)
    price = db.Column(db.Float, nullable=False)


class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cart_id = db.Column(db.Integer, db.ForeignKey('cart.id'), nullable=False)
    product_name = db.Column(db.String, nullable=False)
    product_id = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    price = db.Column(db.Float, nullable=False)


class Cart(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=True)


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(20), nullable=False)
    last_name = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(50), nullable=False, unique=True)
    password = db.Column(db.String(250), nullable=False)


# ==========================================
# FORMS
# ==========================================

class AddProducts(FlaskForm):
    product_name = StringField("Product Name", validators=[DataRequired()])
    img_url = StringField("Image URL", validators=[DataRequired(), URL()])
    size = StringField("Size", validators=[DataRequired()])
    category = SelectField(
        "Choose category",
        choices=[
            ("Clothing", "Clothing"),
            ("Footwear", "Footwear"),
            ("Accessories", "Accessories")
        ]
    )
    featured = BooleanField("Featured? ")
    price = FloatField("Amount", validators=[DataRequired()])
    submit = SubmitField("ADD")


class RegisterForm(FlaskForm):
    fname = StringField('First Name', validators=[DataRequired(message="First name is required.")],
                        render_kw={"placeholder": "Varun"})
    lname = StringField('Last Name', validators=[DataRequired(message="Last name is required.")],
                        render_kw={"placeholder": "Singhania"})
    email = StringField('Email Address', validators=[DataRequired(message="Email is required."),
                                                     Email(message="Please enter a valid email.")],
                        render_kw={"placeholder": "name@example.com"})
    password = PasswordField('Password', validators=[DataRequired(message="Password is required."), Length(min=8,
                                                                                                           message="Password must be at least 8 characters long.")],
                             render_kw={"placeholder": "Min. 8 characters"})
    terms = BooleanField('Terms', validators=[DataRequired(message="You must accept the terms to continue.")])
    submit = SubmitField('Join the Drop')

    def validate_email(self, email):
        existing_user = User.query.filter_by(email=email.data).first()
        if existing_user:
            raise ValidationError("This user already exists!")


class LoginForm(FlaskForm):
    email = StringField('Email Address', validators=[DataRequired(), Email()],
                        render_kw={"placeholder": "you@example.com"})
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)],
                             render_kw={"placeholder": "••••••••"})
    submit = SubmitField('Sign In')


# ==========================================
# ROUTES
# ==========================================

@app.route("/")
def home():
    products = ProductInfo.query.all()
    return render_template("index.html", products=products)


@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        new_user = User(first_name=form.fname.data, last_name=form.lname.data, email=form.email.data,
                        password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash('Account created successfully! You can now log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password,
