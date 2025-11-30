import re
import pandas as pd
from typing import List, Dict, Optional, Tuple

class FlexibleGooglePayParser:
    """Parser for Google Pay HTML exports with flexible regex-based extraction"""
    
    STANDARD_COLUMNS = [
        'timestamp', 'amount', 'currency', 'recipient', 'payment_method',
        'account_number', 'transaction_id', 'status', 'product', 'wallet'
    ]
    
    def __init__(self):
        self.patterns = {
            'amount': r'(₹|€|\$|£)\s*([\d,]+\.?\d*)',
            'recipient': r'(?:Paid|Sent|Received)\s+[₹€$£][\d.,]+\s+(?:to|from|by)\s+([^\n<]+?)(?:\s+using|\s+via|<br|\n|$)',
            'payment_method': r'(?:using|via|through)\s+([^<\n]+?)(?:\s+(?:XXXXXXX|XXXX)|<br|\n|$)',
            'account_number': r'(XXXXXXX[A-Z0-9]{6,}|[A-Z0-9]{4}XXXXXXX[A-Z0-9]{4}|XXX\d+)',
            'status': r'(?:Status|State)[:\s]*(?:</b><br\s*/>&emsp;)?(\w+)(?:<br|$)',
            'timestamp_format1': r'(\d{1,2}\s+\w+,\s+\d{4},\s+\d{1,2}:\d{2}:\d{2}\s+(?:AM|PM)\s+GMT[+-]\d{2}:\d{2})',
            'timestamp_format2': r'(\d{1,2}\s+\w+\s+\d{4},\s+\d{1,2}:\d{2}:\d{2}\s+GMT[+-]\d{2}:\d{2})',
        }
    
    def extract_amount(self, text: str) -> Tuple[Optional[float], Optional[str]]:
        match = re.search(self.patterns['amount'], text)
        if match:
            currency_map = {'₹': 'INR', '€': 'EUR', '$': 'USD', '£': 'GBP'}
            try:
                amount = float(match.group(2).replace(',', ''))
                currency = currency_map.get(match.group(1), match.group(1))
                return amount, currency
            except ValueError:
                pass
        return None, None
    
    def extract_recipient(self, text: str) -> Optional[str]:
        match = re.search(self.patterns['recipient'], text, re.IGNORECASE)
        if match:
            recipient = match.group(1).strip()
            recipient = re.sub(r'\s*<br\s*/?>\s*', ' ', recipient)
            recipient = re.sub(r'&emsp;', '', recipient)
            recipient = re.sub(r'\s+(using|via|through).*', '', recipient, flags=re.IGNORECASE)
            return recipient.strip() if recipient else None
        return None
    
    def extract_payment_method(self, text: str) -> Optional[str]:
        match = re.search(self.patterns['payment_method'], text)
        if match:
            method = match.group(1).strip()
            method = re.sub(r'\s+XXXXXXX[A-Z0-9]{6,}', '', method)
            method = re.sub(r'\s+[A-Z0-9]{4}XXXXXXX[A-Z0-9]{4}', '', method)
            method = ' '.join(method.split())
            return method if method else None
        return None
    
    def extract_account_number(self, text: str) -> Optional[str]:
        match = re.search(self.patterns['account_number'], text)
        return match.group(1).strip() if match else None
    
    def extract_transaction_id(self, text: str) -> Optional[str]:
        match = re.search(r'<b>Details:</b\s*><br\s*/>&emsp;([A-Za-z0-9]+)', text)
        if match:
            tid = match.group(1).strip()
            return tid if len(tid) > 3 else None
        
        match = re.search(r'Details\s*:?<br\s*/>&emsp;([A-Za-z0-9]{6,})', text)
        if match:
            return match.group(1).strip()
        
        return None
    
    def extract_status(self, text: str) -> Optional[str]:
        statuses = ['Completed', 'Pending', 'Failed', 'Cancelled', 'Processing']
        for status in statuses:
            if status in text:
                return status
        
        match = re.search(self.patterns['status'], text)
        return match.group(1).strip() if match else None
    
    def extract_timestamp(self, text: str) -> Optional[str]:
        match = re.search(self.patterns['timestamp_format1'], text)
        if match:
            return self._normalize_timestamp(match.group(1))
        
        match = re.search(self.patterns['timestamp_format2'], text)
        if match:
            return self._normalize_timestamp(match.group(1))
        
        return None
    
    def _normalize_timestamp(self, ts: str) -> str:
        ts = re.sub(r'&emsp;', '', ts).strip()
        
        match = re.search(r'(\w+)\s+(\d{1,2}),\s+(\d{4}),\s+(\d{1,2}):(\d{2}):(\d{2})\s+(AM|PM)', ts)
        if match:
            month_str, day, year, hour, minute, second, ampm = match.groups()
            hour = int(hour)
            if ampm == 'PM' and hour != 12:
                hour += 12
            elif ampm == 'AM' and hour == 12:
                hour = 0
            month_num = self._month_to_num(month_str)
            return f"{year}-{month_num:02d}-{int(day):02d} {int(hour):02d}:{minute}:{second}"
        
        match = re.search(r'(\d{1,2})\s+(\w+)\s+(\d{4}),\s+(\d{1,2}):(\d{2}):(\d{2})', ts)
        if match:
            day, month_str, year, hour, minute, second = match.groups()
            month_num = self._month_to_num(month_str)
            return f"{year}-{month_num:02d}-{int(day):02d} {int(hour):02d}:{minute}:{second}"
        
        return ts
    
    @staticmethod
    def _month_to_num(month_str: str) -> int:
        months = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                  'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
        return months.get(month_str, 1)
    
    def extract_product(self, text: str) -> Optional[str]:
        match = re.search(r'<b>Products:</b><br\s*/>&emsp;([^\n<]+)', text)
        if match:
            product = match.group(1).strip()
            product = re.sub(r'<br\s*/?>', '', product)
            product = re.sub(r'&emsp;', '', product)
            product = product.split('<')[0].strip()
            return product if product else None
        
        return 'Google Pay' if 'Google Pay' in text else None
    
    def extract_from_transaction_block(self, block: str) -> Optional[Dict]:
        if not re.search(r'(Paid|Sent|Received|Credited)', block):
            return None
        
        extracted = {
            'timestamp': None,
            'amount': None,
            'currency': None,
            'recipient': None,
            'payment_method': None,
            'account_number': None,
            'transaction_id': None,
            'status': None,
            'product': None,
            'wallet': None,
        }
        
        extracted['amount'], extracted['currency'] = self.extract_amount(block)
        extracted['recipient'] = self.extract_recipient(block)
        extracted['payment_method'] = self.extract_payment_method(block)
        extracted['account_number'] = self.extract_account_number(block)
        extracted['transaction_id'] = self.extract_transaction_id(block)
        extracted['status'] = self.extract_status(block)
        extracted['timestamp'] = self.extract_timestamp(block)
        extracted['product'] = self.extract_product(block)
        extracted['wallet'] = extracted['product']
        
        return extracted if extracted['amount'] is not None else None
    
    def parse_html_file(self, filepath: str) -> List[Dict]:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        transactions = []
        
        blocks = re.findall(
            r'<div class="outer-cell[^>]*>.*?(?=<div class="outer-cell|$)',
            content, re.DOTALL
        )
        
        if not blocks or len(blocks) < 2:
            blocks = re.findall(
                r'<p class="mdl-typography--title">Google Pay<br /></p>.*?(?=<p class="mdl-typography--title"|$)',
                content, re.DOTALL
            )
        
        if not blocks or len(blocks) < 2:
            blocks = re.findall(
                r'(?:Paid|Sent|Received|Credited)\s+[₹€$£][\d.,]+.*?(?:GMT[+-]\d{2}:\d{2})',
                content, re.DOTALL
            )
        
        for block in blocks:
            try:
                transaction = self.extract_from_transaction_block(block)
                if transaction:
                    transactions.append(transaction)
            except Exception:
                continue
        
        return transactions
    
    def parse_multiple_files(self, filepaths: List[str], columns: Optional[List[str]] = None) -> pd.DataFrame:
        if columns is None:
            columns = self.STANDARD_COLUMNS
        
        all_transactions = []
        
        for filepath in filepaths:
            print(f"Parsing: {filepath}")
            transactions = self.parse_html_file(filepath)
            print(f"  Extracted {len(transactions)} transactions")
            all_transactions.extend(transactions)
        
        df = pd.DataFrame(all_transactions)
        available_cols = [col for col in columns if col in df.columns]
        df = df[available_cols]
        
        if 'timestamp' in df.columns:
            df = df.sort_values('timestamp', ascending=False, na_position='last')
        
        return df


def main():
    parser = FlexibleGooglePayParser()
    
    files = [
        r"c:\Users\Lenovo\Desktop\cardano hack\regex_try\harshal.html",
        r"c:\Users\Lenovo\Desktop\cardano hack\regex_try\My Activity.html"
    ]
    
    df = parser.parse_multiple_files(files)
    
    print(f"\nTotal transactions: {len(df)}")
    print(f"\nColumn breakdown:")
    for col in df.columns:
        non_null = df[col].notna().sum()
        print(f"  {col:20s}: {non_null:4d} records")
    
    print(f"\nFirst 5 transactions:")
    print(df.head(5).to_string())
    
    output_file = r"c:\Users\Lenovo\Desktop\cardano hack\regex_try\transactions.csv"
    df.to_csv(output_file, index=False)
    print(f"\nSaved to {output_file}")


if __name__ == "__main__":
    main()
