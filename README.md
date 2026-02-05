# 🚀 Comprehensive Business Management Suite

This is a powerful and flexible web-based ERP system designed to streamline the operations of a service-based agency. It provides a comprehensive suite of tools for managing customers, products, and applications, with a focus on document handling and workflow automation.

## Key Features

- 🧑‍💼 **Customer Relationship Management (CRM)**: Maintain a centralized database of all your customers, including their personal information, contact details, and a history of their interactions with your agency.
- 📦 **Product Catalog**: Define and manage the services you offer, including their pricing, descriptions, and any associated documents or requirements.
- 📝 **Application Processing**: A sophisticated module for handling customer applications from start to finish. This includes:
  - 📄 **Document Management**: Upload, store, and track all necessary documents for each application.
  - 🤖 **Workflow Automation**: Define and enforce custom workflows for different types of applications, ensuring a consistent and efficient process.
  - ⏱️ **Status Tracking**: Monitor the progress of each application in real-time, from submission to approval.
- 💸 **Invoicing and Payments**: Generate professional invoices for your services and track their payment status. The system supports multiple payment methods and provides a clear overview of your agency's financial health.
- 🔗 **RESTful API**: A comprehensive API that allows for seamless integration with other systems and services. This enables you to extend the functionality of the application and connect it to your existing tools.
- 🎨 **Dynamic Frontend**: The application utilizes a modern and interactive frontend built with a combination of Django templates, Bootstrap, and Javascript frameworks for a responsive and user-friendly experience.
- 🧠 **Advanced Document Processing**:
  - 🛂 **Passport OCR**: Automatically extract information from passport scans, reducing manual data entry and errors.
  - 📑 **PDF Handling**: Generate and process PDF documents as part of the application workflow.
  - 🔍 **MRZ Accuracy Boosters**: Deskewing, adaptive thresholding, and multi-pass OCR retries are applied automatically to squeeze more signal out of low-quality passport scans.
- 🗄️ **Backup and Storage**:
  - 🔒 **Automated Backups**: The system is configured to perform regular backups of the database to a secure cloud storage provider.
  - ☁️ **Cloud Storage Integration**: Store and manage your documents and other files in the cloud for easy access and scalability.
- 👥 **User and Permissions Management**: A granular permissions system allows you to control access to different parts of the application, ensuring that each user only has access to the information and features they need.

## 🛠️ Technical Stack

- 🐍 **Backend**: Django 5, Django REST Framework
- 🖥️ **Frontend**: Django Templates, Bootstrap 5, FontAwesome, Django Unicorn
- 🗃️ **Database**: PostgreSQL
- ⏲️ **Task Queue**: Django Cron
- 🗂️ **File Storage**: Local storage, with support for Dropbox
- 🚢 **Deployment**: Gunicorn, Whitenoise, Docker

## 🦄 Why Django Unicorn?

Django Unicorn is a reactive component framework for Django that allows you to build modern, interactive web applications without leaving the Django ecosystem. We chose Django Unicorn for several reasons:

- **Seamless Integration**: Unicorn is tightly integrated with Django and feels like a natural extension of the core Django experience.
- **Reactive UI**: It enables highly-interactive user interfaces by making AJAX calls in the background and dynamically updating the HTML DOM, similar to frameworks like Vue or React, but with pure Django templates.
- **Simplicity**: Unicorn installs just like any other Django package and is easy to implement. You only need to add a few magic attributes to your Django HTML templates to get started.
- **No JavaScript Required**: You can build interactive components without writing custom JavaScript, reducing complexity and keeping your codebase clean.
- **Modern UX**: It brings the power of reactive components to Django, allowing for a smoother and more engaging user experience.

By using Django Unicorn, our application benefits from a modern, dynamic frontend while maintaining the simplicity and robustness of Django. This choice helps us deliver a better experience to users and developers alike. ✨

## 🚦 Getting Started

To get started with the application, you will need to have Python, Django, and a PostgreSQL database installed. The application is designed to be deployed using Docker, which simplifies the setup process.

