from __future__ import unicode_literals

import random
import string
import datetime
import requests
import re
import os
from urllib.parse import urlparse
from frappe.utils import get_url, get_url_to_form
from urllib.parse import parse_qs, urlparse
import boto3
import frappe

from botocore.exceptions import ClientError
from frappe import _
import magic


class S3Operations(object):

    def __init__(self):
        """
        Function to initialise the aws settings from frappe S3 File attachment
        doctype.
        """
        self.s3_settings_doc = frappe.get_doc(
            'S3 File Attachment',
            'S3 File Attachment',
        )
        if (
            self.s3_settings_doc.aws_key and
            self.s3_settings_doc.aws_secret
        ):
            self.S3_CLIENT = boto3.client(
                's3',
                aws_access_key_id=self.s3_settings_doc.aws_key,
                aws_secret_access_key=self.s3_settings_doc.aws_secret,
                region_name=self.s3_settings_doc.region_name,
                endpoint_url="https://s3." + self.s3_settings_doc.region_name + ".amazonaws.com",
            )
            self.BUCKET = self.s3_settings_doc.bucket_name
            self.folder_name = self.s3_settings_doc.folder_name
        else:
            self.S3_CLIENT = boto3.client(
                's3',
                aws_access_key_id=frappe.conf.aws_access_key_id,
                aws_secret_access_key=frappe.conf.aws_secret_access_key,
                region_name=frappe.conf.aws_bucket_region_name,
                endpoint_url="https://s3." + frappe.conf.aws_bucket_region_name + ".amazonaws.com",
            )
            self.BUCKET = frappe.conf.aws_bucket_name
            if frappe.conf.domain == "onehash.ai":
                self.folder_name = "production/site_files"
            else:
                self.folder_name = "staging/site_files"

    def strip_special_chars(self, file_name):
        """
        Strips file charachters which doesnt match the regex.
        """
        regex = re.compile('[^0-9a-zA-Z._-]')
        file_name = regex.sub('', file_name)
        return file_name

    def key_generator(self, file_name, parent_doctype, parent_name):
        """
        Generate keys for s3 objects uploaded with file name attached.
        """
        hook_cmd = frappe.get_hooks().get("s3_key_generator")
        if hook_cmd:
            try:
                k = frappe.get_attr(hook_cmd[0])(
                    file_name=file_name,
                    parent_doctype=parent_doctype,
                    parent_name=parent_name
                )
                if k:
                    return k.rstrip('/').lstrip('/')
            except:
                pass

        file_name = file_name.replace(' ', '_')
        file_name = self.strip_special_chars(file_name)
        key = ''.join(
            random.choice(
                string.ascii_uppercase + string.digits) for _ in range(8)
        )

        today = datetime.datetime.now()
        year = today.strftime("%Y")
        month = today.strftime("%m")
        day = today.strftime("%d")

        doc_path = None

        if not doc_path:
            if self.folder_name:
                final_key = self.folder_name + "/" + year + "/" + month + \
                    "/" + day + "/" + parent_doctype + "/" + key + "_" + \
                    file_name
            else:
                final_key = year + "/" + month + "/" + day + "/" + \
                    parent_doctype + "/" + key + "_" + file_name
            return final_key
        else:
            final_key = doc_path + '/' + key + "_" + file_name
            return final_key

    def upload_files_to_s3_with_key(
            self, file_path, file_name, is_private, parent_doctype, parent_name
    ):
        """
        Uploads a new file to S3.
        Strips the file extension to set the content_type in metadata.
        """
        mime_type = magic.from_file(file_path, mime=True)
        # frappe.msgprint(file_name)
        # frappe.msgprint("File Name Before")
        file_name = file_name.encode('ascii', 'replace')
        file_name = file_name.decode("utf-8")
        # frappe.msgprint(file_name)
        # frappe.msgprint("File Name After")
        key = self.key_generator(file_name, parent_doctype, parent_name)
        content_type = mime_type
        try:
            if is_private:
                self.S3_CLIENT.upload_file(
                    file_path, self.BUCKET, key,
                    ExtraArgs={
                        "ContentType": content_type,
                        "Metadata": {
                            "ContentType": content_type,
                            "file_name": file_name
                        }
                    }
                )
            else:
                self.S3_CLIENT.upload_file(
                    file_path, self.BUCKET, key,
                    ExtraArgs={
                        "ContentType": content_type,
                        "ACL": 'public-read',
                        "Metadata": {
                            "ContentType": content_type,

                        }
                    }
                )

        except boto3.exceptions.S3UploadFailedError:
            frappe.throw(frappe._("File Upload Failed. Please try again."))
        return key,file_name

    def delete_from_s3(self, key):
        """Delete file from s3"""
        self.s3_settings_doc = frappe.get_doc(
            'S3 File Attachment',
            'S3 File Attachment',
        )
        if (
            self.s3_settings_doc.aws_key and
            self.s3_settings_doc.aws_secret
        ):
            if self.s3_settings_doc.delete_file_from_cloud:
                S3_CLIENT = boto3.client(
                    's3',
                    aws_access_key_id=self.s3_settings_doc.aws_key,
                    aws_secret_access_key=self.s3_settings_doc.aws_secret,
                    region_name=self.s3_settings_doc.region_name,
                )

                try:
                    S3_CLIENT.delete_object(
                        Bucket=self.s3_settings_doc.bucket_name,
                        Key=key
                    )
                except ClientError:
                    frappe.throw(frappe._("Access denied: Could not delete file"))
        else:
            S3_CLIENT = boto3.client(
                's3',
                aws_access_key_id=frappe.conf.aws_access_key_id,
                aws_secret_access_key=frappe.conf.aws_secret_access_key,
                region_name=frappe.conf.aws_bucket_region_name,
            )

            try:
                S3_CLIENT.delete_object(
                    Bucket=frappe.conf.aws_bucket_name,
                    Key=key
                )
            except ClientError:
                frappe.throw(frappe._("Access denied: Could not delete file"))

    def read_file_from_s3(self, key):
        """
        Function to read file from a s3 file.
        """
        return self.S3_CLIENT.get_object(Bucket=self.BUCKET, Key=key)

    def get_url(self, key, file_name=None):
        """
        Return url.

        :param bucket: s3 bucket name
        :param key: s3 object key
        """
        if self.s3_settings_doc.signed_url_expiry_time:
            self.signed_url_expiry_time = self.s3_settings_doc.signed_url_expiry_time # noqa
        else:
            self.signed_url_expiry_time = 120
        params = {
                'Bucket': self.BUCKET,
                'Key': key,

        }
        if file_name:
            params['ResponseContentDisposition'] = 'filename={}'.format(file_name)

        url = self.S3_CLIENT.generate_presigned_url(
            'get_object',
            Params=params,
            ExpiresIn=self.signed_url_expiry_time,
        )

        return url

