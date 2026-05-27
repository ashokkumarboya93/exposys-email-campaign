# 🚀 Exposys Email Campaign Platform

A production-grade, highly-scalable, multi-tenant email campaign automation platform (SaaS Dashboard) designed to handle batch contact imports, sandboxed email template rendering, concurrent batch email orchestration, and real-time analytics rollups.

Built entirely with **Django 4.2**, **Celery**, **Redis**, **Vanilla JavaScript/CSS**, **Bootstrap 5**, and **Chart.js**.

---

## 🏗️ Project Architecture Overview

The system is split into two primary layers that communicate exclusively via a JSON REST API:

1. **Backend REST API**: Powered by Django REST Framework, utilizing djangorestframework-simplejwt for robust authentication, Celery worker pools for background asynchronous tasks, and Redis as the message broker.
2. **Frontend SaaS Dashboard**: Responsive Multi-Page Admin Interface using modern HSL-driven styling (Vanilla CSS, custom CSS properties, Bootstrap 5, Bootstrap Icons, and Chart.js). Completely wired client-side to the REST API via a custom Axios interceptor wrapper.

### Directory Structure
```
Exposys_Email_Compaign/
├── apps/
│   ├── analytics/          # Analytics processing, daily Beat rollups
│   ├── authentication/     # Custom AdminUser model, JWT authorization backend, System Settings
│   ├── campaigns/          # Batch sending orchestration, email logging, celery tasks
│   ├── contacts/           # Excel/CSV parser, validator, contact management
│   └── templates_engine/   # Jinja2 sandboxed email rendering engine
├── config/                 # Project configuration, settings, routing
├── services/               # Core domain-specific business logic services
│   ├── column_recognizer.py# Smart keywords-to-column mapper
│   ├── data_validator.py   # De-duplicator, email regex, cleaner
│   ├── email_service.py    # SES / Brevo delivery engine factory
│   └── template_renderer.py# Jinja2 rendering pipeline
├── static/                 # Styles (CSS), scripts (JS/Axios), and global utilities
├── templates/              # HTML frontend layout templates
├── manage.py               # Management entrypoint
└── requirements.txt        # Package dependencies
```

---

## ⚡ Comprehensive Feature List

### 1. Robust Authentication & Security
* **Custom AdminUser Model**: Employs UUIDs for security. Includes role-based categorization (`superadmin`, `admin`, `viewer`).
* **Silent Token Refreshes**: A custom `api.js` interceptor automatically refreshes expired Access Tokens using the Refresh Token from session storage, avoiding user session disruptions.
* **Token Blacklisting**: Secure logout that blacklists refresh tokens to prevent replay attacks.
* **Global Settings Manager**: Configure AWS SES, Brevo (Sendinblue), Batch Sizes, and Notification triggers directly from the UI using a singleton `SystemSettings` model.

### 2. Smart Contacts Parsing & Import Wizard
* **Excel/CSV Parsing Service**: Safely parses `.csv`, `.xls`, and `.xlsx` files using `Pandas` and `openpyxl`.
* **Dynamic Column Recognition**: The `column_recognizer` automatically matches arbitrary column headers (e.g., `"Email ID"` ➔ `email`, `"Full Name"` ➔ `name`, `"Mobile"` ➔ `phone`, `"University"` ➔ `college`).
* **Intelligent Validation & Cleaning**: Validates email structures using regex, filters duplicates, cleans phone numbers to 10 digits, and flags invalid records for visual debugging.
* **Select All & Bulk Management**: Features a powerful "Select All" module that grabs all contacts across paginated API limits for bulk deletion or immediate addition to campaigns.

### 3. Sandboxed Template Builder
* **HTML/Jinja2 Environment**: Construct beautiful HTML email templates. Employs Jinja2 Sandbox to prevent arbitrary execution of Python methods within user templates.
* **Dynamic Content Interpolation**: Insert placeholders like `{{name}}` or `{{college}}` which automatically pull from the Contact Database during batch sending.
* **LinkedIn Banner Integration**: Includes pre-seeded "Exposys Internship" templates featuring LinkedIn banner imagery, standard company signatures, and professional layout structuring.

### 4. High-Performance Campaign Orchestrator
* **Campaign Wizard**: Create Campaigns, select audiences (All valid contacts, or specific filtered contacts), and attach Templates.
* **Atomic Celery Orchestration**: The `launch_campaign_task` splits campaign contacts into batch sizes (e.g., 50 at a time) and sends them via Celery group tasks with custom batch delays (e.g., 1-second stagger) to respect mail provider rate limits.
* **Database Concurrency**: Campaign counters are updated using Django's `F()` expressions (`pending_count = F('pending_count') - 1`) to avoid race conditions during concurrent celery execution.
* **Dynamic State Management**: Features the ability to Pause running campaigns, Resume them, and Retry Failed emails specifically.
* **Real-time Live Monitor**: Live UI polling automatically updates progress bars, success counters, and failure logs as Celery workers process the queue.

