from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
from app import app, db
from models import FeeReminder

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