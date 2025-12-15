from law_db_query.handler import handle_law_article_query
from data_processing.pipeline import process_pdf_question

def route_message(
    input_dict,
    llm,
    lang_llm,
    retriever,
    excel_handler
):
    message = input_dict["message"]

    # 1. Nhánh DB
    law_response = handle_law_article_query(message)
    if law_response:
        return law_response

    # 2. Nhánh RAG – GIỮ NGUYÊN INPUT
    return process_pdf_question(
        input_dict,
        llm=llm,
        lang_llm=lang_llm,
        retriever=retriever,
        excel_handler=excel_handler
    )
