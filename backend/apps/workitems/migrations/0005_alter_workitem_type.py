# Add the test_case WorkItem type (P3-09b: test cases are work items).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("workitems", "0004_workitem_number_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workitem",
            name="type",
            field=models.CharField(
                choices=[
                    ("epic", "Epic"),
                    ("story", "Story"),
                    ("task", "Task"),
                    ("defect", "Defect"),
                    ("test_case", "Test Case"),
                ],
                default="story",
                max_length=16,
            ),
        ),
    ]
