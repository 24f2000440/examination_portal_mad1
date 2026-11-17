from functools import wraps
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, init_db, User, Course, Examination, ExaminationRubric, ExaminationSlot, Booking, EvaluationScore
from sqlalchemy import or_, cast, String

app = Flask(__name__)
app.config['SECRET_KEY'] = 'emp_super_secret_key_2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///emp.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
init_db(app)

# --- ACCESS CONTROL DECORATORS ---
def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to continue.', 'warning')
                return redirect(url_for('login'))
            if role and session.get('role') != role:
                flash('Unauthorized access for your role.', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.context_processor
def inject_user():
    user = User.query.get(session['user_id']) if 'user_id' in session else None
    return dict(current_user=user)

# --- AUTHENTICATION ROUTES ---
@app.route('/')
def index():
    if 'user_id' in session:
        role = session.get('role')
        if role == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif role == 'examiner':
            return redirect(url_for('examiner_dashboard'))
        elif role == 'student':
            return redirect(url_for('student_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email').strip()
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            if user.status == 'Pending':
                flash('Your Examiner account is awaiting Admin approval.', 'warning')
                return redirect(url_for('login'))
            if user.status == 'Deactivated':
                flash('Your account has been deactivated. Contact Admin.', 'danger')
                return redirect(url_for('login'))

            session['user_id'] = user.id
            session['role'] = user.role
            flash(f'Welcome back, {user.full_name}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid email or password.', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        role = request.form.get('role')
        if role not in ['student', 'examiner']:
            flash('Invalid role selected.', 'danger')
            return redirect(url_for('register'))

        email = request.form.get('email').strip()
        if User.query.filter_by(email=email).first():
            flash('Email is already registered.', 'danger')
            return redirect(url_for('register'))

        new_user = User(
            full_name=request.form.get('full_name').strip(),
            email=email,
            password_hash=generate_password_hash(request.form.get('password')),
            role=role,
            department=request.form.get('department').strip(),
            contact=request.form.get('contact').strip(),
            roll_number=request.form.get('roll_number', '').strip(),
            status='Pending' if role == 'examiner' else 'Active'
        )
        db.session.add(new_user)
        db.session.commit()

        if role == 'examiner':
            flash('Registration submitted! Please wait for Admin approval before logging in.', 'info')
        else:
            flash('Registration successful! You may now log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# --- ADMIN ROUTES ---
@app.route('/admin/dashboard')
@login_required(role='admin')
def admin_dashboard():
    search_q = request.args.get('q', '').strip()
    
    # Efficient count queries
    stats = {
        'courses': Course.query.count(),
        'exams': Examination.query.count(),
        'examiners': User.query.filter_by(role='examiner').count(),
        'students': User.query.filter_by(role='student').count(),
        'slots': ExaminationSlot.query.count(),
        'bookings': Booking.query.count()
    }

    # Initialize base queries
    courses_query = Course.query
    exams_query = Examination.query
    examiners_query = User.query.filter_by(role='examiner')
    students_query = User.query.filter_by(role='student')
    slots_query = ExaminationSlot.query
    bookings_query = Booking.query

    if search_q:
        term = f"%{search_q}%"
        
        # Apply database-level filters (adjust column names if needed)
        courses_query = courses_query.filter(
            or_(Course.course_name.ilike(term), cast(Course.id, String).ilike(term))
        )
        exams_query = exams_query.filter(
            or_(Examination.exam_name.ilike(term), cast(Examination.id, String).ilike(term))
        )
        examiners_query = examiners_query.filter(
            or_(User.full_name.ilike(term), cast(User.id, String).ilike(term))
        )
        students_query = students_query.filter(
            or_(User.full_name.ilike(term), cast(User.id, String).ilike(term))
        )
        slots_query = slots_query.filter(
            cast(ExaminationSlot.id, String).ilike(term)
        )
        # Join with student to filter bookings by student name or booking ID
        bookings_query = bookings_query.join(Booking.student).filter(
            or_(cast(Booking.id, String).ilike(term), User.full_name.ilike(term))
        )

    return render_template(
        'admin_dashboard.html',
        stats=stats, 
        courses=courses_query.all(), 
        exams=exams_query.all(),
        examiners=examiners_query.all(), 
        students=students_query.all(), 
        slots=slots_query.all(),
        bookings=bookings_query.all(), 
        search_q=search_q
    )
@app.route('/admin/course/add', methods=['POST'])
@login_required(role='admin')
def admin_add_course():
    course = Course(
        course_code=request.form.get('course_code').strip(),
        course_name=request.form.get('course_name').strip(),
        description=request.form.get('description').strip()
    )
    db.session.add(course)
    db.session.commit()
    flash('Course created successfully.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/course/delete/<int:course_id>', methods=['POST'])
@login_required(role='admin')
def admin_delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    db.session.delete(course)
    db.session.commit()
    flash('Course deleted.', 'info')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/exam/add', methods=['POST'])
@login_required(role='admin')
def admin_add_exam():
    exam = Examination(
        course_id=int(request.form.get('course_id')),
        exam_name=request.form.get('exam_name').strip(),
        exam_type=request.form.get('exam_type'),
        duration_mins=int(request.form.get('duration_mins')),
        max_marks=float(request.form.get('max_marks')),
        slot_creation_start=datetime.strptime(request.form.get('slot_creation_start'), '%Y-%m-%dT%H:%M'),
        slot_creation_end=datetime.strptime(request.form.get('slot_creation_end'), '%Y-%m-%dT%H:%M'),
        slot_booking_start=datetime.strptime(request.form.get('slot_booking_start'), '%Y-%m-%dT%H:%M'),
        slot_booking_end=datetime.strptime(request.form.get('slot_booking_end'), '%Y-%m-%dT%H:%M'),
        status=request.form.get('status', 'Draft')
    )
    db.session.add(exam)
    db.session.commit()
    flash('Examination created.', 'success')
    return redirect(url_for('admin_dashboard'))
 
@app.route('/admin/exam/<int:exam_id>/manage', methods=['GET', 'POST'])
@login_required(role='admin')
def admin_manage_exam(exam_id):
    exam = Examination.query.get_or_404(exam_id)
    rubrics = ExaminationRubric.query.filter_by(exam_id=exam.id).all()

    if request.method == 'POST':
        criterion_name = (request.form.get('criterion_name') or '').strip()
        max_marks = float(request.form.get('max_marks') or 0)
        current_total = sum(r.max_marks for r in rubrics)

        if max_marks <= 0:
            flash('Max marks must be greater than 0.', 'danger')
        elif current_total + max_marks > exam.max_marks:
            remaining = exam.max_marks - current_total
            flash(f'Cannot add rubric: exceeds full marks ({exam.max_marks}). Remaining: {remaining}.', 'danger')
        else:
            db.session.add(ExaminationRubric(
                exam_id=exam.id,
                criterion_name=criterion_name,
                max_marks=max_marks
            ))
            db.session.commit()
            flash('Rubric criterion added.', 'success')

        return redirect(url_for('admin_manage_exam', exam_id=exam.id))

    return render_template('admin_manage_exam.html', exam=exam, rubrics=rubrics)

@app.route('/admin/exam/delete/<int:exam_id>', methods=['POST'])
@login_required(role='admin')
def admin_delete_exam(exam_id):
    exam = Examination.query.get_or_404(exam_id)
    db.session.delete(exam)
    db.session.commit()
    flash('Examination deleted.', 'info')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/examiner/<int:user_id>/status', methods=['POST'])
@login_required(role='admin')
def admin_examiner_status(user_id):
    user = User.query.get_or_404(user_id)
    user.status = request.form.get('status')
    db.session.commit()
    flash(f'Examiner {user.full_name} marked as {user.status}.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/slot/<int:slot_id>/reassign', methods=['POST'])
@login_required(role='admin')
def admin_reassign_examiner(slot_id):
    slot = ExaminationSlot.query.get_or_404(slot_id)
    slot.examiner_id = int(request.form.get('examiner_id'))
    db.session.commit()
    flash('Examiner reassigned for the slot.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/booking/<int:booking_id>/reschedule', methods=['POST'])
@login_required(role='admin')
def admin_reschedule_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    new_slot_id_raw = request.form.get('new_slot_id')
    if not new_slot_id_raw:
        flash('Please select a valid target slot before clicking Move.', 'danger')
        return redirect(url_for('admin_dashboard'))

    new_slot_id = int(new_slot_id_raw)
    new_slot = ExaminationSlot.query.get_or_404(new_slot_id)

    if new_slot.available_seats <= 0:
        flash('Target slot is full.', 'danger')
        return redirect(url_for('admin_dashboard'))
    # Restore seat to old slot
    old_slot = booking.slot
    old_slot.available_seats += 1
    if old_slot.status == 'Full':
        old_slot.status = 'Available'

    # Deduct seat from new slot
    booking.slot_id = new_slot.id
    new_slot.available_seats -= 1
    if new_slot.available_seats == 0:
        new_slot.status = 'Full'

    db.session.commit()
    flash('Booking rescheduled successfully.', 'success')
    return redirect(url_for('admin_dashboard'))
@app.route('/admin/examiner/add', methods=['POST'])
@login_required(role='admin')
def admin_add_examiner():
    email = request.form.get('email').strip()
    if User.query.filter_by(email=email).first():
        flash('An account with this email already exists.', 'danger')
        return redirect(url_for('admin_dashboard'))

    new_examiner = User(
        full_name=request.form.get('full_name').strip(),
        email=email,
        password_hash=generate_password_hash(request.form.get('password')),
        role='examiner',
        department=request.form.get('department').strip(),
        contact=request.form.get('contact').strip(),
        status='Active'  # Directly active since admin created it
    )
    db.session.add(new_examiner)
    db.session.commit()
    flash(f'Examiner {new_examiner.full_name} added successfully as Active.', 'success')
    return redirect(url_for('admin_dashboard'))
@app.route('/admin/exam/<int:exam_id>/edit', methods=['POST'])
@login_required(role='admin')
def admin_edit_examination_details(exam_id):
    exam = Examination.query.get_or_404(exam_id)
    exam.exam_name = request.form.get('exam_name').strip()
    exam.exam_type = request.form.get('exam_type')
    exam.duration_mins = int(request.form.get('duration_mins'))
    exam.max_marks = float(request.form.get('max_marks'))

    exam.slot_creation_start = datetime.strptime(request.form.get('slot_creation_start'), '%Y-%m-%dT%H:%M')
    exam.slot_creation_end = datetime.strptime(request.form.get('slot_creation_end'), '%Y-%m-%dT%H:%M')
    exam.slot_booking_start = datetime.strptime(request.form.get('slot_booking_start'), '%Y-%m-%dT%H:%M')
    exam.slot_booking_end = datetime.strptime(request.form.get('slot_booking_end'), '%Y-%m-%dT%H:%M')

    exam.status = request.form.get('status')
    db.session.commit()
    flash('Examination details and timelines updated successfully.', 'success')
    return redirect(url_for('admin_manage_exam', exam_id=exam.id))

# --- EXAMINER ROUTES ---
@app.route('/examiner/dashboard')
@login_required(role='examiner')
def examiner_dashboard():
    examiner_id = session['user_id']
    now = datetime.now()
    # Examinations currently open for slot creation
    open_exams = Examination.query.filter(
        Examination.status == 'Slot Creation',
        Examination.slot_creation_start <= now,
        Examination.slot_creation_end >= now
    ).all()
    all_exams = Examination.query.all()
    my_slots = ExaminationSlot.query.filter_by(examiner_id=examiner_id).all()
    
    total_booked = sum(len([b for b in s.bookings if b.status in ['Booked', 'Completed']]) for s in my_slots)
    pending_evals = sum(len([b for b in s.bookings if b.status == 'Booked']) for s in my_slots)

    return render_template(
        'examiner_dashboard.html',
        open_exams=open_exams, all_exams=all_exams,
        my_slots=my_slots, total_booked=total_booked, pending_evals=pending_evals
    )

@app.route('/examiner/slot/create', methods=['POST'])
@login_required(role='examiner')
def examiner_create_slot():
    exam_id = int(request.form.get('exam_id'))
    exam = Examination.query.get_or_404(exam_id)
    now = datetime.now()

    if exam.status != 'Slot Creation' or not (exam.slot_creation_start <= now <= exam.slot_creation_end):
        flash('Slot creation is not currently active for this examination.', 'danger')
        return redirect(url_for('examiner_dashboard'))

    capacity = int(request.form.get('max_capacity'))
    slot = ExaminationSlot(
        exam_id=exam.id,
        examiner_id=session['user_id'],
        date=datetime.strptime(request.form.get('date'), '%Y-%m-%d').date(),
        start_time=datetime.strptime(request.form.get('start_time'), '%H:%M').time(),
        end_time=datetime.strptime(request.form.get('end_time'), '%H:%M').time(),
        max_capacity=capacity,
        available_seats=capacity,
        status='Available'
    )
    db.session.add(slot)
    db.session.commit()
    flash('Examination slot created.', 'success')
    return redirect(url_for('examiner_dashboard'))

@app.route('/examiner/slot/<int:slot_id>/delete', methods=['POST'])
@login_required(role='examiner')
def examiner_delete_slot(slot_id):
    slot = ExaminationSlot.query.get_or_404(slot_id)
    if slot.examiner_id != session['user_id']:
        flash('Unauthorized slot access.', 'danger')
        return redirect(url_for('examiner_dashboard'))
    if slot.examination.status == 'Booking Open' or len(slot.bookings) > 0:
        flash('Cannot delete slot once booking has started or students have booked.', 'danger')
        return redirect(url_for('examiner_dashboard'))

    db.session.delete(slot)
    db.session.commit()
    flash('Slot removed.', 'info')
    return redirect(url_for('examiner_dashboard'))

@app.route('/examiner/evaluate/<int:booking_id>', methods=['GET', 'POST'])
@login_required(role='examiner')
def examiner_evaluate(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.slot.examiner_id != session['user_id']:
        flash('You can only evaluate students booked in your own slots.', 'danger')
        return redirect(url_for('examiner_dashboard'))

    rubrics = booking.slot.examination.rubrics
    if request.method == 'POST':
        # Clear existing scores if re-evaluating
        EvaluationScore.query.filter_by(booking_id=booking.id).delete()
        total_score = 0.0

        for r in rubrics:
            score_val = float(request.form.get(f'rubric_{r.id}', 0))
            if score_val > r.max_marks or score_val < 0:
                flash(f'Score for {r.criterion_name} must be between 0 and {r.max_marks}.', 'danger')
                return redirect(url_for('examiner_evaluate', booking_id=booking.id))
            total_score += score_val
            db.session.add(EvaluationScore(booking_id=booking.id, rubric_id=r.id, marks_awarded=score_val))

        booking.total_marks_awarded = total_score
        booking.remarks = request.form.get('remarks', '').strip()
        booking.status = 'Completed'
        booking.is_published = True
        db.session.commit()
        flash('Evaluation submitted and results published.', 'success')
        return redirect(url_for('examiner_dashboard'))

    return render_template('examiner_evaluate.html', booking=booking, rubrics=rubrics)

# --- STUDENT ROUTES ---
@app.route('/student/dashboard', methods=['GET', 'POST'])
@login_required(role='student')
def student_dashboard():
    student = User.query.get(session['user_id'])
    if request.method == 'POST' and request.form.get('action') == 'update_profile':
        student.full_name = request.form.get('full_name').strip()
        student.department = request.form.get('department').strip()
        student.contact = request.form.get('contact').strip()
        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('student_dashboard'))

    search_q = request.args.get('q', '').strip().lower()
    now = datetime.now()

    available_exams = Examination.query.filter(
        Examination.status == 'Booking Open',
        Examination.slot_booking_start <= now,
        Examination.slot_booking_end >= now
    ).all()

    if search_q:
        available_exams = [
            e for e in available_exams
            if search_q in e.exam_name.lower() or search_q in e.course.course_name.lower() or search_q in e.exam_type.lower()
        ]

    my_bookings = Booking.query.filter_by(student_id=student.id).order_by(Booking.booking_date.desc()).all()
    booked_exam_ids = {b.slot.exam_id for b in my_bookings if b.status in ['Booked', 'Completed']}

    return render_template(
        'student_dashboard.html',
        student=student, available_exams=available_exams,
        my_bookings=my_bookings, booked_exam_ids=booked_exam_ids,
        search_q=search_q, now=now
    )

@app.route('/student/book/<int:slot_id>', methods=['POST'])
@login_required(role='student')
def student_book_slot(slot_id):
    student_id = session['user_id']
    slot = ExaminationSlot.query.get_or_404(slot_id)
    exam = slot.examination
    now = datetime.now()

    # Enforce booking window
    if exam.status != 'Booking Open' or not (exam.slot_booking_start <= now <= exam.slot_booking_end):
        flash('Booking window is closed for this examination.', 'danger')
        return redirect(url_for('student_dashboard'))

    # Prevent duplicate booking for the same exam
    existing = Booking.query.join(ExaminationSlot).filter(
        Booking.student_id == student_id,
        ExaminationSlot.exam_id == exam.id,
        Booking.status.in_(['Booked', 'Completed'])
    ).first()
    if existing:
        flash('You already have an active booking for this examination.', 'warning')
        return redirect(url_for('student_dashboard'))

    # Prevent overbooking
    if slot.available_seats <= 0 or slot.status != 'Available':
        flash('This slot is already full.', 'danger')
        return redirect(url_for('student_dashboard'))

    booking = Booking(student_id=student_id, slot_id=slot.id, status='Booked')
    slot.available_seats -= 1
    if slot.available_seats == 0:
        slot.status = 'Full'

    db.session.add(booking)
    db.session.commit()
    flash('Examination slot booked successfully!', 'success')
    return redirect(url_for('student_dashboard'))

@app.route('/student/cancel/<int:booking_id>', methods=['POST'])
@login_required(role='student')
def student_cancel_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.student_id != session['user_id']:
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('student_dashboard'))

    now = datetime.now()
    if now > booking.slot.examination.slot_booking_end or booking.status != 'Booked':
        flash('Cancellation deadline has passed or booking cannot be cancelled.', 'danger')
        return redirect(url_for('student_dashboard'))

    booking.status = 'Cancelled'
    slot = booking.slot
    slot.available_seats += 1
    if slot.status == 'Full':
        slot.status = 'Available'

    db.session.commit()
    flash('Booking cancelled and seat released.', 'info')
    return redirect(url_for('student_dashboard'))

@app.route('/student/result/<int:booking_id>')
@login_required(role='student')
def student_result(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.student_id != session['user_id'] or not booking.is_published:
        flash('Result not available.', 'warning')
        return redirect(url_for('student_dashboard'))
    return render_template('student_result.html', booking=booking)

# --- OPTIONAL REST API ENDPOINT (JSON) ---
@app.route('/api/examinations', methods=['GET'])
def api_examinations():
    exams = Examination.query.all()
    return jsonify([
        {
            'id': e.id,
            'course_code': e.course.course_code,
            'exam_name': e.exam_name,
            'exam_type': e.exam_type,
            'max_marks': e.max_marks,
            'status': e.status
        } for e in exams
    ])

if __name__ == '__main__':
    app.run(debug=True)