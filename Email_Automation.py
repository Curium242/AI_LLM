import pywhatkit as kit
import datetime
import time
import requests
from apiclient import discovery
from apiclient import errors
from httplib2 import Http
from oauth2client import file, client, tools
import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import base64
from bs4 import BeautifulSoup
import re
import time
import dateutil.parser as parser
from datetime import datetime
import datetime
import csv

API_URL = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2"
headers = {"Authorization": "Bearer #api"}

SCOPES_GMAIL = 'https://www.googleapis.com/auth/gmail.modify' # we are using modify and not readonly, as we will be marking the messages Read
store = file.Storage('storage.json')
creds = store.get()
if not creds or creds.invalid:
    flow = client.flow_from_clientsecrets("storage.json", SCOPES_GMAIL)
    creds = tools.run_flow(flow, store)
GMAIL = discovery.build('gmail', 'v1', http=creds.authorize(Http()))

user_id =  'me'
label_id_one = 'INBOX'
label_id_two = 'UNREAD'

import re
from dateutil import parser
def get_emails():
    user_id = 'me'
    label_ids = ['INBOX',]
    unread_msgs = GMAIL.users().messages().list(userId=user_id, labelIds=label_ids).execute()
    mssg_list = unread_msgs.get('messages', [0])

    print("Total unread messages in inbox: ", len(mssg_list))
    final_list = []

    for mssg in mssg_list[:1]:
        m_id = mssg['id']
        message = GMAIL.users().messages().get(userId=user_id, id=m_id).execute()
        payld = message['payload']
        headers = payld['headers']

        temp_dict = {header['name']: header['value'] for header in headers if header['name'] in ['Subject', 'Date', 'From']}

        # Include subject in the temporary dictionary
        subject = temp_dict.get('Subject', 'No Subject')

        # Handling email content based on structure
        clean_text = "No readable content found."
        if 'parts' in payld:
            for part in payld['parts']:
                if part['mimeType'] == 'text/plain':
                    data = part['body'].get('data', '')
                    clean_text = base64.urlsafe_b64decode(data.encode('ASCII')).decode('utf-8')
                    break
        else:
            body = payld.get('body', {}).get('data', '')
            if body:
                clean_text = base64.urlsafe_b64decode(body.encode('ASCII')).decode('utf-8')

        soup = BeautifulSoup(clean_text, "lxml")
        message_body = soup.get_text()

        temp_dict['Snippet'] = message['snippet']
        temp_dict['Message_body'] = message_body
        final_list.append(temp_dict)

        # Extract action items using model
        action_item_prompt = """
    Extract the action items, times, dates, and venues from the following mail:
    Use the content from the mail only, dont add anything extra
    Action Items, Times, Dates, Venues, Links :


    """ + message_body
        generated_text = query_model(action_item_prompt)

        action_items_start = generated_text.find("Action Items:")
        times_start = generated_text.find("Times:")
        dates_start = generated_text.find("Dates:")
        venues_start = generated_text.find("Venues:")
        links_start = generated_text.find("Links:")

        body = generated_text[:action_items_start - len("Action Items:")].strip()
        action_items = generated_text[action_items_start:times_start].strip()
        times = generated_text[times_start:dates_start].strip()
        dates = generated_text[dates_start:venues_start].strip()
        venues = generated_text[venues_start:links_start].strip()
        links = generated_text[links_start:].strip()

        # print(body)
        print(action_items + "\n")
        print(times + "\n")
        print(dates + "\n")
        print(venues + "\n")
        print(links)

        # GMAIL.users().messages().modify(userId=user_id, id=m_id, body={'removeLabelIds': ['UNREAD']}).execute()

    print("Total messages processed: ", len(final_list))
    return subject, body, action_items, times, dates, venues, links, temp_dict['From']


def authenticate():
    creds = None

    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json')
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "C:/Users/Astatine/Downloads/credentials.json", SCOPES_TASKS)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return creds
def query_model(email_content):
    prompt = "Please extract action items and relevant details from this email:"

    full_input = f"{prompt}\n{email_content}"
    max_input_tokens = 32000
    if len(full_input) > max_input_tokens:
        allowable_content_length = max_input_tokens - len(prompt) - 10
        email_content = email_content[:allowable_content_length]
        full_input = f"{prompt}\n{email_content}"

    payload = {
        "inputs": full_input,
        "parameters": {
            "max_new_tokens": 512
        }
    }
    response = requests.post(API_URL, headers=headers, json=payload)
    if response.status_code == 200:
        response_data = response.json()
        if 'generated_text' in response_data:
            return response_data['generated_text']
        elif isinstance(response_data, list) and 'generated_text' in response_data[0]:
            return response_data[0]['generated_text']
        return "No actionable data found."
    else:
        raise Exception(f"Failed to retrieve data: {response.status_code} - {response.text}")

SCOPES_TASKS = ['https://www.googleapis.com/auth/tasks']
def extract_and_parse_date(dates_text):
    date_matches = re.findall(r'\d{1,2}/\d{1,2}/\d{4}', dates_text)
    if not date_matches:
        print("No dates found in the text.")
        return None

    try:
        parsed_date = parser.parse(date_matches[0], dayfirst=True)
        formatted_date = parsed_date.strftime('%Y-%m-%dT00:00:00Z')
        return formatted_date
    except ValueError as e:
        print(f"Failed to parse date due to: {str(e)}")
        return None

def create_task(subject, action_items, times, dates, venues, links):
    creds = authenticate()
    service = build('tasks', 'v1', credentials=creds)

    due_date = extract_and_parse_date(dates)
    if not due_date:
        print("Invalid or no due date provided; proceeding without a due date.")

    task = {
        'title': subject,
        'notes': f"{action_items}\n{times}\n{dates}\n{venues}\n{links}",
    }

    if due_date:
        task['due'] = due_date

    try:
        result = service.tasks().insert(tasklist='@default', body=task).execute()
        print('Task created: %s' % result['title'])
    except Exception as e:
        print(f"Failed to create task due to API error: {str(e)}")

subject, body, action_items, times, dates, venues, links, from_mail = get_emails()
create_task(subject, action_items, times, dates, venues, links)

keywords = ['important', 'urgent', 'asap']

def send_whatsapp_message(number, message):
    kit.sendwhatmsg_instantly(number, message, 10, tab_close=True)

if any(keyword in body.lower() or keyword in subject.lower() for keyword in keywords):
    notification_message = f"Urgent email from {from_mail}"
    recepient_number = "+919778064180"
    send_whatsapp_message(recepient_number, notification_message)
    print("WhatsApp message sent")