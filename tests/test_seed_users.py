"""D3-R2 Step 0：种子用户 role↔flags 映射验收（ADR-0003 / 字典 §1）。

- ``role=admin`` → ``is_superuser=True``、``is_staff=True``
- 其余 role → 两者均 False
"""

import pytest
from django.core.management import call_command

from core.models import User


@pytest.fixture
def seeded(db):
    call_command("load_demo_seed", flush=True, verbosity=0)


def test_seed_admin_maps_to_superuser(seeded):
    admin = User.objects.get(username="admin")
    assert admin.role == "admin"
    assert admin.is_superuser is True
    assert admin.is_staff is True


def test_seed_non_admin_flags_false(seeded):
    non_admins = User.objects.exclude(role="admin")
    assert non_admins.exists()
    for user in non_admins:
        assert user.is_superuser is False, user.username
        assert user.is_staff is False, user.username