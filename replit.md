# replit.md

## Overview

This is a School Study Plan Management System that helps manage and view weekly class schedules. The application provides two main interfaces: a student view for viewing weekly schedules and an admin/teacher view for managing schedule entries. The system tracks subjects, topics, homework assignments, and allows setting the current week number.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Hybrid Backend Architecture
The project has an unusual hybrid setup with two backend technologies:

1. **Python Flask Backend (Primary)** - Located in `main.py`, this handles the actual application logic:
   - Uses SQLite database (`school.db`) for data storage
   - Serves HTML templates from the `templates/` directory
   - Manages schedule entries, configuration, and user sessions
   - Routes include `/`, `/student`, `/admin`, and authentication endpoints

2. **Node.js/Express Wrapper** - The `server/index.ts` spawns the Python Flask process:
   - Acts as a process manager for the Flask application
   - The TypeScript/Express infrastructure exists but delegates to Python

### Frontend Architecture
The project contains two separate frontend approaches:

1. **Flask Jinja Templates (Active)** - Server-rendered HTML templates:
   - `templates/index.html` - Landing page with role selection
   - `templates/student.html` - Weekly schedule view for students
   - `templates/admin.html` - Schedule management interface
   - `templates/teacher.html` - Teacher portal placeholder

2. **React SPA (Scaffolded but unused)** - Located in `client/src/`:
   - Built with Vite, React, and TypeScript
   - Uses shadcn/ui component library with Radix UI primitives
   - Tailwind CSS for styling
   - React Query for data fetching
   - Wouter for client-side routing
   - Currently only has a 404 page implemented

### Database Design
Two database configurations exist:

1. **SQLite (Active with Flask)** - Tables defined in `main.py`:
   - `config` - Key-value store for settings (current week)
   - `schedule` - Weekly schedule entries with week, day, period, subject, topic, homework

2. **PostgreSQL with Drizzle ORM (Scaffolded)** - In `shared/schema.ts`:
   - `users` table with id, username, password
   - Configured via `drizzle.config.ts` with `DATABASE_URL` environment variable

### Build System
- Development: `npm run dev` runs `tsx server/index.ts` which spawns Python Flask
- Production: `npm run build` uses esbuild for server and Vite for client assets
- Database migrations: `npm run db:push` uses Drizzle Kit

## External Dependencies

### Python Dependencies
- Flask - Web framework
- SQLite3 - Database (built into Python)

### Node.js Dependencies (from package.json)
- **UI Framework**: React with shadcn/ui components, Radix UI primitives
- **Styling**: Tailwind CSS, class-variance-authority
- **State Management**: TanStack React Query
- **Routing**: Wouter
- **Forms**: React Hook Form with Zod validation
- **Database**: Drizzle ORM with PostgreSQL driver (pg), connect-pg-simple for sessions
- **Build Tools**: Vite, esbuild, TypeScript

### Environment Variables Required
- `DATABASE_URL` - PostgreSQL connection string (for Drizzle, if enabled)

### Third-Party Services
- No external APIs or services currently integrated
- The scaffolded code includes dependencies for potential integrations: OpenAI, Google Generative AI, Stripe, Nodemailer