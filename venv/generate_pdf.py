import requests
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class NakivoPDFGenerator:
    def __init__(self, server_address, username, password):
        self.server_address = server_address
        self.username = username
        self.password = password
        self.cookies = None

    def run_request(self, url, data):
        headers = {'Content-Type': 'application/json'}
        try:
            response = requests.post(url, json=data, headers=headers, cookies=self.cookies, verify=False)
            response.raise_for_status()
            return response.json(), response.cookies
        except requests.exceptions.RequestException as e:
            print(f"Error making request to {url}: {e}")
            return None, None

    def authenticate(self):
        url = f"https://{self.server_address}:4443/c/router"
        auth_data = {
            "action": "AuthenticationManagement",
            "method": "login",
            "data": [self.username, self.password, False],
            "type": "rpc",
            "tid": 1
        }
        response, self.cookies = self.run_request(url, auth_data)
        if response is None:
            print("Authentication failed.")
        return self.cookies

    def fetch_tenants(self):
        url = f"https://{self.server_address}:4443/c/router"
        tenant_data = {
            "action": "MultitenancyManagement",
            "method": "getTenants",
            "data": [{"filter": {"start": 0, "count": 3, "criteria": []}}],
            "type": "rpc",
            "tid": 1
        }
        response, _ = self.run_request(url, tenant_data)
        if response and 'data' in response and 'children' in response['data']:
            tenants = response['data']['children']
            tenant_info = [{"id": tenant['uuid'], "name": tenant['name'], "usedVms": tenant['usedVms']} for tenant in tenants]
            return tenant_info
        else:
            print("Unexpected response structure or no response:", response)
            return []

    def fetch_job_details(self, tenant_id):
        url = f"https://{self.server_address}:4443/t/{tenant_id}/c/router"
        job_info_data = {
            "action": "JobSummaryManagement",
            "method": "getProcessedVms",
            "data": [{"periodMinutes": 1440}],
            "type": "rpc",
            "tid": 1
        }
        response, _ = self.run_request(url, job_info_data)
        if response is None or 'data' not in response or 'jobInfoList' not in response['data']:
            print(f"Failed to fetch job details for tenant {tenant_id}")
            return []

        job_info_list = response['data']['jobInfoList']
        jobs = []
        for job_info in job_info_list:
            job = {
                "name": job_info['name'],
                "jobType": job_info['jobType'],
                "latestRun": None,
                "retentionInfo": "N/A",
                "vms": [vm['name'] for vm in job_info['vmInfoList']]
            }
            if job_info['vmInfoList']:
                vm_info = job_info['vmInfoList'][0]
                run_info_list = vm_info.get('runInfoList', [])
                if run_info_list:
                    latest_run = run_info_list[-1]
                    job["latestRun"] = {
                        "state": latest_run['state'],
                        "startDate": latest_run['startDate'],
                        "finishDate": latest_run['finishDate'],
                        "dataTransferred": latest_run['dataTransferred'],
                        "dataTransferredUncompressed": latest_run['dataTransferredUncompressed'],
                        "scheduleName": latest_run['scheduleName']
                    }
                    job["retentionInfo"] = latest_run.get('retentionInfo', 'N/A')

            jobs.append(job)
        return jobs

    def generate_pdf(self, tenants_data):
        pdf_path = "/tmp/nakivo_report.pdf"
        doc = SimpleDocTemplate(pdf_path, pagesize=letter)
        elements = []

        styles = getSampleStyleSheet()
        title_style = styles['Title']
        normal_style = styles['Normal']

        title_style.fontSize = 24
        title_style.textColor = colors.darkblue
        normal_style.fontSize = 12

        title = Paragraph("Nakivo Backup Daily Report", title_style)
        report_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        date_time_text = Paragraph(f"Report generated on: {report_datetime}", normal_style)

        elements.extend([title, Spacer(1, 0.1 * inch), date_time_text])
        elements.append(Spacer(1, 0.2 * inch))

        for tenant in tenants_data:
            elements.append(self.create_tenant_table(tenant))
            elements.extend(self.create_jobs_table(tenant))

        def add_page_numbers(canvas, doc):
            page_num = canvas.getPageNumber()
            text = f"Page {page_num}"
            canvas.setFont('Helvetica', 10)
            canvas.drawString(letter[0] - inch, inch, text)

        doc.build(elements, onLaterPages=add_page_numbers, onFirstPage=add_page_numbers)
        return pdf_path

    def create_tenant_table(self, tenant):
        table_style = TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
        ])
        num_jobs = len(tenant['jobs'])
        data = [
            ['Tenant Name:', tenant['name']],
            ['Number of Jobs:', num_jobs],
            ['Managed VMs:', tenant['usedVms']]
        ]
        return Table(data, style=table_style)

    def create_jobs_table(self, tenant):
        jobs = tenant.get('jobs', [])
        elements = []
        table_style = TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('BACKGROUND', (0, 0), (0, 0), colors.lightblue),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
        ])
        for job in jobs:
            latest_run = job.get('latestRun')
            retention_info = job.get('retentionInfo', 'N/A')
            if latest_run:
                vm_names = ", ".join(job.get('vms', []))
                data = [
                    ['Job Name:', job['name']],
                    ['Job Type:', job['jobType']],
                    ['VMs:', vm_names],
                    ['Last Run Date:', latest_run['finishDate']],
                    ['State:', latest_run['state']],
                    ['Data Transferred:', f"{latest_run['dataTransferred']} bytes"],
                    ['Data Transferred (Uncompressed):', f"{latest_run['dataTransferredUncompressed']} bytes"],
                    ['Schedule Name:', latest_run['scheduleName']],
                    ['Scheduled Run:', 'YES' if latest_run['state'] == "SUCCEEDED" else 'NO'],
                    ['Retention Policy Details:', retention_info]
                ]
                elements.append(Table(data, style=table_style))
                elements.append(Spacer(1, 0.2 * inch))
            else:
                elements.append(Table([['No job details available']], style=table_style))
                elements.append(Spacer(1, 0.2 * inch))
        return elements

def generate_nakivo_report():
    server_address = "172.28.80.1"
    username = "louay"
    password = "louay"

    pdf_generator = NakivoPDFGenerator(server_address, username, password)
    pdf_generator.authenticate()

    tenants = pdf_generator.fetch_tenants()
    tenants_data = []

    for tenant in tenants:
        jobs = pdf_generator.fetch_job_details(tenant['id'])
        if jobs:
            tenant_data = {"name": tenant['name'], "jobs": jobs, "usedVms": tenant['usedVms']}
            tenants_data.append(tenant_data)

    return pdf_generator.generate_pdf(tenants_data)
