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
        if response is None or 'data' not in response or 'children' not in response['data']:
            print("No response received or unexpected response structure:", response)
            return []
        
        tenants = response['data']['children']
        tenant_info = []
        for tenant in tenants:
            tenant_id = tenant['uuid']
            jobs = self.fetch_job_details(tenant_id)
            storage_info = self.fetch_storage_consumption(tenant_id)
            tenant_info.append({
                "id": tenant_id,
                "name": tenant['name'],
                "usedVms": tenant['usedVms'],
                "jobs": jobs,
                "storage": storage_info
            })
        return tenant_info

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

    def fetch_storage_consumption(self, tenant_id):
        url = f"https://{self.server_address}:4443/t/{tenant_id}/c/router"
        storage_data = {
            "action": "BackupManagement",
            "method": "getBackupRepository",
            "data": [1],
            "type": "rpc",
            "tid": 1
        }
        response, _ = self.run_request(url, storage_data)
        if response and 'data' in response:
            storage_info = {
                "totalStorage": response['data']['size'],
                "freeStorage": response['data']['free'],
                "allocatedStorage": response['data']['allocated'],
                "consumedStorage": response['data']['consumed']
            }
            return storage_info
        else:
            print(f"Failed to fetch storage consumption for tenant {tenant_id}")
            return None

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
            elements.append(Paragraph(f"Tenant Name: {tenant['name']}", styles['Heading1']))
            elements.append(Spacer(1, 0.2 * inch))
            elements.append(self.create_summary_matrix(tenant))
            elements.append(Spacer(1, 0.2 * inch))
            elements.append(self.create_tenant_table(tenant))
            elements.append(Spacer(1, 0.3 * inch))
            elements.extend(self.create_jobs_table(tenant))
            elements.append(Spacer(1, 0.5 * inch))

        doc.build(elements)
        return pdf_path

    def create_summary_matrix(self, tenant):
        table_style = TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
        ])

        job_types = ['BACKUP', 'BACKUP_COPY', 'REPLICATION']
        data = [
            ["Job Type", "Total", "Failed", "Successful"]
        ]
        for job_type in job_types:
            num_total = sum(1 for job in tenant['jobs'] if job['jobType'] == job_type)
            num_failed = sum(1 for job in tenant['jobs'] if job['jobType'] == job_type and
                             job.get('latestRun', {}).get('state') == 'FAILED')
            num_successful = sum(1 for job in tenant['jobs'] if job['jobType'] == job_type and
                                 job.get('latestRun', {}).get('state') == 'SUCCEEDED')
            data.append([job_type, num_total, num_failed, num_successful])

        matrix_table = Table(data, style=table_style)
        return matrix_table

    def create_tenant_table(self, tenant):
        table_style = TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
        ])

        consumed_storage = tenant['storage'].get('consumedStorage', 'N/A')
        total_storage = tenant['storage'].get('totalStorage', 'N/A')

        data = [
            ["Number of Reserved Workloads:", tenant['usedVms']],
            ["Number of Licenses Used:", tenant['usedVms']],
            ["Total Storage Consumption:", f"{consumed_storage} bytes"]
        ]

        table = Table(data, style=table_style)
        return table

    def create_jobs_table(self, tenant):
        jobs = tenant.get('jobs', [])
        elements = []

        styles = getSampleStyleSheet()
        table_style = TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
        ])

        job_types = ['BACKUP', 'BACKUP_COPY', 'REPLICATION']
        for job_type in job_types:
            job_section_title = Paragraph(f"Job Type: {job_type}", styles['Heading2'])
            elements.append(job_section_title)
            elements.append(Spacer(1, 0.1 * inch))

            for job in jobs:
                if job['jobType'] == job_type:
                    latest_run = job.get('latestRun')
                    retention_info = job.get('retentionInfo', 'N/A')

                    if latest_run:
                        vm_names = ", ".join(job.get('vms', []))
                        data = [
                            ['Job Name:', job['name']],
                            ['VMs:', vm_names],
                            ['Last Execution Date:', latest_run['finishDate']],
                            ['State:', latest_run['state']],
                            ['Data Transferred:', f"{latest_run['dataTransferred']} bytes"],
                            ['Data Transferred (Uncompressed):', f"{latest_run['dataTransferredUncompressed']} bytes"],
                            ['Scheduler Name:', latest_run['scheduleName']],
                            ['Execution per Schedule:', 'YES' if latest_run['state'] == "SUCCEEDED" else 'NO'],
                            ['Retention Policy Details:', retention_info]
                        ]
                        elements.append(Table(data, style=table_style))
                        elements.append(Spacer(1, 0.2 * inch))
                    else:
                        elements.append(Table([['No job details available']], style=table_style))
                        elements.append(Spacer(1, 0.2 * inch))

        return elements

def generate_nakivo_report():
    server_address = "172.20.240.1"
    username = "louay"
    password = "louay"

    pdf_generator = NakivoPDFGenerator(server_address, username, password)
    pdf_generator.authenticate()

    tenants = pdf_generator.fetch_tenants()
    tenants_data = []

    for tenant in tenants:
        tenant_data = {
            "name": tenant['name'],
            "jobs": tenant['jobs'],
            "usedVms": tenant['usedVms'],
            "storage": tenant['storage']
        }
        tenants_data.append(tenant_data)

    return pdf_generator.generate_pdf(tenants_data)
