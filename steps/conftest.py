import time
import pytest
from selenium import webdriver
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

test_results = {}


@pytest.fixture()
def setup(request):
    driver = webdriver.Chrome()
    driver.maximize_window()
    return {
        'driver': driver
    }


def pytest_runtest_makereport(item, call):
    if call.when == 'call':
        # Extract test case ID from the test name
        pattern = re.compile(r"__(\d+)$")
        match = pattern.search(item.name)
        if match:
            test_case_id = match.group(1)
            # Determine the outcome of the test
            if call.excinfo is not None:
                outcome = 'Fail'
            else:
                outcome = 'Pass'
            # Store the result in the dictionary
            test_results[test_case_id] = {
                'outcome': outcome,
                'duration': call.stop - call.start
            }


def pytest_sessionfinish(session, exitstatus):
    # Print the test results at the end of the session
    print("\nTest Results:")
    for test_case_id, result in test_results.items():
        print(f"Test Case ID: {test_case_id}, Outcome: {result['outcome']}, Duration: {result['duration']:.2f} seconds")

    # Create the HTML table format of the results
    table_data = [
        f"<tr><td>{test_case_id}</td><td style='color: {"red" if result['outcome'] == "Fail" else "blue"}'><b>{result['outcome']}</b></td><td>{result['duration']:.2f} seconds</td></tr>"
        for test_case_id, result in test_results.items()
    ]
    table = f"""
    <html>
    <head>
    <style>
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            border: 1px solid black;
            padding: 8px;
            text-align: left;
        }}
        th {{
            background-color: #f2f2f2;
        }}
        tr:nth-child(even) {{
            background-color: #f2f2f2;
        }}
    </style>
    </head>
    <body>
    <h2>Test Results</h2>
    <table>
        <tr>
            <th>Test Case ID</th>
            <th>Outcome</th>
            <th>Duration</th>
        </tr>
        {''.join(table_data)}
    </table>
    </body>
    </html>
    """

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
    msg.attach(MIMEText(body, 'html'))

    # Send the email with retry mechanism
    retries = 3
    for attempt in range(retries):
        try:
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(sender_email, "dwlckvkgmyqzhsvu")
                server.send_message(msg)
            print("Email sent successfully")
            break
        except Exception as e:
            print(f"Failed to send email on attempt {attempt + 1}: {e}")
            if attempt < retries - 1:
                time.sleep(5)  # Wait for 5 seconds before retrying
            else:
                print("All attempts to send email failed")
