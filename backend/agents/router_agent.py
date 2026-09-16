"""
Router Agent (router_agent.py)
------------------------------
Facade mỏng — nhận câu hỏi từ API, chuyển giao sang AgentPipeline,
ghi lịch sử hội thoại và trả về 2 PHẢN HỒI BỐC TÁCH (2 SEPARATE RESPONSES).
"""

from typing import Optional, Generator, Tuple
from backend.agents.pipeline import agent_pipeline
from backend.database import log_chat_history

# Bản đồ các câu chào xã giao phản hồi 0ms
GREETINGS_MAP = {
    ("hi", "hello", "xin chào", "chào", "chào bạn", "hey", "alo", "chào em", "chào bot"):
        "Xin chào! Tôi là Trợ Lý AI RAG Vạn Năng. Tôi hỗ trợ bóc tách tài liệu, ghi nhật ký công việc & truy vấn CSDL SQLite!",
    ("cảm ơn", "thanks", "thank you", "cảm ơn bạn", "cảm ơn bot", "ok cảm ơn"):
        "Không có chi! Rất vui được hỗ trợ bạn. Bạn có cần tra cứu thêm thông tin nào nữa không?",
    ("bạn là ai", "who are you", "bạn tên gì", "giới thiệu"):
        "Tôi là Trợ lý AI Agent tích hợp RAG, NL2SQL & Daily Logger. Bạn có thể nhắn tin tự nhiên để lưu nhật ký công việc hoặc tra cứu CSDL!",
}


class RouterAgent:
    def check_greeting(self, text: str) -> Optional[str]:
        clean_text = text.strip().lower().rstrip(".!?,")
        for keywords, response in GREETINGS_MAP.items():
            if clean_text in keywords:
                return response
        return None

    def route_and_execute_split(self, question: str, history: Optional[list] = None) -> Tuple[str, str]:
        """
        Trả về đúng 2 Phản hồi riêng biệt (Tuple of 2 Responses):
        - Response 1: Tiến trình tư duy (Thinking Trace)
        - Response 2: Kết quả thực thi (Content Body)
        """
        greeting = self.check_greeting(question)
        if greeting:
            log_chat_history(question, greeting, intent="GREETING")
            return greeting, ""

        thinking = ""
        body = ""
        final_intent = "SQL"
        for stage, content, intent in agent_pipeline.dispatch_stages(question, history=history):
            final_intent = intent
            if stage == "thinking":
                thinking = content
            elif stage == "body":
                body = content

        log_chat_history(question, f"{thinking}\n{body}", intent=final_intent)
        return thinking, body

    def route_and_execute(self, question: str, history: Optional[list] = None) -> str:
        """Thực thi đồng bộ (hỗ trợ multi-turn history)"""
        resp1, resp2 = self.route_and_execute_split(question, history=history)
        if not resp2:
            return resp1
        return f"{resp1}\n\n---RESPONSE_SPLIT---\n\n{resp2}"

    def route_and_stream(self, question: str, history: Optional[list] = None) -> Generator[str, None, None]:
        """
        Stream 2 phản hồi phân tách bằng cờ '---RESPONSE_SPLIT---' (hỗ trợ multi-turn history):
        - Phát Response 1 (Thinking Trace)
        - Phát phân cách '---RESPONSE_SPLIT---'
        - Phát Response 2 (Content Body)
        """
        greeting = self.check_greeting(question)
        if greeting:
            log_chat_history(question, greeting, intent="GREETING")
            yield greeting
            return

        full_chunks = []
        final_intent = "SQL"
        first_stage = True
        
        for stage, content, intent in agent_pipeline.dispatch_stages(question, history=history):
            final_intent = intent
            if not first_stage:
                yield "\n---RESPONSE_SPLIT---\n"
                full_chunks.append("\n---RESPONSE_SPLIT---\n")
            
            full_chunks.append(content)
            yield content
            first_stage = False

        log_chat_history(question, "".join(full_chunks), intent=final_intent)


router_agent = RouterAgent()
