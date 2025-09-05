from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from models import db, User, Member, FitnessClass, ClassRegistration, Payment, FeeReminder, calculate_membership_fee, AttendanceDevice, AttendanceRecord
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///gym.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Scheduler functions
def check_fee_reminders():
    with app.app_context():
        today = datetime.now().date()
        
        # Check for due reminders
        due_reminders = FeeReminder.query.filter(
            FeeReminder.reminder_date <= today,
            FeeReminder.status == 'Pending'
        ).all()
        
        for reminder in due_reminders:
            print(f"Fee reminder due for member ID: {reminder.member_id}, Amount: ${reminder.amount}")
            # Here you could add email/SMS notification logic
        
        # Create next month's reminders for paid fees
        paid_reminders = FeeReminder.query.filter(
            FeeReminder.status == 'Paid',
            FeeReminder.reminder_date <= today
        ).all()
        
        for reminder in paid_reminders:
            # Create next reminder
            next_reminder_date = reminder.reminder_date + timedelta(days=30)
            new_reminder = FeeReminder(
                member_id=reminder.member_id,
                reminder_date=next_reminder_date,
                amount=reminder.amount,
                status='Pending'
            )
            db.session.add(new_reminder)
        
        db.session.commit()

def init_scheduler():
    scheduler = BackgroundScheduler()
    # Run every day at 9 AM
    scheduler.add_job(
        func=check_fee_reminders,
        trigger=CronTrigger(hour=9, minute=0),
        id='fee_reminder_job',
        name='Check fee reminders daily',
        replace_existing=True
    )
    scheduler.start()

# Create admin user if not exists
def create_admin_user():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("Admin user created: admin/admin123")

# Initialize scheduler
init_scheduler()

# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    # If user is already logged in, redirect to dashboard
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out successfully', 'info')
    return redirect(url_for('login'))

# Main routes
@app.route('/')
@login_required
def dashboard():
    total_members = Member.query.count()
    total_classes = FitnessClass.query.count()
    total_payments = Payment.query.count()
    recent_payments = Payment.query.order_by(Payment.payment_date.desc()).limit(5).all()
    
    # Calculate total revenue
    total_revenue = db.session.query(db.func.sum(Payment.amount)).scalar() or 0
    
    # Get pending fee reminders
    pending_reminders = FeeReminder.query.filter_by(status='Pending').count()
    
    # Get today's attendance count
    today = datetime.now().date()
    today_attendance = AttendanceRecord.query.filter(
        db.func.date(AttendanceRecord.check_in) == today
    ).count()
    
    return render_template('dashboard.html', 
                         total_members=total_members,
                         total_classes=total_classes,
                         total_payments=total_payments,
                         total_revenue=total_revenue,
                         pending_reminders=pending_reminders,
                         today_attendance=today_attendance,
                         recent_payments=recent_payments)

# Member management routes
@app.route('/members')
@login_required
def members():
    all_members = Member.query.all()
    return render_template('members.html', members=all_members)

