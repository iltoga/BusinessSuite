from datetime import date
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth.models import User
from core.models import Holiday
from customer_applications.models import DocApplication, DocWorkflow
from customers.models import Customer
from products.models import Product, Task
from core.management.commands.populateholiday import Command as PopulateHolidayCommand
from core.utils.dateutils import calculate_due_date

import warnings
warnings.filterwarnings('ignore', category=UserWarning, module='whitenoise.base')

class DocApplicationTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='12345')
        self.customer = Customer.objects.create(
            full_name='Test Customer',
            title='Mr',
            citizenship='Indonesia',
            birthdate=timezone.now().date(),
        )
        self.product = Product.objects.create(name='Test Product')
        # Populate holidays for 2023
        PopulateHolidayCommand().generate_holiday_for_year(2023, 'ID', True)

    def test_due_date_no_workflow_no_holidays(self):
        # extra setup
        self.tasks_7_days = [
            Task.objects.create(product=self.product, step=1, name='Test Task', duration=2, duration_is_business_days=False),
            Task.objects.create(product=self.product, step=2, name='Test Task', duration=2, duration_is_business_days=False),
            Task.objects.create(product=self.product, step=3, name='Test Task', duration=3, duration_is_business_days=False),
        ]

        # chose a fixed date for doc_date to avoid timezone issues
        doc_date = timezone.datetime(2023, 1, 10, tzinfo=timezone.utc)
        doc_application = DocApplication.objects.create(product=self.product, doc_date=doc_date, created_by=self.user, customer=self.customer)
        self.assertEqual(doc_application.due_date, doc_date + timezone.timedelta(days=7))

    def test_due_date_no_workflow_with_holidays(self):
        self.tasks_21_days = [
            Task.objects.create(product=self.product, step=1, name='Test Task', duration=2, duration_is_business_days=True),
            Task.objects.create(product=self.product, step=2, name='Test Task', duration=2, duration_is_business_days=True),
            Task.objects.create(product=self.product, step=3, name='Test Task', duration=3, duration_is_business_days=True),
            Task.objects.create(product=self.product, step=4, name='Test Task', duration=14, duration_is_business_days=True),
        ]

        # chose a fixed date for doc_date to avoid timezone issues
        doc_date = timezone.datetime(2023, 1, 1, tzinfo=timezone.utc)
        doc_application = DocApplication.objects.create(product=self.product, doc_date=doc_date, created_by=self.user, customer=self.customer)
        tanggal_merah_count = 2
        # 2 weekends + 1 because the due date moved to saturday (2023-01-21) after adding 6 days of the first 2 weekends
        weekend_count = 6
        tot_duration = 21 + tanggal_merah_count + weekend_count
        self.assertEqual(doc_application.due_date, doc_date + timezone.timedelta(days=tot_duration))

    def test_due_date_with_workflow_no_holidays(self):
        # extra setup
        self.tasks_7_days = [
            Task.objects.create(product=self.product, step=1, name='Test Task', duration=2, duration_is_business_days=False),
            Task.objects.create(product=self.product, step=2, name='Test Task', duration=2, duration_is_business_days=False),
            Task.objects.create(product=self.product, step=3, name='Test Task', duration=3, duration_is_business_days=False),
        ]

        doc_date = timezone.datetime(2023, 1, 1, tzinfo=timezone.utc)
        doc_application = DocApplication.objects.create(product=self.product, doc_date=doc_date, created_by=self.user, customer=self.customer)
        # create workflow
        task = self.tasks_7_days[0]
        due_date = calculate_due_date(doc_date, task.duration, task.duration_is_business_days, 'ID')
        docworkflow1 = DocWorkflow.objects.create(
            doc_application=doc_application,
            task=task,
            start_date=doc_date,
            due_date=due_date,
            status='completed',
            created_by=self.user,
        )
        self.assertEqual(doc_application.due_date, date(2023, 1, 8))
        due_date = calculate_due_date(docworkflow1.due_date, task.duration, task.duration_is_business_days, 'ID')
        task = self.tasks_7_days[1]
        docworkflow2 = DocWorkflow.objects.create(
            doc_application=doc_application,
            task=task,
            start_date=docworkflow1.due_date,
            due_date=due_date,
            created_by=self.user,
        )
        self.assertEqual(doc_application.due_date, date(2023, 1, 8))
        tanggal_merah_count = 0
        weekend_count = 0
        tot_duration = 7 + tanggal_merah_count + weekend_count
        self.assertEqual(doc_application.due_date, doc_date.date() + timezone.timedelta(days=tot_duration))

        # add 1 day to the second docworkflow and check if the due date is updated
        docworkflow2.due_date = docworkflow2.due_date + timezone.timedelta(days=1)
        docworkflow2.save()
        self.assertEqual(doc_application.due_date, date(2023, 1, 9))




