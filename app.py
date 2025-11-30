from flask import Flask, jsonify, request
from budgetPlanner import plan_all_goals
import json
import os
import traceback
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "Cardano Insights API",
        "version": "1.0.0"
    }), 200

@app.route('/budget', methods=['GET'])
def get_budget_plan():
    """
    Generate budget plan for a user's savings goals
    Returns: JSON with plan, recommendations, and spending analysis
    """
    try:
        user_id = request.args.get('userId')
        if not user_id:
            return jsonify({
                "success": False,
                "error": "Missing userId parameter",
                "message": "userId query parameter is required"
            }), 400
        
        print(f"🚀 Generating budget plan for user {user_id}...")
        
        # Run the budget planner agent
        plan_result = plan_all_goals(user_id)
        
        if plan_result is None:
            return jsonify({
                "success": False,
                "error": "No plan result",
                "message": "Failed to generate budget plan"
            }), 500
        
        # plan_all_goals already returns a dict, not a string
        if isinstance(plan_result, dict):
            if plan_result.get("success"):
                return jsonify(plan_result), 200
            else:
                return jsonify(plan_result), 500
        
        # Fallback: if it's a string, try to parse it
        result_str = str(plan_result).strip()
        try:
            # Find the start of JSON (first '{')
            json_start = result_str.find('{')
            json_end = result_str.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = result_str[json_start:json_end]
                plan_data = json.loads(json_str)
            else:
                raise ValueError("No JSON found in response")
            
            return jsonify({
                "success": True,
                "plan": plan_data
            }), 200
            
        except json.JSONDecodeError as e:
            print(f"❌ JSON Parse Error: {str(e)}")
            print(f"Raw result: {result_str[:500]}")
            return jsonify({
                "success": False,
                "error": f"Invalid JSON response from AI: {str(e)}",
                "message": "Failed to parse budget plan"
            }), 500
        
    except Exception as e:
        print(f"❌ Error generating budget plan: {str(e)}")
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "Failed to generate budget plan"
        }), 500

@app.route('/', methods=['GET'])
def index():
    """API documentation"""
    return jsonify({
        "name": "Cardano Insights API",
        "version": "1.0.0",
        "endpoints": {
            "GET /health": "Health check",
            "GET /insights?userId=<userId>": "Get financial insights from transaction data",
            "GET /budget?userId=<userId>": "Generate budget plan for user's savings goals"
        },
        "documentation": "Use Postman to access endpoints"
    }), 200

if __name__ == '__main__':
    port = int(os.getenv('INSIGHTS_API_PORT', 5002))
    app.run(debug=True, host='0.0.0.0', port=port)
