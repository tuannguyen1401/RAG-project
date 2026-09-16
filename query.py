import sys
import os
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

CHROMA_PATH = "./chroma_db"

def format_docs_with_sources(documents):
    formatted = []
    for i, doc in enumerate(documents, 1):
        source = doc.metadata.get("source", "Tài liệu")
        page = doc.metadata.get("page", 1)
        formatted.append(f"[Đoạn {i} | File: {source} (Trang {page})]:\n{doc.page_content}")
    return "\n\n".join(formatted)

def load_rag_chain():
    if not os.path.exists(CHROMA_PATH):
        print(f"❌ Không tìm thấy cơ sở dữ liệu tại '{CHROMA_PATH}'.")
        print("Vui lòng chạy `python ingest.py` trước để nạp dữ liệu!")
        sys.exit(1)
        
    embeddings = OllamaEmbeddings(model="nomic-embed-text")
    vectorstore = Chroma(persist_directory=CHROMA_PATH, embedding_function=embeddings)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
    
    llm = ChatOllama(model="qwen2.5:3b", temperature=0.1)
    
    prompt_template = """Dựa vào các đoạn thông tin trích dẫn dưới đây để trả lời câu hỏi một cách chính xác và ngắn gọn.
Nếu ngữ cảnh cung cấp tên file hoặc số trang, hãy chỉ rõ nguồn thông tin ở cuối câu trả lời (Ví dụ: theo file tailieu.pdf, trang 2...).
Nếu không tìm thấy thông tin trong ngữ cảnh, hãy trả lời "Tôi không tìm thấy thông tin này trong tài liệu."

--- NGỮ CẢNH ---
{context}

--- CÂU HỎI ---
{question}

--- TRẢ LỜI ---"""

    prompt = ChatPromptTemplate.from_template(prompt_template)
    
    chain = (
        {"context": retriever | format_docs_with_sources, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )
    return chain, retriever

def main():
    print("⚡ Đang nạp cơ sở dữ liệu ChromaDB và mô hình LLM...")
    rag_chain, retriever = load_rag_chain()
    print("✅ Đã nạp xong! Hệ thống RAG sẵn sàng trả lời.\n")

    # Nếu truyền câu hỏi trực tiếp qua CLI
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        print(f"❓ Câu hỏi: {question}")
        print("⏳ Đang suy nghĩ...\n")
        response = rag_chain.invoke(question)
        print(f"🤖 Trả lời:\n{response}\n")
        return

    # Vòng lặp tương tác liên tục
    print("💬 Nhập câu hỏi của bạn (gõ 'exit' hoặc 'quit' để thoát):")
    print("=" * 60)
    
    while True:
        try:
            user_input = input("\n👤 Bạn: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit", "q", "thoát"]:
                print("👋 Tạm biệt!")
                break
                
            print("⏳ Đang xử lý câu trả lời...")
            response = rag_chain.invoke(user_input)
            print(f"\n🤖 LLM: {response}\n")
            print("-" * 60)
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Tạm biệt!")
            break

if __name__ == "__main__":
    main()
