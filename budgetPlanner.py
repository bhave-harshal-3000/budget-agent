"""
Multi-Goal Budget Planner Agent
Analyzes user's multiple savings goals and spending patterns
Plans how to achieve all goals together
"""

import os
import sys
import json
import subprocess
import traceback
import pymongo
from datetime import datetime, timedelta
from dotenv import load_dotenv
from crewai import Agent, Task, Crew
from crewai.llm import LLM

load_dotenv()

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in environment variables")

MONGO_URI = os.getenv('MONGODB_URI')
DB_NAME = 'financebot'

gemini_llm = LLM(model="gemini-2.0-flash", api_key=GEMINI_API_KEY)

budget_planner_agent = Agent(
    role="Smart Budget Planner",
    goal="Create a simple, achievable plan to save for multiple goals simultaneously",
    backstory="Expert at prioritizing savings goals and finding money in budgets without overwhelming the user",
    llm=gemini_llm,
    verbose=True
)

def export_transactions_to_csv(user_id: str = None):
    """Run the export script to get fresh transaction data for specific user"""
    try:
        export_script = os.path.join(os.path.dirname(__file__), 'export_transactions_to_csv.py')
        
        # Pass user_id as argument to filter transactions
        cmd = ['python', export_script]
        if user_id:
            cmd.append(user_id)
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            print(f"[ERROR] Export failed: {result.stderr}")
            return None
        
        csv_path = os.path.join(os.path.dirname(__file__), 'transactions_export.csv')
        if not os.path.exists(csv_path):
            print("[ERROR] CSV file not generated")
            return None
            
        return csv_path
    except Exception as e:
        print(f"[ERROR] Error exporting transactions: {e}")
        traceback.print_exc()
        return None

def get_user_spending_summary(user_id: str) -> dict:
    """Fetch user's spending patterns from transactions"""
    try:
        client = pymongo.MongoClient(MONGO_URI)
        db = client[DB_NAME]
        
        # Convert user_id to ObjectId
        from bson.objectid import ObjectId
        user_oid = ObjectId(user_id)
        
        # Get last 30 days of transactions
        thirty_days_ago = datetime.now() - timedelta(days=30)
        transactions = list(db['transactions'].find({
            'userId': user_oid,
            'date': {'$gte': thirty_days_ago},
            'type': 'expense'
        }))
        
        if not transactions:
            return {
                "totalSpent": 0,
                "byCategory": {},
                "avgDaily": 0,
                "avgMonthly": 0
            }
        
        # Group by category
        by_category = {}
        total_spent = 0
        
        for tx in transactions:
            cat = tx.get('category', 'Uncategorized')
            amount = tx.get('amount', 0)
            total_spent += amount
            by_category[cat] = by_category.get(cat, 0) + amount
        
        avg_daily = total_spent / 30
        avg_monthly = total_spent
        
        return {
            "totalSpent": total_spent,
            "byCategory": by_category,
            "avgDaily": round(avg_daily, 2),
            "avgMonthly": round(avg_monthly, 2),
            "transactionCount": len(transactions)
        }
        
    except Exception as e:
        print(f"[ERROR] Failed to get spending summary: {e}")
        return {}

def get_user_budget_goals(user_id: str) -> list:
    """Fetch user's budget goals from DB"""
    try:
        client = pymongo.MongoClient(MONGO_URI)
        db = client[DB_NAME]
        
        from bson.objectid import ObjectId
        user_oid = ObjectId(user_id)
        
        budgets = list(db['budgets'].find({
            'userId': user_oid,
            'status': 'active'
        }).sort([('deadline', 1)]))
        
        # Convert ObjectId to string for JSON serialization
        for budget in budgets:
            budget['_id'] = str(budget['_id'])
            budget['userId'] = str(budget['userId'])
            budget['deadline'] = budget['deadline'].isoformat() if isinstance(budget['deadline'], datetime) else str(budget['deadline'])
            budget['createdAt'] = budget['createdAt'].isoformat() if isinstance(budget['createdAt'], datetime) else str(budget['createdAt'])
        
        return budgets
    
    except Exception as e:
        print(f"[ERROR] Failed to get budget goals: {e}")
        return []

