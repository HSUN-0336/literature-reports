# Setup guide: Daily Literature Report

This repository runs a daily GitHub Actions workflow that collects recent literature and emails a report.

## Step 1 — Add GitHub Secrets

Go to:

Repository → Settings → Secrets and variables → Actions → New repository secret

Add these secrets:

EMAIL_SERVICE = gmail
SENDER_EMAIL = your Gmail address
SENDER_PASSWORD = your Google App Password
RECIPIENT_EMAIL = the email address that should receive the report
OPENALEX_EMAIL = your email address
CROSSREF_EMAIL = your email address

Important: SENDER_PASSWORD must be a Google App Password, not your normal Gmail login password.

## Step 2 — Create a Google App Password

1. Open your Google Account.
2. Go to Security.
3. Enable 2-Step Verification.
4. Go to App passwords.
5. Create an app password for Mail.
6. Copy the generated 16-character password.
7. Save it as the GitHub Secret SENDER_PASSWORD.

## Step 3 — Test manually

Go to:

Repository → Actions → Daily Literature Report → Run workflow

Then check your email and the reports folder.

## Schedule

The workflow is scheduled at both 06:00 UTC and 07:00 UTC.
A time gate inside the workflow only proceeds when Paris time is 08:00, which handles summer/winter time.
