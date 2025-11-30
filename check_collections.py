import pymongo
import os
from dotenv import load_dotenv

# Load environment variables from backend/.env
dotenv_path = os.path.join(os.path.dirname(__file__), '..', 'backend', '.env')
load_dotenv(dotenv_path)

# MongoDB connection
MONGO_URI = os.getenv('MONGODB_URI')

try:
    client = pymongo.MongoClient(MONGO_URI)
    db = client['financebot']
    
    print("✅ Connected to financebot database")
    print(f"\n📊 Collections in financebot database:")
    collections = db.list_collection_names()
    for collection in collections:
        count = db[collection].count_documents({})
        print(f"  - {collection}: {count} documents")
    
    # Check each collection for sample data
    print("\n" + "="*50)
    for collection in collections:
        count = db[collection].count_documents({})
        if count > 0:
            print(f"\n📋 Sample from '{collection}' collection:")
            sample = db[collection].find_one({})
            if sample:
                print(f"  Keys: {list(sample.keys())}")
                print(f"  Sample: {str(sample)[:200]}...")
    
    client.close()
except Exception as e:
    print(f"❌ Error: {e}")
