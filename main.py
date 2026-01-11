# main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import uvicorn
from typing import Optional, Any, Dict
from pathlib import Path
import json
import inspect

from starlette.concurrency import run_in_threadpool

from mst.router import is_mst_query
from mst.handler import handle_mst_query
from law_db_query.handler import handle_law_count_query

from excel_visualize import (
    is_excel_visualize_intent,
    handle_excel_visualize
)

from excel_query.excel_query import ExcelQueryHandler


# ===============================
# Import Chatbot từ app.py
# ===============================
try:
    import app  # app.py của bạn (LangChain chatbot + vectordb + llm + emb + excel_handler + sheet funcs)
    CHATBOT_AVAILABLE = True
    print("✅ Đã import thành công module 'app'")
except ImportError as e:
    app = None
    CHATBOT_AVAILABLE = False
    print(f"WARNING: Could not import 'app' module. Error: {e}")


# ===============================
# Helper: parse JSON string từ pipeline
# ===============================
def try_parse_json_string(s: Any):
    """
    Nếu s là JSON string thì parse ra dict/list; không thì trả None.
    """
    if not isinstance(s, str):
        return None
    t = s.strip()
    if not t:
        return None
    if (t.startswith("{") and t.endswith("}")) or (t.startswith("[") and t.endswith("]")):
        try:
            return json.loads(t)
        except Exception:
            return None
    return None


# ===============================
# Lấy các hằng số từ app.py
# ===============================
CONTACT_TRIGGER_RESPONSE = None
if CHATBOT_AVAILABLE and hasattr(app, "CONTACT_TRIGGER_RESPONSE"):
    CONTACT_TRIGGER_RESPONSE = app.CONTACT_TRIGGER_RESPONSE
    print("✅ Đã load CONTACT_TRIGGER_RESPONSE từ app.py")
else:
    CONTACT_TRIGGER_RESPONSE = (
        "Anh/chị vui lòng để lại tên và số điện thoại, chuyên gia của IIP sẽ liên hệ và giải đáp các yêu cầu của anh/chị ạ."
    )
    print("⚠️ Sử dụng CONTACT_TRIGGER_RESPONSE mặc định")


# ===============================
# Kiểm tra Google Sheet availability
# ===============================
SHEET_AVAILABLE = False
try:
    if CHATBOT_AVAILABLE and hasattr(app, "save_contact_info") and hasattr(app, "is_valid_phone"):
        SHEET_AVAILABLE = True
        print("✅ Google Sheet functions đã sẵn sàng từ app.py")
    else:
        print("WARNING: Google Sheet functions not found in app.py")
except Exception as e:
    print(f"WARNING: Error checking Google Sheet availability: {e}")


# --- Khai báo Model cho dữ liệu đầu vào ---
class Question(BaseModel):
    """Định nghĩa cấu trúc dữ liệu JSON đầu vào."""
    question: str
    phone: Optional[str] = None
    name: Optional[str] = None
    url: Optional[str] = None


class ContactInfo(BaseModel):
    """Định nghĩa cấu trúc dữ liệu cho thông tin liên hệ."""
    original_question: str
    phone: str
    name: Optional[str] = None


# ---------------------------------------
# 1️⃣ Khởi tạo FastAPI App + bật CORS
# ---------------------------------------
app_fastapi = FastAPI(
    title="Chatbot Luật Lao động API",
    description="API cho mô hình chatbot",
    version="1.0.0"
)

origins = ["*"]

app_fastapi.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent

# ✅ Local Excel + GeoJSON cho map (KCN/CCN)
EXCEL_FILE_PATH = str(BASE_DIR / "data" / "IIPMap_FULL_63_COMPLETE.xlsx")
GEOJSON_IZ_PATH = str(BASE_DIR / "map_ui" / "industrial_zones.geojson")

excel_kcn_handler = ExcelQueryHandler(
    excel_path=EXCEL_FILE_PATH,
    geojson_path=GEOJSON_IZ_PATH
)


