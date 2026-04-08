from locust import HttpUser, task, between
import json

class ChatUser(HttpUser):
    # 每個模擬使用者在完成一個任務後，等待 1~3 秒再執行下一個任務
    wait_time = between(1, 3)

    @task(2)
    def test_mock_chat(self):
        """
        模擬發送聊天訊息。
        使用 MOCK_TEST 可以觸發我們剛加在 main.py 裡的攔截機制，
        這樣就不會呼叫到 OpenAI。
        """
        payload = {
            "query": "MOCK_TEST",
            "history": [],
            "lang": "zh"
        }
        
        # FastAPI 使用 SSE 串流回傳，因此我們必須將 stream=True 打開
        # catch_response=True 允許我們手動標記結果成功或失敗
        with self.client.post("/chat", json=payload, stream=True, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 429:
                # 遇到 429 Too Many Requests 代表我們成功觸發了 slowapi 速率限制
                # 我們可以視為系統正常防禦，或視為失敗（若您想測試純吞吐量的話）
                response.failure("Hit Rate Limit (429 Too Many Requests)")
            else:
                response.failure(f"Failed with status: {response.status_code}")

    @task(1)
    def test_frontend_static(self):
        """
        同時測試 FastAPI 吐回 React 靜態檔案的能力
        """
        with self.client.get("/", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Frontend returned status: {response.status_code}")