def extract_key_and_file_name(file_url):
    parsed_url = urlparse(file_url)
    query_params = parse_qs(parsed_url.query)

    key = query_params.get("key", [None])[0]
    file_name = query_params.get("file_name", [None])[0]

    return key, file_name

@frappe.whitelist()
def transfer_file(doc, method):
    """
    Transfer file from public to private and vice-versa
    """
    frappe.log_error("is doc new?", doc.is_new())
    if doc.is_folder or doc.is_new():
        return

    path = doc.file_url
    if path and path.startswith(("http://", "https://")) and doc.is_private != doc.get_db_value("is_private"):
        if doc.doctype == "File" and not doc.attached_to_doctype:
            parent_doctype = doc.doctype
            parent_name = doc.name
        else:
            parent_doctype = doc.attached_to_doctype
            parent_name = doc.attached_to_name

        ignore_s3_upload_for_doctype = frappe.local.conf.get('ignore_s3_upload_for_doctype') or ['Data Import']
        if parent_doctype not in ignore_s3_upload_for_doctype:
            key,filename = s3_upload.upload_files_to_s3_with_key(
                path, doc.file_name,
                doc.is_private, parent_doctype,
                parent_name
            )
            s3.delete_from_s3(doc.content_hash)

            if doc.is_private:
                method = "frappe_s3_attachment.controller.generate_file"
                site_base_url = get_url()
                file_url = """{0}/api/method/{1}?key={2}&file_name={3}""".format(site_base_url, method, key, filename)
            else:
                file_url = '{}/{}/{}'.format(
                    s3_upload.S3_CLIENT.meta.endpoint_url,
                    s3_upload.BUCKET,
                    key
                )
            frappe.db.sql("""UPDATE `tabFile` SET file_url=%s, folder=%s,
                old_parent=%s, content_hash=%s WHERE name=%s""", (
                file_url, doc.folder, doc.old_parent, key, doc.name))

            # From this PR, this code is unuseful
            # https://github.com/zerodha/frappe-attachments-s3/pull/39
            # if frappe.get_meta(parent_doctype).get('image_field'):
            #     frappe.db.set_value(parent_doctype, parent_name, frappe.get_meta(
            #         parent_doctype).get('image_field'), file_url)

            frappe.db.commit()
            doc.reload()

