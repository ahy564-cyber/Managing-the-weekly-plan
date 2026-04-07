# replit.md

## Overview

School Study Plan Management System for managing weekly class schedules. Provides admin, teacher, and student interfaces. Features Excel/CSV import for master schedules, drag & drop editing (admin only), audit reporting, and Arabic RTL interface with DCS teal (#0d9488) theme.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Backend Architecture
- **Python Flask Backend** (`main.py`) - Main application logic
  - Uses PostgreSQL database via SQLAlchemy ORM
  - Serves HTML templates from `templates/` directory
  - Routes: `/`, `/login`, `/admin`, `/teacher`, `/student` (public landing), `/student/<g_id>/<c_id>` (public view), `/admin/upload_master`, `/admin/upload_teachers`, `/admin/audit_report`, `/admin/activity_log`, `/admin/swap_schedule` (AJAX)
  - Public routes (no login): `/`, `/student`, `/student/<g_id>/<c_id>`
  - Protected routes: `/admin/*` (admin only), `/teacher` (login required)

- **Node.js Proxy** (`server/index.ts`) - HTTP proxy on port 5000
  - Proxies all requests to Flask running on port 5001
  - Required because Replit's port detection works better with Node.js

### Database (PostgreSQL)
Tables defined in `main.py`:
- `grade` - Grade levels (e.g., اول ابتدائي)
- `class` - Classes within grades (e.g., أ, ب)
- `subject` - Master schedule (class_id, day, period, name, school_id)
- `weekly_data` - Weekly teacher data (class_id, week_number, day, period, subject_name, topic, homework, school_id, teacher_id, updated_at)
- `setting` - Key-value store (admin_password, current_week, school_name, etc.)
- `locked_day` - Days locked from teacher editing
- `activity_log` - Audit trail (user_role, action, timestamp, school_id, teacher_name, action_type, target_subject, description)
- `school` - School records (id=1 is default: مدارس الثقافة الرقمية)
- `teacher_account` - Teacher login accounts (name, username, password, school_id, is_active)

**Important**: `school_id` is nullable in subject and weekly_data tables but defaults to 1. The school table MUST have a record with id=1.

**Data Protection**: The `save_fixed_schedule` action only updates `subject_name` in WeeklyData records where teachers have NOT entered topic/homework. Teacher-entered data (topic + homework) is never overwritten by admin master schedule saves. The `teacher_id` and `updated_at` columns on `weekly_data` track who saved each entry and when.

**Database Migration**: `before_request` hook (runs once per worker) ensures `teacher_account` table and `teacher_id`/`updated_at` columns exist. Uses `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE ADD COLUMN IF NOT EXISTS` — safe to run repeatedly.

### Frontend (Flask Jinja Templates)
- `templates/index.html` - Landing page with role selection
- `templates/student_landing.html` - Public grade/class picker for students
- `templates/student.html` - Weekly schedule view for students (public)
- `templates/admin.html` - Admin panel (grades, classes, master schedule, settings, import, audit)
- `templates/teacher.html` - Teacher portal (view subjects read-only, edit topic/homework)
- `templates/login.html` - Unified login (admin + teacher)
- `templates/audit_report.html` - Missing data report
- `templates/activity_log.html` - Full activity log with filtering (teacher name, action type, date) and pagination

### Excel Import Logic (`/admin/upload_master`)
- Skips first 2 header rows (skiprows=2, header=None)
- Column 0: Class name (e.g., "اول ابتدائي" or "Grade - Class")
- Sunday: Columns 1-8, Monday: 9-16, Tuesday: 17-24, Wednesday: 25-32, Thursday: 33-40
- Cleans `\n` characters from cells using `.replace('\n', ' ').strip()`
- UPSERT logic: deletes existing Subject, creates new one; updates or creates WeeklyData
- All records set school_id=1
- **FIX**: Creates/updates WeeklyData for ALL 19 weeks (1-19) — not just current_week; teacher-entered topic/homework always protected
- Pre-loads existing WeeklyData per class into dict for efficient batch processing

### Key Features
- **Edit Grade/Class names**: Inline edit with save button in admin panel
- **Drag & Drop (Deep Move)**: AJAX-based swap via `/admin/swap_schedule` — moves subject_name + topic + homework together; works for both master schedule and weekly override grids; shows toast confirmation
- **Weekly Achievement Dashboard**: Shows completion % + filled/total periods counter; filters by school_id=1
- **Teacher view**: Subject names shown as read-only tags, teachers only edit topic/homework
- **Day locking**: Admin can lock specific days per week to prevent teacher edits
- **Audit report**: Shows individual missing entries per subject/day/period with school_id=1 filter
- **Activity log**: Dedicated `/admin/activity_log` page with filtering (teacher name, action type, date), pagination (50 per page), color-coded badges for action types. Swap/drag-drop operations are logged. All log entries include school_id=1.
- **Teacher Authentication**: Unified login page (admin uses password only or username=admin; teachers use username+password). Teacher accounts managed in admin panel — add individually or bulk upload from Excel (columns: name, username, password). Admin can reset passwords, toggle active/inactive, delete accounts. Teacher/student routes require login.

## Running the Project

- Workflow: `npm run dev` → Node.js proxy (port 5000) → Flask (port 5001)
- Flask port configured via `FLASK_PORT` env var (default 5000, set to 5001 by Node.js)
- Admin login password: `fast490` (stored in settings table)

## Python Dependencies
- Flask, Flask-SQLAlchemy, pandas, openpyxl, gunicorn, waitress

## Environment Variables
- `DATABASE_URL` - PostgreSQL connection string
- `SESSION_SECRET` - Flask session secret
- `FLASK_PORT` - Flask listening port (set by Node.js to 5001)
