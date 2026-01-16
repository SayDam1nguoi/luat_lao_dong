# File: excel_visualize/rag_core.py
import os
import pandas as pd
import re
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser

# Load environment variables
load_dotenv()
EXCEL_PATH = os.getenv("EXCEL_FILE_PATH")
OPENAI_API_KEY = os.getenv("OPENAI__API_KEY") 

class ExcelQueryAgent:
    def __init__(self):
        self.excel_path = EXCEL_PATH
        self.df = self._load_data()
        
        # --- GIA CỐ & CHUẨN HÓA DỮ LIỆU ---
        if not self.df.empty:
            # 1. Chuẩn hóa cột Loại
            if "Loại" in self.df.columns:
                self.df["Loại_norm"] = self.df["Loại"].astype(str).str.lower().str.strip()
            else:
                self.df["Loại_norm"] = "khu công nghiệp"

            # 2. Chuẩn hóa cột Tên
            if "Tên" in self.df.columns:
                self.df["Tên_norm"] = self.df["Tên"].astype(str).str.lower().str.strip()
            else:
                self.df["Tên_norm"] = ""

            # 3. Tính toán cột số liệu (Giá & Diện tích)
            if "Giá thuê đất" in self.df.columns:
                self.df["Price_num"] = self.df["Giá thuê đất"].apply(self._parse_price)
            else:
                self.df["Price_num"] = None

            if "Tổng diện tích" in self.df.columns:
                self.df["Area_num"] = self.df["Tổng diện tích"].apply(self._parse_area)
            else:
                self.df["Area_num"] = None
            
        self.llm = ChatOpenAI(
            model="gpt-3.5-turbo", 
            temperature=0, 
            api_key=OPENAI_API_KEY
        )
        
        if not self.df.empty and "Tỉnh/Thành phố" in self.df.columns:
            self.provinces_list = self.df["Tỉnh/Thành phố"].dropna().unique().tolist()
        else:
            self.provinces_list = []

    def _load_data(self) -> pd.DataFrame:
        if not self.excel_path or not os.path.exists(self.excel_path):
            if self.excel_path:
                alt_path = self.excel_path.replace(".xlsx", ".csv")
                if os.path.exists(alt_path): return pd.read_csv(alt_path)
            backup = "data/IIPMap_FULL_63_COMPLETE.xlsx - Sheet1.csv"
            if os.path.exists(backup): return pd.read_csv(backup)
            print(f"❌ Lỗi: Không tìm thấy file dữ liệu tại {self.excel_path}")
            return pd.DataFrame()

        try: return pd.read_excel(self.excel_path, sheet_name=0)
        except: return pd.read_csv(self.excel_path.replace(".xlsx", ".csv"))

    def _parse_price(self, value) -> Optional[float]:
        if pd.isna(value): return None
        s = str(value).lower().strip()
        for kw in ["usd/m²/năm", "usd/m2/năm", "usd", "/m2", "/năm", "m2"]:
            s = s.replace(kw, "")
        s = s.strip()
        if "-" in s:
            try:
                parts = s.split("-")
                return (float(parts[0]) + float(parts[1])) / 2
            except: return None
        try: return float(s)
        except: return None

    def _parse_area(self, value) -> Optional[float]:
        if pd.isna(value): return None
        s = str(value).lower().strip()
        s = s.replace("ha", "").replace("hecta", "").replace(",", ".").strip()
        try: return float(s)
        except: return None

    def retrieve_filters(self, user_query: str) -> Dict[str, Any]:
        """
        Phân tích câu hỏi nâng cao cho cả Giá và Diện tích.
        """
        if self.df.empty:
             return {"filter_type": "error", "message": "Chưa load được dữ liệu Excel."}

        parser = JsonOutputParser()
        provinces_str = ", ".join([str(p) for p in self.provinces_list])
        
        prompt_template = """
        Bạn là chuyên gia dữ liệu Bất động sản công nghiệp.
        
        DANH SÁCH TỈNH: [{provinces_list}]
        CÂU HỎI: "{query}"
        
        NHIỆM VỤ: Trích xuất JSON điều kiện lọc.
        
        1. "target_type": "Khu công nghiệp" hoặc "Cụm công nghiệp".
        
        2. "filter_type": 
           - "province": Nếu user hỏi về Tỉnh.
           - "specific_zones": Nếu hỏi về Tên KCN hoặc lọc theo số liệu (giá/diện tích).
        
        3. "search_keywords":
           - Tên Tỉnh (nếu filter_type=province).
           - Tên KCN cụ thể hoặc Thương hiệu (VSIP, Amata...).
           - Nếu là Tên KCN hoặc CCN:
             + Trường hợp Tên cụ thể (có số hiệu I, II, III...): Hãy giữ nguyên chính xác số hiệu. Ví dụ: User hỏi "VSIP I", keyword phải là "VSIP I".
             + Trường hợp Thương hiệu chung: Nếu user chỉ nói tên gốc (VD: "VSIP", "Amata") mà KHÔNG kèm số hiệu, hãy trả về tên gốc đó để tìm tất cả các khu thuộc thương hiệu.
             + Nếu so sánh nhiều khu: Trả về danh sách các tên (các khu công nghiệp/cụm công nghiệp chính xác).
           - Trả về **chính xác tên** của khu công nghiệp hoặc cụm công nghiệp được yêu cầu mà không bao gồm thông tin không liên quan như tỉnh hoặc loại cụm (trừ khi có yêu cầu thêm).
        
        4. "numeric_filters" (QUAN TRỌNG):
           - "metric": 
             + "price": Nếu câu hỏi liên quan đến GIÁ, TIỀN, USD.
             + "area": Nếu câu hỏi liên quan đến DIỆN TÍCH, RỘNG, QUY MÔ, HA, HECTA.
           - "operator": ">" (lớn hơn, trên), "<" (nhỏ hơn, dưới), "=" (bằng), ">=" (từ), "<=" (đến).
           - "value": Số thực.
           
           Ví dụ: 
           - "lớn hơn 100 ha" -> metric: "area", value: 100.
           - "giá dưới 50 USD" -> metric: "price", value: 50.
        
        OUTPUT JSON:
        {{
            "target_type": "...",
            "filter_type": "province" | "specific_zones",
            "search_keywords": ["..."],
            "numeric_filters": [
                {{"metric": "area", "operator": ">", "value": 100}}
            ]
        }}
        """

        prompt = PromptTemplate(
            template=prompt_template,
            input_variables=["query", "provinces_list"],
        )

        try:
            print(f"🔍 Analyzing query: {user_query}")
            chain = prompt | self.llm | parser
            llm_result = chain.invoke({"query": user_query, "provinces_list": provinces_str})
            
            target_type = llm_result.get("target_type", "Khu công nghiệp")
            filter_type = llm_result.get("filter_type", "specific_zones") 
            keywords = llm_result.get("search_keywords", [])
            numeric_filters = llm_result.get("numeric_filters", [])
            
            # --- LOGIC LỌC PYTHON ---
            
            # 1. Lọc Loại
            if "cụm" in target_type.lower():
                type_mask = self.df["Loại_norm"].str.contains("cụm|ccn", na=False)
            else:
                type_mask = self.df["Loại_norm"].str.contains("khu|kcn", na=False)
            df_filtered = self.df[type_mask].copy()

            # 2. Lọc Tên/Tỉnh
            if keywords:
                if filter_type == "province":
                    mask = df_filtered["Tỉnh/Thành phố"].astype(str).isin(keywords)
                    df_filtered = df_filtered[mask]
                
                elif filter_type == "specific_zones":
                    masks = []
                    for kw in keywords:
                        # Regex boundary để tránh match nhầm (VSIP I vs VSIP III)
                        try:
                            if len(kw) >= 3: 
                                pattern = r"\b" + re.escape(kw.lower())
                                # Chỉ dùng boundary đầu (\bKW) để cho phép biến thể phía sau 
                                # nếu user nói tên thương hiệu (VD: VSIP -> VSIP I, VSIP II)
                                # Nhưng prompt đã xử lý việc trích xuất tên chính xác.
                                m = df_filtered["Tên_norm"].str.contains(kw.lower(), regex=False, na=False)
                            else:
                                m = df_filtered["Tên_norm"].str.contains(kw.lower(), regex=False, na=False)
                        except:
                            m = df_filtered["Tên_norm"].str.contains(kw.lower(), regex=False, na=False)
                        masks.append(m)
                    
                    if masks:
                        final_mask = pd.concat(masks, axis=1).any(axis=1)
                        df_filtered = df_filtered[final_mask]

            # 3. Lọc Số (Hỗ trợ cả Price và Area)
            for f in numeric_filters:
                metric = f.get("metric")
                op = f.get("operator")
                val = f.get("value")
                
                col = None
                if metric == "price" and "Price_num" in df_filtered.columns:
                    col = "Price_num"
                elif metric == "area" and "Area_num" in df_filtered.columns:
                    col = "Area_num"
                
                if col:
                    if op == ">": df_filtered = df_filtered[df_filtered[col] > val]
                    elif op == "<": df_filtered = df_filtered[df_filtered[col] < val]
                    elif op == ">=": df_filtered = df_filtered[df_filtered[col] >= val]
                    elif op == "<=": df_filtered = df_filtered[df_filtered[col] <= val]
                    elif op == "=": df_filtered = df_filtered[df_filtered[col] == val]

            final_result = {
                "industrial_type": target_type,
                "filter_type": filter_type,
                "data": df_filtered
            }
            return final_result

        except Exception as e:
            print(f"❌ Query Error: {e}")
            return {"filter_type": "error", "message": str(e)}

# Export
rag_agent = ExcelQueryAgent()