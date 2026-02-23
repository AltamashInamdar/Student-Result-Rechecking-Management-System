from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from wtforms import StringField, PasswordField, SubmitField, SelectField
from wtforms.validators import DataRequired
import os
import pandas as pd
from datetime import datetime

# Flask App Initialization
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = "mysql://root:Password@localhost/Tablename"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['SESSION_PROTECTION'] = "basic"

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Models
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(10), nullable=False)

class Student(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    roll_number = db.Column(db.String(50), unique=True, nullable=False)
    math = db.Column(db.Integer, default=0)
    science = db.Column(db.Integer, default=0)
    english = db.Column(db.Integer, default=0)
    total_marks = db.Column(db.Integer, default=0)
    percentage = db.Column(db.Float, default=0.0)

class RecheckingRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    subject = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='Pending')  
    request_date = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship('Student', backref=db.backref('rechecking_requests', lazy=True))

# Flask WTForms
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    role = SelectField('Role', choices=[('teacher', 'Teacher'), ('student', 'Student')])
    submit = SubmitField('Register')

class UploadForm(FlaskForm):
    math_file = SubmitField('Upload Math File')
    science_file = SubmitField('Upload Science File')
    english_file = SubmitField('Upload English File')

# User Loader
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))  # Yeh line properly indented honi chahiye

# Routes
@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/teacher_dashboard', methods=['GET', 'POST'])
@login_required
def teacher_dashboard():
    
    if current_user.role != 'teacher':
        return redirect(url_for('login'))
    
    form = UploadForm()
    rechecking_requests = db.session.query(
        RecheckingRequest.id,
        RecheckingRequest.subject,
        RecheckingRequest.status,
        RecheckingRequest.request_date,
        Student.name,
        Student.roll_number
    ).join(Student).all()

    subject_mapping = {
        'math_file': 'math',
        'science_file': 'science',
        'english_file': 'english'
    }

    for field_name, subject in subject_mapping.items():
        if getattr(form, field_name).data:
            file = request.files.get(field_name)
            if file:
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                file.save(file_path)

                try:
                    df = pd.read_excel(file_path)

                    expected_columns = {'s_name', 'sr_number', subject}
                    if not expected_columns.issubset(set(df.columns)):
                        flash(f"Excel columns must be: 's_name', 'sr_number', '{subject}'", "danger")
                        return render_template('teacher_dashboard.html', form=form, rechecking_requests=rechecking_requests)

                    for _, row in df.iterrows():
                        student = Student.query.filter_by(roll_number=row['sr_number']).first()

                        if student:
                            setattr(student, subject, row[subject])
                        else:
                            student = Student(
                                name=row['s_name'],
                                roll_number=row['sr_number'],
                                **{subject: row[subject]}
                            )
                            db.session.add(student)

                        # Calculate total marks and percentage
                        student.total_marks = (student.math or 0) + (student.science or 0) + (student.english or 0)
                        student.percentage = (student.total_marks / 300) * 100

                    db.session.commit()
                    flash(f'{student.capitalize()} file uploaded and data saved!', 'success')
                except Exception as e:
                    db.session.rollback()
                    flash(f"Error processing {subject} file: {str(e)}", "danger")
                    
                    
        students = Student.query.all()    #student marks show in the teacher dashboard
    return render_template('teacher_dashboard.html', form=form, rechecking_requests=rechecking_requests , students=students )


@app.route('/student_dashboard')
@login_required
def student_dashboard():
    if current_user.role != 'student':
        return redirect(url_for('login'))

    student = Student.query.filter_by(name=current_user.username).first()

    if not student:
        flash("Student data not found!", "danger")
        return redirect(url_for('login'))

    rechecking_requests = RecheckingRequest.query.filter_by(student_id=student.id).all()

    return render_template('student_dashboard.html', student=student, rechecking_requests=rechecking_requests)

@app.route('/submit_rechecking', methods=['POST'])
@login_required
def submit_rechecking():
    if current_user.role != 'student':
        flash("Unauthorized access!", "danger")
        return redirect(url_for('student_dashboard'))

    subject = request.form.get('subject')
    student = Student.query.filter_by(name=current_user.username).first()

    if not student:
        flash("Student record not found.", "danger")
        return redirect(url_for('student_dashboard'))

    new_request = RecheckingRequest(student_id=student.id, subject=subject)
    db.session.add(new_request)
    db.session.commit()

    flash("Rechecking request submitted successfully!", "success")
    return redirect(url_for('student_dashboard'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        username = form.username.data
        password = generate_password_hash(form.password.data)
        role = form.role.data

        if User.query.filter_by(username=username).first():
            flash("Username already exists. Choose another one.", "danger")
        else:
            user = User(username=username, password=password, role=role)
            db.session.add(user)
            db.session.commit()
            flash("Registration successful! You can now log in.", "success")
            return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password, form.password.data):
            login_user(user)
            return redirect(url_for('teacher_dashboard' if user.role == 'teacher' else 'student_dashboard'))
        flash('Invalid username or password', 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Run the app
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