def create_multi_goal_plan_task(goals: list, spending_summary: dict, csv_content: str) -> Task:
    """Create task for multi-goal planning"""
    
    goals_text = "\n".join([
        f"• {g['goalName']}: ₹{g['targetAmount']} by {g['deadline']} (Priority: {g.get('priority', 'medium')})"
        for g in goals
    ])
    
    return Task(
        description=f"""User has {len(goals)} savings goals. Analyze the complete transaction data and create a detailed savings plan in natural language (NLP format):

GOALS:
{goals_text}

SPENDING SUMMARY (Last 30 days):
- Total spent: ₹{spending_summary.get('totalSpent', 0)}
- Average daily: ₹{spending_summary.get('avgDaily', 0)}
- Average monthly: ₹{spending_summary.get('avgMonthly', 0)}

Top spending categories:
{json.dumps(spending_summary.get('byCategory', {}), indent=2)}

COMPLETE TRANSACTION DATA (CSV):
{csv_content}

INSTRUCTIONS:
- Analyze the actual transaction CSV data to identify real spending patterns
- Use SIMPLE language, not too much analysis
- Give specific numbers for monthly/weekly savings needed for each goal
- Prioritize goals by deadline and importance (high priority goals first)
- Suggest SPECIFIC categories to cut spending from based on actual transactions
- Keep response natural and conversational
- Format as NLP text, not JSON
- Be encouraging and practical
- Reference actual spending amounts from the transaction data

Example format:
"You have 3 goals... Watch in 2 months needs ₹3000/month savings. Bike in 6 months needs ₹2000/month. 
I analyzed your transactions - you spent ₹15000 on dining this month. If you cut to ₹12000, you save ₹3000/month.
You also spent ₹8000 on subscriptions - cutting unused ones saves ₹1000/month.
Together you can save ₹4500/month to achieve all goals with these cuts..."

Provide the plan now:""",
        expected_output="Natural language plan with specific numbers from transaction analysis and actionable advice",
        agent=budget_planner_agent,
    )

def plan_all_goals(user_id: str):
    """Main function to plan all user's budget goals"""
    try:
        print(f"[INFO] Planning budget for user: {user_id}")
        
        # Fetch user's data
        goals = get_user_budget_goals(user_id)
        spending = get_user_spending_summary(user_id)
        
        if not goals:
            return {
                "success": False,
                "message": "No active budget goals found. Create some goals first!"
            }
        
        print(f"[INFO] Found {len(goals)} active goals")
        print(f"[INFO] Spending summary: {spending}")
        
        # Export transactions to CSV and read content
        print("[INFO] Exporting transactions to CSV...")
        csv_path = export_transactions_to_csv(user_id)
        csv_content = ""
        
        if csv_path:
            try:
                with open(csv_path, 'r', encoding='utf-8') as f:
                    csv_content = f.read()
                print(f"[INFO] CSV content loaded ({len(csv_content)} chars)")
            except Exception as e:
                print(f"[ERROR] Failed to read CSV: {e}")
                csv_content = "Transaction data not available"
        else:
            print("[WARN] Could not generate CSV, continuing without it")
            csv_content = "Transaction data not available"
        
        # Create and run crew with CSV content
        task = create_multi_goal_plan_task(goals, spending, csv_content)
        crew = Crew(
            agents=[budget_planner_agent],
            tasks=[task],
            verbose=True,
        )
        
        print("[INFO] Running budget planner agent...")
        result = crew.kickoff()
        
        if result:
            plan_text = result.raw if hasattr(result, 'raw') else str(result)
            
            return {
                "success": True,
                "goalsCount": len(goals),
                "goals": goals,
                "spendingSummary": spending,
                "plan": str(plan_text).strip()
            }
        
        return {"success": False, "error": "Failed to generate plan"}
        
    except Exception as e:
        print(f"[ERROR] Budget planning failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    # Get user_id from command line argument or use test id
    user_id = sys.argv[1] if len(sys.argv) > 1 else "692b0fde18cc3700664fa995"
    result = plan_all_goals(user_id)
    print(json.dumps(result, indent=2, default=str))
