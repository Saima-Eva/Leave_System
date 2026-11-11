"""One-time script: original.docx -> leave_template.docx (adds {{ placeholders }})."""
from docx import Document

def put(cell, text):
    p = cell.paragraphs[0]
    if p.runs:
        p.runs[0].text = text
        for r in p.runs[1:]:
            r.text = ""
    else:
        p.add_run(text)

d = Document("original.docx")
d.paragraphs[2].runs[1].text = " {{ form_date }} "
t0, t1, t2, t3 = d.tables
r = t0.rows
put(r[0].cells[1], "{{ emp_name }}");   put(r[0].cells[3], "{{ emp_id }}")
put(r[1].cells[1], "{{ join_date }}");  put(r[1].cells[3], "{{ leave_type }}")
put(r[2].cells[1], "{{ job_title }}")
put(r[3].cells[1], "{{ leave_days }}"); put(r[3].cells[3], "{{ start_date }}")
put(r[4].cells[1], "{{ end_date }}");   put(r[4].cells[3], "{{ return_date }}")
put(r[5].cells[1], "{{ address }}")
put(t1.rows[0].cells[1], "{{ replacement_name }}")
put(t1.rows[1].cells[1], "{{ manager_name }}")
put(t2.rows[0].cells[1], "{{ entitlement }}");     put(t2.rows[0].cells[3], "{{ entitlement_until }}")
put(t2.rows[1].cells[1], "{{ hr_leave_period }}"); put(t2.rows[1].cells[3], "{{ hr_period_until }}")
put(t2.rows[2].cells[1], "{{ leave_balance }}")
put(t3.rows[0].cells[1], "{{ yes_box }} Yes          {{ no_box }} No")
d.save("leave_template.docx")
print("template saved")