@app.route('/add_member', methods=['GET', 'POST'])
@login_required
def add_member():
    if request.method == 'POST':
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        email = request.form['email']
        phone = request.form['phone']
        dob_str = request.form['dob']
        membership_type = request.form['membership_type']
        
        # Handle date conversion
        dob = None
        if dob_str:
            try:
                dob = datetime.strptime(dob_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid date format', 'danger')
                return render_template('add_member.html')
        
        # Check if email already exists
        if Member.query.filter_by(email=email).first():
            flash('A member with this email already exists', 'danger')
            return render_template('add_member.html')
        
        new_member = Member(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            date_of_birth=dob,
            membership_type=membership_type
        )
        
        try:
            db.session.add(new_member)
            db.session.commit()
            flash('Member added successfully!', 'success')
            return redirect(url_for('members'))
        except Exception as e:
            db.session.rollback()
            flash('Error adding member: ' + str(e), 'danger')
    
    return render_template('add_member.html')

@app.route('/edit_member/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_member(id):
    member = Member.query.get_or_404(id)
    
    if request.method == 'POST':
        member.first_name = request.form['first_name']
        member.last_name = request.form['last_name']
        member.email = request.form['email']
        member.phone = request.form['phone']
        
        # Handle date conversion
        dob_str = request.form['dob']
        if dob_str:
            try:
                member.date_of_birth = datetime.strptime(dob_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid date format', 'danger')
                return render_template('edit_member.html', member=member)
        
        member.membership_type = request.form['membership_type']
        member.status = request.form['status']
        
        try:
            db.session.commit()
            flash('Member updated successfully!', 'success')
            return redirect(url_for('members'))
        except Exception as e:
            db.session.rollback()
            flash('Error updating member: ' + str(e), 'danger')
    
    return render_template('edit_member.html', member=member)

@app.route('/delete_member/<int:id>')
@login_required
def delete_member(id):
    member = Member.query.get_or_404(id)
    
    # Check if member has payments or registrations
    if member.payments or member.registrations or member.fee_reminders or member.attendance_records:
        flash('Cannot delete member with associated payments, class registrations, fee reminders, or attendance records', 'danger')
        return redirect(url_for('members'))
    
    try:
        db.session.delete(member)
        db.session.commit()
        flash('Member deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting member: ' + str(e), 'danger')
    
    return redirect(url_for('members'))

# Class management routes
@app.route('/classes')
@login_required
def classes():
    all_classes = FitnessClass.query.all()
    return render_template('classes.html', classes=all_classes)

@app.route('/add_class', methods=['GET', 'POST'])
@login_required
def add_class():
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        instructor = request.form['instructor']
        schedule_str = request.form['schedule']
        duration = request.form['duration']
        capacity = request.form['capacity']
        
        # Handle datetime conversion
        try:
            schedule = datetime.strptime(schedule_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('Invalid datetime format', 'danger')
            return render_template('add_class.html')
        
        new_class = FitnessClass(
            name=name,
            description=description,
            instructor=instructor,
            schedule=schedule,
            duration=int(duration),
            capacity=int(capacity)
        )
        
        try:
            db.session.add(new_class)
            db.session.commit()
            flash('Class added successfully!', 'success')
            return redirect(url_for('classes'))
        except Exception as e:
            db.session.rollback()
            flash('Error adding class: ' + str(e), 'danger')
    
    return render_template('add_class.html')

@app.route('/edit_class/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_class(id):
    fitness_class = FitnessClass.query.get_or_404(id)
    
    if request.method == 'POST':
        fitness_class.name = request.form['name']
        fitness_class.description = request.form['description']
        fitness_class.instructor = request.form['instructor']
        
        # Handle datetime conversion
        schedule_str = request.form['schedule']
        try:
            fitness_class.schedule = datetime.strptime(schedule_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('Invalid datetime format', 'danger')
            return render_template('edit_class.html', fitness_class=fitness_class)
        
        fitness_class.duration = int(request.form['duration'])
        fitness_class.capacity = int(request.form['capacity'])
        
        try:
            db.session.commit()
            flash('Class updated successfully!', 'success')
            return redirect(url_for('classes'))
        except Exception as e:
            db.session.rollback()
            flash('Error updating class: ' + str(e), 'danger')
    
    return render_template('edit_class.html', fitness_class=fitness_class)

@app.route('/delete_class/<int:id>')
@login_required
def delete_class(id):
    fitness_class = FitnessClass.query.get_or_404(id)
    
    # Check if class has registrations
    if fitness_class.registrations:
        flash('Cannot delete class with registered members', 'danger')
        return redirect(url_for('classes'))
    
    try:
        db.session.delete(fitness_class)
        db.session.commit()
        flash('Class deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting class: ' + str(e), 'danger')
    
    return redirect(url_for('classes'))

# Payment management routes
@app.route('/payments')
@login_required
def payments():
    all_payments = Payment.query.order_by(Payment.payment_date.desc()).all()
    return render_template('payments.html', payments=all_payments)

@app.route('/add_payment', methods=['GET', 'POST'])
@login_required
def add_payment():
    if request.method == 'POST':
        member_id = request.form['member_id']
        amount = request.form['amount']
        payment_method = request.form['payment_method']
        notes = request.form['notes']
        
        # Validate member exists
        member = Member.query.get(member_id)
        if not member:
            flash('Invalid member selected', 'danger')
            return redirect(url_for('add_payment'))
        
        new_payment = Payment(
            member_id=member_id,
            amount=float(amount),
            payment_method=payment_method,
            notes=notes
        )
        
        try:
            db.session.add(new_payment)
            db.session.commit()
            flash('Payment recorded successfully!', 'success')
            return redirect(url_for('payments'))
        except Exception as e:
            db.session.rollback()
            flash('Error recording payment: ' + str(e), 'danger')
    
    members = Member.query.all()
    return render_template('add_payment.html', members=members)

@app.route('/edit_payment/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_payment(id):
    payment = Payment.query.get_or_404(id)
    
    if request.method == 'POST':
        payment.member_id = request.form['member_id']
        payment.amount = float(request.form['amount'])
        payment.payment_method = request.form['payment_method']
        payment.status = request.form['status']
        payment.notes = request.form['notes']
        
        try:
            db.session.commit()
            flash('Payment updated successfully!', 'success')
            return redirect(url_for('payments'))
        except Exception as e:
            db.session.rollback()
            flash('Error updating payment: ' + str(e), 'danger')
    
    members = Member.query.all()
    return render_template('edit_payment.html', payment=payment, members=members)

@app.route('/delete_payment/<int:id>')
@login_required
def delete_payment(id):
    payment = Payment.query.get_or_404(id)
    
    try:
        db.session.delete(payment)
        db.session.commit()
        flash('Payment deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting payment: ' + str(e), 'danger')
    
    return redirect(url_for('payments'))

# Class registration routes
@app.route('/class_registrations')
@login_required
def class_registrations():
    registrations = ClassRegistration.query.all()
    return render_template('class_registrations.html', registrations=registrations)

@app.route('/register_member_class', methods=['GET', 'POST'])
@login_required
def register_member_class():
    if request.method == 'POST':
        member_id = request.form['member_id']
        class_id = request.form['class_id']
        
        # Check if registration already exists
        existing_registration = ClassRegistration.query.filter_by(
            member_id=member_id, class_id=class_id
        ).first()
        
        if existing_registration:
            flash('This member is already registered for this class!', 'warning')
        else:
            new_registration = ClassRegistration(
                member_id=member_id,
                class_id=class_id
            )
            
            try:
                db.session.add(new_registration)
                db.session.commit()
                flash('Member registered for class successfully!', 'success')
            except Exception as e:
                db.session.rollback()
                flash('Error registering member for class: ' + str(e), 'danger')
        
        return redirect(url_for('class_registrations'))
    
    members = Member.query.all()
    classes = FitnessClass.query.all()
    return render_template('register_member_class.html', members=members, classes=classes)

@app.route('/delete_registration/<int:id>')
@login_required
def delete_registration(id):
    registration = ClassRegistration.query.get_or_404(id)
    
    try:
        db.session.delete(registration)
        db.session.commit()
        flash('Registration deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting registration: ' + str(e), 'danger')
    
    return redirect(url_for('class_registrations'))

# Fee reminder routes
@app.route('/fee_reminders')
@login_required
def fee_reminders():
    all_reminders = FeeReminder.query.order_by(FeeReminder.reminder_date).all()
    return render_template('fee_reminders.html', reminders=all_reminders)

@app.route('/mark_paid/<int:reminder_id>')
@login_required
def mark_paid(reminder_id):
    reminder = FeeReminder.query.get_or_404(reminder_id)
    reminder.status = 'Paid'
    
    try:
        db.session.commit()
        flash('Fee marked as paid successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error updating fee reminder: ' + str(e), 'danger')
    
    return redirect(url_for('fee_reminders'))

@app.route('/add_fee_reminder/<int:member_id>', methods=['GET', 'POST'])
@login_required
def add_fee_reminder(member_id):
    member = Member.query.get_or_404(member_id)
    
    if request.method == 'POST':
        reminder_date = datetime.strptime(request.form['reminder_date'], '%Y-%m-%d').date()
        amount = float(request.form['amount'])
        notes = request.form['notes']
        
        new_reminder = FeeReminder(
            member_id=member_id,
            reminder_date=reminder_date,
            amount=amount,
            notes=notes,
            status='Pending'
        )
        
        try:
            db.session.add(new_reminder)
            db.session.commit()
            flash('Fee reminder added successfully!', 'success')
            return redirect(url_for('members'))
        except Exception as e:
            db.session.rollback()
            flash('Error adding fee reminder: ' + str(e), 'danger')
    
    # Set default date to 30 days from now
    default_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
    default_amount = calculate_membership_fee(member.membership_type)
    
    return render_template('add_fee_reminder.html', member=member, default_date=default_date, default_amount=default_amount)

@app.route('/delete_reminder/<int:reminder_id>')
@login_required
def delete_reminder(reminder_id):
    reminder = FeeReminder.query.get_or_404(reminder_id)
    
    try:
        db.session.delete(reminder)
        db.session.commit()
        flash('Fee reminder deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting fee reminder: ' + str(e), 'danger')
    
    return redirect(url_for('fee_reminders'))

# Attendance management routes
@app.route('/attendance')
@login_required
def attendance():
    today = datetime.now().date()
    today_attendance = AttendanceRecord.query.filter(
        db.func.date(AttendanceRecord.check_in) == today
    ).order_by(AttendanceRecord.check_in.desc()).all()
    
    return render_template('attendance.html', attendance_records=today_attendance, today=today)

@app.route('/attendance_history')
@login_required
def attendance_history():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    attendance_records = AttendanceRecord.query.order_by(
        AttendanceRecord.check_in.desc()
    ).paginate(page=page, per_page=per_page)
    
    return render_template('attendance_history.html', attendance_records=attendance_records)

@app.route('/check_in_biometric', methods=['POST'])
def check_in_biometric():
    if request.method == 'POST':
        member_id = request.form.get('member_id')
        
        if not member_id:
            return jsonify({'success': False, 'message': 'Member ID required'})
        
        member = Member.query.get(member_id)
        if not member:
            return jsonify({'success': False, 'message': 'Member not found'})
        
        # Create attendance record
        new_attendance = AttendanceRecord(
            member_id=member_id,
            attendance_type='biometric',
            check_in=datetime.now()
        )
        
        try:
            db.session.add(new_attendance)
            db.session.commit()
            return jsonify({
                'success': True, 
                'message': f'Check-in recorded for {member.first_name} {member.last_name}'
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Error: {str(e)}'})
    
    return jsonify({'success': False, 'message': 'Invalid request'})

@app.route('/check_in_code', methods=['POST'])
def check_in_code():
    if request.method == 'POST':
        code = request.form.get('code')
        
        if not code:
            return jsonify({'success': False, 'message': 'Code required'})
        
        # In a real system, you'd have a code-to-member mapping
        # For demo purposes, let's assume code is the member ID
        try:
            member_id = int(code)
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid code format'})
        
        member = Member.query.get(member_id)
        if not member:
            return jsonify({'success': False, 'message': 'Invalid code'})
        
        # Create attendance record
        new_attendance = AttendanceRecord(
            member_id=member_id,
            attendance_type='code',
            check_in=datetime.now()
        )
        
        try:
            db.session.add(new_attendance)
            db.session.commit()
            return jsonify({
                'success': True, 
                'message': f'Check-in recorded for {member.first_name} {member.last_name}'
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Error: {str(e)}'})
    
    return jsonify({'success': False, 'message': 'Invalid request'})

@app.route('/check_out/<int:record_id>')
@login_required
def check_out(record_id):
    attendance_record = AttendanceRecord.query.get_or_404(record_id)
    
    if attendance_record.check_out:
        flash('Member already checked out', 'warning')
    else:
        attendance_record.check_out = datetime.now()
        db.session.commit()
        flash('Check-out recorded successfully', 'success')
    
    return redirect(url_for('attendance'))

@app.route('/attendance_devices')
@login_required
def attendance_devices():
    devices = AttendanceDevice.query.all()
    return render_template('attendance_devices.html', devices=devices)

@app.route('/add_device', methods=['GET', 'POST'])
@login_required
def add_device():
    if request.method == 'POST':
        name = request.form['name']
        device_type = request.form['device_type']
        location = request.form['location']
        
        new_device = AttendanceDevice(
            name=name,
            device_type=device_type,
            location=location
        )
        
        try:
            db.session.add(new_device)
            db.session.commit()
            flash('Device added successfully!', 'success')
            return redirect(url_for('attendance_devices'))
        except Exception as e:
            db.session.rollback()
            flash('Error adding device: ' + str(e), 'danger')
    
    return render_template('add_device.html')

@app.route('/manual_check_in', methods=['GET', 'POST'])
@login_required
def manual_check_in():
    if request.method == 'POST':
        member_id = request.form['member_id']
        check_in_time = request.form['check_in_time']
        notes = request.form['notes']
        
        try:
            check_in_datetime = datetime.strptime(check_in_time, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('Invalid datetime format', 'danger')
            return redirect(url_for('manual_check_in'))
        
        new_attendance = AttendanceRecord(
            member_id=member_id,
            attendance_type='manual',
            check_in=check_in_datetime,
            notes=notes
        )
        
        try:
            db.session.add(new_attendance)
            db.session.commit()
            flash('Manual check-in recorded successfully!', 'success')
            return redirect(url_for('attendance'))
        except Exception as e:
            db.session.rollback()
            flash('Error recording check-in: ' + str(e), 'danger')
    
    members = Member.query.all()
    return render_template('manual_check_in.html', members=members)

# User management routes (admin only)
@app.route('/users')
@login_required
def users():
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('dashboard'))
    
    all_users = User.query.all()
    return render_template('users.html', users=all_users)

@app.route('/add_user', methods=['GET', 'POST'])
@login_required
def add_user():
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        
        # Check if username already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return render_template('add_user.html')
        
        new_user = User(username=username, role=role)
        new_user.set_password(password)
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('User added successfully!', 'success')
            return redirect(url_for('users'))
        except Exception as e:
            db.session.rollback()
            flash('Error adding user: ' + str(e), 'danger')
    
    return render_template('add_user.html')

@app.route('/delete_user/<int:id>')
@login_required
def delete_user(id):
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('dashboard'))
    
    user = User.query.get_or_404(id)
    
    # Prevent deleting the current user
    if user.id == current_user.id:
        flash('Cannot delete your own account', 'danger')
        return redirect(url_for('users'))
    
    try:
        db.session.delete(user)
        db.session.commit()
        flash('User deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting user: ' + str(e), 'danger')
    
    return redirect(url_for('users'))

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

if __name__ == '__main__':
    # Create admin user and database tables
    create_admin_user()
    app.run(debug=True)