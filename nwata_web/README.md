# Nwata Web

Django web app for receiving and processing Nwata agent data.

## Setup

1. Install dependencies: `pip install -r requirements.txt`
2. Run migrations: `python manage.py migrate`
3. Run server: `python manage.py runserver`

## API

The API accepts POST requests to `/api/activity/` with JSON data from the Nwata agent.

### Example Request

```python
import requests

data = {
    "email": "user@example.com",
    "app_name": "Chrome",
    "window_title": "Tab Title",
    "start_time": "2023-01-01T10:00:00Z",
    "end_time": "2023-01-01T10:30:00Z",
    "category": "Work",
    "points": 10,
    "streak": 5,
    "date": "2023-01-01"
}

response = requests.post("http://localhost:8000/api/activity/", json=data)
```

### Models

- **Organization**: Represents an organization with name and subdomain.
- **User**: Users belonging to an organization.
- **ActivityLog**: Logs of user activities (app usage, time spent).
- **Gamification**: Points and streaks per user per date.

### Notes

- A superuser has been created: username `admin`, password `admin`. Use this to log in at `/admin/` and create organizations/users.
- Users must exist in the database before sending data. Create them via Django admin at `/admin/`.
- The dashboard app is set up but not implemented yet. Add views for analytics as needed.