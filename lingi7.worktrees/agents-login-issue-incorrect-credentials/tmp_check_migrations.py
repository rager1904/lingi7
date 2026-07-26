import importlib
import os
import django
from django.conf import settings

django.setup()
for app in settings.INSTALLED_APPS:
    try:
        module = importlib.import_module(app)
        pkg = module.__path__[0]
        migrations_path = os.path.join(pkg, 'migrations')
        has = os.path.isdir(migrations_path) and any(f.endswith('.py') for f in os.listdir(migrations_path))
    except Exception:
        has = False
    print(f"{app} {'has_migrations' if has else 'no_migrations'}")
