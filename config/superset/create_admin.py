from superset.app import create_app
from superset import security_manager
app = create_app()
with app.app_context():
    if not security_manager.find_user(username='admin'):
        security_manager.add_user(
            username='admin', first_name='Local', last_name='Student',
            email='student@example.invalid',
            role=security_manager.find_role('Admin') or security_manager.add_role('Admin'),
            password='admin-local')
