
from flask import Flask, jsonify, render_template, request
from openqa_client.client import OpenQA_Client
from openqa_client.exceptions import RequestError
from urllib.parse import urlparse
import logging
import re

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    log_url = request.json['log_url']
    job_id = "unknown"
    hostname = None
    debug_log = []
    try:
        app.logger.info(f"Received analysis request for URL: {log_url}")
        parsed_url = urlparse(log_url)
        hostname = parsed_url.hostname
        debug_log.append({"level": "info", "message": f"Parsed hostname: {hostname}"})
        app.logger.info(f"Parsed hostname: {hostname}")

        # Extract job ID from the URL path
        match = re.search(r'/tests/(\d+)', parsed_url.path)
        if not match:
            error_msg = 'Error: Could not find job ID in the URL.'
            debug_log.append({"level": "error", "message": error_msg})
            app.logger.error(error_msg)
            return jsonify({"error": error_msg, "debug_log": debug_log}), 400
        job_id = match.group(1)
        debug_log.append({"level": "info", "message": f"Extracted job ID: {job_id}"})
        app.logger.info(f"Extracted job ID: {job_id}")

        client = OpenQA_Client(server=hostname)
        # The following line disables SSL certificate verification.
        # This is a workaround for the 'CERTIFICATE_VERIFY_FAILED' error,
        # which typically occurs when the server uses a self-signed or
        # internal CA certificate not trusted by your system.
        # WARNING: This is insecure and should NOT be used in production
        # without understanding the risks. A better solution is to provide
        # a path to your CA bundle: client.session.verify = '/path/to/ca.pem'
        client.session.verify = False
        debug_log.append({"level": "error", "message": "WARNING: SSL certificate verification has been disabled. This is insecure."})
        app.logger.warning("SSL certificate verification has been disabled.")

        debug_log.append({"level": "info", "message": f"Initialized OpenQA_Client for server: {hostname}"})
        app.logger.info(f"Initialized OpenQA_Client for server: {hostname}")

        debug_log.append({"level": "info", "message": f"Fetching details for job {job_id} from API..."})
        app.logger.info(f"Fetching details for job {job_id} from API...")
        # Fetch job details using the job ID. The client's openqa_request
        # method handles prepending the /api/v1 prefix.
        job_details_response = client.openqa_request('GET', f"jobs/{job_id}")

        # For debugging, log the raw response to the console and send to frontend
        app.logger.debug(f"Full API response for job {job_id}: {job_details_response}")
        debug_log.append({"level": "debug", "message": f"Full API response for job {job_id}: {job_details_response}"})

        job_details = job_details_response.get('job')

        if not job_details:
            error_msg = f"Error: Could not find 'job' key in the API response for ID {job_id}."
            debug_log.append({"level": "error", "message": error_msg})
            app.logger.error(f"{error_msg} Raw response: {job_details_response}")
            return jsonify({"error": error_msg, "raw_response": job_details_response, "debug_log": debug_log}), 404

        app.logger.info(f"Successfully fetched details for job {job_id}")
        return jsonify({"job": job_details, "debug_log": debug_log})
    except RequestError as e:
        error_message = f"API Error from {hostname} for job {job_id}: Status {e.status_code} - {e.text}"
        debug_log.append({"level": "error", "message": error_message})
        app.logger.error(error_message)
        return jsonify({"error": error_message, "debug_log": debug_log}), e.status_code
    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        if hostname:
            error_message = f'Error connecting to {hostname}: {e}'
        debug_log.append({"level": "error", "message": error_message})
        app.logger.exception(error_message)
        return jsonify({"error": error_message, "debug_log": debug_log}), 500

if __name__ == '__main__':
    app.run(debug=True)