@frappe.whitelist()
def file_upload_to_s3(doc, method):
    """
    check and upload files to s3. the path check and
    """
    if doc.is_folder == True:
        return
    s3_upload = S3Operations()
    path = doc.file_url
    if path and path.startswith(("http://", "https://")):
        if "frappe_s3_attachment.controller.generate_file" in path:
            site_base_url = frappe.utils.get_url()
            key, file_name = extract_key_and_file_name(path)
            signed_url_request = f"{site_base_url}/api/method/frappe_s3_attachment.controller.generate_signed_url?key={key}&file_name={file_name}"
            response = requests.get(signed_url_request)

            if response.status_code == 200:
                signed_url = response.json().get("message")
            else:
                frappe.throw(f"Failed to generate signed URL: {response.status_code}")
        else:
            signed_url = path
            file_name = doc.file_name

        response = requests.get(signed_url, stream=True)
        if response.status_code == 200:
            site_path = frappe.utils.get_site_path()

            # Define local path (match Frappe's expected storage location)
            if doc.is_private:
                file_path = os.path.join(site_path, "private", "files", file_name)
            else:
                file_path = os.path.join(site_path, "public", "files", file_name)

            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            # Save the file locally
            with open(file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024):
                    f.write(chunk)

            # Update path to local
            if not doc.is_private:
                path = '/files/' + file_name
            else:
                path = '/private/files/' + file_name
        else:
            frappe.throw(f"Failed to download file from {path} (Status: {response.status_code})")
    site_path = frappe.utils.get_site_path()
    if doc.doctype == "File" and not doc.attached_to_doctype:
        parent_doctype = doc.doctype
        parent_name = doc.name
    else:
        parent_doctype = doc.attached_to_doctype
        parent_name = doc.attached_to_name
    ignore_s3_upload_for_doctype = frappe.local.conf.get('ignore_s3_upload_for_doctype') or ['Data Import']
    if parent_doctype not in ignore_s3_upload_for_doctype:
        if not doc.is_private:
            file_path = site_path + '/public' + path
        else:
            file_path = site_path + path
        key,filename = s3_upload.upload_files_to_s3_with_key(
            file_path, doc.file_name,
            doc.is_private, parent_doctype,
            parent_name
        )

        if doc.is_private:
            method = "frappe_s3_attachment.controller.generate_file"
            site_base_url = get_url()
            file_url = """{0}/api/method/{1}?key={2}&file_name={3}""".format(site_base_url, method, key, filename)
        else:
            file_url = '{}/{}/{}'.format(
                s3_upload.S3_CLIENT.meta.endpoint_url,
                s3_upload.BUCKET,
                key
            )
        frappe.db.sql("""UPDATE `tabFile` SET file_url=%s, folder=%s,
            old_parent=%s, content_hash=%s WHERE name=%s""", (
            file_url, doc.folder, doc.old_parent, key, doc.name))

        # From this PR, this code is unuseful
        # https://github.com/zerodha/frappe-attachments-s3/pull/39
        # if frappe.get_meta(parent_doctype).get('image_field'):
        #     frappe.db.set_value(parent_doctype, parent_name, frappe.get_meta(
        #         parent_doctype).get('image_field'), file_url)

        frappe.db.commit()
        doc.reload()
        os.remove(file_path)


@frappe.whitelist()
def generate_file(key=None, file_name=None):
    """
    Function to stream file from s3.
    """
    if key:
        s3_upload = S3Operations()
        signed_url = s3_upload.get_url(key, file_name)
        frappe.local.response["type"] = "redirect"
        frappe.local.response["location"] = signed_url
    else:
        frappe.local.response['body'] = "Key not found."
    return

@frappe.whitelist(allow_guest=True)
def generate_signed_url(key=None, file_name=None):
    """
    Function to stream file from s3.
    """
    if key:
        s3_upload = S3Operations()
        signed_url = s3_upload.get_url(key, file_name)
        return signed_url
    else:
        frappe.throw(_("Key not found."))
    return


def upload_existing_files_s3(name):
    """
    Function to upload all existing files.
    """
    file_doc_name = frappe.db.get_value('File', {'name': name})
    if file_doc_name:
        doc = frappe.get_doc('File', name)
        s3_upload = S3Operations()
        path = doc.file_url
        site_path = frappe.utils.get_site_path()
        parent_doctype = doc.attached_to_doctype
        parent_name = doc.attached_to_name
        if not doc.is_private:
            file_path = site_path + '/public' + path
        else:
            file_path = site_path + path
        key,filename = s3_upload.upload_files_to_s3_with_key(
            file_path, doc.file_name,
            doc.is_private, parent_doctype,
            parent_name
        )

        if doc.is_private:
            method = "frappe_s3_attachment.controller.generate_file"
            site_base_url = get_url()
            file_url = """{0}/api/method/{1}?key={2}""".format(site_base_url, method, key)
        else:
            file_url = '{}/{}/{}'.format(
                s3_upload.S3_CLIENT.meta.endpoint_url,
                s3_upload.BUCKET,
                key
            )

        # Remove file from local.
        os.remove(file_path)

        frappe.db.sql(
            """UPDATE `tabFile` SET file_url=%s, folder=%s,
            old_parent=%s, content_hash=%s WHERE name=%s""",
            (file_url, "Home/Attachments", "Home/Attachments", key, doc.name),
        )
        frappe.db.commit()


def s3_file_regex_match(file_url):
    """
    Match the public file regex match.
    """
    return re.match(
        r'^(https:|/api/method/frappe_s3_attachment.controller.generate_file)',
        file_url
    )


@frappe.whitelist()
def migrate_existing_files():
    """
    Function to migrate the existing files to s3.
    """

    files_list = frappe.get_all(
        'File',
        fields=['name', 'file_url']
    )
    for file in files_list:
        if file['file_url']:
            if not s3_file_regex_match(file['file_url']):
                upload_existing_files_s3(file['name'])
    return True


def delete_from_cloud(doc, method):
    """Delete file from s3"""
    if doc.is_folder == True:
        return
    s3 = S3Operations()
    s3.delete_from_s3(doc.content_hash)


@frappe.whitelist()
def ping():
    """
    Test function to check if api function work.
    """
    return "pong"