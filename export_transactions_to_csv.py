import pymongo
import pandas as pd
import os
import sys
from datetime import datetime
from bson.objectid import ObjectId
from dotenv import load_dotenv

# Load environment variables from backend/.env
dotenv_path = os.path.join(os.path.dirname(__file__), '..', 'backend', '.env')
load_dotenv(dotenv_path)

# MongoDB connection - use MONGODB_URI from backend/.env
MONGO_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/financebot')
DB_NAME = 'financebot'
COLLECTION_NAME = 'transactions'

def export_transactions_to_csv(user_id: str = None):
    """
    Fetch transactions from MongoDB, convert to DataFrame, and export to CSV
    If user_id is provided, filter transactions for that user only
    """
    try:
        # Connect to MongoDB
        client = pymongo.MongoClient(MONGO_URI)
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]
        
        print(f"Connecting to MongoDB: {MONGO_URI}")
        print(f"Database: {DB_NAME}, Collection: {COLLECTION_NAME}")
        
        # Build query filter
        query_filter = {}
        if user_id:
            try:
                user_oid = ObjectId(user_id)
                query_filter = {'userId': user_oid}
                print(f"Filtering transactions for user_id: {user_id}")
            except Exception as e:
                print(f"[WARN] Invalid user_id format: {user_id}, fetching all transactions: {e}")
        
        # Fetch transactions with optional user filter
        transactions = list(collection.find(query_filter))
        
        if not transactions:
            print("No transactions found in the database.")
            return
        
        print(f"Found {len(transactions)} transactions")
        
        # Convert to DataFrame
        df = pd.DataFrame(transactions)
        
        # Clean up MongoDB-specific fields for CSV
        # Convert ObjectId to string
        if '_id' in df.columns:
            df['_id'] = df['_id'].astype(str)
        if 'userId' in df.columns:
            df['userId'] = df['userId'].astype(str)
        
        # Flatten nested objects (htmlFile object)
        if 'htmlFile' in df.columns:
            htmlFile_data = []
            for hf in df['htmlFile']:
                if pd.isna(hf) or hf is None:
                    htmlFile_data.append(None)
                elif isinstance(hf, dict):
                    # Store only fileName and uploadDate, skip content
                    htmlFile_data.append(f"{hf.get('fileName', '')} ({hf.get('uploadDate', '')})")
                else:
                    htmlFile_data.append(str(hf))
            df['htmlFile'] = htmlFile_data
        
        # Convert tags array to string
        if 'tags' in df.columns:
            df['tags'] = df['tags'].apply(lambda x: ','.join(x) if isinstance(x, list) else x)
        
        # Convert datetime objects to string
        for col in df.columns:
            if df[col].dtype == 'object':
                try:
                    df[col] = df[col].apply(lambda x: x.isoformat() if isinstance(x, datetime) else x)
                except:
                    pass
        
        # Reorder columns for better readability
        preferred_order = [
            '_id', 'userId', 'type', 'amount', 'currency', 'category', 'description',
            'recipient', 'paymentMethod', 'accountNumber', 'transactionId', 'status',
            'date', 'walletAddress', 'blockchainTxHash', 'tags', 'UPI', 'UserInput',
            'htmlFile', '__v'
        ]
        
        # Only include columns that exist
        available_cols = [col for col in preferred_order if col in df.columns]
        other_cols = [col for col in df.columns if col not in preferred_order]
        df = df[available_cols + other_cols]
        
        # Create CSV file with consistent name (overwrites previous)
        csv_filename = "transactions_export.csv"
        csv_filepath = os.path.join(os.path.dirname(__file__), csv_filename)
        
        # Export to CSV
        df.to_csv(csv_filepath, index=False, encoding='utf-8')
        
        print("\n[SUCCESS] CSV exported successfully!")
        print(f"File: {csv_filepath}")
        print(f"Total rows: {len(df)}")
        print(f"Total columns: {len(df.columns)}")
        print(f"\nColumns: {', '.join(df.columns.tolist())}")
        
        # Print summary statistics
        print("\n[STATS] Summary Statistics:")
        print(f"  Total Transactions: {len(df)}")
        if 'type' in df.columns:
            print(f"  Income: {len(df[df['type'] == 'income'])}")
            print(f"  Expenses: {len(df[df['type'] == 'expense'])}")
        if 'amount' in df.columns:
            print(f"  Total Amount: {df['amount'].sum()}")
        if 'UPI' in df.columns and 'UserInput' in df.columns:
            upi_count = (df['UPI'] == 1).sum()
            user_input_count = (df['UserInput'] == 1).sum()
            print(f"  HTML Imports (UPI=1): {upi_count}")
            print(f"  Manual Inputs (UserInput=1): {user_input_count}")
        
        client.close()
        return csv_filepath
        
    except Exception as e:
        print(f"[ERROR] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == '__main__':
    # Get user_id from command line argument if provided
    user_id = sys.argv[1] if len(sys.argv) > 1 else None
    export_transactions_to_csv(user_id)
