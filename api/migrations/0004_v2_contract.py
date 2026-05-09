# Generated manually for the EventLight v2 API contract.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


DEFAULT_CATEGORIES = (
    ('Worship', 'worship', 'heart', 'Worship and praise gatherings', 1),
    ('Music', 'music', 'music', 'Music concerts and worship music events', 2),
    ('Conference', 'conference', 'mic', 'Conferences and summits', 3),
    ('Seminar', 'seminar', 'book', 'Seminars and focused learning sessions', 4),
    ('Fellowship', 'fellowship', 'users', 'Fellowship and community gatherings', 5),
    ('Prayer', 'prayer', 'sun', 'Prayer meetings and vigils', 6),
    ('Youth', 'youth', 'award', 'Youth-focused events', 7),
    ('Outreach', 'outreach', 'message', 'Outreach and evangelism events', 8),
    ('Teaching', 'teaching', 'book', 'Teaching and discipleship events', 9),
    ('Children', 'children', 'star', 'Children and family events', 10),
)


def update_category_seed_data(apps, schema_editor):
    category_model = apps.get_model('api', 'Category')
    for name, slug, icon, description, sort_order in DEFAULT_CATEGORIES:
        category, _created = category_model.objects.get_or_create(
            slug=slug,
            defaults={'name': name},
        )
        category.name = name
        category.icon = icon
        category.description = description
        category.sort_order = sort_order
        category.is_active = True
        category.save()

    category_model.objects.filter(slug__in=['bible_study', 'community_service']).update(is_active=False)


def populate_event_category_fk(apps, schema_editor):
    event_model = apps.get_model('api', 'Event')
    category_model = apps.get_model('api', 'Category')
    fallback, _created = category_model.objects.get_or_create(
        slug='worship',
        defaults={'name': 'Worship', 'icon': 'heart', 'sort_order': 1},
    )

    for event in event_model.objects.all():
        category = category_model.objects.filter(slug=getattr(event, 'category', '')).first() or fallback
        event.category_ref_id = category.id
        event.save(update_fields=['category_ref'])


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0003_event_organizer'),
    ]

    operations = [
        migrations.AddField(
            model_name='category',
            name='icon',
            field=models.CharField(default='zap', max_length=40),
        ),
        migrations.AddField(
            model_name='category',
            name='sort_order',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterModelOptions(
            name='category',
            options={'ordering': ['sort_order', 'name'], 'verbose_name_plural': 'categories'},
        ),
        migrations.RunPython(update_category_seed_data, migrations.RunPython.noop),
        migrations.AddField(
            model_name='event',
            name='capacity',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='event',
            name='end_date',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='event',
            name='is_featured',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='event',
            name='location_lat',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name='event',
            name='location_lng',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name='event',
            name='rejection_reason',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='event',
            name='ticket_price',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AlterField(
            model_name='event',
            name='approval_status',
            field=models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending', max_length=20),
        ),
        migrations.AlterField(
            model_name='event',
            name='event_type',
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AlterField(
            model_name='event',
            name='image',
            field=models.ImageField(blank=True, null=True, upload_to='events/'),
        ),
        migrations.AddField(
            model_name='event',
            name='category_ref',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='api.category'),
        ),
        migrations.RunPython(populate_event_category_fk, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='event',
            name='category',
        ),
        migrations.RenameField(
            model_name='event',
            old_name='category_ref',
            new_name='category',
        ),
        migrations.AlterField(
            model_name='event',
            name='category',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='events', to='api.category'),
        ),
        migrations.AlterField(
            model_name='event',
            name='language',
            field=models.CharField(choices=[('english', 'English'), ('yoruba', 'Yoruba'), ('igbo', 'Igbo'), ('hausa', 'Hausa'), ('pidgin', 'Pidgin'), ('french', 'French'), ('multilingual', 'Multilingual')], max_length=80),
        ),
        migrations.AlterField(
            model_name='event',
            name='age_group',
            field=models.CharField(choices=[('all_ages', 'All Ages'), ('children', 'Children (0-12)'), ('teenagers', 'Teenagers (13-19)'), ('young_adults', 'Young Adults (20-35)'), ('adults', 'Adults (36-60)'), ('seniors', 'Seniors (60+)')], max_length=80),
        ),
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type', models.CharField(choices=[('reminder', 'Reminder'), ('event_approved', 'Event approved'), ('event_rejected', 'Event rejected'), ('new_event_nearby', 'New event nearby'), ('rsvp_confirmed', 'RSVP confirmed'), ('event_cancelled', 'Event cancelled')], max_length=40)),
                ('title', models.CharField(max_length=160)),
                ('body', models.CharField(max_length=255)),
                ('detail', models.TextField(blank=True)),
                ('is_read', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('event', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notifications', to='api.event')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='RSVP',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rsvps', to='api.event')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='event_rsvps', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('user', 'event'), name='unique_event_rsvp')],
            },
        ),
    ]
