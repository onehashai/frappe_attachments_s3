import frappe

def execute():
    frappe.db.set_single_value("S3 File Attachment", "download_file_from_link", 1)