### 5. Rich Analytics & Histograms
* **KPI Metrics**: Real-time delivery rates, sent counters, success rates, and bounce rates.
* **Data Visualization via Chart.js**: 
  - **Performance Overview**: Sent vs. Failed Area charts over Time (7 days, 30 days, All Time).
  - **Doughnut Charts**: Visualizes current pending vs sent distributions.
  - **Activity Heatmaps**: Tracks Day of Week vs. Hour of Day sending trends using complex backend SQL aggregation.

---

## 🛠️ API Endpoints Reference

The backend exposes a full JSON REST API. Here are the core modules:

**Authentication**
- `POST /api/auth/login/` - Authenticate and retrieve JWT tokens
- `POST /api/auth/refresh/` - Rotate tokens
- `POST /api/auth/logout/` - Blacklist active tokens
- `GET /api/auth/me/` - Get profile

**Settings**
- `GET/POST /api/auth/settings/` - Retrieve or update system configurations (SMTP/AWS/Brevo parameters)

**Contacts**
- `GET /api/contacts/` - List/filter paginated contacts
- `POST /api/contacts/upload/` - Upload CSV/Excel
- `POST /api/contacts/process/` - Confirm and commit parsed import
- `POST /api/contacts/bulk-action/` - Bulk delete selected contacts
- `GET /api/contacts/colleges/` - Fetch unique college lists

**Templates**
- `GET/POST /api/templates/` - CRUD email templates

**Campaigns**
- `GET/POST /api/campaigns/` - Create/List campaigns
- `DELETE /api/campaigns/<id>` - Delete a campaign
- `POST /api/campaigns/<id>/launch/` - Initiate Celery background processing
- `POST /api/campaigns/<id>/pause/` - Pause queue execution
- `POST /api/campaigns/<id>/retry/` - Retry only failed emails
- `GET /api/campaigns/<id>/status/` - Realtime polling status

**Analytics**
- `GET /api/analytics/dashboard/` - Fetch KPIs and trend charts
- `GET /api/analytics/heatmap/` - Fetch DOW vs HOD activity map

---

## ⚙️ Environment Configuration & Setup

### 1. Prerequisites
Ensure you have the following installed on your machine:
* **Python 3.12 or 3.13**
* **Redis Server** (Requires Redis listening on `127.0.0.1:6379`. On Windows, use WSL, Docker, or Memurai).

### 2. Environment Variables (.env)
Create a `.env` file in the project root:
```ini
SECRET_KEY=dev-secret-key-1234567890
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Redis URLs (CRITICAL for Celery)
REDIS_URL=redis://127.0.0.1:6379/0
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1

# Pluggable Email Provider (brevo or ses)
EMAIL_PROVIDER=brevo

# Brevo Configuration (Make sure you whitelist your IP in Brevo Dashboard!)
BREVO_API_KEY=your-api-key
BREVO_SENDER_EMAIL=noreply@example.com
BREVO_SENDER_NAME="Exposys Campaign"
```

### 3. Dependencies Installation
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 4. Database Migrations & Superuser
```powershell
python manage.py makemigrations authentication contacts templates_engine campaigns analytics
python manage.py migrate
python manage.py createsuperadmin --email admin@exposys.com --name "Exposys Admin" --password adminpassword123
```

---

## 🚀 Running the Services

To run the application fully, you **MUST** spin up three separate processes concurrently. If any of these are missing, background campaigns will not execute.

### Process 1: Django HTTP Web Server
Starts the web backend and hosts the HTML pages at port 8000.
```powershell
python manage.py runserver
```
* **Dashboard URL**: [http://127.0.0.1:8000](http://127.0.0.1:8000)

### Process 2: Celery Worker
Runs the background parsing task, smart de-duplication, and handles email delivery orchestration batches.
```powershell
celery -A config worker -Q email_sending,celery -P threads --loglevel=info
```

### Process 3: Celery Beat (Periodic Scheduler)
Schedules periodic aggregation routines, such as daily midnight KPI summaries.
```powershell
celery -A config beat --loglevel=info
```

---

## 🛡️ Troubleshooting & Notes

- **Redis Connection Refused Error**: If Celery fails with `Error 10061 connecting to 127.0.0.1:6379`, your Redis server is offline. Please start Redis via WSL or Docker.
- **Emails Failing immediately**: If your campaigns complete but log as "Failed" with `401 Unauthorized` specifically on Brevo, your IP address has dynamically changed. You must log into `https://app.brevo.com/security/authorised_ips` and whitelist your current IPv4/IPv6 address.
- **Trailing Slashes**: The API is configured strictly to *not* use trailing slashes. `POST /api/campaigns` will work, `POST /api/campaigns/` will throw a 404 error. This is enforced by `DefaultRouter(trailing_slash=False)`.
