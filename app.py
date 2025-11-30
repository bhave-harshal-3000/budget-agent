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
    return jsonify({
        "status": "available",
        "type": "masumi-agent",
        "message": "Cardano Financial Insights Agent is online"
    }), 200


@app.get("/input_schema")
def input_schema():
    """
    Required by Sokosumi — defines the upload UI form.
    """
    return jsonify({
        "input_data": [
            {
                "id": "identifier_from_purchaser",
                "type": "string",
                "name": "Job Identifier",
                "data": {"placeholder": "Enter job ID (ex: job123, user1-analysis)"},
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
    }), 200


@app.post("/start_job")
def start_job():
    """
    Main Masumi endpoint triggered by Sokosumi.
    """
    try:
        if not request.is_json:
            return jsonify({"status": "error", "message": "Content-Type must be application/json"}), 415

        data = request.get_json()
        identifier = data.get("identifier_from_purchaser")
        input_data = data.get("input_data", {})

        if not identifier:
            return jsonify({"status": "error", "message": "identifier_from_purchaser required"}), 400

        if "html_file" not in input_data:
            return jsonify({"status": "error", "message": "html_file required"}), 400

        # decode base64
        try:
            html_content = base64.b64decode(input_data["html_file"]).decode("utf-8")
        except Exception as e:
            return jsonify({"status": "error", "message": f"Invalid base64 file: {e}"}), 400

        job_id = f"job_{uuid.uuid4().hex[:8]}"
        status_id = str(uuid.uuid4())
        blockchain_id = f"block_{uuid.uuid4().hex[:8]}"

        now = datetime.utcnow()

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
            "status": "success",
            "job_id": job_id,
            "blockchainIdentifier": blockchain_id,
            "payByTime": int((now + timedelta(hours=1)).timestamp()),
            "submitResultTime": int((now + timedelta(hours=2)).timestamp()),
            "unlockTime": int((now + timedelta(hours=3)).timestamp()),
            "externalDisputeUnlockTime": int((now + timedelta(hours=4)).timestamp()),
            "agentIdentifier": AGENT_IDENTIFIER,
            "sellerVKey": SELLER_VKEY,
            "identifierFromPurchaser": identifier,
            "input_hash": hashlib.md5(html_content.encode()).hexdigest()
        }), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.get("/status")
def status():
    job_id = request.args.get("job_id")

    if not job_id:
        return jsonify({"status": "error", "message": "job_id required"}), 400

    job = get_job(job_id)
    if not job:
        return jsonify({"status": "error", "message": "Job not found"}), 404

    return jsonify({
        "id": str(uuid.uuid4()),
        "job_id": job_id,
        "status": job["status"],
        "result": job.get("result")
    }), 200


@app.route("/", methods=["GET"])
def root():
    return jsonify({"message": "Cardano Financial Agent MIP-003 Ready"}), 200


if __name__ == "__main__":
    port = int(os.getenv('PORT', 10000))
    app.run(host="0.0.0.0", port=port)
