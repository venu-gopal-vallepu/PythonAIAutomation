from junitparser import JUnitXml
import re
from tabulate import tabulate
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Load the JUnit XML file
xml = JUnitXml.fromfile('test-results.xml')

# Regular expression pattern to match '__' followed by any number (which represents the test case ID)
pattern = re.compile(r"__(\d+)$")

# List to store test case results
test_results = []

# Iterate through each test suite and case
for suite in xml:
    for case in suite:
        match = pattern.search(case.name)
        if match:
            test_case_id = match.group(1)
            # Initialize outcome
            outcome = 'Pass'
            # Check if case.result is a list
            if isinstance(case.result, list):
                # Iterate through the results
                for result in case.result:
                    if result._tag == 'failure':
                        outcome = 'Fail'
                        break  # No need to check other results if one has failed
                    elif result._tag == 'skipped':
                        outcome = 'Skipped'
                        break  # Consider skipped if any result is skipped
            elif case.result:  # case.result is not a list, but a single result object
                if case.result._tag == 'failure':
                    outcome = 'Fail'
                elif case.result._tag == 'skipped':
                    outcome = 'Skipped'
            # Append the test case ID and outcome to the results list
            test_results.append([test_case_id, outcome])

# Create the tabular format of the results
table = tabulate(test_results, headers=["Test Case ID", "Outcome"], tablefmt="grid")

# Email configuration
sender_email = "venugopalvallepub4@gmail.com"
receiver_email = "nikhilaniharika04@gmail.com"
subject = "Test Results"
body = f"Please find the test results below:\n\n{table}"

# Create the email message
msg = MIMEMultipart()
msg['From'] = sender_email
msg['To'] = receiver_email
msg['Subject'] = subject
msg.attach(MIMEText(body, 'plain'))

# Send the email
try:
    with smtplib.SMTP('smtp.example.com', 465) as server:
        server.starttls()
        server.login(sender_email, "your_password")
        server.send_message(msg)
    print("Email sent successfully")
except Exception as e:
    print(f"Failed to send email: {e}")
