from flask import Flask, jsonify, request
from flask_cors import CORS
import uuid
import base64
import hashlib
from datetime import datetime, timedelta
import os
import json
import traceback
from dotenv import load_dotenv

# ---- Your existing logic imports ----
from budgetPlanner import plan_all_goals

# ---------------------------------------------------
# INITIALIZE APP
# ---------------------------------------------------
load_dotenv()
app = Flask(__name__)
CORS(app)

app.url_map.strict_slashes = False

# Masumi required
AGENT_IDENTIFIER = os.getenv("AGENT_IDENTIFIER")  # MUST MATCH Masumi registry
SELLER_VKEY = os.getenv("SELLER_VKEY")

jobs = {}  # temporary in-memory job store


# ---------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------
def store_job(job_id, data):
    jobs[job_id] = data


def get_job(job_id):
    return jobs.get(job_id)


def get_input_schema_definition():
    """
    MIP-003 /input_schema definition.

    This defines the expected fields for /start_job.
    Here we expose:
      - a purchaser-defined identifier (for UI + tracking)
      - a Google Pay activity HTML file (base64-encoded)
    """
    return {
        "input_data": [
            {
                "id": "identifier_from_purchaser",
                "type": "string",
                "name": "Job Identifier",
                "data": {
                    "placeholder": "Enter job ID (ex: job123, user1-analysis)"
                },
                "validations": [{"type": "required"}]
            },
            {
                "id": "html_file",
                "type": "file",
                "name": "Google Pay Activity File (.html)",
                "data": {
                    "accept": ".html",
                    "maxSize": 5000000,
                    "outputFormat": "base64"
                },
                "validations": [{"type": "required"}]
            }
        ]
    }


# ---------------------------------------------------
# YOUR EXISTING ENDPOINTS
# ---------------------------------------------------

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "service": "Cardano Insights API",
        "version": "1.0.0"
    }), 200


@app.route('/budget', methods=['GET'])
def get_budget_plan():
    try:
        user_id = request.args.get('userId')
        if not user_id:
            return jsonify({"success": False, "error": "Missing userId"}), 400

        plan = plan_all_goals(user_id)

        if isinstance(plan, dict):
            return jsonify(plan), 200

        # fallback: parse string
        try:
            json_start = plan.find("{")
            json_end = plan.rfind("}") + 1
            json_data = json.loads(plan[json_start:json_end])
            return jsonify({"success": True, "plan": json_data}), 200

        except Exception:
            return jsonify({
                "success": False,
                "error": "Invalid AI response",
                "raw": plan
            }), 500

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


# ---------------------------------------------------
# MIP-003 REQUIRED ENDPOINTS
# ---------------------------------------------------

@app.get("/availability")
def availability():
    """
    MIP-003: /availability
    Checks if the agentic service is operational.
    """
    return jsonify({
        "status": "available",          # "available" | "unavailable"
        "type": "masumi-agent",         # service type identifier
        "message": "Cardano Financial Insights Agent is online"
    }), 200


@app.get("/input_schema")
def input_schema():
    """
    MIP-003: /input_schema
    Returns the expected input schema for /start_job.
    Used by Masumi / Sokosumi to build the UI.
    """
    return jsonify(get_input_schema_definition()), 200


@app.post("/start_job")
def start_job():
    """
    MIP-003: /start_job
    Initiates a job on this agentic service.

    Expected JSON body:
    {
        "identifier_from_purchaser": "string",   # required (top-level)
        "input_data": {
            "html_file": "<base64 encoded html>" # required as per input_schema
        }
    }
    """
    try:
        if not request.is_json:
            return jsonify({
                "status": "error",
                "message": "Content-Type must be application/json"
            }), 415

        data = request.get_json()
        identifier = data.get("identifier_from_purchaser")
        input_data = data.get("input_data", {})

        if not identifier:
            return jsonify({
                "status": "error",
                "message": "identifier_from_purchaser required"
            }), 400

        if "html_file" not in input_data:
            return jsonify({
                "status": "error",
                "message": "html_file required in input_data"
            }), 400

        # decode base64 file content
        try:
            html_content = base64.b64decode(input_data["html_file"]).decode("utf-8")
        except Exception as e:
            return jsonify({
                "status": "error",
                "message": f"Invalid base64 file: {e}"
            }), 400

        job_id = f"job_{uuid.uuid4().hex[:8]}"
        status_id = str(uuid.uuid4())
        blockchain_id = f"block_{uuid.uuid4().hex[:8]}"

        now = datetime.utcnow()

        # initial status is "awaiting_payment" as per MIP-003 examples
        store_job(job_id, {
            "job_id": job_id,
            "status": "awaiting_payment",
            "status_id": status_id,
            "html": html_content,
            "identifier": identifier,
            "result": None
        })

        return jsonify({
            "id": status_id,
            "status": "success",                 # "success" | "error"
            "job_id": job_id,
            "blockchainIdentifier": blockchain_id,
            "payByTime": int((now + timedelta(hours=1)).timestamp()),
            "submitResultTime": int((now + timedelta(hours=2)).timestamp()),
            "unlockTime": int((now + timedelta(hours=3)).timestamp()),
            "externalDisputeUnlockTime": int((now + timedelta(hours=4)).timestamp()),
            "agentIdentifier": AGENT_IDENTIFIER,
            "sellerVKey": SELLER_VKEY,
            "identifierFromPurchaser": identifier,
            "input_hash": hashlib.md5(html_content.encode("utf-8")).hexdigest()
        }), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.get("/status")
