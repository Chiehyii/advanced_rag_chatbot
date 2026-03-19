import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import json
import os
import config
import asyncio

# New Ragas imports
from ragas import SingleTurnSample
from ragas.metrics import Faithfulness, ResponseRelevancy, LLMContextPrecisionWithoutReference

# Langchain components for Ragas
# NOTE: You may need to install new packages: pip install langchain-openai
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

# --- Constants ---
DB_FILE = "evaluation.db"
TABLE_NAME = config.DB_TABLE_NAME
OPENAI_API_KEY = config.OPENAI_API_KEY

# --- Ragas Components Initialization ---
# Ragas v0.1+ is designed to work well with Langchain components
# Use a newer model and enforce JSON output mode to prevent validation errors.
# This requires a model version that supports JSON mode (e.g., gpt-4o, gpt-4-turbo, gpt-3.5-turbo-0125).
evaluator_llm = ChatOpenAI(
    model=config.OPENAI_MODEL_NAME,  
    openai_api_key=OPENAI_API_KEY,
    model_kwargs={"response_format": {"type": "json_object"}},
) 
# ResponseRelevancy and LLMContextPrecisionWithoutReference require embeddings
evaluator_embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)

# Instantiate metrics
faithfulness_metric = Faithfulness(llm=evaluator_llm)
response_relevancy_metric = ResponseRelevancy(llm=evaluator_llm, embeddings=evaluator_embeddings)
context_precision_metric = LLMContextPrecisionWithoutReference(llm=evaluator_llm)

def fetch_unevaluated_data():
    """從資料庫中獲取尚未評估的問答紀錄"""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        # 使用 row_factory 讓每一行都像字典一樣方便存取
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        

        # 選擇 faithfulness_score 或新指標為空的紀錄，代表尚未評估
        # This also handles rows that were partially evaluated before adding the new metric
        cursor.execute(f"SELECT id, rephrased_question, answer, retrieved_contexts FROM {TABLE_NAME} WHERE faithfulness_score IS NULL")
        rows = cursor.fetchall()
        
        print(f"找到 {len(rows)} 筆尚未評估的紀錄。")
        return rows

    except sqlite3.Error as e:
        # 🚨 ERROR：資料庫讀取錯誤
        print(f"[DB] 無法讀取資料庫: {e}")
        return []
    finally:
        if conn:
            conn.close()

def update_scores_in_db(results_list):
    """將評估分數更新回資料庫"""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # 新增 context_precision_score 欄位
        # We can try to add the column if it doesn't exist
        try:
            cursor.execute(f"ALTER TABLE {TABLE_NAME} ADD COLUMN context_precision_score REAL")
            conn.commit()
            print("已成功新增 'context_precision_score' 欄位。")
        except sqlite3.OperationalError:
            # Column already exists, which is fine
            pass
        

        update_query = f'''UPDATE {TABLE_NAME} SET 
                         faithfulness_score = ?,
                         response_relevancy_score = ?,
                         context_precision_score = ?
                         WHERE id = ?'''
        
        # results_list is a list of dicts: [{'id': 1, 'faithfulness_score': 1.0, ...}, ...]
        records_to_update = [
            (
                res.get('faithfulness_score'),
                res.get('response_relevancy_score'),
                res.get('context_precision_score'),
                res.get('id')
            )
            for res in results_list
        ]

        cursor.executemany(update_query, records_to_update)
        conn.commit()
        print(f"\n成功將 {len(records_to_update)} 筆評估分數更新至資料庫。")

    except sqlite3.Error as e:
        # 🚨 ERROR：資料庫更新錯誤
        print(f"\n[DB] 更新分數時出錯: {e}")
    finally:
        if conn:
            conn.close()


async def main():
    """主執行函式"""
    # 1. 從資料庫獲取資料
    unevaluated_rows = fetch_unevaluated_data()
    if not unevaluated_rows:
        print("沒有需要評估的新資料。程式結束。")
        return

    all_results = []
    print(f"\n準備對 {len(unevaluated_rows)} 筆資料進行評估...")

    # 2. 迭代並評估每一筆紀錄
    for i, row in enumerate(unevaluated_rows):
        try:
            # 準備單一樣本的資料
            contexts_list_of_dicts = json.loads(row['retrieved_contexts'])
            context_text_list = [doc["text"] for doc in contexts_list_of_dicts]

            if not row['answer'] or not context_text_list:
                print(f"跳過紀錄 ID {row['id']}，因為答案或上下文為空。")
                continue

            # Using the SingleTurnSample object as intended by the new API.
            sample = SingleTurnSample(
                user_input=row["rephrased_question"],
                response=row["answer"],
                retrieved_contexts=context_text_list
            )

            print(f"正在評估紀錄 ID {row['id']} ({i+1}/{len(unevaluated_rows)})...")

            # 3. 非同步評估所有指標
            # Use 'single_turn_ascore' as recommended, with the SingleTurnSample object.
            faithfulness_score, response_relevancy_score, context_precision_score = await asyncio.gather(
                faithfulness_metric.single_turn_ascore(sample),
                response_relevancy_metric.single_turn_ascore(sample),
                context_precision_metric.single_turn_ascore(sample)
            )

            # 儲存結果
            result = {
                "id": row["id"],
                "faithfulness_score": faithfulness_score,
                "response_relevancy_score": response_relevancy_score,
                "context_precision_score": context_precision_score,
            }
            all_results.append(result)
            print(f"  - Faithfulness: {faithfulness_score:.2f}, Response Relevancy: {response_relevancy_score:.2f}, Context Precision: {context_precision_score:.2f}")

        except Exception as e:
            print(f"評估紀錄 ID {row['id']} 時發生錯誤: {e}")


    if not all_results:
        print("\n沒有成功評估的紀錄。程式結束。")
        return

    # 4. 更新資料庫
    print("\n所有評估完成！")
    update_scores_in_db(all_results)


if __name__ == "__main__":
    # For Windows compatibility of asyncio
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # 使用 asyncio.run() 來執行 async main 函式
    asyncio.run(main())