# ---------------------------------------
# 2️⃣ Route kiểm tra hoạt động (GET /)
# ---------------------------------------
@app_fastapi.get("/", summary="Kiểm tra trạng thái API")
async def home():
    vectordb_status = "Unknown"
    if CHATBOT_AVAILABLE:
        try:
            stats = app.get_vectordb_stats()
            if stats.get("exists", False):
                vectordb_status = f"Ready ({stats.get('total_documents', 0)} docs)"
            else:
                vectordb_status = "Empty or Not Found"
        except Exception as e:
            vectordb_status = f"Error: {str(e)}"

    return {
        "message": "✅ Chatbot Luật Lao động API đang hoạt động.",
        "usage": "Gửi POST tới /chat với JSON { 'question': 'Câu hỏi của bạn' }",
        "chatbot_status": "Available" if CHATBOT_AVAILABLE else "Not Available",
        "vectordb_status": vectordb_status,
        "sheet_status": "Available" if SHEET_AVAILABLE else "Not Available",
        "contact_trigger": CONTACT_TRIGGER_RESPONSE
    }


# ---------------------------------------
# 3️⃣ Route chính: /chat (POST)
# ---------------------------------------
@app_fastapi.post("/chat", summary="Dự đoán/Trả lời câu hỏi từ Chatbot")
async def predict(data: Question):
    question = (data.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Thiếu trường 'question' trong JSON hoặc câu hỏi bị rỗng.")

    try:
        answer: Optional[str] = None
        requires_contact = False

        # ===============================
        # 0️⃣ LAW COUNT – SQL FIRST
        # ===============================
        payload = handle_law_count_query(question)
        if isinstance(payload, dict) and payload.get("intent") == "law_count":
            response = await run_in_threadpool(
                app.chatbot.invoke,
                {
                    "message": question,
                    "law_count": payload["total_laws"],
                },
                config={"configurable": {"session_id": "api_session"}},
            )

            # response thường là string, nhưng cứ xử lý parse JSON nếu có
            parsed = try_parse_json_string(response)
            if isinstance(parsed, dict) and parsed.get("type") == "flowchart":
                return {
                    "answer": "Đây là flowchart do ChatIIP tạo cho bạn:",
                    "type": "flowchart",
                    "payload": {
                        "format": parsed.get("format", "mermaid"),
                        "code": parsed.get("code", ""),
                        "explanation": parsed.get("explanation", ""),
                    },
                    "requires_contact": False,
                }

            return {"answer": response, "requires_contact": False}

        # ===============================
        # 1️⃣ MST INTENT (ƯU TIÊN CAO NHẤT)
        # ===============================
        if is_mst_query(question):
            if not CHATBOT_AVAILABLE:
                return {"answer": "Backend chưa sẵn sàng (không import được app.py).", "requires_contact": False}

            mst_answer = await run_in_threadpool(
                handle_mst_query,
                message=question,
                llm=app.llm,
                embedding=app.emb,
            )
            return {"answer": mst_answer, "requires_contact": False}

        # ===============================
        # 2️⃣ EXCEL VISUALIZE INTENT
        # ===============================
        if is_excel_visualize_intent(question):
            if not CHATBOT_AVAILABLE:
                return {"answer": "Backend chưa sẵn sàng (không import được app.py).", "requires_contact": False}

            excel_result = await run_in_threadpool(
                handle_excel_visualize,
                message=question,
                excel_handler=app.excel_handler,
            )

            return {
                "answer": "Đây là biểu đồ do Chatiip tạo cho bạn: ",
                "type": "excel_visualize",
                "payload": excel_result,
                "requires_contact": False,
            }

        # ===============================
        # 3️⃣ EXCEL KCN/CCN (BẢNG + TỌA ĐỘ) - ƯU TIÊN TRƯỚC LLM
        # ===============================
        handled, excel_payload = await run_in_threadpool(
            excel_kcn_handler.process_query,
            question,
            True,  # return_json=True
        )

        if handled and excel_payload:
            try:
                excel_obj = json.loads(excel_payload) if isinstance(excel_payload, str) else excel_payload
            except Exception:
                excel_obj = {"error": "ExcelQuery trả về dữ liệu không hợp lệ."}

            # Nếu có lỗi yêu cầu làm rõ (thiếu tỉnh/thiếu loại)
            if isinstance(excel_obj, dict) and excel_obj.get("error"):
                return {
                    "answer": excel_obj,
                    "type": "excel_query",
                    "map_intent": None,
                    "requires_contact": False,
                }

            iz_list = []
            if isinstance(excel_obj, dict):
                for r in (excel_obj.get("data", []) or []):
                    coords = r.get("coordinates")
                    if isinstance(coords, list) and len(coords) == 2:
                        iz_list.append(
                            {
                                "name": r.get("Tên", ""),
                                "kind": r.get("Loại", excel_obj.get("type")),
                                "address": r.get("Địa chỉ", ""),
                                "coordinates": coords,
                            }
                        )

            province = excel_obj.get("province") if isinstance(excel_obj, dict) else None

            if province and province != "TOÀN QUỐC":
                map_intent = {
                    "type": "province",
                    "province": province,
                    "iz_list": iz_list,
                    "kind": excel_obj.get("type") if isinstance(excel_obj, dict) else None,
                }
            else:
                map_intent = {
                    "type": "points",
                    "iz_list": iz_list,
                    "kind": excel_obj.get("type") if isinstance(excel_obj, dict) else None,
                }

            return {
                "answer": excel_obj,
                "type": "excel_query",
                "map_intent": map_intent,
                "requires_contact": False,
            }

        # ===============================
        # 4️⃣ FALLBACK: GỌI CHATBOT (RAG/PDF PIPELINE)
        # ===============================
        if CHATBOT_AVAILABLE and hasattr(app, "chatbot"):
            session = "api_session"

            if not hasattr(app.chatbot, "invoke"):
                return {"answer": "Lỗi: Chatbot không có phương thức invoke", "requires_contact": False}

            try:
                # invoke async hay sync?
                if inspect.iscoroutinefunction(app.chatbot.invoke):
                    response = await app.chatbot.invoke(
                        {"message": question},
                        config={"configurable": {"session_id": session}},
                    )
                else:
                    response = await run_in_threadpool(
                        app.chatbot.invoke,
                        {"message": question},
                        config={"configurable": {"session_id": session}},
                    )

                # Chuẩn hoá response -> string
                if isinstance(response, dict) and "output" in response:
                    answer = response["output"]
                elif isinstance(response, str):
                    answer = response
                else:
                    answer = f"Lỗi: Chatbot trả về định dạng không mong muốn: {repr(response)}"

                # ✅ NEW: Nếu pipeline trả JSON string (flowchart/...)
                parsed = try_parse_json_string(answer)
                if isinstance(parsed, dict) and parsed.get("type") == "flowchart":
                    return {
                        "answer": "Đây là flowchart do ChatIIP tạo cho bạn:",
                        "type": "flowchart",
                        "payload": {
                            "format": parsed.get("format", "mermaid"),
                            "code": parsed.get("code", ""),
                            "explanation": parsed.get("explanation", ""),
                        },
                        "requires_contact": False,
                    }

                # Trigger contact giống app.py
                if answer and answer.strip() == CONTACT_TRIGGER_RESPONSE.strip():
                    requires_contact = True
                    print(f"🔔 TRIGGER PHÁT HIỆN: Câu hỏi '{question}' cần thu thập thông tin liên hệ")

            except Exception as invoke_error:
                print(f"❌ Lỗi khi gọi chatbot.invoke: {invoke_error}")
                answer = "Xin lỗi, đã xảy ra lỗi khi xử lý câu hỏi của bạn."

        else:
            answer = (
                f"(Chatbot mô phỏng - LỖI BACKEND: Không tìm thấy đối tượng app.chatbot) "
                f"Bạn hỏi: '{question}'"
            )

        # ===============================
        # 5️⃣ Nếu người dùng gửi phone ngay từ đầu (tuỳ chọn)
        # ===============================
        if data.phone and SHEET_AVAILABLE and CHATBOT_AVAILABLE:
            try:
                await run_in_threadpool(
                    app.save_contact_info,
                    question,
                    data.phone,
                    data.name or "",
                )
                print(f"✅ Đã ghi thông tin liên hệ sớm: {data.phone}")
            except Exception as sheet_error:
                print(f"⚠️ Lỗi ghi Google Sheet: {sheet_error}")

        return {"answer": answer, "requires_contact": requires_contact}

    except HTTPException:
        raise
    except Exception as e:
        print(f"LỖI CHATBOT: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi xử lý Chatbot: {str(e)}. Vui lòng kiểm tra log backend của bạn.",
        )


# ---------------------------------------
# 4️⃣ Route mới: /submit-contact (POST)
# ---------------------------------------
@app_fastapi.post("/submit-contact", summary="Gửi thông tin liên hệ sau khi chatbot yêu cầu")
async def submit_contact(data: ContactInfo):
    if not SHEET_AVAILABLE or not CHATBOT_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Google Sheet không khả dụng. Vui lòng kiểm tra cấu hình server.",
        )

    phone = (data.phone or "").strip()
    if not app.is_valid_phone(phone):
        raise HTTPException(
            status_code=400,
            detail="Số điện thoại không hợp lệ. Vui lòng nhập số điện thoại hợp lệ (tối thiểu 7 ký tự, chỉ chứa số, khoảng trắng hoặc dấu gạch ngang).",
        )

    try:
        await run_in_threadpool(
            app.save_contact_info,
            data.original_question,
            phone,
            data.name or "",
        )

        print("✅ Đã lưu thông tin liên hệ:")
        print(f"   - Câu hỏi: {data.original_question}")
        print(f"   - Phone: {phone}")
        print(f"   - Name: {data.name or 'Không cung cấp'}")

        return {
            "success": True,
            "message": "Cảm ơn anh/chị! Chuyên gia của IIP sẽ liên hệ với anh/chị trong thời gian sớm nhất.",
            "contact_saved": {
                "question": data.original_question,
                "phone": phone,
                "name": data.name or "",
            },
        }

    except Exception as e:
        print(f"❌ Lỗi khi lưu thông tin liên hệ: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Không thể lưu thông tin liên hệ. Lỗi: {str(e)}",
        )