def status():
    """
    MIP-003: /status
    Returns job status and optional input_schema (when awaiting_input).

    Query params:
      ?job_id=job_456abc
    """
    job_id = request.args.get("job_id")

    if not job_id:
        return jsonify({
            "status": "error",
            "message": "job_id required"
        }), 400

    job = get_job(job_id)
    if not job:
        return jsonify({
            "status": "error",
            "message": "Job not found"
        }), 404

    response = {
        "id": str(uuid.uuid4()),
        "job_id": job_id,
        "status": job["status"],   # "awaiting_payment", "awaiting_input", "running", "completed", "failed"
    }

    # When the job is in "awaiting_input", also return the schema
    if job["status"] == "awaiting_input":
        response["input_schema"] = get_input_schema_definition()

    # Include result if available
    if job.get("result") is not None:
        response["result"] = job["result"]

    return jsonify(response), 200


@app.post("/provide_input")
def provide_input():
    """
    MIP-003: /provide_input
    Provides additional input for a job in "awaiting_input" state.

    Expected JSON body:
    {
        "job_id": "job_456abc",            # required
        "status_id": "status-uuid",        # required
        "input_data": { ... } OR           # optional
        "input_groups": [ ... ]            # optional
    }

    You must supply exactly one of `input_data` or `input_groups`.
    """
    try:
        if not request.is_json:
            return jsonify({
                "status": "error",
                "message": "Content-Type must be application/json"
            }), 415

        body = request.get_json()
        job_id = body.get("job_id")
        status_id = body.get("status_id")
        input_data = body.get("input_data")
        input_groups = body.get("input_groups")

        if not job_id or not status_id:
            return jsonify({
                "status": "error",
                "message": "job_id and status_id are required"
            }), 400

        job = get_job(job_id)
        if not job:
            return jsonify({
                "status": "error",
                "message": "Job not found"
            }), 404

        # Must be in awaiting_input for this to make sense per spec
        if job["status"] != "awaiting_input":
            return jsonify({
                "status": "error",
                "message": "Job is not awaiting input"
            }), 400

        # Optionally enforce status_id match (recommended)
        if job.get("status_id") and job["status_id"] != status_id:
            return jsonify({
                "status": "error",
                "message": "status_id does not match current job status"
            }), 400

        # Exactly one of input_data / input_groups
        if (input_data is None and input_groups is None) or \
           (input_data is not None and input_groups is not None):
            return jsonify({
                "status": "error",
                "message": "You must provide exactly one of input_data or input_groups"
            }), 400

        # Store the extra input and move the job forward (e.g. to "running")
        extra_input = input_data if input_data is not None else input_groups
        job["extra_input"] = extra_input
        job["status"] = "running"

        # Compute hash of submitted input (for integrity verification)
        input_json_str = json.dumps(extra_input, sort_keys=True)
        input_hash = hashlib.md5(input_json_str.encode("utf-8")).hexdigest()

        # NOTE:
        # For full MIP-003 compatibility, this should be a real Ed25519 signature
        # (similar to CIP-08) using the agent's private key.
        #
        # Here we return a placeholder signature derived from the hash.
        # Replace this with real signing in production.
        signature_payload = f"{job_id}:{status_id}:{input_hash}"
        signature = base64.b64encode(signature_payload.encode("utf-8")).decode("utf-8")

        return jsonify({
            "status": "success",
            "input_hash": input_hash,
            "signature": signature
        }), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# ---------------------------------------------------
# MAIN
# ---------------------------------------------------
if __name__ == '__main__':
    port = int(os.getenv('INSIGHTS_API_PORT', 5002))
    app.run(debug=True, host='0.0.0.0', port=port)
