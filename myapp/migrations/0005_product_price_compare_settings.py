from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("myapp", "0004_adminauditlog_newebpaystoremapselection"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="price_compare_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="product",
            name="price_compare_query",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
