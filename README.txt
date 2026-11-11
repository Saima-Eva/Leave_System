Leave Form System (Employee submit -> HR download)

Run:
  pip install -r requirements.txt
  python app.py            -> http://localhost:5000

First login (HR): username = hr   password = hr12345   (age password change korun)
HR "Employees" page theke employee account banan; employee nijer login diye leave request submit kore.
HR "All Requests" theke Review (Section 2-4 fill) ar Download .docx.

Production: SECRET_KEY environment variable set korun, HTTPS + gunicorn/waitress use korun.
Word layout change korte leave_template.docx edit korun ({{ ... }} tag rekhe).
