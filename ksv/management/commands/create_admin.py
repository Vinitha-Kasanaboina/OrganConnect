from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from ksv.models import UserProfile

class Command(BaseCommand):
    help = "Creates or updates a Master Admin superuser account for OrganConnect."

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            default='admin',
            help='Username for the master admin account (default: admin)'
        )
        parser.add_argument(
            '--password',
            type=str,
            default='admin123',
            help='Password for the master admin account (default: admin123)'
        )
        parser.add_argument(
            '--email',
            type=str,
            default='admin@organconnect.gov.in',
            help='Email for the master admin account'
        )

    def handle(self, *args, **options):
        username = options['username']
        password = options['password']
        email = options['email']

        user, created = User.objects.get_or_create(username=username, defaults={'email': email})
        user.email = email
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save()

        profile, p_created = UserProfile.objects.get_or_create(user=user, defaults={'role': 'ADMIN'})
        profile.role = 'ADMIN'
        profile.save()

        action = "Created" if created else "Updated password and credentials for"
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully {action} Master Admin user '{username}' with password '{password}'."
            )
        )
