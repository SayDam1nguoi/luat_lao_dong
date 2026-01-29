"""
Module xử lý truy vấn trực tiếp file Excel về KCN/CCN
Tích hợp vào chatbot để trả về dữ liệu dạng JSON khi người dùng hỏi
về số lượng hoặc danh sách khu/cụm công nghiệp.

✅ BỔ SUNG:
- Load industrial_zones.geojson (tuỳ chọn) để gắn tọa độ cho từng KCN/CCN
- Trả JSON có thêm:
    - data[i]["coordinates"] = [lng, lat] (nếu match được)
    - not_found_coordinates: danh sách tên không match được tọa độ
"""

import pandas as pd
import re
import json
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

# RapidFuzz (khuyến nghị). Nếu không có sẽ dùng fallback match cơ bản.
try:
    from rapidfuzz import fuzz, process
except Exception:
    fuzz = None
    process = None


class ExcelQueryHandler:
    def __init__(
        self,
        excel_path: str,
        geojson_path: Optional[str] = None,
        match_threshold: int = 82,
        llm=None
    ):
        """
        Khởi tạo handler với đường dẫn file Excel

        Args:
            excel_path: Đường dẫn đến file Excel chứa thông tin KCN/CCN
            geojson_path: (tuỳ chọn) Đường dẫn industrial_zones.geojson để gắn tọa độ
            match_threshold: ngưỡng match tên (RapidFuzz) để chấp nhận tọa độ
            llm: Language model để xử lý prompt-based (BẮT BUỘC)
        """
        self.excel_path = excel_path
        self.df: Optional[pd.DataFrame] = None
        self.llm = llm

        if not self.llm:
            print("⚠️ WARNING: Hệ thống prompt-based cần LLM. Sẽ fallback về keyword nếu cần.")

        self.match_threshold = match_threshold
        self.geojson_path = geojson_path

        # Lưu index map toạ độ: name_norm -> [lng, lat]
        self._iz_name_to_coord: Dict[str, List[float]] = {}
        self._iz_names_original: List[str] = []
        self._iz_names_norm: List[str] = []

        # Khai báo các cột cần thiết
        self.columns_map = {
            "province": None,
            "type": None,  # Cột Loại (KCN/CCN)
            "name": None,
            "address": None,
            "operation_time": None,
            "area": None,
            "rental_price": None,
            "industry": None
        }

        self._load_excel()
        self._load_geojson_if_provided()

    # ==========================================================
    # 🧩 LOAD FILE EXCEL & NHẬN DIỆN CỘT
    # ==========================================================
    def _load_excel(self):
        """Load file Excel và tự động phát hiện các cột quan trọng"""
        try:
            self.df = pd.read_excel(self.excel_path)
            self.df.columns = self.df.columns.str.strip()

            for col in self.df.columns:
                col_lower = col.lower()
                if any(k in col_lower for k in ["tỉnh", "thành phố", "province"]):
                    self.columns_map["province"] = col
                elif any(k in col_lower for k in ["loại", "loai", "type"]):
                    self.columns_map["type"] = col
                elif any(k in col_lower for k in ["tên", "ten", "kcn", "ccn"]) and "loại" not in col_lower:
                    self.columns_map["name"] = col
                elif any(k in col_lower for k in ["địa chỉ", "dia chi", "address"]):
                    self.columns_map["address"] = col
                elif any(k in col_lower for k in ["thời gian", "vận hành", "operation"]):
                    self.columns_map["operation_time"] = col
                elif any(k in col_lower for k in ["diện tích", "dien tich", "area"]):
                    self.columns_map["area"] = col
                elif any(k in col_lower for k in ["giá thuê", "gia thue", "rent", "rental"]):
                    self.columns_map["rental_price"] = col
                elif any(k in col_lower for k in ["ngành nghề", "nganh nghe", "industry"]):
                    self.columns_map["industry"] = col

            print(f"✅ Đã load Excel: {len(self.df)} bản ghi")
            print("🧭 Cấu trúc cột nhận diện được:")
            for key, val in self.columns_map.items():
                print(f"   - {key}: {val}")

        except Exception as e:
            print(f"❌ Lỗi khi load Excel: {e}")
            self.df = None

    # ==========================================================
    # 🗺️ LOAD GEOJSON (industrial_zones.geojson) để gắn tọa độ
    # ==========================================================
    def _load_geojson_if_provided(self):
        """
        Load GeoJSON nếu có path.
        Kết quả: map name_norm -> [lng, lat]
        """
        if not self.geojson_path:
            return

        p = Path(self.geojson_path)
        if not p.exists():
            print(f"⚠️ GeoJSON không tồn tại: {self.geojson_path} (bỏ qua gắn tọa độ)")
            return

        try:
            with open(p, "r", encoding="utf-8") as f:
                gj = json.load(f)

            features = gj.get("features", []) or []
            name_to_coord: Dict[str, List[float]] = {}

            iz_names_original: List[str] = []
            iz_names_norm: List[str] = []

            for fe in features:
                props = fe.get("properties", {}) or {}
                geom = fe.get("geometry", {}) or {}
                coords = geom.get("coordinates")

                name = str(props.get("name", "")).strip()
                if not name:
                    continue

                # Chỉ hỗ trợ Point [lng, lat] như file của bạn đang dùng
                if isinstance(coords, list) and len(coords) == 2 and all(isinstance(x, (int, float)) for x in coords):
                    n = self._normalize_text(name)
                    name_to_coord[n] = [float(coords[0]), float(coords[1])]
                    iz_names_original.append(name)
                    iz_names_norm.append(n)

            self._iz_name_to_coord = name_to_coord
            self._iz_names_original = iz_names_original
            self._iz_names_norm = iz_names_norm

            print(f"✅ Đã load GeoJSON IZ: {len(self._iz_name_to_coord)} điểm có tọa độ")

        except Exception as e:
            print(f"⚠️ Lỗi load GeoJSON: {e}. (bỏ qua gắn tọa độ)")

    # ==========================================================
    # 🤖 PROMPT-BASED QUERY ANALYSIS
    # ==========================================================
    def _analyze_query_with_llm(self, question: str) -> Dict[str, Any]:
        """
        Sử dụng LLM để phân tích toàn bộ câu hỏi và trả về thông tin cần thiết
        
        Returns:
            {
                "is_industrial_query": bool,
                "province": str or None,
                "query_type": "KCN" | "CCN" | None (None = tất cả),
                "search_type": "province" | "specific_name",
                "specific_name": str or None,
                "confidence": float,
                "reasoning": str
            }
        """
        if not self.llm or self.df is None:
            # Fallback về keyword nếu không có LLM
            return self._fallback_keyword_analysis(question)
        
        # Lấy danh sách tỉnh có trong dữ liệu
        available_provinces = self.df[self.columns_map["province"]].dropna().unique().tolist()
        available_provinces_str = ", ".join(available_provinces)
        
        # Lấy một số tên KCN/CCN mẫu để LLM hiểu format
        sample_names = []
        if self.columns_map["name"] is not None:
            sample_names = self.df[self.columns_map["name"]].dropna().head(10).tolist()
        sample_names_str = ", ".join(sample_names[:5]) if sample_names else "Không có dữ liệu mẫu"
        
        prompt = f"""
Bạn là chuyên gia phân tích câu hỏi về khu công nghiệp và cụm công nghiệp Việt Nam.

DANH SÁCH TỈNH/THÀNH PHỐ CÓ DỮ LIỆU:
{available_provinces_str}

MỘT SỐ TÊN KCN/CCN MẪU:
{sample_names_str}

CÂU HỎI NGƯỜI DÙNG: "{question}"

NHIỆM VỤ: Phân tích câu hỏi và trả về JSON với các thông tin sau:

1. "is_industrial_query": true/false
   - true nếu câu hỏi về khu công nghiệp (KCN) hoặc cụm công nghiệp (CCN)
   - false nếu không liên quan

2. "search_type": "province" hoặc "specific_name"
   - "province" nếu người dùng hỏi về KCN/CCN trong một tỉnh/thành phố
   - "specific_name" nếu người dùng hỏi về một KCN/CCN cụ thể theo tên

3. "province": tên tỉnh/thành phố (chỉ khi search_type = "province")
   - Trích xuất tên tỉnh từ câu hỏi
   - Phải khớp CHÍNH XÁC với một trong các tỉnh trong danh sách
   - Trả về null nếu không tìm thấy hoặc không khớp

4. "specific_name": tên KCN/CCN cụ thể (chỉ khi search_type = "specific_name")
   - Trích xuất tên KCN/CCN từ câu hỏi
   - Bao gồm cả từ khóa "KHU CÔNG NGHIỆP" hoặc "CỤM CÔNG NGHIỆP" nếu có

5. "query_type": loại truy vấn - QUAN TRỌNG: PHÂN BIỆT RÕ RÀNG
   - "KCN" nếu câu hỏi CHỈ NHẮC ĐẾN "khu công nghiệp", "kcn", "khu cn", "khu" (và KHÔNG có "cụm")
   - "CCN" nếu câu hỏi CHỈ NHẮC ĐẾN "cụm công nghiệp", "ccn", "cụm cn", "cụm" (và KHÔNG có "khu")
   - null chỉ khi câu hỏi NHẮC ĐẾN CẢ HAI: "khu và cụm", "kcn và ccn", "khu công nghiệp và cụm công nghiệp"

6. "confidence": độ tin cậy (0.0-1.0)
   - Mức độ chắc chắn về phân tích

7. "reasoning": lý do phân tích
   - Giải thích ngắn gọn tại sao phân tích như vậy

QUAN TRỌNG - PHÂN BIỆT QUERY_TYPE:
- Nếu câu hỏi chỉ có "khu" hoặc "kcn" (và KHÔNG có "cụm") → query_type = "KCN"
- Nếu câu hỏi chỉ có "cụm" hoặc "ccn" (và KHÔNG có "khu") → query_type = "CCN"  
- Nếu câu hỏi có cả "khu" và "cụm" → query_type = null
- "công nghiệp" không quyết định loại, chỉ có "khu" vs "cụm" mới quyết định
- LUÔN LUÔN kiểm tra xem câu hỏi có cả "khu" và "cụm" không trước khi quyết định
- Ví dụ: "cụm công nghiệp ở Vĩnh Long" → chỉ có "cụm", không có "khu" → query_type = "CCN"
- Ví dụ: "khu công nghiệp ở Hà Nội" → chỉ có "khu", không có "cụm" → query_type = "KCN"

BƯỚC PHÂN TÍCH QUERY_TYPE:
1. Tìm từ "khu" hoặc "kcn" trong câu hỏi → has_khu = true/false
2. Tìm từ "cụm" hoặc "ccn" trong câu hỏi → has_cum = true/false  
3. Nếu has_khu = true và has_cum = true → query_type = null
4. Nếu has_khu = true và has_cum = false → query_type = "KCN"
5. Nếu has_khu = false và has_cum = true → query_type = "CCN"
6. Nếu has_khu = false và has_cum = false → query_type = null

VÍ DỤ SEARCH_TYPE = "province":
- "khu công nghiệp ở Hà Nội" → {{"query_type": "KCN", "reasoning": "Chỉ hỏi về KHU công nghiệp, không nhắc đến cụm"}}
- "cụm công nghiệp ở Bình Dương" → {{"query_type": "CCN", "reasoning": "Chỉ hỏi về CỤM công nghiệp, không nhắc đến khu"}}
- "khu và cụm công nghiệp ở Đà Nẵng" → {{"query_type": null, "reasoning": "Hỏi về CẢ HAI khu và cụm"}}
- "danh sách cụm công nghiệp ở Bình Dương" → {{"query_type": "CCN", "reasoning": "Chỉ hỏi về CỤM công nghiệp, không nhắc đến khu"}}
- "vẽ biểu đồ cụm công nghiệp ở Hải Phòng" → {{"query_type": "CCN", "reasoning": "Chỉ hỏi về CỤM công nghiệp, không nhắc đến khu"}}

VÍ DỤ SEARCH_TYPE = "specific_name":
- "cho tôi thông tin về KHU CÔNG NGHIỆP NGŨ LẠC - VĨNH LONG" → {{"query_type": "KCN", "reasoning": "Tìm KCN cụ thể"}}
- "thông tin về cụm công nghiệp ABC" → {{"query_type": "CCN", "reasoning": "Tìm CCN cụ thể"}}

CHỈ TRẢ VỀ JSON (không có markdown, không có text thêm):
"""

        try:
            from langchain_core.messages import HumanMessage
            
            # Kiểm tra LLM có khả dụng không
            if not hasattr(self.llm, 'invoke'):
                print("⚠️ LLM does not have invoke method")
                return self._fallback_keyword_analysis(question)
            
            # Gọi LLM với error handling
            try:
                llm_response = self.llm.invoke([HumanMessage(content=prompt)])
                if not llm_response or not hasattr(llm_response, 'content'):
                    print("⚠️ LLM returned invalid response object")
                    return self._fallback_keyword_analysis(question)
                
                response = llm_response.content
                if not isinstance(response, str):
                    response = str(response)
                
                response = response.strip()
                
            except Exception as llm_error:
                print(f"⚠️ LLM invoke error: {llm_error}")
                return self._fallback_keyword_analysis(question)
            
            # Kiểm tra response có rỗng không
            if not response:
                print("⚠️ LLM returned empty response")
                return self._fallback_keyword_analysis(question)
            
            # Debug: In ra response để kiểm tra (chỉ khi có lỗi)
            # print(f"🔍 LLM raw response: '{response}'")
            
            # Thử parse JSON
            import json
            try:
                result = json.loads(response)
            except json.JSONDecodeError as json_error:
                # Chỉ log lỗi nếu response không rỗng
                if response.strip():
                    print(f"⚠️ JSON parse error: {json_error}")
                else:
                    print("⚠️ Empty response from LLM")
                    return self._fallback_keyword_analysis(question)
                
                # Thử extract JSON từ response nếu có markdown format
                import re
                
                # Loại bỏ markdown code blocks
                cleaned_response = response.strip()
                if cleaned_response.startswith('```json'):
                    cleaned_response = cleaned_response[7:]  # Bỏ ```json
                if cleaned_response.startswith('```'):
                    cleaned_response = cleaned_response[3:]   # Bỏ ```
                if cleaned_response.endswith('```'):
                    cleaned_response = cleaned_response[:-3]  # Bỏ ```
                
                cleaned_response = cleaned_response.strip()
                
                # Kiểm tra cleaned response có rỗng không
                if not cleaned_response:
                    print("⚠️ Cleaned response is empty")
                    return self._fallback_keyword_analysis(question)
                
                # Thử parse lại
                try:
                    result = json.loads(cleaned_response)
                    # print("✅ Successfully parsed cleaned JSON")
                except json.JSONDecodeError:
                    # Thử tìm JSON object trong text
                    json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', cleaned_response, re.DOTALL)
                    if json_match:
                        try:
                            result = json.loads(json_match.group())
                            # print("✅ Successfully extracted JSON from response")
                        except:
                            print("❌ Failed to extract JSON from response")
                            return self._fallback_keyword_analysis(question)
                    else:
                        print("❌ No JSON found in response")
                        return self._fallback_keyword_analysis(question)
            
            # Validate result
            required_keys = ["is_industrial_query", "search_type", "province", "specific_name", "query_type", "confidence", "reasoning"]
            if not isinstance(result, dict):
                print(f"⚠️ LLM response is not a dict: {type(result)}")
                return self._fallback_keyword_analysis(question)
                
            if not all(key in result for key in required_keys):
                missing_keys = [key for key in required_keys if key not in result]
                print(f"⚠️ LLM response missing keys: {missing_keys}")
                return self._fallback_keyword_analysis(question)
            
            return result
                
        except Exception as e:
            print(f"⚠️ LLM analysis failed: {e}")
            return self._fallback_keyword_analysis(question)

    def _fallback_keyword_analysis(self, question: str) -> Dict[str, Any]:
        """Fallback keyword-based analysis khi LLM không khả dụng"""
        question_norm = self._normalize_text(question.lower())
        
        # Check if industrial query
        industrial_keywords = [
            "kcn", "ccn", "khu cong nghiep", "cum cong nghiep",
            "khu cn", "cum cn", "khu nghiep", "cum nghiep"
        ]
        is_industrial = any(k in question_norm for k in industrial_keywords)
        
        if not is_industrial:
            return {
                "is_industrial_query": False,
                "search_type": "province",
                "province": None,
                "specific_name": None,
                "query_type": None,
                "confidence": 0.9,
                "reasoning": "Không phải câu hỏi về khu/cụm công nghiệp"
            }
        
        # Extract province first (improved with TP.HCM recognition)
        province = None
        specific_name = None
        search_type = "province"
        
        if self.df is not None and self.columns_map["province"] is not None:
            unique_provinces = self.df[self.columns_map["province"]].dropna().unique()
            
            # Special handling for TP.HCM variations
            hcm_variations = [
                "thanh pho ho chi minh", "tp ho chi minh", "tp.hcm", "tphcm", 
                "ho chi minh", "hcm", "sai gon", "saigon"
            ]
            
            # Check for TP.HCM variations first
            for hcm_var in hcm_variations:
                if hcm_var in question_norm:
                    # Find the actual province name in data
                    for prov in unique_provinces:
                        prov_norm = self._normalize_text(str(prov).lower())
                        if "ho chi minh" in prov_norm or "hcm" in prov_norm:
                            province = str(prov)
                            break
                    if province:
                        break
            
            # If not TP.HCM, check other provinces
            if not province:
                for prov in unique_provinces:
                    prov_norm = self._normalize_text(str(prov).lower())
                    if prov_norm in question_norm:
                        province = str(prov)
                        break
        
        # Determine search type based on patterns
        # Check for location indicators (province search)
        location_indicators = ["o ", "tai ", "trong ", "tinh ", "thanh pho ", "danh sach"]
        has_location_indicator = any(indicator in question_norm for indicator in location_indicators)
        
        # Check for specific name indicators
        specific_indicators = ["thong tin ve", "cho toi thong tin", "chi tiet ve", "ve khu cong nghiep", "ve cum cong nghiep"]
        has_specific_indicator = any(indicator in question_norm for indicator in specific_indicators)
        
        # Decision logic: prioritize province search if we found a province OR have location indicators
        if province or has_location_indicator:
            search_type = "province"
            specific_name = None
        elif has_specific_indicator:
            search_type = "specific_name"
            # Try to extract the specific name (simplified)
            if "khu cong nghiep" in question_norm:
                # Find text after "khu cong nghiep"
                parts = question_norm.split("khu cong nghiep")
                if len(parts) > 1:
                    specific_name = f"khu cong nghiep{parts[1]}".strip()
            elif "cum cong nghiep" in question_norm:
                # Find text after "cum cong nghiep"
                parts = question_norm.split("cum cong nghiep")
                if len(parts) > 1:
                    specific_name = f"cum cong nghiep{parts[1]}".strip()
        
        # Detect type (simplified) - CẢI THIỆN LOGIC
        has_cum = any(k in question_norm for k in ["cum", "ccn"])
        has_khu = any(k in question_norm for k in ["khu", "kcn"])
        
        # QUAN TRỌNG: Chỉ trả về loại cụ thể khi chỉ có 1 loại
        if has_cum and has_khu:
            query_type = None  # Có cả hai
        elif has_cum and not has_khu:
            query_type = "CCN"  # Chỉ có cụm
        elif has_khu and not has_cum:
            query_type = "KCN"  # Chỉ có khu
        else:
            query_type = None  # Không rõ ràng
        
        return {
            "is_industrial_query": True,
            "search_type": search_type,
            "province": province,
            "specific_name": specific_name,
            "query_type": query_type,
            "confidence": 0.7,
            "reasoning": "Fallback keyword analysis"
        }

    def _generate_smart_error_message(self, question: str, extracted_province: Optional[str]) -> str:
        """Tạo thông báo lỗi thông minh khi không tìm thấy tỉnh"""
        if not self.llm or self.df is None:
            return "❓ Bạn vui lòng nêu rõ tỉnh/thành phố cần tra cứu."
        
        available_provinces = self.df[self.columns_map["province"]].dropna().unique().tolist()
        available_provinces_str = ", ".join(available_provinces)
        
        prompt = f"""
Bạn là trợ lý thông minh về dữ liệu khu công nghiệp Việt Nam.

DANH SÁCH TỈNH/THÀNH PHỐ CÓ DỮ LIỆU:
{available_provinces_str}

CÂU HỎI NGƯỜI DÙNG: "{question}"
TỈNH ĐƯỢC TRÍCH XUẤT: "{extracted_province}"

NHIỆM VỤ: Tạo thông báo lỗi thông minh và hữu ích:
1. Thông báo tỉnh không có dữ liệu (nếu có tỉnh được trích xuất)
2. Gợi ý 2-3 tỉnh gần nhất hoặc tương tự có dữ liệu
3. Giải thích ngắn gọn bằng tiếng Việt

Nếu không trích xuất được tỉnh nào, chỉ cần nói "❓ Bạn vui lòng nêu rõ tỉnh/thành phố cần tra cứu."

CHỈ TRẢ VỀ THÔNG BÁO BẰNG TIẾNG VIỆT:
"""

        try:
            from langchain_core.messages import HumanMessage
            response = self.llm.invoke([HumanMessage(content=prompt)]).content.strip()
            return response
        except Exception as e:
            print(f"⚠️ Error message generation failed: {e}")
            if extracted_province:
                return f"❌ Không tìm thấy dữ liệu cho '{extracted_province}'. Vui lòng kiểm tra lại tên tỉnh."
            else:
                return "❓ Bạn vui lòng nêu rõ tỉnh/thành phố cần tra cứu."

    # ==========================================================
    # 🧠 NHẬN DIỆN CÂU HỎI NGƯỜI DÙNG
    # ==========================================================
    def is_count_query(self, question: str) -> bool:
        """
        Nhận diện câu hỏi về tra cứu KCN/CCN (đếm, liệt kê, danh sách...).

        NOTE: bản cũ kiểm tra count_keywords nhưng cuối cùng vẫn return has_industrial.
        Ở đây giữ “thoáng” nhưng hợp lý hơn: cần có industrial keyword.
        """
        analysis = self._analyze_query_with_llm(question)
        return analysis.get("is_industrial_query", False)

    # ==========================================================
    # 🧭 XÁC ĐỊNH LOẠI TRUY VẤN (KHU / CỤM / CẢ HAI)
    # ==========================================================
    def detect_type(self, question: str) -> Optional[str]:
        """
        Xác định người dùng hỏi khu hay cụm công nghiệp hoặc cả hai sử dụng LLM analysis.
        """
        analysis = self._analyze_query_with_llm(question)
        return analysis.get("query_type")

    # ==========================================================
    # 🤖 KIỂM TRA TỈNH THÔNG MINH VỚI LLM
    # ==========================================================
    def _smart_province_check(self, question: str, extracted_province: Optional[str]) -> Tuple[bool, str]:
        """
        Sử dụng LLM để kiểm tra tỉnh có tồn tại trong dữ liệu hay không
        và đưa ra phản hồi thông minh
        
        Returns:
            (is_valid: bool, message: str)
        """
        if extracted_province is None:
            return False, "❓ Bạn vui lòng nêu rõ tỉnh/thành phố cần tra cứu."
            
        if self.df is None:
            return False, "❌ Không có dữ liệu để tra cứu."
        
        # Lấy danh sách tỉnh có trong dữ liệu
        available_provinces = self.df[self.columns_map["province"]].dropna().unique().tolist()
        
        # Kiểm tra exact match trước
        province_normalized = self._normalize_text(extracted_province.lower())
        for available_province in available_provinces:
            if self._normalize_text(available_province.lower()) == province_normalized:
                return True, ""
        
        # Kiểm tra partial match
        for available_province in available_provinces:
            available_normalized = self._normalize_text(available_province.lower())
            if province_normalized in available_normalized or available_normalized in province_normalized:
                return True, ""
        
        # Nếu không có LLM, sử dụng logic fallback đơn giản
        if not self.llm:
            # Tìm tỉnh gần nhất
            similar_provinces = []
            for available_province in available_provinces:
                available_normalized = self._normalize_text(available_province.lower())
                # Kiểm tra có từ chung không
                province_words = set(province_normalized.split())
                available_words = set(available_normalized.split())
                if province_words.intersection(available_words):
                    similar_provinces.append(available_province)
            
            if similar_provinces:
                suggestion = f"Có thể bạn muốn tìm: {', '.join(similar_provinces[:3])}"
            else:
                # Gợi ý một số tỉnh phổ biến
                popular_provinces = [p for p in available_provinces if any(keyword in self._normalize_text(p.lower()) 
                                   for keyword in ['ha noi', 'ho chi minh', 'da nang', 'binh duong', 'dong nai'])][:3]
                if popular_provinces:
                    suggestion = f"Một số tỉnh có dữ liệu: {', '.join(popular_provinces)}"
                else:
                    suggestion = f"Một số tỉnh có dữ liệu: {', '.join(available_provinces[:3])}"
            
            return False, f"❌ Không tìm thấy dữ liệu cho '{extracted_province}'. {suggestion}."
        
        # Sử dụng LLM nếu có
        available_provinces_str = ", ".join(available_provinces)
        
        prompt = f"""
Bạn là trợ lý thông minh về dữ liệu khu công nghiệp Việt Nam.

DANH SÁCH TỈNH/THÀNH PHỐ CÓ DỮ LIỆU:
{available_provinces_str}

CÂU HỎI NGƯỜI DÙNG: "{question}"
TỈNH ĐƯỢC TRÍCH XUẤT: "{extracted_province}"

NHIỆM VỤ:
1. Kiểm tra tỉnh được trích xuất có trong danh sách không
2. Nếu KHÔNG có, đưa ra phản hồi thông minh:
   - Thông báo tỉnh không có dữ liệu
   - Gợi ý 2-3 tỉnh gần nhất hoặc tương tự có dữ liệu
   - Giải thích ngắn gọn

ĐỊNH DẠNG PHẢN HỒI:
- Nếu tỉnh CÓ trong danh sách: trả về "VALID"
- Nếu tỉnh KHÔNG có: trả về thông báo chi tiết bằng tiếng Việt

CHỈ TRẢ VỀ MỘT TRONG HAI:
- "VALID" (nếu tỉnh có dữ liệu)
- Thông báo chi tiết (nếu tỉnh không có dữ liệu)
"""

        try:
            from langchain_core.messages import HumanMessage
            response = self.llm.invoke([HumanMessage(content=prompt)]).content.strip()
            
            if response == "VALID":
                return True, ""
            else:
                return False, response
                
        except Exception as e:
            print(f"⚠️ LLM check failed: {e}")
            # Fallback về logic đơn giản đã viết ở trên
            similar_provinces = []
            for available_province in available_provinces:
                available_normalized = self._normalize_text(available_province.lower())
                province_words = set(province_normalized.split())
                available_words = set(available_normalized.split())
                if province_words.intersection(available_words):
                    similar_provinces.append(available_province)
            
            if similar_provinces:
                suggestion = f"Có thể bạn muốn tìm: {', '.join(similar_provinces[:3])}"
            else:
                popular_provinces = [p for p in available_provinces if any(keyword in self._normalize_text(p.lower()) 
                               for keyword in ['ha noi', 'ho chi minh', 'da nang', 'binh duong', 'dong nai'])][:3]
                if popular_provinces:
                    suggestion = f"Một số tỉnh có dữ liệu: {', '.join(popular_provinces)}"
                else:
                    suggestion = f"Một số tỉnh có dữ liệu: {', '.join(available_provinces[:3])}"
            
            return False, f"❌ Không tìm thấy dữ liệu cho '{extracted_province}'. {suggestion}."

    # ==========================================================
    # 🧩 TRÍCH XUẤT TỈNH/THÀNH PHỐ - CẢI THIỆN
    # ==========================================================
    def extract_province(self, question: str) -> Optional[str]:
        """Trích xuất tên tỉnh/thành phố từ câu hỏi sử dụng LLM analysis."""
        analysis = self._analyze_query_with_llm(question)
        return analysis.get("province")

    # ==========================================================
    # 🔡 CHUẨN HÓA TEXT (BỎ DẤU)
    # ==========================================================
    def _normalize_text(self, text: str) -> str:
        intab = "àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ"
        outtab = "aaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyyd"
        intab_upper = "ÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴĐ"
        outtab_upper = "AAAAAAAAAAAAAAAAAEEEEEEEEEEEIIIIIOOOOOOOOOOOOOOOOOUUUUUUUUUUUYYYYYD"
        transtab = str.maketrans(intab + intab_upper, outtab + outtab_upper)
        return str(text).translate(transtab).lower().strip()

    # ==========================================================
    # 🔍 TRUY VẤN DỮ LIỆU
    # ==========================================================
    def query_by_province(self, province_name: str, query_type: Optional[str]) -> Optional[pd.DataFrame]:
        """
        Lọc dữ liệu theo tỉnh/thành phố và loại (KCN/CCN).
        Sử dụng cột "Loại" có sẵn trong Excel để lọc chính xác.
        """
        if self.df is None or self.columns_map["province"] is None:
            return None

        # Lọc theo tỉnh/thành phố
        if province_name == "TOÀN QUỐC":
            df_filtered = self.df.copy()
        else:
            df_filtered = self.df[
                self.df[self.columns_map["province"]].astype(str).str.lower().str.contains(
                    str(province_name).lower(), na=False
                )
            ].copy()

        # Lọc theo loại KCN/CCN dựa vào cột "Loại"
        if query_type and self.columns_map["type"] is not None:
            df_filtered = df_filtered[
                df_filtered[self.columns_map["type"]].astype(str).str.strip().str.upper() == query_type
            ]

        return df_filtered

    def query_by_specific_name(self, specific_name: str, query_type: Optional[str]) -> Optional[pd.DataFrame]:
        """
        Tìm kiếm KCN/CCN theo tên cụ thể.
        Sử dụng fuzzy matching để tìm tên gần nhất.
        """
        if self.df is None or self.columns_map["name"] is None:
            return None

        specific_name_norm = self._normalize_text(specific_name.lower())
        
        # Lọc theo loại KCN/CCN trước nếu có
        df_to_search = self.df.copy()
        if query_type and self.columns_map["type"] is not None:
            df_to_search = df_to_search[
                df_to_search[self.columns_map["type"]].astype(str).str.strip().str.upper() == query_type
            ]

        # Tìm kiếm exact match trước
        exact_matches = df_to_search[
            df_to_search[self.columns_map["name"]].astype(str).apply(
                lambda x: self._normalize_text(x.lower()) == specific_name_norm
            )
        ]
        
        if not exact_matches.empty:
            return exact_matches

        # Tìm kiếm partial match (contains)
        partial_matches = df_to_search[
            df_to_search[self.columns_map["name"]].astype(str).apply(
                lambda x: specific_name_norm in self._normalize_text(x.lower()) or 
                         self._normalize_text(x.lower()) in specific_name_norm
            )
        ]
        
        if not partial_matches.empty:
            return partial_matches

        # Sử dụng fuzzy matching nếu có rapidfuzz
        if process is not None and fuzz is not None:
            all_names = df_to_search[self.columns_map["name"]].astype(str).tolist()
            if all_names:
                # Tìm tên gần nhất
                result = process.extractOne(specific_name, all_names, scorer=fuzz.WRatio)
                if result and result[1] >= 70:  # Threshold 70% cho tên KCN/CCN
                    best_match = result[0]
                    fuzzy_matches = df_to_search[
                        df_to_search[self.columns_map["name"]].astype(str) == best_match
                    ]
                    return fuzzy_matches

        # Không tìm thấy
        return pd.DataFrame()

    # ==========================================================
    # 🧭 MATCH TỌA ĐỘ THEO TÊN KCN/CCN
    # ==========================================================
    def _match_coordinates(self, zone_name: str) -> Optional[List[float]]:
        """
        Trả về [lng, lat] nếu match được tên zone trong GeoJSON.
        """
        if not zone_name:
            return None
        if not self._iz_name_to_coord:
            return None

        z_norm = self._normalize_text(zone_name)

        # 1) exact match normalized
        if z_norm in self._iz_name_to_coord:
            return self._iz_name_to_coord[z_norm]

        # 2) fuzzy match nếu có rapidfuzz
        if process is not None and fuzz is not None and self._iz_names_original:
            result = process.extractOne(zone_name, self._iz_names_original, scorer=fuzz.WRatio)
            if result and result[1] >= self.match_threshold:
                best_name = result[0]
                best_norm = self._normalize_text(best_name)
                return self._iz_name_to_coord.get(best_norm)

        # 3) fallback: contains match normalized (thô)
        for n, coord in self._iz_name_to_coord.items():
            if n and (n in z_norm or z_norm in n):
                return coord

        return None

    # ==========================================================
    # 🧾 TRẢ KẾT QUẢ DẠNG JSON (dict hoặc string)
    # ==========================================================
    def format_json_response(
        self,
        df: pd.DataFrame,
        province_name: str,
        query_type: Optional[str],
        as_string: bool = True
    ) -> Any:
        """
        Trả kết quả truy vấn dạng JSON.
        - as_string=True: trả về chuỗi JSON
        - as_string=False: trả về dict (khuyến nghị khi dùng trong Flask)
        """
        # Cải thiện label hiển thị
        if query_type == "KCN":
            label = "khu"
        elif query_type == "CCN":
            label = "cụm"
        else:  # query_type is None - tất cả
            label = "khu/cụm"

        if df is None or df.empty:
            obj = {
                "province": province_name,
                "type": query_type,
                "count": 0,
                "message": f"Không tìm thấy {label} công nghiệp tại {province_name}.",
                "data": [],
                "not_found_coordinates": []
            }
            return json.dumps(obj, ensure_ascii=False, indent=2) if as_string else obj

        cols = self.columns_map
        records = []
        not_found = []

        for _, row in df.iterrows():
            name_val = str(row.get(cols["name"], "")).strip()

            coord = self._match_coordinates(name_val)

            item = {
                "Tỉnh/Thành phố": str(row.get(cols["province"], "")),
                "Loại": str(row.get(cols["type"], "")),
                "Tên": name_val,
                "Địa chỉ": str(row.get(cols["address"], "")),
                "Thời gian vận hành": str(row.get(cols["operation_time"], "")),
                "Tổng diện tích": str(row.get(cols["area"], "")),
                "Giá thuê đất": str(row.get(cols["rental_price"], "")),
                "Ngành nghề": str(row.get(cols["industry"], "")),
                # ✅ BỔ SUNG TỌA ĐỘ
                "coordinates": coord
            }

            if coord is None and name_val:
                not_found.append(name_val)

            records.append(item)

        # Cải thiện thông báo kết quả
        if query_type is None:  # Tất cả loại
            # Đếm số lượng từng loại
            kcn_count = sum(1 for r in records if r.get("Loại", "").upper() == "KCN")
            ccn_count = sum(1 for r in records if r.get("Loại", "").upper() == "CCN")
            
            if kcn_count > 0 and ccn_count > 0:
                message = f"{province_name} có {kcn_count} khu công nghiệp và {ccn_count} cụm công nghiệp."
            elif kcn_count > 0:
                message = f"{province_name} có {kcn_count} khu công nghiệp."
            elif ccn_count > 0:
                message = f"{province_name} có {ccn_count} cụm công nghiệp."
            else:
                message = f"{province_name} có {len(records)} khu/cụm công nghiệp."
        else:
            message = f"{province_name} có {len(records)} {label} công nghiệp."

        obj = {
            "province": province_name,
            "type": query_type,
            "count": len(records),
            "message": message,
            "data": records,
            "not_found_coordinates": not_found
        }

        return json.dumps(obj, ensure_ascii=False, indent=2) if as_string else obj

    def format_json_response_for_specific_name(
        self,
        df: pd.DataFrame,
        specific_name: str,
        query_type: Optional[str],
        as_string: bool = True
    ) -> Any:
        """
        Trả kết quả truy vấn theo tên cụ thể dạng JSON.
        - as_string=True: trả về chuỗi JSON
        - as_string=False: trả về dict (khuyến nghị khi dùng trong Flask)
        """
        # Cải thiện label hiển thị
        if query_type == "KCN":
            label = "khu"
        elif query_type == "CCN":
            label = "cụm"
        else:  # query_type is None - tất cả
            label = "khu/cụm"

        if df is None or df.empty:
            obj = {
                "search_type": "specific_name",
                "specific_name": specific_name,
                "type": query_type,
                "count": 0,
                "message": f"Không tìm thấy {label} công nghiệp với tên '{specific_name}'.",
                "data": [],
                "not_found_coordinates": []
            }
            return json.dumps(obj, ensure_ascii=False, indent=2) if as_string else obj

        cols = self.columns_map
        records = []
        not_found = []

        for _, row in df.iterrows():
            name_val = str(row.get(cols["name"], "")).strip()

            coord = self._match_coordinates(name_val)

            item = {
                "Tỉnh/Thành phố": str(row.get(cols["province"], "")),
                "Loại": str(row.get(cols["type"], "")),
                "Tên": name_val,
                "Địa chỉ": str(row.get(cols["address"], "")),
                "Thời gian vận hành": str(row.get(cols["operation_time"], "")),
                "Tổng diện tích": str(row.get(cols["area"], "")),
                "Giá thuê đất": str(row.get(cols["rental_price"], "")),
                "Ngành nghề": str(row.get(cols["industry"], "")),
                # ✅ BỔ SUNG TỌA ĐỘ
                "coordinates": coord
            }

            if coord is None and name_val:
                not_found.append(name_val)

            records.append(item)

        # Tạo thông báo kết quả cho specific name search
        if len(records) == 1:
            message = f"Tìm thấy thông tin về '{specific_name}'."
        else:
            message = f"Tìm thấy {len(records)} kết quả phù hợp với '{specific_name}'."

        obj = {
            "search_type": "specific_name",
            "specific_name": specific_name,
            "type": query_type,
            "count": len(records),
            "message": message,
            "data": records,
            "not_found_coordinates": not_found
        }

        return json.dumps(obj, ensure_ascii=False, indent=2) if as_string else obj

    # ==========================================================
    # ⚙️ XỬ LÝ TRUY VẤN NGƯỜI DÙNG
    # ==========================================================
    def process_query(self, question: str, return_json: bool = True, enable_rag: bool = False) -> Tuple[bool, Optional[Any]]:
        """
        Xử lý truy vấn và trả kết quả sử dụng prompt-based analysis.
        Hỗ trợ cả tìm kiếm theo tỉnh và theo tên KCN/CCN cụ thể.
        - return_json=True: trả JSON (mặc định)
            + trả về STRING JSON (để backward compatible)
        - return_json=False: trả text bảng (như cũ)
        - enable_rag=True: bổ sung RAG analysis

        Return:
            (handled: bool, response: Optional[str|dict])
        """
        # Sử dụng LLM để phân tích toàn bộ câu hỏi một lần
        analysis = self._analyze_query_with_llm(question)
        
        # Kiểm tra xem có phải câu hỏi về KCN/CCN không
        if not analysis.get("is_industrial_query", False):
            return False, None

        search_type = analysis.get("search_type", "province")
        province = analysis.get("province")
        specific_name = analysis.get("specific_name")
        query_type = analysis.get("query_type")
        
        # Xử lý theo loại tìm kiếm
        if search_type == "specific_name":
            # Tìm kiếm theo tên KCN/CCN cụ thể
            if specific_name is None:
                error_message = "❓ Vui lòng cung cấp tên KCN/CCN cụ thể cần tìm kiếm."
                err = {"error": error_message}
                return True, json.dumps(err, ensure_ascii=False) if return_json else error_message
            
            # Truy vấn dữ liệu theo tên cụ thể
            df_result = self.query_by_specific_name(specific_name, query_type)
            
            if df_result is None or df_result.empty:
                error_message = f"❌ Không tìm thấy KCN/CCN với tên '{specific_name}'. Vui lòng kiểm tra lại tên hoặc thử tìm theo tỉnh/thành phố."
                err = {"error": error_message}
                return True, json.dumps(err, ensure_ascii=False) if return_json else error_message
            
            # Trả kết quả cho specific name search
            if return_json:
                result = self.format_json_response_for_specific_name(df_result, specific_name, query_type, as_string=False)
                
                # ✅ THÊM RAG ANALYSIS CHO SPECIFIC NAME
                if enable_rag and isinstance(result, dict):
                    rag_analysis = self.enhance_list_with_rag(result, question)
                    if rag_analysis:
                        result["rag_analysis"] = rag_analysis
                        result["has_rag"] = True
                    else:
                        result["has_rag"] = False
                
                return True, json.dumps(result, ensure_ascii=False, indent=2)
            else:
                return True, self.format_table_response_for_specific_name(df_result, specific_name, query_type)
        
        else:
            # Tìm kiếm theo tỉnh (logic cũ)
            # Kiểm tra tỉnh có hợp lệ không
            if province is None:
                error_message = self._generate_smart_error_message(question, province)
                err = {"error": error_message}
                return True, json.dumps(err, ensure_ascii=False) if return_json else error_message
            
            # Kiểm tra tỉnh có trong dữ liệu không
            is_valid, error_message = self._smart_province_check(question, province)
            if not is_valid:
                err = {"error": error_message}
                return True, json.dumps(err, ensure_ascii=False) if return_json else error_message

            # Truy vấn dữ liệu theo tỉnh
            df_result = self.query_by_province(province, query_type)

            if return_json:
                # ✅ trả dict để có thể thêm RAG analysis
                result = self.format_json_response(df_result, province, query_type, as_string=False)
                
                # ✅ THÊM RAG ANALYSIS CHO PROVINCE QUERY
                if enable_rag and isinstance(result, dict):
                    rag_analysis = self.enhance_list_with_rag(result, question)
                    if rag_analysis:
                        result["rag_analysis"] = rag_analysis
                        result["has_rag"] = True
                    else:
                        result["has_rag"] = False
                
                return True, json.dumps(result, ensure_ascii=False, indent=2)
            else:
                return True, self.format_table_response(df_result, province, query_type)

    # ==========================================================
    # 🧩 GIỮ LẠI HÀM CŨ (BẢNG TEXT)
    # ==========================================================
    def format_table_response(self, df: pd.DataFrame, province_name: str, query_type: Optional[str]) -> str:
        """(Tuỳ chọn) Hiển thị kết quả dạng bảng text"""
        # Cải thiện label hiển thị
        if query_type == "KCN":
            label = "khu"
        elif query_type == "CCN":
            label = "cụm"
        else:  # query_type is None - tất cả
            label = "khu/cụm"

        if df is None or df.empty:
            return f"Không tìm thấy {label} công nghiệp tại {province_name}."

        cols = self.columns_map
        
        # Cải thiện thông báo kết quả cho text response
        if query_type is None:  # Tất cả loại
            # Đếm số lượng từng loại
            kcn_count = sum(1 for _, row in df.iterrows() if str(row.get(cols["type"], "")).upper() == "KCN")
            ccn_count = sum(1 for _, row in df.iterrows() if str(row.get(cols["type"], "")).upper() == "CCN")
            
            if kcn_count > 0 and ccn_count > 0:
                response = f"📊 {province_name} có {kcn_count} khu công nghiệp và {ccn_count} cụm công nghiệp.\n\n"
            elif kcn_count > 0:
                response = f"📊 {province_name} có {kcn_count} khu công nghiệp.\n\n"
            elif ccn_count > 0:
                response = f"📊 {province_name} có {ccn_count} cụm công nghiệp.\n\n"
            else:
                response = f"📊 {province_name} có {len(df)} khu/cụm công nghiệp.\n\n"
        else:
            response = f"📊 {province_name} có {len(df)} {label} công nghiệp.\n\n"
            
        for _, row in df.iterrows():
            loai = str(row.get(cols['type'], '')).upper()
            ten = row.get(cols['name'], 'Không rõ')
            dia_chi = row.get(cols['address'], '')
            response += f"- [{loai}] {ten} ({dia_chi})\n"
        return response

    def format_table_response_for_specific_name(self, df: pd.DataFrame, specific_name: str, query_type: Optional[str]) -> str:
        """(Tuỳ chọn) Hiển thị kết quả tìm kiếm theo tên cụ thể dạng bảng text"""
        # Cải thiện label hiển thị
        if query_type == "KCN":
            label = "khu"
        elif query_type == "CCN":
            label = "cụm"
        else:  # query_type is None - tất cả
            label = "khu/cụm"

        if df is None or df.empty:
            return f"Không tìm thấy {label} công nghiệp với tên '{specific_name}'."

        cols = self.columns_map
        
        # Tạo thông báo kết quả cho specific name search
        if len(df) == 1:
            response = f"📊 Tìm thấy thông tin về '{specific_name}':\n\n"
        else:
            response = f"📊 Tìm thấy {len(df)} kết quả phù hợp với '{specific_name}':\n\n"
            
        for _, row in df.iterrows():
            loai = str(row.get(cols['type'], '')).upper()
            ten = row.get(cols['name'], 'Không rõ')
            dia_chi = row.get(cols['address'], '')
            tinh = row.get(cols['province'], '')
            response += f"- [{loai}] {ten} - {tinh} ({dia_chi})\n"
        return response

    # ==========================================================
    # 🆕 IMPROVED KCN DETAIL QUERY WITH MULTIPLE CHOICE SUPPORT
    # ==========================================================
    
    def is_kcn_detail_query(self, question: str) -> bool:
        """
        Kiểm tra xem câu hỏi có phải là tra cứu chi tiết KCN/CCN không
        """
        question_lower = question.lower().strip()
        
        # Kiểm tra từ khóa "Detail" trước - ưu tiên cao nhất
        if question_lower.startswith('detail '):
            # Nếu bắt đầu bằng "Detail" và có KCN/CCN thì chắc chắn là detail query
            kcn_keywords = ['kcn', 'ccn', 'khu công nghiệp', 'cụm công nghiệp']
            if any(keyword in question_lower for keyword in kcn_keywords):
                print(f"🎯 Detected Detail query: {question}")
                return True
        
        # Loại trừ các query tổng quát trước
        general_keywords = [
            'các khu công nghiệp', 'danh sách', 'tất cả', 'những khu công nghiệp',
            'khu công nghiệp nào', 'có bao nhiêu', 'số lượng', 'liệt kê',
            'ở ', ' tại ', ' trong ', 'tỉnh ', 'thành phố'
        ]
        
        # Nếu có từ khóa tổng quát, kiểm tra kỹ hơn
        has_general = any(keyword in question_lower for keyword in general_keywords)
        
        # Keywords chỉ tra cứu chi tiết
        detail_keywords = [
            'thông tin về', 'cho tôi biết về', 'tìm hiểu về', 'giới thiệu về',
            'chi tiết về', 'mô tả về', 'ở đâu', 'nằm ở đâu', 'vị trí',
            'địa chỉ của', 'liên hệ', 'contact', 'detail'
        ]
        
        # Keywords KCN/CCN
        kcn_keywords = [
            'khu công nghiệp', 'kcn', 'cụm công nghiệp', 'ccn',
            'khu cn', 'cụm cn'
        ]
        
        # Kiểm tra có keyword detail và KCN
        has_detail_keyword = any(keyword in question_lower for keyword in detail_keywords)
        has_kcn_keyword = any(keyword in question_lower for keyword in kcn_keywords)
        
        # Pattern đặc biệt: chỉ có "KCN/CCN + tên" mà không có từ tổng quát
        # Ví dụ: "Khu công nghiệp VSIP", "CCN Tân Bình"
        simple_kcn_patterns = [
            r'^(khu công nghiệp|kcn)\s+[a-zA-ZÀ-ỹ0-9]+(?:\s+[a-zA-ZÀ-ỹ0-9\-]+)*\s*$',
            r'^(cụm công nghiệp|ccn)\s+[a-zA-ZÀ-ỹ0-9]+(?:\s+[a-zA-ZÀ-ỹ0-9\-]+)*\s*$'
        ]
        
        # Kiểm tra pattern đơn giản trước
        for pattern in simple_kcn_patterns:
            if re.match(pattern, question_lower):
                print(f"🎯 Detected simple KCN pattern: {question}")
                return True
        
        # Nếu có từ tổng quát nhưng không có detail keyword thì không phải detail query
        if has_general and not has_detail_keyword:
            return False
        
        # Kiểm tra có tên KCN cụ thể (không chỉ là từ khóa chung)
        specific_kcn_patterns = [
            r'(khu công nghiệp|kcn)\s+[a-zA-ZÀ-ỹ0-9]+(?:\s+[a-zA-ZÀ-ỹ0-9\-]+)*',
            r'(cụm công nghiệp|ccn)\s+[a-zA-ZÀ-ỹ0-9]+(?:\s+[a-zA-ZÀ-ỹ0-9\-]+)*'
        ]
        
        has_specific_name = False
        for pattern in specific_kcn_patterns:
            matches = re.findall(pattern, question_lower)
            if matches:
                # Kiểm tra xem có phải chỉ là tên tỉnh không
                for match in matches:
                    full_match = match[0] + ' ' + match[1] if isinstance(match, tuple) else match
                    # Loại trừ nếu chỉ là "khu công nghiệp ở [tỉnh]"
                    if not re.search(r'\s+ở\s+', full_match) and len(full_match.split()) >= 3:
                        has_specific_name = True
                        break
        
        # Trường hợp đặc biệt: "KCN ABC ở đâu" - có tên cụ thể + "ở đâu"
        location_question_pattern = r'(khu công nghiệp|kcn|ccn)\s+[a-zA-ZÀ-ỹ0-9]+(?:\s+[a-zA-ZÀ-ỹ0-9\-]+)*\s+ở\s+đâu'
        if re.search(location_question_pattern, question_lower):
            has_specific_name = True
            has_detail_keyword = True
        
        result = (has_detail_keyword and has_kcn_keyword and has_specific_name) or \
                 (has_specific_name and not has_general)
        
        if result:
            print(f"🎯 Detected KCN detail query: {question}")
        
        return result

    def process_kcn_detail_query_with_multiple_choice(self, question: str) -> Optional[Dict]:
        """
        Xử lý câu hỏi tra cứu chi tiết KCN/CCN với hỗ trợ multiple choice
        
        Returns:
            - Nếu có 1 kết quả: {"type": "kcn_detail", "kcn_info": {...}, ...}
            - Nếu có nhiều kết quả: {"type": "kcn_multiple_choice", "options": [...], ...}
            - Nếu không tìm thấy: {"type": "kcn_detail_not_found", "message": "..."}
        """
        print(f"🔍 Processing KCN detail query: {question}")
        
        if not self.is_kcn_detail_query(question):
            print("❌ Not a KCN detail query")
            return None
        
        # Sử dụng LLM để phân tích và trích xuất tên KCN
        specific_name = None
        query_type = None
        
        if self.llm:
            print("🤖 Using LLM for analysis")
            analysis = self._analyze_query_with_llm(question)
            
            if not analysis.get("is_industrial_query", False):
                print("❌ LLM says not industrial query")
                return None
            
            if analysis.get("search_type") == "specific_name":
                specific_name = analysis.get("specific_name")
                query_type = analysis.get("query_type")
                print(f"🎯 LLM extracted: {specific_name}, type: {query_type}")
        
        # Fallback: extract name manually when no LLM or LLM failed
        if not specific_name:
            print("🔧 Using fallback extraction")
            specific_name = self._extract_kcn_name_fallback(question)
            query_type = None  # Let query_by_specific_name handle this
            print(f"🎯 Fallback extracted: {specific_name}")
        
        if not specific_name:
            print("❌ Could not extract KCN name")
            return None
        
        # Tìm thông tin KCN từ structured data
        print(f"🔍 Searching for: {specific_name}")
        df_result = self.query_by_specific_name(specific_name, query_type)
        
        if df_result is None or df_result.empty:
            print(f"❌ No results found for: {specific_name}")
            return {
                "type": "kcn_detail_not_found",
                "message": f"Không tìm thấy thông tin về '{specific_name}'. Vui lòng kiểm tra lại tên hoặc thử tìm kiếm với từ khóa khác.",
                "query_name": specific_name
            }
        
        print(f"✅ Found {len(df_result)} results")
        
        # 🆕 KIỂM TRA NHIỀU KẾT QUẢ TRÙNG TÊN
        if len(df_result) > 1:
            print(f"🔀 Multiple results found, creating choice list")
            return self._create_multiple_choice_response(df_result, specific_name, query_type)
        
        # Chỉ có 1 kết quả - trả về chi tiết như cũ
        return self._create_single_kcn_detail_response(df_result.iloc[0], specific_name, question)

    def _create_single_kcn_detail_response(self, row, specific_name: str, question: str) -> Dict:
        """
        Tạo response cho 1 KCN duy nhất
        """
        cols = self.columns_map
        
        kcn_info = {
            "Tên": str(row.get(cols["name"], "")),
            "Địa chỉ": str(row.get(cols["address"], "")),
            "Tỉnh/Thành phố": str(row.get(cols["province"], "")),
            "Loại": str(row.get(cols["type"], "")),
            "Tổng diện tích": str(row.get(cols["area"], "")),
            "Giá thuê đất": str(row.get(cols["rental_price"], "")),
            "Thời gian vận hành": str(row.get(cols["operation_time"], "")),
            "Ngành nghề": str(row.get(cols["industry"], "")),
        }
        
        print(f"📋 KCN Info: {kcn_info['Tên']}")
        
        # Tìm tọa độ
        coordinates = self._match_coordinates(kcn_info["Tên"])
        print(f"📍 Coordinates: {coordinates}")
        
        # Enhance với RAG
        rag_analysis = self._enhance_with_rag(kcn_info, question)
        
        result = {
            "type": "kcn_detail",
            "kcn_info": kcn_info,
            "coordinates": coordinates,
            "zoom_level": 16,  # Zoom rất gần để thấy chi tiết vị trí
            "matched_name": kcn_info["Tên"],
            "query_name": specific_name,
            "message": f"Thông tin chi tiết về {kcn_info['Tên']}"
        }
        
        # Thêm RAG analysis nếu có
        if rag_analysis:
            result["rag_analysis"] = rag_analysis
            result["has_rag"] = True
            print("✅ Added RAG analysis")
        else:
            result["has_rag"] = False
            print("⚠️ No RAG analysis")
        
        print("✅ KCN detail query processed successfully")
        return result

    def _extract_kcn_name_fallback(self, question: str) -> Optional[str]:
        """
        Fallback method để trích xuất tên KCN/CCN khi không có LLM
        """
        import re
        
        question_clean = question.strip()
        
        # Pattern đặc biệt cho "Detail KCN/CCN [tên]"
        detail_match = re.search(r'detail\s+(kcn|ccn|khu công nghiệp|cụm công nghiệp)\s+(.+?)(?:\s*$|\s*\?)', question_clean, re.IGNORECASE)
        if detail_match:
            kcn_type = detail_match.group(1).lower()
            kcn_name = detail_match.group(2).strip()
            if kcn_type in ['kcn', 'khu công nghiệp']:
                return f"khu công nghiệp {kcn_name}"
            else:
                return f"cụm công nghiệp {kcn_name}"
        
        # Pattern 1: "về [tên KCN]"
        match = re.search(r'về\s+(.+?)(?:\s*$|\s*\?)', question_clean, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        
        # Pattern 2: Chỉ có "KCN/CCN + tên" (pattern đơn giản)
        simple_patterns = [
            r'^(khu công nghiệp|kcn)\s+(.+?)(?:\s*$|\s*\?)',
            r'^(cụm công nghiệp|ccn)\s+(.+?)(?:\s*$|\s*\?)'
        ]
        
        for pattern in simple_patterns:
            match = re.search(pattern, question_clean, re.IGNORECASE)
            if match:
                kcn_type = match.group(1).lower()
                kcn_name = match.group(2).strip()
                return f"{kcn_type} {kcn_name}"
        
        # Pattern 3: Tìm tên có chứa KCN/CCN keywords trong câu
        kcn_patterns = [
            r'(khu công nghiệp[\w\s\-]+?)(?:\s*$|\s*\?|ở|tại)',
            r'(kcn[\w\s\-]+?)(?:\s*$|\s*\?|ở|tại)',
            r'(cụm công nghiệp[\w\s\-]+?)(?:\s*$|\s*\?|ở|tại)',
            r'(ccn[\w\s\-]+?)(?:\s*$|\s*\?|ở|tại)'
        ]
        
        for pattern in kcn_patterns:
            match = re.search(pattern, question_clean, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return None

    def _create_multiple_choice_response(self, df_result: pd.DataFrame, specific_name: str, query_type: Optional[str]) -> Dict:
        """
        Tạo response khi có nhiều KCN/CCN trùng tên để người dùng lựa chọn
        """
        cols = self.columns_map
        options = []
        
        for idx, row in df_result.iterrows():
            kcn_name = str(row.get(cols["name"], ""))
            kcn_province = str(row.get(cols["province"], ""))
            kcn_address = str(row.get(cols["address"], ""))
            kcn_type = str(row.get(cols["type"], ""))
            
            # Tìm tọa độ cho từng option
            coordinates = self._match_coordinates(kcn_name)
            
            option = {
                "id": idx,  # ID để người dùng chọn
                "name": kcn_name,
                "province": kcn_province,
                "address": kcn_address,
                "type": kcn_type,
                "coordinates": coordinates,
                "display_text": f"{kcn_name} - {kcn_province}"
            }
            options.append(option)
        
        # Tạo message thông báo
        if query_type == "KCN":
            type_label = "khu công nghiệp"
        elif query_type == "CCN":
            type_label = "cụm công nghiệp"
        else:
            type_label = "khu/cụm công nghiệp"
        
        message = f"Tìm thấy {len(options)} {type_label} có tên tương tự '{specific_name}'. Vui lòng chọn một trong các tùy chọn sau:"
        
        return {
            "type": "kcn_multiple_choice",  # Thay đổi type để main.py xử lý
            "options": options,
            "message": message,
            "query_name": specific_name,
            "total_options": len(options)
        }

    def _enhance_with_rag(self, kcn_info: Dict, question: str) -> str:
        """
        Sử dụng RAG để bổ sung thông tin chi tiết về KCN (simplified version)
        """
        if not self.llm:
            return ""
        
        try:
            # Tạo context từ structured data
            kcn_name = kcn_info.get('Tên', 'N/A')
            kcn_address = kcn_info.get('Địa chỉ', 'N/A')
            kcn_province = kcn_info.get('Tỉnh/Thành phố', 'N/A')
            
            # Tạo enhanced query cho RAG
            rag_query = f"Hãy cung cấp thông tin chi tiết về {kcn_name} tại {kcn_province}. Địa chỉ: {kcn_address}"
            
            # Gọi RAG system
            if hasattr(self.llm, 'invoke'):
                rag_response = self.llm.invoke(rag_query)
                if isinstance(rag_response, str):
                    return rag_response
                elif hasattr(rag_response, 'content'):
                    return rag_response.content
                else:
                    return str(rag_response)
            
            return ""
            
        except Exception as e:
            print(f"⚠️ RAG enhancement error: {e}")
            return ""

    def enhance_list_with_rag(self, query_result: Dict, question: str) -> str:
        """
        Sử dụng RAG để bổ sung thông tin cho danh sách KCN/CCN
        """
        if not self.llm:
            return ""
        
        try:
            # Trích xuất thông tin từ query result
            province = query_result.get('province', 'N/A')
            count = query_result.get('count', 0)
            query_type = query_result.get('type', 'N/A')
            
            # Lấy tên một số KCN/CCN tiêu biểu
            data = query_result.get('data', [])
            sample_names = [item.get('Tên', '') for item in data[:5]]
            sample_names_str = ', '.join(sample_names) if sample_names else 'N/A'
            
            # Tạo context-aware RAG query
            if query_type == "KCN":
                type_label = "khu công nghiệp"
            elif query_type == "CCN":
                type_label = "cụm công nghiệp"
            else:
                type_label = "khu và cụm công nghiệp"
            
            rag_query = f"""
Phân tích tình hình {type_label} tại tỉnh {province}.

Dữ liệu hiển thị {count} {type_label}, bao gồm: {sample_names_str}

Hãy cung cấp thông tin chi tiết về:
1. Tổng quan về tình hình phát triển {type_label} tại {province}
2. Chính sách ưu đãi đầu tư và thu hút FDI của tỉnh
3. Ngành nghề trọng điểm và lợi thế cạnh tranh
4. Hạ tầng giao thông, logistics và kết nối vùng
5. Chất lượng nguồn nhân lực và đào tạo
6. Môi trường đầu tư và thủ tục hành chính
7. Kế hoạch phát triển trong 5-10 năm tới
8. So sánh với các tỉnh lân cận trong khu vực

Câu hỏi gốc của người dùng: "{question}"

Hãy trả lời một cách chi tiết và thực tế, tập trung vào thông tin hữu ích cho nhà đầu tư.
"""
            
            # Gọi RAG system
            if hasattr(self.llm, 'invoke'):
                rag_response = self.llm.invoke(rag_query)
                if isinstance(rag_response, str):
                    return rag_response
                elif hasattr(rag_response, 'content'):
                    return rag_response.content
                else:
                    return str(rag_response)
            
            return ""
            
        except Exception as e:
            print(f"⚠️ List RAG enhancement error: {e}")
            return ""

    def enhance_chart_with_rag(self, chart_data: Dict, question: str) -> str:
        """
        Sử dụng RAG để bổ sung phân tích cho biểu đồ
        """
        if not self.llm:
            return ""
        
        try:
            # Trích xuất thông tin từ chart data
            province = chart_data.get('province', 'N/A')
            chart_type = chart_data.get('chart_type', 'N/A')
            data_count = len(chart_data.get('data', []))
            
            # Tạo context-aware RAG query
            rag_query = f"""
Phân tích biểu đồ {chart_type} về khu công nghiệp tại {province}.

Dữ liệu hiển thị {data_count} khu công nghiệp.

Hãy cung cấp phân tích chi tiết về:
1. Tình hình phát triển khu công nghiệp tại {province}
2. Chính sách ưu đãi đầu tư của tỉnh
3. Ngành nghề trọng điểm và tiềm năng
4. Hạ tầng giao thông và logistics
5. So sánh với các tỉnh lân cận
6. Xu hướng phát triển trong tương lai
7. Phân tích dữ liệu từ biểu đồ và đưa ra nhận xét

Câu hỏi gốc của người dùng: "{question}"

Hãy trả lời một cách chi tiết, tập trung vào phân tích xu hướng và cơ hội đầu tư.
"""
            
            # Gọi RAG system
            if hasattr(self.llm, 'invoke'):
                rag_response = self.llm.invoke(rag_query)
                if isinstance(rag_response, str):
                    return rag_response
                elif hasattr(rag_response, 'content'):
                    return rag_response.content
                else:
                    return str(rag_response)
            
            return ""
            
        except Exception as e:
            print(f"⚠️ Chart RAG enhancement error: {e}")
            return ""


# ==========================================================
# 🔌 TÍCH HỢP VÀO CHATBOT
# ==========================================================
def integrate_excel_to_chatbot(excel_path: str, geojson_path: Optional[str] = None, llm=None):
    """Tích hợp module Excel vào chatbot"""
    if not Path(excel_path).exists():
        print(f"❌ Không tìm thấy file Excel: {excel_path}")
        return None
    handler = ExcelQueryHandler(excel_path, geojson_path=geojson_path, llm=llm)
    print("✅ Đã tích hợp module truy vấn Excel với LLM support.")
    return handler


# ==========================================================
# 🧪 TEST MODULE
# ==========================================================
if __name__ == "__main__":
    EXCEL_FILE = r"./data/IIPMap_FULL_63_COMPLETE.xlsx"
    GEOJSON_FILE = r"./map_ui/industrial_zones.geojson"  

    # Khởi tạo LLM cho test
    try:
        from langchain_openai import ChatOpenAI
        test_llm = ChatOpenAI(
            model_name="gpt-4o-mini",
            temperature=0
        )
        print("✅ LLM initialized for testing")
    except:
        test_llm = None
        print("⚠️ LLM not available for testing")

    handler = ExcelQueryHandler(EXCEL_FILE, geojson_path=GEOJSON_FILE, llm=test_llm)

    test_queries = [
        "Danh sách cụm công nghiệp ở Bắc Ninh",
        "Danh sách khu công nghiệp ở Bắc Ninh",
        "Danh sách khu và cụm công nghiệp ở Bắc Ninh",
        "Danh sách tất cả khu công nghiệp và cụm công nghiệp ở Hà Nội",
        "Vẽ biểu đồ cột về diện tích của khu công nghiệp ở Hồ Chí Minh",
        "Vẽ biểu đồ cột về diện tích của cụm công nghiệp ở Đà Nẵng",
        "Vẽ biểu đồ cột về diện tích của cả khu và cụm công nghiệp ở Bình Dương",
        "Khu và cụm công nghiệp tỉnh Lai Châu",  # Test tỉnh không có dữ liệu
        "Danh sách khu công nghiệp ở Điện Biên",  # Test tỉnh không có dữ liệu
        # Test specific name searches
        "cho tôi thông tin về KHU CÔNG NGHIỆP NGŨ LẠC - VĨNH LONG",
        "thông tin về khu công nghiệp Sóng Thần",
        "tìm cụm công nghiệp Tân Bình",
        "KHU CÔNG NGHIỆP VSIP BẮC NINH",
        "cụm công nghiệp Phú Mỹ"
    ]

    print("\n" + "=" * 80)
    print("TEST MODULE TRẢ KẾT QUẢ DẠNG JSON (CÓ TỌA ĐỘ + LLM SMART CHECK)")
    print("=" * 80)

    for query in test_queries:
        print(f"\n❓ {query}")
        handled, response = handler.process_query(query, return_json=True)
        if handled:
            print(response)
        else:
            print("⏭️ Bỏ qua - Không phải câu hỏi liệt kê KCN/CCN hoặc thiếu thông tin")
        print("-" * 80)

    # ==========================================================
    # 🆕 MULTIPLE CHOICE SUPPORT FOR KCN DETAIL QUERIES
    # ==========================================================
    
    def _create_multiple_choice_response(self, df_result: pd.DataFrame, specific_name: str, query_type: Optional[str]) -> Dict:
        """
        Tạo response khi có nhiều KCN/CCN trùng tên để người dùng lựa chọn
        """
        cols = self.columns_map
        options = []
        
        for idx, row in df_result.iterrows():
            kcn_name = str(row.get(cols["name"], ""))
            kcn_province = str(row.get(cols["province"], ""))
            kcn_address = str(row.get(cols["address"], ""))
            kcn_type = str(row.get(cols["type"], ""))
            
            # Tìm tọa độ cho từng option
            coordinates = self._match_coordinates(kcn_name)
            
            option = {
                "id": idx,  # ID để người dùng chọn
                "name": kcn_name,
                "province": kcn_province,
                "address": kcn_address,
                "type": kcn_type,
                "coordinates": coordinates,
                "display_text": f"{kcn_name} - {kcn_province}"
            }
            options.append(option)
        
        # Tạo message thông báo
        if query_type == "KCN":
            type_label = "khu công nghiệp"
        elif query_type == "CCN":
            type_label = "cụm công nghiệp"
        else:
            type_label = "khu/cụm công nghiệp"
        
        message = f"Tìm thấy {len(options)} {type_label} có tên tương tự '{specific_name}'. Vui lòng chọn một trong các tùy chọn sau:"
        
        return {
            "type": "kcn_multiple_choice",  # Thay đổi type để main.py xử lý
            "options": options,
            "message": message,
            "query_name": specific_name,
            "total_options": len(options)
        }

    def process_kcn_detail_query(self, question: str) -> Optional[Dict]:
        """
        Xử lý câu hỏi tra cứu chi tiết KCN/CCN với hỗ trợ multiple choice
        """
        print(f"🔍 Processing KCN detail query: {question}")
        
        if not self.is_kcn_detail_query(question):
            print("❌ Not a KCN detail query")
            return None
        
        # Sử dụng LLM để phân tích và trích xuất tên KCN
        specific_name = None
        query_type = None
        
        if self.llm:
            print("🤖 Using LLM for analysis")
            analysis = self._analyze_query_with_llm(question)
            
            if not analysis.get("is_industrial_query", False):
                print("❌ LLM says not industrial query")
                return None
            
            if analysis.get("search_type") == "specific_name":
                specific_name = analysis.get("specific_name")
                query_type = analysis.get("query_type")
                print(f"🎯 LLM extracted: {specific_name}, type: {query_type}")
        
        # Fallback: extract name manually when no LLM or LLM failed
        if not specific_name:
            print("🔧 Using fallback extraction")
            specific_name = self._extract_kcn_name_fallback(question)
            query_type = None  # Let query_by_specific_name handle this
            print(f"🎯 Fallback extracted: {specific_name}")
        
        if not specific_name:
            print("❌ Could not extract KCN name")
            return None
        
        # Tìm thông tin KCN từ structured data
        print(f"🔍 Searching for: {specific_name}")
        df_result = self.query_by_specific_name(specific_name, query_type)
        
        if df_result is None or df_result.empty:
            print(f"❌ No results found for: {specific_name}")
            return {
                "type": "kcn_detail_not_found",
                "message": f"Không tìm thấy thông tin về '{specific_name}'. Vui lòng kiểm tra lại tên hoặc thử tìm kiếm với từ khóa khác.",
                "query_name": specific_name
            }
        
        print(f"✅ Found {len(df_result)} results")
        
        # 🆕 KIỂM TRA NHIỀU KẾT QUẢ TRÙNG TÊN
        if len(df_result) > 1:
            print(f"🔀 Multiple results found, creating choice list")
            
            # Tạo thông báo với danh sách lựa chọn trong message
            choice_response = self._create_multiple_choice_response(df_result, specific_name, query_type)
            
            # Format thành text message để main.py có thể hiển thị
            options = choice_response.get("options", [])
            message_lines = [choice_response.get("message", "")]
            message_lines.append("")  # Dòng trống
            
            for i, option in enumerate(options):
                display_text = option.get("display_text", "N/A")
                message_lines.append(f"{i+1}. {display_text}")
            
            message_lines.append("")
            message_lines.append("Vui lòng gửi số thứ tự (ví dụ: '1', '2', '3'...) để xem thông tin chi tiết.")
            
            full_message = "\n".join(message_lines)
            
            # Trả về dạng text message thay vì multiple_choice để tương thích với main.py
            return {
                "type": "kcn_detail_not_found",  # Sử dụng type này để main.py trả về text
                "message": full_message,
                "query_name": specific_name,
                # Lưu thông tin để xử lý sau nếu cần
                "_multiple_choice_data": choice_response
            }
        
        # Chỉ có 1 kết quả - xử lý như cũ
        first_row = df_result.iloc[0]
        cols = self.columns_map
        
        kcn_info = {
            "Tên": str(first_row.get(cols["name"], "")),
            "Địa chỉ": str(first_row.get(cols["address"], "")),
            "Tỉnh/Thành phố": str(first_row.get(cols["province"], "")),
            "Loại": str(first_row.get(cols["type"], "")),
            "Tổng diện tích": str(first_row.get(cols["area"], "")),
            "Giá thuê đất": str(first_row.get(cols["rental_price"], "")),
            "Thời gian vận hành": str(first_row.get(cols["operation_time"], "")),
            "Ngành nghề": str(first_row.get(cols["industry"], "")),
        }
        
        print(f"📋 KCN Info: {kcn_info['Tên']}")
        
        # Tìm tọa độ
        coordinates = self._match_coordinates(kcn_info["Tên"])
        print(f"📍 Coordinates: {coordinates}")
        
        # Enhance với RAG
        rag_analysis = self._enhance_with_rag(kcn_info, question)
        
        result = {
            "type": "kcn_detail",
            "kcn_info": kcn_info,
            "coordinates": coordinates,
            "zoom_level": 16,  # Zoom rất gần để thấy chi tiết vị trí
            "matched_name": kcn_info["Tên"],
            "query_name": specific_name,
            "message": f"Thông tin chi tiết về {kcn_info['Tên']}"
        }
        
        # Thêm RAG analysis nếu có
        if rag_analysis:
            result["rag_analysis"] = rag_analysis
            result["has_rag"] = True
            print("✅ Added RAG analysis")
        else:
            result["has_rag"] = False
            print("⚠️ No RAG analysis")
        
        print("✅ KCN detail query processed successfully")
        return result

    def _extract_kcn_name_fallback(self, question: str) -> Optional[str]:
        """
        Fallback method để trích xuất tên KCN/CCN khi không có LLM
        """
        import re
        
        question_clean = question.strip()
        
        # Pattern đặc biệt cho "Detail KCN/CCN [tên]"
        detail_match = re.search(r'detail\s+(kcn|ccn|khu công nghiệp|cụm công nghiệp)\s+(.+?)(?:\s*$|\s*\?)', question_clean, re.IGNORECASE)
        if detail_match:
            kcn_type = detail_match.group(1).lower()
            kcn_name = detail_match.group(2).strip()
            if kcn_type in ['kcn', 'khu công nghiệp']:
                return f"khu công nghiệp {kcn_name}"
            else:
                return f"cụm công nghiệp {kcn_name}"
        
        # Pattern 1: "về [tên KCN]"
        match = re.search(r'về\s+(.+?)(?:\s*$|\s*\?)', question_clean, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        
        # Pattern 2: Chỉ có "KCN/CCN + tên" (pattern đơn giản)
        simple_patterns = [
            r'^(khu công nghiệp|kcn)\s+(.+?)(?:\s*$|\s*\?)',
            r'^(cụm công nghiệp|ccn)\s+(.+?)(?:\s*$|\s*\?)'
        ]
        
        for pattern in simple_patterns:
            match = re.search(pattern, question_clean, re.IGNORECASE)
            if match:
                kcn_type = match.group(1).lower()
                kcn_name = match.group(2).strip()
                return f"{kcn_type} {kcn_name}"
        
        # Pattern 3: Tìm tên có chứa KCN/CCN keywords trong câu
        kcn_patterns = [
            r'(khu công nghiệp[\w\s\-]+?)(?:\s*$|\s*\?|ở|tại)',
            r'(kcn[\w\s\-]+?)(?:\s*$|\s*\?|ở|tại)',
            r'(cụm công nghiệp[\w\s\-]+?)(?:\s*$|\s*\?|ở|tại)',
            r'(ccn[\w\s\-]+?)(?:\s*$|\s*\?|ở|tại)'
        ]
        
        for pattern in kcn_patterns:
            match = re.search(pattern, question_clean, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return None
    # ==========================================================
    # 🆕 IMPROVED KCN DETAIL QUERY WITH MULTIPLE CHOICE SUPPORT
    # ==========================================================
    
    def is_kcn_detail_query(self, question: str) -> bool:
        """
        Kiểm tra xem câu hỏi có phải là tra cứu chi tiết KCN/CCN không
        """
        question_lower = question.lower().strip()
        
        # Kiểm tra từ khóa "Detail" trước - ưu tiên cao nhất
        if question_lower.startswith('detail '):
            # Nếu bắt đầu bằng "Detail" và có KCN/CCN thì chắc chắn là detail query
            kcn_keywords = ['kcn', 'ccn', 'khu công nghiệp', 'cụm công nghiệp']
            if any(keyword in question_lower for keyword in kcn_keywords):
                print(f"🎯 Detected Detail query: {question}")
                return True
        
        # Loại trừ các query tổng quát trước
        general_keywords = [
            'các khu công nghiệp', 'danh sách', 'tất cả', 'những khu công nghiệp',
            'khu công nghiệp nào', 'có bao nhiêu', 'số lượng', 'liệt kê',
            'ở ', ' tại ', ' trong ', 'tỉnh ', 'thành phố'
        ]
        
        # Nếu có từ khóa tổng quát, kiểm tra kỹ hơn
        has_general = any(keyword in question_lower for keyword in general_keywords)
        
        # Keywords chỉ tra cứu chi tiết
        detail_keywords = [
            'thông tin về', 'cho tôi biết về', 'tìm hiểu về', 'giới thiệu về',
            'chi tiết về', 'mô tả về', 'ở đâu', 'nằm ở đâu', 'vị trí',
            'địa chỉ của', 'liên hệ', 'contact', 'detail'
        ]
        
        # Keywords KCN/CCN
        kcn_keywords = [
            'khu công nghiệp', 'kcn', 'cụm công nghiệp', 'ccn',
            'khu cn', 'cụm cn'
        ]
        
        # Kiểm tra có keyword detail và KCN
        has_detail_keyword = any(keyword in question_lower for keyword in detail_keywords)
        has_kcn_keyword = any(keyword in question_lower for keyword in kcn_keywords)
        
        # Pattern đặc biệt: chỉ có "KCN/CCN + tên" mà không có từ tổng quát
        # Ví dụ: "Khu công nghiệp VSIP", "CCN Tân Bình"
        simple_kcn_patterns = [
            r'^(khu công nghiệp|kcn)\s+[a-zA-ZÀ-ỹ0-9]+(?:\s+[a-zA-ZÀ-ỹ0-9\-]+)*\s*$',
            r'^(cụm công nghiệp|ccn)\s+[a-zA-ZÀ-ỹ0-9]+(?:\s+[a-zA-ZÀ-ỹ0-9\-]+)*\s*$'
        ]
        
        # Kiểm tra pattern đơn giản trước
        for pattern in simple_kcn_patterns:
            if re.match(pattern, question_lower):
                print(f"🎯 Detected simple KCN pattern: {question}")
                return True
        
        # Nếu có từ tổng quát nhưng không có detail keyword thì không phải detail query
        if has_general and not has_detail_keyword:
            return False
        
        # Kiểm tra có tên KCN cụ thể (không chỉ là từ khóa chung)
        specific_kcn_patterns = [
            r'(khu công nghiệp|kcn)\s+[a-zA-ZÀ-ỹ0-9]+(?:\s+[a-zA-ZÀ-ỹ0-9\-]+)*',
            r'(cụm công nghiệp|ccn)\s+[a-zA-ZÀ-ỹ0-9]+(?:\s+[a-zA-ZÀ-ỹ0-9\-]+)*'
        ]
        
        has_specific_name = False
        for pattern in specific_kcn_patterns:
            matches = re.findall(pattern, question_lower)
            if matches:
                # Kiểm tra xem có phải chỉ là tên tỉnh không
                for match in matches:
                    full_match = match[0] + ' ' + match[1] if isinstance(match, tuple) else match
                    # Loại trừ nếu chỉ là "khu công nghiệp ở [tỉnh]"
                    if not re.search(r'\s+ở\s+', full_match) and len(full_match.split()) >= 3:
                        has_specific_name = True
                        break
        
        # Trường hợp đặc biệt: "KCN ABC ở đâu" - có tên cụ thể + "ở đâu"
        location_question_pattern = r'(khu công nghiệp|kcn|ccn)\s+[a-zA-ZÀ-ỹ0-9]+(?:\s+[a-zA-ZÀ-ỹ0-9\-]+)*\s+ở\s+đâu'
        if re.search(location_question_pattern, question_lower):
            has_specific_name = True
            has_detail_keyword = True
        
        result = (has_detail_keyword and has_kcn_keyword and has_specific_name) or \
                 (has_specific_name and not has_general)
        
        if result:
            print(f"🎯 Detected KCN detail query: {question}")
        
        return result

    def process_kcn_detail_query_with_multiple_choice(self, question: str) -> Optional[Dict]:
        """
        Xử lý câu hỏi tra cứu chi tiết KCN/CCN với hỗ trợ multiple choice
        
        Returns:
            - Nếu có 1 kết quả: {"type": "kcn_detail", "kcn_info": {...}, ...}
            - Nếu có nhiều kết quả: {"type": "kcn_multiple_choice", "options": [...], ...}
            - Nếu không tìm thấy: {"type": "kcn_detail_not_found", "message": "..."}
        """
        print(f"🔍 Processing KCN detail query: {question}")
        
        if not self.is_kcn_detail_query(question):
            print("❌ Not a KCN detail query")
            return None
        
        # Sử dụng LLM để phân tích và trích xuất tên KCN
        specific_name = None
        query_type = None
        
        if self.llm:
            print("🤖 Using LLM for analysis")
            analysis = self._analyze_query_with_llm(question)
            
            if not analysis.get("is_industrial_query", False):
                print("❌ LLM says not industrial query")
                return None
            
            if analysis.get("search_type") == "specific_name":
                specific_name = analysis.get("specific_name")
                query_type = analysis.get("query_type")
                print(f"🎯 LLM extracted: {specific_name}, type: {query_type}")
        
        # Fallback: extract name manually when no LLM or LLM failed
        if not specific_name:
            print("🔧 Using fallback extraction")
            specific_name = self._extract_kcn_name_fallback(question)
            query_type = None  # Let query_by_specific_name handle this
            print(f"🎯 Fallback extracted: {specific_name}")
        
        if not specific_name:
            print("❌ Could not extract KCN name")
            return None
        
        # Tìm thông tin KCN từ structured data
        print(f"🔍 Searching for: {specific_name}")
        df_result = self.query_by_specific_name(specific_name, query_type)
        
        if df_result is None or df_result.empty:
            print(f"❌ No results found for: {specific_name}")
            return {
                "type": "kcn_detail_not_found",
                "message": f"Không tìm thấy thông tin về '{specific_name}'. Vui lòng kiểm tra lại tên hoặc thử tìm kiếm với từ khóa khác.",
                "query_name": specific_name
            }
        
        print(f"✅ Found {len(df_result)} results")
        
        # 🆕 KIỂM TRA NHIỀU KẾT QUẢ TRÙNG TÊN
        if len(df_result) > 1:
            print(f"🔀 Multiple results found, creating choice list")
            return self._create_multiple_choice_response(df_result, specific_name, query_type)
        
        # Chỉ có 1 kết quả - trả về chi tiết như cũ
        return self._create_single_kcn_detail_response(df_result.iloc[0], specific_name, question)

    def _create_single_kcn_detail_response(self, row, specific_name: str, question: str) -> Dict:
        """
        Tạo response cho 1 KCN duy nhất
        """
        cols = self.columns_map
        
        kcn_info = {
            "Tên": str(row.get(cols["name"], "")),
            "Địa chỉ": str(row.get(cols["address"], "")),
            "Tỉnh/Thành phố": str(row.get(cols["province"], "")),
            "Loại": str(row.get(cols["type"], "")),
            "Tổng diện tích": str(row.get(cols["area"], "")),
            "Giá thuê đất": str(row.get(cols["rental_price"], "")),
            "Thời gian vận hành": str(row.get(cols["operation_time"], "")),
            "Ngành nghề": str(row.get(cols["industry"], "")),
        }
        
        print(f"📋 KCN Info: {kcn_info['Tên']}")
        
        # Tìm tọa độ
        coordinates = self._match_coordinates(kcn_info["Tên"])
        print(f"📍 Coordinates: {coordinates}")
        
        # Enhance với RAG
        rag_analysis = self._enhance_with_rag(kcn_info, question)
        
        result = {
            "type": "kcn_detail",
            "kcn_info": kcn_info,
            "coordinates": coordinates,
            "zoom_level": 16,  # Zoom rất gần để thấy chi tiết vị trí
            "matched_name": kcn_info["Tên"],
            "query_name": specific_name,
            "message": f"Thông tin chi tiết về {kcn_info['Tên']}"
        }
        
        # Thêm RAG analysis nếu có
        if rag_analysis:
            result["rag_analysis"] = rag_analysis
            result["has_rag"] = True
            print("✅ Added RAG analysis")
        else:
            result["has_rag"] = False
            print("⚠️ No RAG analysis")
        
        print("✅ KCN detail query processed successfully")
        return result