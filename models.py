from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'admin', 'examiner', 'student'
    
    # Examiner & Student Profile Fields
    department = db.Column(db.String(100), nullable=True)
    contact = db.Column(db.String(50), nullable=True)
    roll_number = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(20), default='Active')  # 'Pending', 'Active', 'Deactivated'

    # Relationships
    slots = db.relationship('ExaminationSlot', backref='examiner', lazy=True)
    bookings = db.relationship('Booking', backref='student', lazy=True)

class Course(db.Model):
    __tablename__ = 'courses'
    id = db.Column(db.Integer, primary_key=True)
    course_code = db.Column(db.String(20), unique=True, nullable=False)
    course_name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='Active')

    examinations = db.relationship('Examination', backref='course', cascade="all, delete-orphan", lazy=True)

class Examination(db.Model):
    __tablename__ = 'examinations'
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    exam_name = db.Column(db.String(150), nullable=False)
    exam_type = db.Column(db.String(50), nullable=False)  # Viva, Practical, Project Demo, Assessment
    duration_mins = db.Column(db.Integer, nullable=False)
    max_marks = db.Column(db.Float, nullable=False)
    
    slot_creation_start = db.Column(db.DateTime, nullable=False)
    slot_creation_end = db.Column(db.DateTime, nullable=False)
    slot_booking_start = db.Column(db.DateTime, nullable=False)
    slot_booking_end = db.Column(db.DateTime, nullable=False)
    
    # Status: 'Draft', 'Slot Creation', 'Booking Open', 'Closed', 'Completed'
    status = db.Column(db.String(30), default='Draft')

    rubrics = db.relationship('ExaminationRubric', backref='examination', cascade="all, delete-orphan", lazy=True)
    slots = db.relationship('ExaminationSlot', backref='examination', cascade="all, delete-orphan", lazy=True)

class ExaminationRubric(db.Model):
    __tablename__ = 'examination_rubrics'
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('examinations.id'), nullable=False)
    criterion_name = db.Column(db.String(120), nullable=False)
    max_marks = db.Column(db.Float, nullable=False)
    weightage = db.Column(db.Float, nullable=True)
    description = db.Column(db.Text, nullable=True)

class ExaminationSlot(db.Model):
    __tablename__ = 'examination_slots'
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('examinations.id'), nullable=False)
    examiner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    max_capacity = db.Column(db.Integer, nullable=False)
    available_seats = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='Available')  # 'Available', 'Full', 'Cancelled', 'Completed'

    bookings = db.relationship('Booking', backref='slot', cascade="all, delete-orphan", lazy=True)

class Booking(db.Model):
    __tablename__ = 'bookings'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    slot_id = db.Column(db.Integer, db.ForeignKey('examination_slots.id'), nullable=False)
    booking_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='Booked')  # 'Booked', 'Cancelled', 'Completed'
    
    # Evaluation Summary
    total_marks_awarded = db.Column(db.Float, nullable=True)
    remarks = db.Column(db.Text, nullable=True)
    is_published = db.Column(db.Boolean, default=False)

    rubric_scores = db.relationship('EvaluationScore', backref='booking', cascade="all, delete-orphan", lazy=True)

class EvaluationScore(db.Model):
    __tablename__ = 'evaluation_scores'
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=False)
    rubric_id = db.Column(db.Integer, db.ForeignKey('examination_rubrics.id'), nullable=False)
    marks_awarded = db.Column(db.Float, nullable=False)
    
    rubric = db.relationship('ExaminationRubric')

def init_db(app):
    with app.app_context():
        db.create_all()
        # Seed pre-existing Admin superuser if not present
        admin = User.query.filter_by(role='admin').first()
        if not admin:
            default_admin = User(
                full_name='System Administrator',
                email='admin@emp.edu',
                password_hash=generate_password_hash('admin123'),
                role='admin',
                department='Examination Cell',
                status='Active'
            )
            db.session.add(default_admin)
            db.session.commit()