from flask import Flask, render_template, redirect, url_for, send_file
import generate_pdf  # Ensure generate_pdf.py is in the same directory

app = Flask(__name__)

# Define routes for each solution
@app.route('/')
def dashboard():
    solutions = {
        'backup': {'name': 'Backup Solution', 'details': 'Summary of backup solution metrics.', 'route': 'backup'},
        'email': {'name': 'Email Solution', 'details': 'Summary of email solution metrics.', 'route': 'email'},
        'iaas': {'name': 'IaaS Solution', 'details': 'Summary of IaaS solution metrics.', 'route': 'iaas'}
    }
    return render_template('dashboard.html', solutions=solutions)

# Route to navigate to Backup Solution page
@app.route('/backup')
def backup():
    solution = {"name": "Backup Solution", "details": "Details about the backup solution."}
    return render_template('backup.html', solution=solution)

# Route to navigate to Email Solution page
@app.route('/email')
def email():
    return render_template('email.html')

# Route to navigate to IaaS Solution page
@app.route('/iaas')
def iaas():
    return render_template('iaas.html')

# Route to generate the Backup PDF report
@app.route('/generate_backup_report')
def generate_backup_report():
    pdf_path = generate_pdf.generate_nakivo_report()
    return send_file(pdf_path, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