# ---------------------------------------
# 5️⃣ Route kiểm tra trạng thái VectorDB
# ---------------------------------------
@app_fastapi.get("/status", summary="Kiểm tra trạng thái chi tiết của hệ thống")
async def get_status():
    if not CHATBOT_AVAILABLE:
        return {
            "chatbot": "Not Available",
            "vectordb": "Unknown",
            "google_sheet": "Unknown",
            "error": "Module app.py không được import thành công",
        }

    vectordb_info: Dict[str, Any] = {}
    try:
        stats = app.get_vectordb_stats()
        vectordb_info = {
            "status": "Ready" if stats.get("exists", False) else "Not Ready",
            "index_name": stats.get("name", "Unknown"),
            "total_documents": stats.get("total_documents", 0),
            "dimension": stats.get("dimension", 0),
            "exists": stats.get("exists", False),
        }
    except Exception as e:
        vectordb_info = {"status": "Error", "error": str(e)}

    sheet_info = {
        "status": "Available" if SHEET_AVAILABLE else "Not Available",
        "sheet_id": os.getenv("GOOGLE_SHEET_ID", "Not configured"),
    }

    return {
        "chatbot": "Available",
        "vectordb": vectordb_info,
        "google_sheet": sheet_info,
        "trigger_response": CONTACT_TRIGGER_RESPONSE,
    }


# ---------------------------------------
# 6️⃣ Khởi động server Uvicorn (FastAPI)
# ---------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    # file này tên main.py => "main:app_fastapi"
    uvicorn.run("main:app_fastapi", host="0.0.0.0", port=port, log_level="info", reload=True)
