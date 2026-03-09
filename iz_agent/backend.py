import pandas as pd
import json
import re
import io
import base64
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

# Fallback cho rapidfuzz
try:
    from rapidfuzz import fuzz, process
except ImportError:
    fuzz = None
    process = None

class IIPMapBackend:
    def __init__(self, excel_path: str, geojson_path: str = None):
        try:
            self.df = pd.read_excel(excel_path)
            self.df.columns = self.df.columns.str.strip()
        except Exception as e:
            print(f"❌ Lỗi load Excel: {e}")
            self.df = pd.DataFrame()
            
        self.geojson_map = {}
        
        # Mapping cột chuẩn (tự động tìm nếu không khớp)
        self.cols = {
            "province": "Tỉnh/Thành phố", 
            "type": "Loại", 
            "name": "Tên",
            "address": "Địa chỉ", 
            "price": "Giá thuê đất", 
            "area": "Tổng diện tích",
            "industry": "Ngành nghề",
        }
        
        # Phân chia 3 miền Việt Nam
        self.regions = {
            "Miền Bắc": [
                "Hà Nội", "Hải Phòng", "Quảng Ninh", "Bắc Ninh", "Bắc Giang", 
                "Hải Dương", "Hưng Yên", "Thái Bình", "Nam Định", "Ninh Bình",
                "Vĩnh Phúc", "Phú Thọ", "Thái Nguyên", "Lạng Sơn", "Cao Bằng",
                "Bắc Kạn", "Tuyên Quang", "Lào Cai", "Yên Bái", "Hà Giang",
                "Điện Biên", "Lai Châu", "Sơn La", "Hòa Bình"
            ],
            "Miền Trung": [
                "Thanh Hóa", "Nghệ An", "Hà Tĩnh", "Quảng Bình", "Quảng Trị",
                "Thừa Thiên Huế", "Đà Nẵng", "Quảng Nam", "Quảng Ngãi", 
                "Bình Định", "Phú Yên", "Khánh Hòa", "Ninh Thuận", "Bình Thuận",
                "Kon Tum", "Gia Lai", "Đắk Lắk", "Đắk Nông", "Lâm Đồng"
            ],
            "Miền Nam": [
                "Hồ Chí Minh", "Bình Dương", "Đồng Nai", "Bà Rịa - Vũng Tàu",
                "Long An", "Tiền Giang", "Bến Tre", "Trà Vinh", "Vĩnh Long",
                "Đồng Tháp", "An Giang", "Kiên Giang", "Cần Thơ", "Hậu Giang",
                "Sóc Trăng", "Bạc Liêu", "Cà Mau", "Tây Ninh", "Bình Phước"
            ]
        }
        
        # Load GeoJSON
        if geojson_path and Path(geojson_path).exists():
            try:
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for feat in data.get('features', []):
                    props = feat.get('properties', {})
                    geom = feat.get('geometry', {})
                    if props.get('name') and geom.get('coordinates'):
                        norm_name = self._normalize(props['name'])
                        self.geojson_map[norm_name] = geom['coordinates']
            except Exception as e:
                print(f"⚠️ GeoJSON Error: {e}")

        # Pre-process số liệu
        if not self.df.empty:
            self._map_columns_dynamic()
            
            # Tạo các cột chuẩn hóa cho tìm kiếm - TỰ ĐỘNG NHẬN DIỆN
            # Tìm cột tên
            name_col = None
            for col in self.df.columns:
                if any(keyword in col.lower() for keyword in ['tên', 'name']) and not col.endswith('_num'):
                    name_col = col
                    break
            if name_col:
                self.df['name_norm'] = self.df[name_col].astype(str).apply(self._normalize)
            
            # Tìm cột loại
            type_col = None  
            for col in self.df.columns:
                if any(keyword in col.lower() for keyword in ['loại', 'type', 'kind']):
                    type_col = col
                    break
            if type_col:
                self.df['type_norm'] = self.df[type_col].astype(str).apply(self._normalize)
            
            # Tìm cột tỉnh
            prov_col = None
            for col in self.df.columns:
                if any(keyword in col.lower() for keyword in ['tỉnh', 'thành phố', 'province', 'city']):
                    prov_col = col
                    break
            if prov_col:
                self.df['prov_norm'] = self.df[prov_col].astype(str).apply(self._normalize)
            
            # Tự động tạo các cột số cho tất cả cột có thể chứa số
            self._create_numeric_columns()

    def _map_columns_dynamic(self):
        """Tìm tên cột gần đúng trong file Excel nếu tên cứng không khớp"""
        for key, val in self.cols.items():
            if val not in self.df.columns:
                for real_col in self.df.columns:
                    if val.lower() in real_col.lower():
                        self.cols[key] = real_col
                        break

    def get_all_columns(self):
        if self.df.empty: return []
        return self.df.columns.tolist()

    def _normalize(self, text):
        return str(text).lower().strip()
    
    def _clean_dict_for_json(self, data_dict):
        """Clean dictionary for JSON serialization by handling NaN values"""
        import math
        import pandas as pd
        
        cleaned = {}
        for key, value in data_dict.items():
            # Bỏ qua các cột _num
            if key.endswith('_num'):
                continue
                
            # Xử lý float NaN/Infinity
            if isinstance(value, float):
                if math.isnan(value) or math.isinf(value):
                    cleaned[key] = None
                    continue
            
            # Xử lý pandas NaN
            if pd.isna(value):
                cleaned[key] = None
                continue
                
            # Xử lý string "nan", "inf"
            if isinstance(value, str):
                if value.lower() in ['nan', 'inf', '-inf', 'infinity', '-infinity']:
                    cleaned[key] = None
                    continue
            
            cleaned[key] = value
        return cleaned

    def _extract_number(self, s):
        """Hàm tách số mạnh mẽ từ chuỗi lộn xộn (VD: '&nbsp;60%')"""
        # Thay thế các ký tự lạ thường gặp trong web scraping
        s = s.replace("&nbsp;", "").replace("%", "").replace(",", ".")
        match = re.search(r'(\d+\.?\d*)', s)
        return float(match.group(1)) if match else None

    def _parse_smart(self, val, col_name):
        """Parser đơn giản - tự động nhận diện"""
        if pd.isna(val): return None
        
        s = str(val).lower().strip()
        
        # ✅ KIỂM TRA CÁC GIÁ TRỊ KHÔNG HỢP LỆ TRƯỚC
        # Nếu là "Đang cập nhật", "N/A", "TBA", v.v. → trả về None
        invalid_values = ['đang cập nhật', 'dang cap nhat', 'n/a', 'na', 'tba', 'updating', 'unknown', 'không rõ', 'khong ro']
        if any(invalid in s for invalid in invalid_values):
            return None
        
        # Giá: có "giá", "price", "usd"
        if any(x in col_name.lower() for x in ['giá', 'price']) or 'usd' in s:
            s = s.replace("usd", "").replace("/m²/năm", "").replace("/m2/năm", "")
            if "-" in s:
                parts = s.split("-")
                try: 
                    num1 = self._extract_number(parts[0])
                    num2 = self._extract_number(parts[1])
                    if num1 and num2:
                        return (num1 + num2) / 2
                except: 
                    pass
        
        # Diện tích: có "diện tích", "area", "ha"  
        elif any(x in col_name.lower() for x in ['diện tích', 'area']) or 'ha' in s:
            s = s.replace("ha", "").replace("hecta", "")
        
        # Thời gian vận hành: KHÔNG parse ở đây (xử lý riêng)
        elif any(x in col_name.lower() for x in ['thời gian', 'vận hành', 'operation']):
            return None  # Sẽ xử lý riêng trong _create_operation_time_columns
        
        # ✅ Tất cả: tách số, nếu không có số thì trả về None (KHÔNG phải 0)
        result = self._extract_number(s)
        return result if result is not None else None

    def _create_numeric_columns(self):
        """Tạo cột số cho tất cả cột"""
        for col in self.df.columns:
            if col not in ['name_norm', 'type_norm', 'prov_norm']:
                self.df[f"{col}_num"] = self.df[col].apply(lambda x: self._parse_smart(x, col))
        
        # Xử lý riêng cho "Thời gian vận hành"
        self._create_operation_time_columns()
    
    def _create_operation_time_columns(self):
        """Tạo các cột phụ trợ cho Thời gian vận hành"""
        operation_col = None
        for col in self.df.columns:
            if any(keyword in col.lower() for keyword in ['thời gian', 'vận hành', 'operation']):
                operation_col = col
                break
        
        if not operation_col or operation_col not in self.df.columns:
            return
        
        def parse_operation_time(val):
            """Parse thời gian vận hành thành dict với nhiều thông tin
            
            Logic tính số năm vận hành:
            - "2015 - 2065" → duration = 2065 - 2015 = 50 năm
            - "50 năm" hoặc "50 năm kể từ..." → duration = 50 năm
            """
            if pd.isna(val):
                return {'start': None, 'end': None, 'duration': None}
            
            s = str(val).strip()
            result = {'start': None, 'end': None, 'duration': None}
            
            # Case 1: "2015 - 2065" hoặc "2015 – 2065" (năm bắt đầu - năm kết thúc)
            # QUAN TRỌNG: Tính duration = năm kết thúc - năm bắt đầu
            match = re.search(r'(\d{4})\s*[-–]\s*(\d{4})', s)
            if match:
                start_year = int(match.group(1))
                end_year = int(match.group(2))
                result['start'] = start_year
                result['end'] = end_year
                result['duration'] = end_year - start_year  # Công thức: năm phải - năm trái
                return result
            
            # Case 2: "50 năm" hoặc "50 năm kể từ..." (chỉ có số năm)
            # QUAN TRỌNG: Lấy số năm trực tiếp
            match = re.search(r'(\d+)\s*năm', s)
            if match:
                duration = int(match.group(1))
                result['duration'] = duration
                # Không có start/end vì không biết năm cụ thể
                return result
            
            # Case 3: Chỉ có 1 năm (năm bắt đầu) - KHÔNG tính duration
            match = re.search(r'(\d{4})', s)
            if match:
                year = int(match.group(1))
                result['start'] = year
                # Không tính duration vì không có năm kết thúc
                return result
            
            return result
        
        # Tạo các cột phụ trợ
        parsed = self.df[operation_col].apply(parse_operation_time)
        
        # Chỉ lấy giá trị hợp lệ (>0), các giá trị None/0 sẽ bị loại bỏ khi filter
        self.df[f"{operation_col}_start_num"] = parsed.apply(lambda x: x['start'] if x['start'] and x['start'] > 0 else None)
        self.df[f"{operation_col}_end_num"] = parsed.apply(lambda x: x['end'] if x['end'] and x['end'] > 0 else None)
        self.df[f"{operation_col}_duration_num"] = parsed.apply(lambda x: x['duration'] if x['duration'] and x['duration'] > 0 else None)

    def _get_numeric_column(self, col_name):
        """Tìm cột số - logic thông minh với ưu tiên từ khóa"""
        col_name_lower = col_name.lower()
        
        # 1. Thử trực tiếp với tên cột
        if f"{col_name}_num" in self.df.columns:
            return f"{col_name}_num"
        
        # 2. Xử lý đặc biệt cho "Thời gian vận hành"
        if any(keyword in col_name_lower for keyword in ['thời gian', 'vận hành', 'operation']):
            # Tìm cột gốc
            operation_col = None
            for col in self.df.columns:
                if any(kw in col.lower() for kw in ['thời gian', 'vận hành', 'operation']) and not col.endswith('_num'):
                    operation_col = col
                    break
            
            if operation_col:
                # Phân loại theo từ khóa
                if any(kw in col_name_lower for kw in ['bắt đầu', 'start', 'từ']):
                    return f"{operation_col}_start_num"
                elif any(kw in col_name_lower for kw in ['kết thúc', 'end', 'hết hạn', 'đến', 'hạn']):
                    return f"{operation_col}_end_num"
                elif any(kw in col_name_lower for kw in ['số năm', 'duration', 'thời hạn', 'năm']):
                    return f"{operation_col}_duration_num"
                else:
                    # Mặc định: số năm vận hành
                    return f"{operation_col}_duration_num"
        
        # 3. Ưu tiên tìm cột chính xác với từ khóa đặc biệt
        # Tránh nhầm lẫn giữa "hệ số sử dụng đất" và "diện tích"
        priority_keywords = {
            'lấp đầy': ['lấp đầy', 'occupancy'],
            'sử dụng': ['sử dụng đất', 'sử dụng', 'utilization'],
            'hệ số': ['hệ số', 'tỷ lệ', 'ratio'],
            'diện tích': ['diện tích', 'area'],
            'giá': ['giá', 'price'],
        }
        
        # Tìm nhóm từ khóa phù hợp
        for group_key, keywords in priority_keywords.items():
            if any(kw in col_name_lower for kw in keywords):
                # Tìm cột có chứa từ khóa này
                for real_col in self.df.columns:
                    real_col_lower = real_col.lower()
                    # Kiểm tra cột có chứa từ khóa và có _num
                    if any(kw in real_col_lower for kw in keywords) and f"{real_col}_num" in self.df.columns:
                        # Đảm bảo không nhầm lẫn (vd: "sử dụng đất" không match với "diện tích")
                        if group_key == 'sử dụng' and 'diện tích' in real_col_lower:
                            continue
                        if group_key == 'diện tích' and any(x in real_col_lower for x in ['lấp đầy', 'sử dụng', 'occupancy']):
                            continue
                        return f"{real_col}_num"
        
        # 4. Thử tìm cột tương tự (fuzzy matching - fallback)
        for real_col in self.df.columns:
            if col_name_lower in real_col.lower() and f"{real_col}_num" in self.df.columns:
                return f"{real_col}_num"
        
        # 5. Thử mapping ngược từ tên thân thiện sang tên thật
        for key, real_col_name in self.cols.items():
            if col_name_lower == key.lower() and f"{real_col_name}_num" in self.df.columns:
                return f"{real_col_name}_num"
        
        return None

    def _parse_general_number(self, val):
        """Dùng cho các cột động (Mật độ, Tầng cao...) - DEPRECATED, dùng _parse_smart"""
        if pd.isna(val): return 0
        s = str(val).lower()
        return self._extract_number(s) or 0

    def search_single_zone(self, zone_name: str):
        """Tìm kiếm 1 KCN/CCN cụ thể với logic thông minh"""
        if self.df.empty:
            return {"type": "error", "message": "Không có dữ liệu."}
        
        zone_name_norm = self._normalize(zone_name)
        
        # Tìm cột tên
        name_col = None
        for col in self.df.columns:
            if any(keyword in col.lower() for keyword in ['tên', 'name']) and not col.endswith('_num'):
                name_col = col
                break
        
        if not name_col:
            return {"type": "error", "message": "Không tìm thấy cột tên trong dữ liệu."}
        
        # 1. Tìm exact match (khớp hoàn toàn)
        exact_matches = self.df[self.df['name_norm'] == zone_name_norm]
        if len(exact_matches) == 1:
            return {"type": "single_result", "data": self._clean_dict_for_json(exact_matches.iloc[0].to_dict())}
        
        # 2. Tìm partial match (chứa từ khóa)
        partial_matches = self.df[self.df['name_norm'].str.contains(zone_name_norm, na=False)]
        
        if len(partial_matches) == 0:
            return {"type": "not_found", "message": f"Không tìm thấy KCN/CCN nào có tên chứa '{zone_name}'."}
        
        elif len(partial_matches) == 1:
            return {"type": "single_result", "data": partial_matches.iloc[0].to_dict()}
        
        else:
            # 3. Nhiều kết quả - tạo danh sách lựa chọn
            choices = []
            for idx, row in partial_matches.head(10).iterrows():  # Tối đa 10 lựa chọn
                # Tìm cột tỉnh
                location = "Không rõ"
                for col in self.df.columns:
                    if any(keyword in col.lower() for keyword in ['tỉnh', 'thành phố', 'province']):
                        location = str(row.get(col, "Không rõ"))
                        break
                
                # Tìm cột loại
                zone_type = "Không rõ"
                for col in self.df.columns:
                    if any(keyword in col.lower() for keyword in ['loại', 'type']):
                        zone_type = str(row.get(col, "Không rõ"))
                        break
                
                choices.append({
                    "name": str(row.get(name_col, "")),
                    "location": location,
                    "type": zone_type,
                    "coordinates": self.match_coordinates(str(row.get(name_col, ""))),
                    "full_data": self._clean_dict_for_json(row.to_dict())
                })
            
            return {
                "type": "multiple_choices",
                "message": f"Tìm thấy {len(partial_matches)} KCN/CCN có tên tương tự '{zone_name}'. Bạn đang tìm:",
                "choices": choices,
                "total_found": len(partial_matches)
            }

    def match_coordinates(self, name: str):
        norm = self._normalize(name)
        if norm in self.geojson_map: return self.geojson_map[norm]
        if process and self.geojson_map:
            match = process.extractOne(norm, list(self.geojson_map.keys()), scorer=fuzz.WRatio)
            if match and match[1] > 85: return self.geojson_map[match[0]]
        return None

    def query_flexible(self, filters: dict):
            df_res = self.df.copy()

            # Lấy logic mode (AND hoặc OR)
            logic_mode = filters.get("logic_mode", "AND").upper()

            # 1. LỌC LOẠI (KCN/CCN)
            zone_type = filters.get("zone_type", "ALL")
            if zone_type != "ALL":
                try:
                    if zone_type == "KCN":
                        df_res = df_res[df_res['type_norm'].str.contains("khu|kcn|ip|iz", regex=True, na=False)]
                    elif zone_type == "CCN":
                        df_res = df_res[df_res['type_norm'].str.contains("cụm|ccn|cluster", regex=True, na=False)]
                except Exception as e:
                    print(f"❌ Error in zone_type filter: {e}")

            # 2. LỌC THEO MIỀN
            region = filters.get("region")
            if region:
                provinces = self.get_provinces_by_region(region)
                if provinces:
                    region_pattern = "|".join([self._normalize(p) for p in provinces])
                    df_res = df_res[df_res['prov_norm'].str.contains(region_pattern, regex=True, na=False)]

            # 3. LỌC SỐ HỌC (Numeric Filters) với AND/OR
            numeric_filters = filters.get("numeric_filters", [])

            if isinstance(numeric_filters, dict):
                converted_filters = []
                for col_name, value in numeric_filters.items():
                    clean_col = col_name.replace("_num", "")

                    if isinstance(value, dict):
                        converted_filters.append({
                            "col": clean_col,
                            "op": value.get("op", ">="),
                            "val": value.get("val", 0)
                        })
                    else:
                        converted_filters.append({
                            "col": clean_col,
                            "op": ">=",
                            "val": value
                        })
                numeric_filters = converted_filters

            if numeric_filters and logic_mode == "OR":
                # OR logic: Tạo mask cho từng điều kiện, sau đó OR lại
                masks = []
                for nf in numeric_filters:
                    if not isinstance(nf, dict):
                        continue

                    col = nf.get("col")
                    op = nf.get("op", ">=")
                    val = nf.get("val", 0)

                    try:
                        val = float(val)
                    except (ValueError, TypeError):
                        continue

                    numeric_col = self._get_numeric_column(col)
                    if numeric_col and numeric_col in df_res.columns:
                        try:
                            if op == "<":
                                masks.append(df_res[numeric_col] < val)
                            elif op == ">":
                                masks.append(df_res[numeric_col] > val)
                            elif op == "<=":
                                masks.append(df_res[numeric_col] <= val)
                            elif op == ">=":
                                masks.append(df_res[numeric_col] >= val)
                        except Exception as e:
                            print(f"⚠️ Lỗi filter numeric {col}: {e}")

                # Combine masks with OR
                if masks:
                    combined_mask = masks[0]
                    for mask in masks[1:]:
                        combined_mask = combined_mask | mask
                    df_res = df_res[combined_mask]
            else:
                # AND logic (mặc định): Áp dụng từng điều kiện
                for nf in numeric_filters:
                    if not isinstance(nf, dict):
                        continue

                    col = nf.get("col")
                    op = nf.get("op", ">=")
                    val = nf.get("val", 0)

                    try:
                        val = float(val)
                    except (ValueError, TypeError):
                        continue

                    numeric_col = self._get_numeric_column(col)
                    if numeric_col and numeric_col in df_res.columns:
                        try:
                            # Lọc bỏ các giá trị None/NaN trước khi so sánh
                            if op == "<":
                                df_res = df_res[df_res[numeric_col].notna() & (df_res[numeric_col] < val)]
                            elif op == ">":
                                df_res = df_res[df_res[numeric_col].notna() & (df_res[numeric_col] > val)]
                            elif op == "<=":
                                df_res = df_res[df_res[numeric_col].notna() & (df_res[numeric_col] <= val)]
                            elif op == ">=":
                                df_res = df_res[df_res[numeric_col].notna() & (df_res[numeric_col] >= val)]
                        except Exception as e:
                            print(f"⚠️ Lỗi filter numeric {col}: {e}")

            # 4. LỌC TEXT (Ngành nghề, địa chỉ, v.v.) với AND/OR
            text_filters = filters.get("text_filters", [])

            if text_filters and logic_mode == "OR":
                # OR logic cho text filters
                masks = []
                for tf in text_filters:
                    if not isinstance(tf, dict):
                        continue

                    col = tf.get("col")
                    val = tf.get("val", "")

                    real_col = col if col in df_res.columns else None
                    if not real_col:
                        for c in df_res.columns:
                            if col.lower() == c.lower():
                                real_col = c
                                break

                    if real_col and val:
                        try:
                            masks.append(df_res[real_col].astype(str).str.contains(str(val), case=False, na=False))
                        except Exception as e:
                            print(f"⚠️ Lỗi filter text {col}: {e}")

                if masks:
                    combined_mask = masks[0]
                    for mask in masks[1:]:
                        combined_mask = combined_mask | mask
                    df_res = df_res[combined_mask]
            else:
                # AND logic cho text filters
                for tf in text_filters:
                    if not isinstance(tf, dict):
                        continue

                    col = tf.get("col")
                    val = tf.get("val", "")

                    real_col = col if col in df_res.columns else None
                    if not real_col:
                        for c in df_res.columns:
                            if col.lower() == c.lower():
                                real_col = c
                                break

                    if real_col and val:
                        try:
                            df_res = df_res[df_res[real_col].astype(str).str.contains(str(val), case=False, na=False)]
                        except Exception as e:
                            print(f"⚠️ Lỗi filter text {col}: {e}")

            # 5. LỌC CÁC CỘT KHÁC (backward compatibility)
            for col, val in filters.items():
                if col in ["zone_type", "numeric_filters", "text_filters", "sort_by", "limit", "region", "logic_mode"]: 
                    continue

                real_col = col if col in df_res.columns else None
                if not real_col:
                    for c in df_res.columns:
                        if col.lower() == c.lower():
                            real_col = c
                            break

                if real_col:
                    if any(keyword in real_col.lower() for keyword in ['tỉnh', 'thành phố', 'province']):
                        df_res = df_res[df_res['prov_norm'].str.contains(self._normalize(val), na=False)]
                    elif any(keyword in real_col.lower() for keyword in ['tên', 'name']) and not real_col.endswith('_num'):
                        df_res = df_res[df_res['name_norm'].str.contains(self._normalize(val), na=False)]
                    else:
                        df_res = df_res[df_res[real_col].astype(str).str.contains(str(val), case=False, na=False)]

            # 6. SẮP XẾP
            sort_by = filters.get("sort_by")
            if sort_by:
                sort_col = sort_by.get("col")
                sort_order = sort_by.get("order", "desc")

                if sort_col:
                    numeric_col = self._get_numeric_column(sort_col)
                    if numeric_col and numeric_col in df_res.columns:
                        # ✅ LỌC BỎ GIÁ TRỊ KHÔNG HỢP LỆ (None, NaN, 0) TRƯỚC KHI SORT
                        # Đặc biệt quan trọng cho "Giá thuê đất" có giá trị "Đang cập nhật"
                        df_res = df_res[df_res[numeric_col].notna() & (df_res[numeric_col] > 0)]
                        
                        ascending = (sort_order == "asc")
                        df_res = df_res.sort_values(by=numeric_col, ascending=ascending)

            # 7. GIỚI HẠN SỐ LƯỢNG
            limit = filters.get("limit")
            if limit and isinstance(limit, int) and limit > 0:
                df_res = df_res.head(limit)

            return df_res

    def generate_chart_base64(self, df: pd.DataFrame, title: str, metric_col: str = "dual", limit: int = None):
        if df.empty:
            print("⚠️ generate_chart_base64: DataFrame rỗng, trả về None")
            return None
        df_plot = df.copy()
        
        # Xử lý limit
        if limit == -1:
            # -1 = unlimited, hiển thị tất cả
            limit = len(df_plot)
        elif limit is None:
            # None = default 50 để tránh biểu đồ quá dài
            limit = min(len(df_plot), 50)
        
        # --- Logic Vẽ Biểu Đồ CỘT (BAR CHART) ---
        if metric_col == 'dual':
            # Dual chart: tự động tìm cột giá và diện tích
            price_col = None
            area_col = None
            
            # Tìm cột giá (có chứa từ khóa liên quan)
            for col in df_plot.columns:
                if any(keyword in col.lower() for keyword in ['giá', 'price', 'thuê']) and col.endswith('_num'):
                    price_col = col
                    break
            
            # Tìm cột diện tích (có chứa từ khóa liên quan)  
            for col in df_plot.columns:
                if any(keyword in col.lower() for keyword in ['diện tích', 'area']) and col.endswith('_num'):
                    # Loại trừ các cột về tỷ lệ/hệ số
                    if not any(exclude in col.lower() for exclude in ['lấp đầy', 'sử dụng', 'occupancy', 'tỷ lệ', 'hệ số']):
                        area_col = col
                        break
            
            # ✅ LỌC BỎ GIÁ TRỊ KHÔNG HỢP LỆ TRƯỚC KHI SORT VÀ VẼ
            if price_col and area_col:
                # Lọc bỏ các dòng có giá hoặc diện tích không hợp lệ
                df_plot = df_plot[(df_plot[price_col].notna()) & (df_plot[price_col] > 0) & 
                                  (df_plot[area_col].notna()) & (df_plot[area_col] > 0)]
                df_plot = df_plot.sort_values([price_col, area_col], ascending=False).head(limit)
            elif price_col:
                # Chỉ lọc theo giá
                df_plot = df_plot[(df_plot[price_col].notna()) & (df_plot[price_col] > 0)]
                df_plot = df_plot.sort_values(price_col, ascending=False).head(limit)
            elif area_col:
                # Chỉ lọc theo diện tích
                df_plot = df_plot[(df_plot[area_col].notna()) & (df_plot[area_col] > 0)]
                df_plot = df_plot.sort_values(area_col, ascending=False).head(limit)
            else:
                print(f"⚠️ generate_chart_base64: Không tìm thấy cột giá hoặc diện tích cho dual chart")
                return None
        else:
            # Tìm cột số tương ứng
            numeric_col = self._get_numeric_column(metric_col)
            if numeric_col and numeric_col in df_plot.columns:
                # ✅ LỌC BỎ GIÁ TRỊ KHÔNG HỢP LỆ TRƯỚC KHI SORT VÀ VẼ
                df_plot = df_plot[(df_plot[numeric_col].notna()) & (df_plot[numeric_col] > 0)]
                df_plot = df_plot.sort_values(numeric_col, ascending=False).head(limit)
            else:
                print(f"⚠️ generate_chart_base64: Không tìm thấy cột số cho metric '{metric_col}'")
                return None

        df_plot = df_plot.iloc[::-1] # Đảo ngược để vẽ
        
        # Tự động tìm cột tên để làm label
        name_col = None
        for col in df_plot.columns:
            if any(keyword in col.lower() for keyword in ['tên', 'name']) and not col.endswith('_num'):
                name_col = col
                break
        
        if not name_col:
            name_col = df_plot.columns[0]  # Fallback: dùng cột đầu tiên
            
        names = df_plot[name_col].tolist()
        
        # Điều chỉnh kích thước biểu đồ cho vertical bars (cột dọc)
        width = max(12, len(names) * 0.6)  # Tăng chiều rộng theo số items
        height = 8  # Chiều cao cố định
        plt.figure(figsize=(width, height))
        
        # --- VẼ BIỂU ĐỒ CỘT ---
        if metric_col == 'dual':
            # Tự động tìm cột giá để vẽ
            price_col = None
            for col in df_plot.columns:
                if any(keyword in col.lower() for keyword in ['giá', 'price', 'thuê']) and col.endswith('_num'):
                    price_col = col
                    break
            
            if price_col and price_col in df_plot.columns:
                vals = df_plot[price_col].fillna(0).tolist()
                bars = plt.bar(names, vals, color='#1f77b4')
                plt.ylabel("Giá thuê (USD/m²/năm)")
                # Thêm giá trị lên đầu mỗi cột
                for bar, val in zip(bars, vals):
                    if val > 0:
                        plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(vals)*0.01, 
                                f'{val:.0f}', ha='center', va='bottom', fontsize=8)
        else:
            # Vẽ biểu đồ cho bất kỳ cột nào
            numeric_col = self._get_numeric_column(metric_col)
            if numeric_col in df_plot.columns:
                vals = df_plot[numeric_col].fillna(0).tolist()
                
                # Chọn màu dựa trên loại dữ liệu
                if any(keyword in metric_col.lower() for keyword in ['lấp đầy', 'sử dụng', 'occupancy', 'tỷ lệ', 'hệ số']):
                    color = '#ff7f0e'  # Cam cho hệ số/tỷ lệ
                elif any(keyword in metric_col.lower() for keyword in ['diện tích', 'area']):
                    color = '#2ca02c'  # Xanh lá cho diện tích
                elif any(keyword in metric_col.lower() for keyword in ['giá', 'price']):
                    color = '#1f77b4'  # Xanh dương cho giá
                else:
                    color = '#ff7f0e'  # Cam mặc định
                
                bars = plt.bar(names, vals, color=color)
                plt.ylabel(f"{metric_col} (Số liệu)")
                
                # Thêm giá trị lên đầu mỗi cột
                for bar, val in zip(bars, vals):
                    if val > 0:
                        plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(vals)*0.01, 
                                f'{val:.1f}', ha='center', va='bottom', fontsize=8)

        plt.title(f"{title} ({len(names)} kết quả)", fontsize=14, fontweight='bold')
        
        # Xoay labels để tránh chồng chéo và cải thiện hiển thị
        plt.xticks(rotation=90, ha='center', fontsize=9)
        plt.xlabel("Khu công nghiệp", fontsize=12)
        
        # Thêm grid để dễ đọc
        plt.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode('utf-8')
        plt.close()
        
        # Kiểm tra base64 có null không
        if not b64 or b64 == "":
            print("❌ generate_chart_base64: Chuỗi base64 rỗng!")
            return None
        
        print(f"✅ generate_chart_base64: Đã tạo base64 thành công (độ dài: {len(b64)} ký tự)")
        return b64

    def get_region_name(self, province: str) -> str:
        """Lấy tên miền từ tên tỉnh"""
        province_norm = self._normalize(province)
        for region, provinces in self.regions.items():
            for prov in provinces:
                if self._normalize(prov) in province_norm or province_norm in self._normalize(prov):
                    return region
        return "Không xác định"

    def get_provinces_by_region(self, region: str) -> list:
        """Lấy danh sách tỉnh theo miền"""
        region_norm = self._normalize(region)
        for region_name, provinces in self.regions.items():
            if region_norm in self._normalize(region_name):
                return provinces
        return []