1. 📥 Clone the repository.
2. 📦 Install the required dependencies using [uv](https://github.com/astral-sh/uv) and `pyproject.toml`:

   ```sh
   uv pip install --editable .
   ```

3. ⚙️ Configure the database settings in the `.env` file.
4. 🛠️ Run the database migrations using `python manage.py migrate`.
5. 🚀 Start the development server using `python manage.py runserver`.

For a production environment, it is recommended to use the provided Docker setup.

## 📚 Useful Knowledge

This section provides links to detailed guides and how-tos for advanced setup and configuration:

- **[GRAFANA_CLOUD_SETUP.md](howtos/GRAFANA_CLOUD_SETUP.md)**: Comprehensive guide to setting up Grafana Alloy for shipping logs from Docker containers (bs-core, bs-worker, bs-frontend) to Grafana Cloud, including credential setup, configuration, and verification steps.

## Development Utilities

- **Detect inline script tags**: To help centralize JavaScript and avoid inline scripts in templates, run:
  - `scripts/check_inline_script_tags.py` — scans `templates/` for inline script tags (e.g., `<script>...</script>`) and exits with non-zero code if any are found.
  - You can add this to CI or as a git pre-commit hook to prevent regressions.

  ## Internationalization (i18n)

  To enable translations and generate compiled message files used by Django, follow these steps:
  1. Create or edit translation files under `locale/<lang>/LC_MESSAGES/django.po`.
  2. Compile translations to binary `.mo` files with:

  ```sh
  python manage.py compilemessages
  ```

  After compiling, make sure `LOCALE_PATHS` in `business_suite/settings/base.py` points to the `locale/` folder (it already does).

  We include a minimal Indonesian translation for the `Male` and `Female` labels in `locale/id/LC_MESSAGES/django.po`. Run `compilemessages` to generate `django.mo` and have Django display the translated labels during runtime and tests.

## API Usage

## 📡 API Usage

The application exposes a RESTful API for interacting with its various modules. To use the API, you will need to obtain an authentication token. The API endpoints are documented and can be explored using the browsable API feature of Django REST Framework.

---

## 📣 Observability — django-auditlog (Recommended)

We use `django-auditlog` to record model changes (create/update/delete) and optionally record access events. Audit entries are persisted to the database (viewable in Django Admin).

Quick steps:

1. Install the package (using uv):

   ```sh
   uv pip install django-auditlog
   ```

2. Add the app and middleware to your `settings.py`:

   ```python
   INSTALLED_APPS.append('auditlog')
   # Place AuditlogMiddleware after AuthenticationMiddleware so actor can be set automatically
   MIDDLEWARE.insert(MIDDLEWARE.index('django.contrib.auth.middleware.AuthenticationMiddleware') + 1, 'auditlog.middleware.AuditlogMiddleware')
   ```

3. Run migrations for auditlog tables:

   ```bash
   python manage.py migrate auditlog
   ```

4. Register models for auditing (we do this automatically for apps in `LOGGING_MODE`). You can also register manually:

   ```python
   from auditlog.registry import auditlog
   auditlog.register(MyModel, exclude_fields=['sensitive_field'])
   ```

Note: Audit log DB retention is configured via the `AUDITLOG_RETENTION_DAYS` environment variable / Django setting (default: 14 days). A daily Huey cron job runs to prune `auditlog.LogEntry` rows older than this threshold; set `AUDITLOG_RETENTION_SCHEDULE` to change the daily run time or set it to an empty string to disable scheduling.

5. Optional settings you can tweak:
   - `AUDIT_ENABLED` (default: `True`) — Use this env var / Django setting to enable/disable audit forwarding at application startup.
   - `AUDIT_URL_SKIP_LIST` — a list of URL prefixes to ignore when forwarding request-related structured logs.
   - `AUDIT_PURGE_AFTER_DAYS` — retention/fwd purge window for forwarded logs.

Notes:

- We will automatically register models listed in `LOGGING_MODE` for audit logging on app ready.
- If you previously used `django-easy-audit`, run `python manage.py drop_easyaudit --yes` to remove easyaudit DB tables, then remove the package and its `INSTALLED_APPS` entry.
- The project forwards new `auditlog.LogEntry` objects to Loki (structured logs) so you can continue using Loki/Grafana for observability.

---

## Grafana Alloy — scraping container logs & files 🔍

We recommend using **Grafana Alloy** to collect logs from both Docker container stdout/stderr and host log files. This keeps the application from needing to push logs directly to Loki and centralizes collection in Alloy.

Quick checklist:

- Ensure Django writes per-module logs into `logs/` (the project's `Logger` does this by default).
- Ensure the Angular frontend writes to `/logs/frontend.log` (the Dockerfile and compose mounts have been updated to do this).
- Mount the host `${DATA_PATH}/logs` directory into Alloy as `/host_logs` so Alloy can scrape files.

Example Alloy file source (add to `config-local.alloy` / `config-prod.alloy`):

```alloy
loki.source.file "host_logs" {
  paths = ["/host_logs/*.log"]
  forward_to = [loki.write.grafana_cloud.receiver]  # use loki.write.local.receiver for dev
}
```

Example `docker-compose` mounts:

```yaml
services:
  bs-frontend:
    volumes:
      - type: bind
        source: ${DATA_PATH}/logs
        target: /logs

  bs-alloy:
    volumes:
      - type: bind
        source: ${DATA_PATH}/logs
        target: /host_logs:ro
```

Notes:

- Make sure `${DATA_PATH}/logs` exists on the host and is writable by app containers; Alloy only needs read access.
- Avoid duplicating logs: Alloy's Docker scraper collects container stdout, and the file source reads log files — do not add console handlers to the same logger that also writes the file unless you intentionally want duplicate records.

---

This comprehensive business management suite is a powerful tool for any agency looking to streamline its operations, improve efficiency, and provide a better experience for its customers. Its modular design and flexible architecture make it easy to customize and extend to meet the specific needs of your business. ✨
