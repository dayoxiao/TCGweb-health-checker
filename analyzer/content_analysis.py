import os
import re
import json
from datetime import datetime
from dataclasses import dataclass
from typing import Dict

import google.generativeai as genai
from crawler.web_crawler import CrawlResult

@dataclass
class AnalysisResult:
    url: str
    status: str
    last_updated: str
    score: int
    notes: str
    broken_links: str


class ContentAnalysisAgent:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables.")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.5-flash-lite-preview-06-17')


    def analyze(self, crawl_result: CrawlResult) -> AnalysisResult:
        if not crawl_result.html:
            return AnalysisResult(
                url=crawl_result.url,
                status="❌ 錯誤",
                last_updated="",
                score=100,
                notes="無法抓取網頁內容",
                broken_links="",
            )

        today_str = datetime.now().strftime("%Y-%m-%d")

        broken_links_list = [
            f"{link} (狀態: {code})"
            for link, code in crawl_result.link_status.items()
            if code != 200
        ]
        broken_links_str = "\n".join(broken_links_list)

        prompt = f"""
        請根據以下HTML內容和抓取到的資訊，評估一個政府網站是否過時。
        你的角色是一位網站健檢專家。

        **參考資訊:**
        - **今天日期**: {today_str}
        - 網站 URL: {crawl_result.url}
        - 最後更新日期: {crawl_result.last_updated or '未找到'}
        - **失效連結**: {broken_links_str or '無'}

**3. 評分指南 (請嚴格遵循，總分100分):**
        您必須針對以下三個主要項目，各自給予規定的分數。分數越高，代表該項目越過時或問題越嚴重。
        此外，您需要根據失效連結的數量給予一個額外的加分項。

        **A. 過時元件 (Outdated Component) - (0-40分):**
        - **基準**: jQuery < 3.0, React < 16.8, Vue < 2.6 皆視為過時。
        - **0分**: 未偵測到函式庫，或使用的函式庫皆為現代版本。
        - **1-20分**: 使用了一個過時的函式庫。
        - **21-40分**: 使用了多個過時的函式庫，或版本極為古老 (例如 jQuery 1.x)。

        **B. 過時內容 (Outdated Content) - (0-40分):**
        - **0分**: 內容非常新穎，提及近期的活動或資訊。
        - **1-20分**: 內容看起來不常更新 (例如都是通用性說明)，但沒有明確的過期指標。
        - **21-40分**: 內容有非常明確的過期資訊 (例如: 提及數年前的活動、新聞、法規，且無更新跡象)。

        **C. 過久未更新 (Last Update) - (0-20分):**
        - **0分**: 「最後更新日期」在一年內。
        - **1-10分**: 「最後更新日期」距今 1-2 年。
        - **11-20分**: 「最後更新日期」距今超過 2 年。
        - **注意**: 如果沒有找到「最後更新日期」，可能為爬蟲程式判別不到，請斟酌給分。

        **D. 額外加分 - 失效連結 (Broken Link Penalty) - (0-5分):**
        - **0分**: 沒有失效連結。
        - **1-2分**: 存在 1-4 個失效連結。
        - **3-5分**: 存在 5 個或更多失效連結。
        - **注意**: 403可能是跳轉驗證，所以可以忽略。

        **4. 你的任務:**
        請根據以上所有資訊，綜合判斷並完全按照下面的 JSON 格式回傳你的分析結果，不得有其他種回復格式，不然系統會出錯。
        在 `notes` 中，請簡潔地總結你的主要發現，並點出判斷的關鍵依據 (例如：「偵測到使用過時的 jQuery 1.12.4，且最後更新日為三年前，並發現3個失效連結。」)。

        **HTML 內容 (前 2000 字元):**
        ```html
        {crawl_result.html[:2000]}
        ```

        **輸出要求:**
        請嚴格按照以下 JSON 格式回傳，不要有任何額外的文字或說明：
        {{\n          "score": <一個 0-100 的整數，分數越高代表越過時>,\n          "notes": "<一段簡短的中文說明，總結你的發現，如果發現失效連結，請在說明中提及(完整連結url)>"\n        }}
        """

        try:
            response = self.model.generate_content(prompt)
            # 清理並解析 JSON
            cleaned_response = response.text.strip().replace('`', '')
            if cleaned_response.startswith("json"):
                cleaned_response = cleaned_response[4:]
            
            data = json.loads(cleaned_response)
            score = data.get("score", 100)
            notes = data.get("notes", "無法從 API 取得有效回覆")

        except (json.JSONDecodeError, ValueError, Exception) as e:
            print(f"Error processing API response for {crawl_result.url}: {e}")
            score = 100
            notes = f"API 回應解析失敗: {e}"


        if score < 50:
            status = "✅ 正常"
        elif score < 80:
            status = "⚠️ 疑似"
        else:
            status = "❌ 過時"

        return AnalysisResult(
            url=crawl_result.url,
            status=status,
            last_updated=crawl_result.last_updated,
            score=score,
            notes=notes,
            broken_links=broken_links_str,
        )
