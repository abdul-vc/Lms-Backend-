import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0001_initial'),
        ('users', '0001_initial'),
        ('courses', '0010_alter_course_category'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='is_scorm',
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name='ScormPackage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('package_file', models.FileField(blank=True, null=True, upload_to='scorm_zips/')),
                ('extracted_dir', models.CharField(max_length=500)),
                ('manifest_id', models.CharField(blank=True, default='', max_length=255)),
                ('title', models.CharField(blank=True, default='', max_length=255)),
                ('version', models.CharField(default='1.2', max_length=50)),
                ('launch_url', models.CharField(blank=True, default='', max_length=500)),
                ('schema_version', models.CharField(blank=True, default='', max_length=50)),
                ('mastery_score', models.FloatField(blank=True, null=True)),
                ('raw_manifest_xml', models.TextField(blank=True, default='')),
                ('sco_structure', models.JSONField(blank=True, default=list)),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('course', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='scorm_package', to='courses.course')),
                ('organization', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='scorm_packages', to='organizations.organization')),
            ],
        ),
        migrations.CreateModel(
            name='ScormTracking',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('lesson_status', models.CharField(choices=[('not attempted', 'Not Attempted'), ('incomplete', 'Incomplete'), ('completed', 'Completed'), ('passed', 'Passed'), ('failed', 'Failed'), ('browsed', 'Browsed')], default='not attempted', max_length=50)),
                ('lesson_location', models.CharField(blank=True, default='', max_length=255)),
                ('suspend_data', models.TextField(blank=True, default='')),
                ('score_raw', models.FloatField(blank=True, null=True)),
                ('score_max', models.FloatField(blank=True, null=True)),
                ('score_min', models.FloatField(blank=True, null=True)),
                ('score_scaled', models.FloatField(blank=True, null=True)),
                ('session_time', models.CharField(blank=True, default='', max_length=50)),
                ('total_time_seconds', models.IntegerField(default=0)),
                ('cmi_data', models.JSONField(blank=True, default=dict)),
                ('first_accessed', models.DateTimeField(auto_now_add=True)),
                ('last_accessed', models.DateTimeField(auto_now=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='scorm_trackings', to='courses.course')),
                ('organization', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='scorm_trackings', to='organizations.organization')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='scorm_trackings', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'unique_together': {('user', 'course')},
            },
        ),
    ]
