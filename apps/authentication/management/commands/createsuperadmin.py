import sys
from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError
from apps.authentication.models import AdminUser

class Command(BaseCommand):
    help = 'Create a superadmin user'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True, type=str, help='Email address')
        parser.add_argument('--name', required=True, type=str, help='Full name')
        parser.add_argument('--password', required=True, type=str, help='Password')

    def handle(self, *args, **options):
        email = options['email']
        name = options['name']
        password = options['password']

        if AdminUser.objects.filter(email=email).exists():
            self.stdout.write('Admin already exists.')
            sys.exit(0)

        try:
            user = AdminUser.objects.create(
                email=email,
                full_name=name,
                password_hash=make_password(password),
                role='superadmin',
                is_active=True
            )
            self.stdout.write(self.style.SUCCESS(f'Superadmin created: {user.email}'))
        except IntegrityError as e:
            self.stdout.write(self.style.ERROR(f'Failed to create superadmin: {e}'))
            sys.exit(1)
