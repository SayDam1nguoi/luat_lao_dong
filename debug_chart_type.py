#!/usr/bin/env python3
"""
Debug script để kiểm tra chart_type trong kết quả
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from excel_visualize import handle_excel_visualize

def debug_chart_type():
    """Debug chart_type field"""
    
    query = "Vẽ biểu đồ về khu và cụm công nghiệp ở Hải Phòng"
    
    print(f"🔍 Query: {query}")
    print("=" * 50)
    
    try:
        result = handle_excel_visualize(query)
        
        if result is None:
            print("❌ Result is None")
            return
        
        print(f"📋 Full Result Keys: {list(result.keys())}")
        print()
        
        # Kiểm tra từng field quan trọng
        important_fields = ['type', 'province', 'industrial_type', 'metric', 'chart_type', 'count']
        
        for field in important_fields:
            if field in result:
                print(f"✅ {field}: {result[field]}")
            else:
                print(f"❌ Missing {field}")
        
        # In ra toàn bộ result để debug
        print(f"\n📄 Full Result:")
        for key, value in result.items():
            if key == 'data':
                print(f"   {key}: [{len(value)} items]")
            elif key == 'chart_base64':
                print(f"   {key}: [base64 data - {len(str(value))} chars]")
            else:
                print(f"   {key}: {value}")
                
    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_chart_type()