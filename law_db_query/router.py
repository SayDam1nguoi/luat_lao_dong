from law_db_query.handler import handle_law_article_query
from data_processing.pipeline import process_pdf_question


def route_message(
    input_dict,
    llm,
    lang_llm,
    retriever,
    retriever_vsic_2018=None,   
    excel_handler=None
):
    message = input_dict["message"]

    # ==================================================
    # 1. NHÁNH DB – TRA ĐIỀU LUẬT (GIỮ NGUYÊN)
    # ==================================================
    law_response = handle_law_article_query(message)
    if law_response:
        return law_response

    # ==================================================
    # 2. NHÁNH RAG – TRUYỀN THÊM VSIC 2018
    # ==================================================
    return process_pdf_question(
        input_dict,
        llm=llm,
        lang_llm=lang_llm,
        retriever=retriever,                     
        retriever_vsic_2018=retriever_vsic_2018, 
        excel_handler=excel_handler
    )
