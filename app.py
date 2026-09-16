from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

# 1. Đọc và chia nhỏ file
print("1. Đang đọc file và chia nhỏ...")
loader = TextLoader("tailieu.txt", encoding="utf-8")
docs = loader.load()

text_splitter = RecursiveCharacterTextSplitter(chunk_size=300, chunk_overlap=30)
splits = text_splitter.split_documents(docs)

# 2. Tạo Vector Store với nomic-embed-text
print("2. Đang tạo vector nhúng qua Ollama...")
embeddings = OllamaEmbeddings(model="nomic-embed-text")
vectorstore = Chroma.from_documents(documents=splits, embedding=embeddings)
retriever = vectorstore.as_retriever(search_kwargs={"k": 2})

# 3. Khởi tạo LLM parable4b
llm = ChatOllama(model="qwen2.5:3b", temperature=0.1)

# Định dạng các tài liệu tìm được thành một đoạn text liền
def format_docs(documents):
    return "\n\n".join(doc.page_content for doc in documents)

# 4. Tạo Prompt & Pipeline (LCEL)
prompt_template = """Dựa vào ngữ cảnh dưới đây để trả lời câu hỏi ngắn gọn:
{context}

Câu hỏi: {question}
Trả lời:"""

prompt = ChatPromptTemplate.from_template(prompt_template)

rag_chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)

# 5. Chạy thử
cau_hoi = "Người đại diện theo pháp luật của công ty là ai và công ty làm về mảng gì?"
print(f"\nCâu hỏi: {cau_hoi}")
print("Đang xử lý câu trả lời...\n")

response = rag_chain.invoke(cau_hoi)
print(f"Trả lời: {response}")