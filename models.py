from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from sqlalchemy import event

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), default='staff')  # admin, staff
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Member(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    date_of_birth = db.Column(db.Date)
    join_date = db.Column(db.Date, default=datetime.utcnow)
    membership_type = db.Column(db.String(50), nullable=False)  # Basic, Premium, VIP
    status = db.Column(db.String(20), default='Active')  # Active, Inactive, Suspended
    
    payments = db.relationship('Payment', backref='member', lazy=True)
    registrations = db.relationship('ClassRegistration', backref='member', lazy=True)
    fee_reminders = db.relationship('FeeReminder', backref='member', lazy=True)
    attendance_records = db.relationship('AttendanceRecord', backref='member', lazy=True)

class FitnessClass(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    instructor = db.Column(db.String(100), nullable=False)
    schedule = db.Column(db.DateTime, nullable=False)
    duration = db.Column(db.Integer, nullable=False)  # in minutes
    capacity = db.Column(db.Integer, nullable=False)
    
    registrations = db.relationship('ClassRegistration', backref='fitness_class', lazy=True)

class ClassRegistration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('member.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('fitness_class.id'), nullable=False)
    registration_date = db.Column(db.DateTime, default=datetime.utcnow)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('member.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    payment_method = db.Column(db.String(50))  # Credit Card, Cash, Bank Transfer
    status = db.Column(db.String(20), default='Completed')  # Completed, Pending, Failed
    notes = db.Column(db.Text)

class FeeReminder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('member.id'), nullable=False)
    reminder_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='Pending')  # Pending, Sent, Paid
    amount = db.Column(db.Float, nullable=False)
    notes = db.Column(db.Text)

# Attendance tracking models
class AttendanceDevice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    device_type = db.Column(db.String(50), nullable=False)  # biometric, keypad
    location = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)
    last_sync = db.Column(db.DateTime)

class AttendanceRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('member.id'), nullable=False)
    device_id = db.Column(db.Integer, db.ForeignKey('attendance_device.id'))
    check_in = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    check_out = db.Column(db.DateTime)
    attendance_type = db.Column(db.String(20), default='biometric')  # biometric, code, manual
    notes = db.Column(db.Text)
    
    device = db.relationship('AttendanceDevice', backref=db.backref('attendance_records', lazy=True))

# Function to calculate membership fee based on type
def calculate_membership_fee(membership_type):
    # Define your membership fees here
    fees = {
        'Basic': 1000.00,
        'Premium': 2000.00,
        'VIP': 3000.00
    }
    return fees.get(membership_type, 50.00)  # Default to Rs 50 if not found

# Function to create fee reminders when a new member is added
@event.listens_for(Member, 'after_insert')
def create_initial_fee_reminder(mapper, connection, target):
    # Create first fee reminder for one month from join date
    if target.join_date:
        first_reminder_date = target.join_date + timedelta(days=30)
    else:
        first_reminder_date = datetime.utcnow().date() + timedelta(days=30)
    
    fee_reminder = FeeReminder(
        member_id=target.id,
        reminder_date=first_reminder_date,
        amount=calculate_membership_fee(target.membership_type),
        status='Pending'
    )
    
    # Add to session but don't commit yet (will be committed with the member)
    db.session.add(fee_reminder)