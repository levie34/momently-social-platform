MOMENTLY — Social Surprises MVP
================================

What this version includes
- New brand: MOMENTLY — "Make someone's day."
- Account registration, login, logout and editable profile
- Public community feed for surprises and moments
- Create a surprise page for couples, friends, family, birthdays and other occasions
- Shareable surprise links (copy the link from the surprise page)
- Emoji reactions and comments
- Dashboard showing your creations and received reactions
- Report button for community moderation
- Admin moderation dashboard (hide reported content and manage posts)
- SQLite database; no paid APIs or paid services required to run locally

IMPORTANT MVP LIMITS
- This is a starter MVP, not a finished large-scale production social network.
- Use fictional/demo data while testing. Do not collect sensitive personal information.
- Email verification, password reset emails, image uploads, private messaging, push notifications,
  real-time chat, payments, and automated content moderation are not implemented yet.
- User-generated content is public when marked Public. Do not post private details.
- On free hosting, local SQLite files may be erased on some platforms during restarts/redeploys.
  For durable shared production data, configure a managed database and backups before launch.
- The admin account is created from ADMIN_USERNAME and ADMIN_PASSWORD environment variables.
  Change both before publishing. Never publish the .env file or secrets.

RUN ON WINDOWS (PowerShell)
1. Extract this ZIP.
2. Open PowerShell in the extracted Momently_Social_Platform folder.
3. Create a virtual environment:
   python -m venv .venv
4. Activate it:
   .\.venv\Scripts\Activate.ps1
   If PowerShell blocks activation, run:
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   .\.venv\Scripts\Activate.ps1
5. Install dependencies:
   python -m pip install -r requirements.txt
6. Start the site:
   python app.py
7. Open:
   http://127.0.0.1:5000

FIRST ADMIN LOGIN
- Username: admin
- Password: ChangeMe-123!
These are local-development defaults only. Set ADMIN_USERNAME, ADMIN_PASSWORD and SECRET_KEY
as environment variables before hosting publicly. Do not use the defaults on a public site.

HOSTING NOTES
- Render supports free web services for demos, but free services sleep when idle and their local
  filesystem is ephemeral. See https://render.com/docs/free
- PythonAnywhere has a free account, with current limits. See https://www.pythonanywhere.com/
- Read the host's current terms and storage limits before deploying.
- A free host is fine for testing; a public social platform needs durable database storage,
  moderation, backups, privacy terms and security review before real users rely on it.

Suggested next upgrades
1. Email verification and password reset
2. Persistent PostgreSQL database and database migrations
3. Image uploads using a trusted object-storage service
4. Follow/friend system and private messages
5. Invite-only beta, community guidelines and stronger moderation tools
6. Accessibility, mobile testing, security testing and privacy policy
