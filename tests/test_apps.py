def test_app_imports():
    import django_countdown

    assert django_countdown


def test_appconfig_loads():
    from django.apps import apps

    config = apps.get_app_config("django_countdown")
    assert config.name == "django_countdown"
