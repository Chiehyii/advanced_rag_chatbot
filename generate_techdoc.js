/**
 * 慈濟大學獎助學金 RAG 諮詢聊天機器人 — 專業技術文件生成器
 * Tzu Chi University Scholarship RAG Chatbot — Technical Documentation Generator
 *
 * Generates a bilingual (Traditional Chinese + English) .docx technical document.
 */

const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  WidthType, AlignmentType, HeadingLevel, BorderStyle, ShadingType,
  PageBreak, Header, Footer, PageNumber, NumberFormat, TableOfContents,
  LevelFormat, Tab, TabStopPosition, TabStopType, convertInchesToTwip,
} = require("docx");
const fs = require("fs");
const path = require("path");

// ──────────────────────────────────────────────
// Constants
// ──────────────────────────────────────────────
const PAGE_WIDTH = 11906; // A4 width in DXA
const PAGE_HEIGHT = 16838; // A4 height in DXA
const MARGIN = 2540; // ~4.5 cm
const CONTENT_WIDTH = PAGE_WIDTH - MARGIN * 2; // usable content width

const COLOR = {
  primary: "2E5FA3",
  accent: "4A90C4",
  lightBg: "E8F0FA",
  altRow: "F5F8FD",
  body: "1A1A1A",
  white: "FFFFFF",
  codeBg: "F4F4F4",
  lineRule: "2E5FA3",
};

const FONT = { ch: "標楷體", en: "Arial", code: "Courier New" };

// ──────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────
function heading1(text) {
  return new Paragraph({
    spacing: { before: 400, after: 200 },
    children: [new TextRun({ text, size: 32, bold: true, color: COLOR.primary, font: FONT.en })],
    heading: HeadingLevel.HEADING_1,
  });
}

function heading2(text) {
  return new Paragraph({
    spacing: { before: 300, after: 150 },
    children: [new TextRun({ text, size: 26, bold: true, color: COLOR.accent, font: FONT.en })],
    heading: HeadingLevel.HEADING_2,
  });
}

function heading3(text) {
  return new Paragraph({
    spacing: { before: 200, after: 100 },
    children: [new TextRun({ text, size: 24, bold: false, color: COLOR.primary, font: FONT.en })],
    heading: HeadingLevel.HEADING_3,
  });
}

function bodyZh(text) {
  return new Paragraph({
    spacing: { after: 120 },
    children: [new TextRun({ text, size: 22, color: COLOR.body, font: FONT.ch })],
  });
}

function bodyEn(text) {
  return new Paragraph({
    spacing: { after: 120 },
    children: [new TextRun({ text, size: 22, color: COLOR.body, font: FONT.en, italics: true })],
  });
}

function bodyBold(text) {
  return new Paragraph({
    spacing: { after: 80 },
    children: [new TextRun({ text, size: 22, color: COLOR.body, font: FONT.ch, bold: true })],
  });
}

function emptyLine() {
  return new Paragraph({ spacing: { after: 200 }, children: [] });
}

function horizontalRule() {
  return new Paragraph({
    spacing: { before: 100, after: 100 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: COLOR.lineRule } },
    children: [],
  });
}

function bulletItem(text) {
  return new Paragraph({
    spacing: { after: 60 },
    bullet: { level: 0 },
    children: [new TextRun({ text, size: 22, font: FONT.ch, color: COLOR.body })],
  });
}

function numberedItem(text, num) {
  return new Paragraph({
    spacing: { after: 60 },
    children: [
      new TextRun({ text: `${num}. `, size: 22, font: FONT.en, color: COLOR.body, bold: true }),
      new TextRun({ text, size: 22, font: FONT.ch, color: COLOR.body }),
    ],
  });
}

/**
 * Build a styled table.
 * @param {string[]} headers - column header texts
 * @param {string[][]} rows - 2D array of cell texts
 * @param {number[]} [colWidths] - optional column widths in DXA
 */
function styledTable(headers, rows, colWidths) {
  const numCols = headers.length;
  const defaultWidth = Math.floor(CONTENT_WIDTH / numCols);
  const widths = colWidths || headers.map(() => defaultWidth);

  const headerRow = new TableRow({
    children: headers.map((h, i) =>
      new TableCell({
        width: { size: widths[i], type: WidthType.DXA },
        shading: { fill: COLOR.lightBg, type: ShadingType.CLEAR, color: "auto" },
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [new TextRun({ text: h, size: 20, bold: true, color: COLOR.primary, font: FONT.en })],
        })],
      })
    ),
  });

  const dataRows = rows.map((row, ri) =>
    new TableRow({
      children: row.map((cell, ci) =>
        new TableCell({
          width: { size: widths[ci], type: WidthType.DXA },
          shading: { fill: ri % 2 === 0 ? COLOR.white : COLOR.altRow, type: ShadingType.CLEAR, color: "auto" },
          children: [new Paragraph({
            children: [new TextRun({ text: cell, size: 20, font: FONT.ch, color: COLOR.body })],
          })],
        })
      ),
    })
  );

  return new Table({
    width: { size: CONTENT_WIDTH, type: WidthType.DXA },
    columnWidths: widths,
    rows: [headerRow, ...dataRows],
  });
}

function codeBlock(text) {
  return new Table({
    width: { size: CONTENT_WIDTH, type: WidthType.DXA },
    columnWidths: [CONTENT_WIDTH],
    rows: [new TableRow({
      children: [new TableCell({
        shading: { fill: COLOR.codeBg, type: ShadingType.CLEAR, color: "auto" },
        margins: { top: 120, bottom: 120, left: 180, right: 180 },
        width: { size: CONTENT_WIDTH, type: WidthType.DXA },
        children: text.split("\n").map(line =>
          new Paragraph({
            children: [new TextRun({ text: line, font: FONT.code, size: 18, color: COLOR.body })],
          })
        ),
      })],
    })],
  });
}

// ──────────────────────────────────────────────
// Cover Page
// ──────────────────────────────────────────────
function buildCoverPage() {
  return [
    horizontalRule(),
    emptyLine(),
    emptyLine(),
    emptyLine(),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 200 },
      children: [new TextRun({ text: "慈濟大學獎助學金 RAG 諮詢聊天機器人", size: 48, bold: true, color: COLOR.primary, font: FONT.ch })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 100 },
      children: [new TextRun({ text: "Tzu Chi University Scholarship RAG Chatbot", size: 28, color: COLOR.accent, font: FONT.en })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 60 },
      children: [new TextRun({ text: "系統技術文件 / Technical Documentation", size: 24, color: COLOR.accent, font: FONT.en })],
    }),
    emptyLine(),
    emptyLine(),
    emptyLine(),
    // Metadata table
    new Table({
      width: { size: 5000, type: WidthType.DXA },
      columnWidths: [2200, 2800],
      alignment: AlignmentType.CENTER,
      rows: [
        ["開發者 Developer", "C.Y"],
        ["學校 School", "慈濟大學 資訊工程學系"],
        ["指導老師 Advisor", "J.M"],
        ["版本 Version", "v1.0.0"],
        ["日期 Date", "2026-04-21"],
      ].map((r, ri) =>
        new TableRow({
          children: [
            new TableCell({
              width: { size: 2200, type: WidthType.DXA },
              shading: { fill: ri % 2 === 0 ? COLOR.lightBg : COLOR.white, type: ShadingType.CLEAR, color: "auto" },
              children: [new Paragraph({ children: [new TextRun({ text: r[0], size: 20, bold: true, font: FONT.en, color: COLOR.primary })] })],
            }),
            new TableCell({
              width: { size: 2800, type: WidthType.DXA },
              shading: { fill: ri % 2 === 0 ? COLOR.lightBg : COLOR.white, type: ShadingType.CLEAR, color: "auto" },
              children: [new Paragraph({ children: [new TextRun({ text: r[1], size: 20, font: FONT.ch, color: COLOR.body })] })],
            }),
          ],
        })
      ),
    }),
    emptyLine(),
    emptyLine(),
    emptyLine(),
    horizontalRule(),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 100 },
      children: [new TextRun({ text: "機密等級：內部使用 / Confidentiality: Internal Use", size: 18, color: COLOR.accent, font: FONT.en, italics: true })],
    }),
    new Paragraph({ children: [new PageBreak()] }),
  ];
}

// ──────────────────────────────────────────────
// Table of Contents
// ──────────────────────────────────────────────
function buildTOC() {
  return [
    heading1("目錄 / Table of Contents"),
    new TableOfContents("目錄", {
      hyperlink: true,
      headingStyleRange: "1-3",
    }),
    new Paragraph({ children: [new PageBreak()] }),
  ];
}

// ──────────────────────────────────────────────
// Section 1: Project Overview
// ──────────────────────────────────────────────
function buildSection1() {
  return [
    heading1("1. 專案概述 / Project Overview"),

    heading2("1.1 背景與動機 / Background & Motivation"),
    bodyZh("慈濟大學提供多元的獎助學金方案，涵蓋校內自辦、政府補助及校外捐贈等類型。然而，由於獎助學金種類繁多、申請條件各異、資訊分散於不同網頁與公告中，學生在尋找適合自身條件的獎助學金時經常面臨資訊獲取困難的問題。"),
    bodyZh("本系統旨在運用先進的 AI 技術——檢索增強生成（Retrieval-Augmented Generation, RAG）——建構一個智慧型獎助學金諮詢聊天機器人，讓學生能夠以自然語言提問，即時獲得精準、有依據的獎助學金資訊回覆。"),
    bodyEn("Tzu Chi University offers a wide range of scholarship and financial aid programs. However, due to the variety of scholarships, differing eligibility criteria, and information scattered across multiple web pages, students often struggle to find relevant information. This system leverages advanced AI technology — Retrieval-Augmented Generation (RAG) — to build an intelligent scholarship consultation chatbot that enables students to ask questions in natural language and receive accurate, evidence-based responses in real time."),
    emptyLine(),

    heading2("1.2 系統目標 / System Objectives"),
    bulletItem("提供 24/7 全天候獎助學金諮詢服務，降低行政負擔"),
    bulletItem("透過 RAG 技術確保回答有據可查，減少 AI 幻覺 (Hallucination)"),
    bulletItem("支援中英雙語對話，服務本地與國際學生"),
    bulletItem("提供管理後台，讓行政人員可即時維護獎學金知識庫"),
    bulletItem("整合自動化排程器，定期偵測網頁內容變更並通知管理員"),
    bodyEn("Provide 24/7 scholarship consultation services; ensure evidence-based answers via RAG; support bilingual (Chinese/English) conversations; offer an admin dashboard for knowledge base management; and integrate automated content change detection."),
    emptyLine(),

    heading2("1.3 目標使用者 / Target Users"),
    styledTable(
      ["使用者類型 User Type", "說明 Description"],
      [
        ["慈濟大學在學生", "五專、二技、大學部、碩博士班學生，查詢獎助學金資訊"],
        ["國際學生 / 境外生", "使用英語介面查詢適用之獎助學金方案"],
        ["學務處 / 全球事務處行政人員", "透過管理後台維護知識庫內容、審核自動偵測到的變更"],
        ["指導老師 / 導師", "協助學生查詢獎助學金資訊"],
      ],
      [3000, CONTENT_WIDTH - 3000]
    ),
    emptyLine(),

    heading2("1.4 系統範圍與限制 / Scope & Constraints"),
    bodyZh("本系統的知識範圍限於慈濟大學「衣珠專案」所涵蓋之獎助學金、補助、工讀、急難救助等相關資訊。系統不提供個人化的申請狀態查詢、線上申請功能或與校務系統的即時資料串接。"),
    bulletItem("知識庫依賴人工或半自動方式更新，非即時同步校務資料庫"),
    bulletItem("AI 回覆為參考性質，最終資訊仍以學校官方公告為準"),
    bulletItem("系統不儲存使用者的個人隱私資料（無需登入即可使用）"),
    bodyEn("The system's knowledge scope is limited to the Tzu Chi University 'Yi Zhu Project' scholarships. It does not provide real-time application status tracking or online application functionality. All AI responses are for reference only."),
    new Paragraph({ children: [new PageBreak()] }),
  ];
}

// ──────────────────────────────────────────────
// Section 2: System Architecture
// ──────────────────────────────────────────────
function buildSection2() {
  return [
    heading1("2. 系統架構 / System Architecture"),

    heading2("2.1 整體架構圖說明 / Architecture Overview"),
    bodyZh("本系統採用前後端分離架構，前端部署於 Vercel，後端部署於 Zeabur，兩者透過 CORS 控制的 RESTful API 進行通訊。核心 RAG 管線結合了混合檢索（Dense + Sparse）、Cross-Encoder 重排序及 GPT 串流生成，並搭配 PostgreSQL 記錄對話日誌、Zilliz Cloud (Milvus) 儲存向量知識庫。"),
    bodyEn("The system uses a decoupled frontend-backend architecture. The frontend is deployed on Vercel and the backend on Zeabur, communicating via CORS-controlled RESTful APIs. The core RAG pipeline combines hybrid retrieval (Dense + Sparse), Cross-Encoder re-ranking, and GPT streaming generation, with PostgreSQL for conversation logging and Zilliz Cloud (Milvus) for vector knowledge storage."),
    emptyLine(),
    bodyZh("系統架構流程如下："),
    bodyZh("使用者 (Browser) → React 前端 (Vercel) → FastAPI 後端 (Zeabur) → [意圖分類 + 過濾條件提取] → [Milvus 混合檢索 (Dense + BM25 Sparse)] → [Cross-Encoder 重排序] → [GPT-4o-mini 串流生成] → SSE 串流回傳前端"),
    emptyLine(),

    heading2("2.2 技術堆疊總覽 / Tech Stack Overview"),
    styledTable(
      ["層級 Layer", "技術 Technology", "說明 Description"],
      [
        ["前端 Frontend", "React 18 + TypeScript + Vite", "SPA 單頁應用，SSE 串流接收，Markdown 渲染"],
        ["後端 Backend", "Python FastAPI + Uvicorn", "非同步 API 伺服器，SSE 串流推送"],
        ["AI 引擎 AI Engine", "OpenAI GPT-4o-mini", "對話生成、意圖分類、資訊萃取"],
        ["嵌入模型 Embedding", "OpenAI text-embedding-3-small", "1536 維度 Dense 向量嵌入"],
        ["重排序 Re-Ranker", "BAAI/bge-reranker-base", "Cross-Encoder 精準語意重排"],
        ["向量資料庫 Vector DB", "Zilliz Cloud (Milvus)", "混合索引（COSINE + BM25）"],
        ["關聯式資料庫 RDBMS", "PostgreSQL (Zeabur)", "對話日誌、獎學金元資料、排程狀態"],
        ["前端部署 Frontend Deploy", "Vercel", "全球 CDN、自動 CI/CD"],
        ["後端部署 Backend Deploy", "Zeabur", "容器化部署、自動擴縮"],
        ["排程器 Scheduler", "APScheduler", "每 12 小時自動偵測網頁內容變更"],
        ["通知系統 Notification", "LINE Messaging API", "變更偵測結果推播通知管理員"],
        ["速率限制 Rate Limiting", "SlowAPI", "防止 API 濫用與暴力破解"],
        ["重試機制 Retry", "Tenacity", "指數退避重試（OpenAI、Milvus）"],
      ],
      [2000, 2500, CONTENT_WIDTH - 4500]
    ),
    emptyLine(),

    heading2("2.3 資料流程說明 / Data Flow Description"),
    bodyBold("使用者提問流程 (Query Flow)："),
    numberedItem("使用者在前端輸入問題，附帶對話歷史與語言偏好", 1),
    numberedItem("後端 Middleware 產生 Request ID，注入 contextvars", 2),
    numberedItem("若有多輪對話，先透過 LLM 重構問題 (Rephrase with History)", 3),
    numberedItem("意圖分類 (Intent) + Milvus 過濾條件提取 (Filter Extraction)，一次 API 呼叫完成", 4),
    numberedItem("若英文提問，先翻譯為繁體中文以利 BM25 Sparse 檢索", 5),
    numberedItem("混合檢索：Dense (COSINE) + Sparse (BM25) → RRF 融合排序", 6),
    numberedItem("Cross-Encoder (bge-reranker-base) 對 Top-10 結果重排序，過濾低於 0.2 分的文件", 7),
    numberedItem("將通過重排的文件交給 GPT-4o-mini 以串流方式生成回答", 8),
    numberedItem("前端透過 SSE (Server-Sent Events) 即時接收並渲染回覆", 9),
    numberedItem("串流結束後記錄對話日誌到 PostgreSQL，回傳參考來源與推薦追問", 10),
    emptyLine(),
    bodyBold("知識庫管理流程 (Knowledge Base Management)："),
    numberedItem("管理員登入管理後台，取得 JWT Token", 1),
    numberedItem("可手動新增/編輯獎學金，或透過 AI 從 URL 自動擷取資訊", 2),
    numberedItem("Markdown 內容經 RecursiveCharacterTextSplitter 切分為 chunks (1000 字元/200 重疊)", 3),
    numberedItem("批次呼叫 OpenAI Embedding API 生成向量", 4),
    numberedItem("連同 metadata (identity, education_system, tags) 寫入 Milvus + PostgreSQL", 5),
    emptyLine(),

    heading2("2.4 部署環境 / Deployment Environment"),
    styledTable(
      ["服務 Service", "平台 Platform", "說明 Description"],
      [
        ["React Frontend", "Vercel", "自動從 GitHub 部署，環境變數 VITE_API_URL 指向後端"],
        ["FastAPI Backend", "Zeabur", "Docker 容器化部署，支援 Auto-Scaling"],
        ["PostgreSQL", "Zeabur", "託管資料庫服務，自動備份"],
        ["Milvus Vector DB", "Zilliz Cloud", "全託管向量資料庫，Serverless 模式"],
      ],
      [2000, 1500, CONTENT_WIDTH - 3500]
    ),
    new Paragraph({ children: [new PageBreak()] }),
  ];
}

// ──────────────────────────────────────────────
// Section 3: Functional Specification
// ──────────────────────────────────────────────
function buildSection3() {
  return [
    heading1("3. 功能規格 / Functional Specification"),

    heading2("3.1 核心功能列表 / Core Features"),
    styledTable(
      ["功能 Feature", "說明 Description", "模組 Module"],
      [
        ["智慧問答 RAG Chat", "基於 RAG 的獎助學金問答，附帶來源引用標註", "rag_service.py"],
        ["串流回覆 Streaming", "SSE 即時串流 LLM 回覆，提升使用者體驗", "main.py / App.tsx"],
        ["中英雙語 Bilingual", "支援中文/英文介面與對話，英文提問自動翻譯", "llm_service.py / prompts.py"],
        ["獎學金篩選 Filter", "前端 Modal 篩選特定獎學金，精準限縮 RAG 檢索範圍", "ScholarshipFilterModal.tsx"],
        ["推薦追問 Chips", "根據回答內容自動預測 3 個追問建議", "llm_service.py"],
        ["回饋系統 Feedback", "使用者可對回答按讚/倒讚並提交文字回饋", "FeedbackModal.tsx / main.py"],
        ["管理後台 Admin Panel", "JWT 認證、獎學金 CRUD、AI 資訊擷取", "admin_api.py / AdminApp.tsx"],
        ["自動巡檢 Scheduler", "每 12 小時偵測網頁變更，AI 萃取草稿待審核", "scheduler.py"],
        ["LINE 通知 Notification", "變更偵測結果即時推播管理員 LINE", "notifier.py"],
        ["意圖分類 Intent", "一次 API 呼叫同時辨識意圖 + 提取 Milvus 過濾條件", "query_analyzer.py"],
        ["對話追蹤 Tracking", "Request ID / Session ID / User ID 全鏈路追蹤", "logger.py / main.py"],
        ["速率限制 Rate Limiting", "限制 API 呼叫頻率，防止濫用", "main.py / admin_api.py"],
      ],
      [2200, 3500, CONTENT_WIDTH - 5700]
    ),
    emptyLine(),

    heading2("3.2 使用者互動流程 / User Interaction Flow"),
    bodyBold("一般使用者 (學生)："),
    numberedItem("開啟網頁 → 看到歡迎畫面與範例問題", 1),
    numberedItem("（可選）點選「獎學金篩選」Modal，選擇最多 3 個特定獎學金標籤", 2),
    numberedItem("輸入問題或點選範例問題 → 系統開始串流回覆", 3),
    numberedItem("回覆包含 Markdown 格式、來源引用標註 [X]、參考連結", 4),
    numberedItem("可點選推薦追問 Chips 繼續對話", 5),
    numberedItem("可對回答按讚或倒讚，倒讚時可填寫文字回饋", 6),
    emptyLine(),
    bodyBold("管理員："),
    numberedItem("進入 /admin 路由 → 輸入帳號密碼登入 → 進入管理後台", 1),
    numberedItem("左側邊欄查看獎學金列表，黃色標記表示有待審核變更", 2),
    numberedItem("點選獎學金進入編輯頁面 → 直接修改或使用 AI 擷取功能", 3),
    numberedItem("儲存後自動同步 PostgreSQL + Milvus 向量知識庫", 4),
    numberedItem("可捨棄排程器自動偵測到的草稿變更", 5),
    emptyLine(),

    heading2("3.3 非功能需求 / Non-Functional Requirements"),
    styledTable(
      ["項目 Item", "規格 Specification"],
      [
        ["回應時間 Response Time", "首個 Token 到達 < 2 秒（視網路條件）"],
        ["並發支援 Concurrency", "CPU 密集操作限制為 2 Worker Threads"],
        ["語言支援 Language", "繁體中文 / English"],
        ["可用性 Availability", "依 Vercel + Zeabur SLA（> 99.9%）"],
        ["速率限制 Rate Limit", "Chat: 10 次/分鐘  Feedback: 20 次/分鐘  Login: 5 次/分鐘"],
        ["日誌保留 Log Retention", "30 天自動輪替檔案日誌"],
      ],
      [3000, CONTENT_WIDTH - 3000]
    ),
    new Paragraph({ children: [new PageBreak()] }),
  ];
}

// ──────────────────────────────────────────────
// Section 4: Conversational AI Design
// ──────────────────────────────────────────────
function buildSection4() {
  return [
    heading1("4. AI 對話設計 / Conversational AI Design"),

    heading2("4.1 AI 引擎整合方式 / AI Engine Integration"),
    bodyZh("系統使用 OpenAI GPT-4o-mini 作為核心 LLM，透過 AsyncOpenAI Python SDK 與 OpenAI API 進行非同步通訊。所有 LLM 呼叫均啟用串流模式 (stream=True)，並透過 stream_options 收集 Token 使用量。"),
    bodyZh("關鍵 AI 呼叫點包含："),
    bulletItem("對話生成 (RAG Answer Generation) — temperature=0.0，確保一致性"),
    bulletItem("閒聊回覆 (Small Talk) — temperature=0.7，增加自然度"),
    bulletItem("問題重構 (Rephrase with History) — temperature=0.0"),
    bulletItem("意圖分類 + 過濾條件提取 (Intent + Filter) — Structured Output (response_format)"),
    bulletItem("推薦追問生成 (Suggested Replies) — Structured Output + temperature=0.7"),
    bulletItem("獎學金資訊擷取 (Extract Info) — JSON Mode"),
    bodyEn("The system uses OpenAI GPT-4o-mini as the core LLM via the AsyncOpenAI Python SDK. All LLM calls use streaming mode for real-time response delivery."),
    emptyLine(),

    heading2("4.2 System Prompt 設計策略 / Prompt Design Strategy"),
    bodyZh("系統採用多語言 Prompt 字典架構 (prompts.py)，依語言 (zh/en) 分別定義各場景的 System Prompt 與 User Prompt 模板。"),
    bodyBold("RAG 回答 Prompt 設計要點："),
    bulletItem("強制引用標註規則：回答中必須標記 [X] 對應的文件編號"),
    bulletItem("多獎學金自動比較表：找到 2 個以上獎學金時，必須先輸出 Markdown 表格"),
    bulletItem("Few-Shot 範例：在 Prompt 中內嵌完整的排版範例，確保格式一致性"),
    bulletItem("禁止虛構資訊：不可捏造文件編號或不存在的獎學金"),
    emptyLine(),

    heading2("4.3 知識庫建置方式 / Knowledge Base Construction"),
    bodyZh("本系統採用 RAG (Retrieval-Augmented Generation) 架構，知識庫建置流程如下："),
    numberedItem("獎學金資訊以 Markdown 格式儲存於 PostgreSQL scholarships 表", 1),
    numberedItem("markdown_content 透過 LangChain RecursiveCharacterTextSplitter 切分（chunk_size=1000, overlap=200）", 2),
    numberedItem("每個 chunk 透過 OpenAI text-embedding-3-small 生成 1536 維 Dense 向量", 3),
    numberedItem("Milvus 同時建立 BM25 Sparse 索引（自動由 text 欄位生成）", 4),
    numberedItem("檢索時使用 Hybrid Search：Dense (COSINE) + Sparse (BM25) + RRF 融合排序", 5),
    numberedItem("Top-10 結果交由 Cross-Encoder (bge-reranker-base) 重排序，過濾分數 < 0.2 的文件", 6),
    numberedItem("最終 Top-5 高分文件作為 Context 交給 LLM 生成回答", 7),
    emptyLine(),

    heading2("4.4 對話記憶管理 / Conversation Memory Management"),
    bodyZh("系統使用以下機制管理多輪對話記憶："),
    bulletItem("前端將對話歷史儲存於 sessionStorage，重新整理頁面後保留"),
    bulletItem("每次 API 請求附帶最近的對話歷史（最多 20 條訊息）"),
    bulletItem("後端使用 tiktoken 計算 Token 預算（上限 2500 tokens），從最新訊息往前填充"),
    bulletItem("多輪對話時透過 LLM 將不完整問題重構為獨立完整的問題"),
    bulletItem("首次提問跳過重構步驟，直接進入檢索流程"),
    emptyLine(),

    heading2("4.5 Fallback 機制 / Fallback Handling"),
    bodyZh("系統在多個層級設計了 Fallback 機制："),
    styledTable(
      ["層級 Level", "Fallback 策略 Strategy"],
      [
        ["意圖分類失敗", "預設為 scholarship 意圖，進行無過濾的 RAG 檢索"],
        ["混合檢索失敗", "退化為 Dense-only 檢索（Hybrid → Dense Fallback）"],
        ["帶 Filter 搜不到結果", "自動移除 Filter 重新搜尋（Filter Relaxation）"],
        ["Cross-Encoder 全部低分", "進入 Small Talk 模式，禮貌告知無相關資訊"],
        ["OpenAI API 失敗", "Tenacity 指數退避重試（最多 3 次）"],
        ["翻譯/重構 失敗", "Fallback 回原始問題文字"],
        ["資料庫寫入失敗", "記錄錯誤日誌，不影響串流回覆"],
      ],
      [3000, CONTENT_WIDTH - 3000]
    ),
    new Paragraph({ children: [new PageBreak()] }),
  ];
}

// ──────────────────────────────────────────────
// Section 5: Data Design
// ──────────────────────────────────────────────
function buildSection5() {
  return [
    heading1("5. 資料設計 / Data Design"),

    heading2("5.1 資料來源與格式 / Data Sources & Formats"),
    bodyZh("獎學金資料主要來源為慈濟大學官方網頁，透過以下方式匯入系統："),
    bulletItem("手動輸入：管理員在後台直接編寫 Markdown 格式的獎學金內容"),
    bulletItem("AI 擷取：提供 URL 或純文字，由 GPT 自動提取結構化欄位與 Markdown 內容"),
    bulletItem("自動巡檢：排程器定期爬取已登錄的 URL，偵測到變更時由 AI 自動萃取草稿"),
    emptyLine(),

    heading2("5.2 欄位定義 / Field Definitions"),
    bodyBold("scholarships 資料表："),
    styledTable(
      ["欄位 Field", "型態 Type", "說明 Description"],
      [
        ["scholarship_code", "VARCHAR (PK)", "獎學金唯一識別碼，格式：sch-xxxxxxxx"],
        ["title", "VARCHAR", "獎學金名稱"],
        ["link", "VARCHAR", "原始網頁連結"],
        ["category", "VARCHAR", "衣珠類別（例如：生活無憂、安心就學）"],
        ["education_system", "JSON Array", "適用學制：五專/二技/大學部/碩士班/博士班"],
        ["tags", "JSON Array", "分類標籤：獎學金/助學金/工讀/急難救助 等"],
        ["identity", "JSON Array", "適用身分：一般生/原住民/低收入戶/境外生 等"],
        ["amount_summary", "VARCHAR", "金額說明"],
        ["description", "VARCHAR", "簡要描述"],
        ["application_date_text", "VARCHAR", "申請期間說明"],
        ["contact", "VARCHAR", "聯絡窗口"],
        ["markdown_content", "TEXT", "完整 Markdown 格式知識庫內容"],
        ["content_hash", "VARCHAR", "網頁內容 MD5 雜湊值（變更偵測用）"],
        ["last_checked_at", "TIMESTAMP", "最後巡檢時間"],
        ["needs_review", "BOOLEAN", "是否有待審核的變更 (default: false)"],
        ["pending_data", "JSONB", "排程器偵測到變更後的暫存草稿"],
        ["created_at", "TIMESTAMP", "建立時間"],
      ],
      [2200, 1800, CONTENT_WIDTH - 4000]
    ),
    emptyLine(),
    bodyBold("qa_logs2 對話日誌表："),
    styledTable(
      ["欄位 Field", "型態 Type", "說明 Description"],
      [
        ["id", "SERIAL (PK)", "自動遞增主鍵"],
        ["request_id", "VARCHAR", "後端產生的 8 碼 Request ID"],
        ["session_id", "VARCHAR", "前端 sessionStorage UUID"],
        ["user_id", "VARCHAR", "前端 localStorage UUID"],
        ["question", "TEXT", "使用者原始問題"],
        ["rephrased_question", "TEXT", "重構後的問題（多輪對話用）"],
        ["answer", "TEXT", "LLM 生成的完整回答"],
        ["retrieved_contexts", "JSONB", "檢索到的文件 metadata 與文字"],
        ["latency_ms", "FLOAT", "處理延遲（毫秒）"],
        ["prompt_tokens", "INTEGER", "LLM 使用的 Prompt Tokens"],
        ["completion_tokens", "INTEGER", "LLM 使用的 Completion Tokens"],
        ["total_tokens", "INTEGER", "總 Token 使用量"],
        ["feedback_type", "VARCHAR", "使用者回饋類型 (like/dislike/null)"],
        ["feedback_text", "TEXT", "使用者文字回饋"],
        ["created_at", "TIMESTAMP", "記錄時間"],
      ],
      [2200, 1800, CONTENT_WIDTH - 4000]
    ),
    emptyLine(),

    heading2("5.3 資料維護流程 / Data Maintenance Process"),
    bodyZh("系統提供三種資料維護方式："),
    numberedItem("手動維護：管理員登入後台，直接新增/編輯/刪除獎學金資料", 1),
    numberedItem("半自動維護：管理員提供 URL，AI 自動擷取結構化資訊，管理員審核後儲存", 2),
    numberedItem("自動偵測：排程器每 12 小時爬取所有已登錄 URL，比對 MD5 雜湊值；若偵測到變更，AI 自動萃取草稿並標記 needs_review，同時透過 LINE 通知管理員前往後台審核", 3),
    new Paragraph({ children: [new PageBreak()] }),
  ];
}

// ──────────────────────────────────────────────
// Section 6: API Specification
// ──────────────────────────────────────────────
function buildSection6() {
  return [
    heading1("6. API 介面規格 / API Specification"),

    heading2("6.1 端點列表 / Endpoint List"),
    bodyBold("公開端點 (Public Endpoints)："),
    styledTable(
      ["Method", "Endpoint", "說明 Description", "速率限制 Rate Limit"],
      [
        ["POST", "/chat", "RAG 智慧問答（SSE 串流）", "10/minute"],
        ["POST", "/feedback", "提交使用者回饋", "20/minute"],
        ["GET", "/scholarships/filter", "取得獎學金篩選清單", "20/minute"],
        ["GET", "/metadata_schema.json", "取得 Metadata Schema", "無限制"],
      ],
      [1000, 2500, 2500, CONTENT_WIDTH - 6000]
    ),
    emptyLine(),
    bodyBold("管理端點 (Admin Endpoints — 需 JWT Bearer Token)："),
    styledTable(
      ["Method", "Endpoint", "說明 Description"],
      [
        ["POST", "/api/login", "管理員登入，取得 JWT Token"],
        ["GET", "/api/scholarships", "列出所有獎學金"],
        ["GET", "/api/scholarships/{code}", "取得單一獎學金詳細資料"],
        ["POST", "/api/scholarships", "新增獎學金 (PostgreSQL + Milvus)"],
        ["PUT", "/api/scholarships/{code}", "更新獎學金 (刪除舊向量 + 重新嵌入)"],
        ["DELETE", "/api/scholarships/{code}", "刪除獎學金 (Milvus 優先，再刪 PostgreSQL)"],
        ["PATCH", "/api/scholarships/{code}/discard_pending", "捨棄排程器暫存的變更草稿"],
        ["POST", "/api/extract_info", "AI 擷取獎學金資訊（URL 或純文字）"],
      ],
      [1000, 3500, CONTENT_WIDTH - 4500]
    ),
    emptyLine(),

    heading2("6.2 Request / Response 格式 / Request & Response Format"),
    bodyBold("POST /chat — 發送問題"),
    bodyZh("Request Body (JSON):"),
    codeBlock(`{
  "query": "低收入可以申請甚麼獎學金？",
  "history": [
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好！..."}
  ],
  "lang": "zh",
  "title_filter": ["慈濟大學弱勢學生助學金"],
  "session_id": "a1b2c3d4-...",
  "user_id": "e5f6g7h8-..."
}`),
    emptyLine(),
    bodyZh("Response: SSE (text/event-stream)"),
    codeBlock(`data: {"type": "content", "data": "你好！"}

data: {"type": "content", "data": "為您找到..."}

event: end_stream
data: {"type": "final_data", "data": {
  "contexts": [...],
  "log_id": 123,
  "chips": ["申請截止日？", "需要甚麼文件？", "金額多少？"]
}}`),
    emptyLine(),

    heading2("6.3 錯誤碼定義 / Error Code Definitions"),
    styledTable(
      ["HTTP Code", "說明 Description", "觸發場景 Trigger"],
      [
        ["400", "Bad Request", "Invalid scholarship_code / 缺少必要欄位 / 不安全 URL"],
        ["401", "Unauthorized", "JWT 過期或無效 / 帳密錯誤"],
        ["404", "Not Found", "獎學金不存在"],
        ["429", "Too Many Requests", "超過速率限制"],
        ["500", "Internal Server Error", "DB 錯誤 / Vector DB 錯誤 / AI 擷取失敗"],
        ["503", "Service Unavailable", "資料庫連線池不可用"],
      ],
      [1500, 2200, CONTENT_WIDTH - 3700]
    ),
    new Paragraph({ children: [new PageBreak()] }),
  ];
}

// ──────────────────────────────────────────────
// Section 7: Security & Privacy
// ──────────────────────────────────────────────
function buildSection7() {
  return [
    heading1("7. 安全性與隱私 / Security & Privacy"),

    heading2("7.1 API 金鑰保護 / API Key Protection"),
    bulletItem("所有敏感金鑰（OpenAI、Zilliz、PostgreSQL、JWT、LINE）透過 .env 環境變數管理"),
    bulletItem(".env 檔案已加入 .gitignore，不會提交至版本控制"),
    bulletItem("部署環境中透過 Zeabur / Vercel 的環境變數面板安全注入"),
    bulletItem("前端僅透過 VITE_API_URL 連接後端，不接觸任何 API Key"),
    emptyLine(),

    heading2("7.2 個資處理原則 / Personal Data Handling"),
    bulletItem("系統不要求使用者登入或提供個人資料"),
    bulletItem("Session ID 儲存於 sessionStorage（關閉分頁即消失）"),
    bulletItem("User ID 儲存於 localStorage（匿名 UUID，不可追溯真實身份）"),
    bulletItem("對話日誌僅記錄問題與回答，不記錄 IP 位址或瀏覽器指紋"),
    bulletItem("回饋內容為自願填寫，不包含身份識別資訊"),
    emptyLine(),

    heading2("7.3 輸入過濾與防濫用 / Input Filtering & Abuse Prevention"),
    styledTable(
      ["防護措施 Measure", "實作方式 Implementation"],
      [
        ["查詢長度限制", "Pydantic Field: max_length=1000 字元"],
        ["歷史訊息限制", "最多 20 條 + tiktoken Token 預算 2500"],
        ["Filter 標籤限制", "最多 3 個 title_filter"],
        ["速率限制 (SlowAPI)", "Chat: 10/min, Feedback: 20/min, Login: 5/min"],
        ["CORS 白名單", "僅允許設定的前端域名存取 API"],
        ["JWT 認證", "管理端點需 Bearer Token，HS256 + 24h 過期"],
        ["密碼安全", "Bcrypt 雜湊比對 (72-byte 截斷)，移除明文備用機制"],
        ["Milvus 注入防護", "scholarship_code 白名單驗證 (英數字+連字符+底線)"],
        ["SSRF 防護", "URL 驗證：阻擋 Private IP / Loopback / AWS Metadata"],
        ["URL Schema 驗證", "僅允許 http/https 協定"],
      ],
      [2500, CONTENT_WIDTH - 2500]
    ),
    new Paragraph({ children: [new PageBreak()] }),
  ];
}

// ──────────────────────────────────────────────
// Section 8: Testing Strategy
// ──────────────────────────────────────────────
function buildSection8() {
  return [
    heading1("8. 測試策略 / Testing Strategy"),

    heading2("8.1 測試範疇 / Test Scope"),
    bulletItem("單元測試 (Unit Tests)：使用 pytest 框架，測試核心 RAG 管線邏輯"),
    bulletItem("API 測試：驗證各端點的 Request/Response 格式與錯誤處理"),
    bulletItem("前端元件測試：React 元件的渲染與互動行為"),
    bulletItem("整合測試：端對端的 RAG 管線，從提問到回覆的完整流程"),
    bulletItem("AI 品質評估：使用 RAGAS 框架評估 RAG 回答品質"),
    emptyLine(),

    heading2("8.2 測試案例範例 / Sample Test Cases"),
    styledTable(
      ["測試類別 Category", "測試案例 Test Case", "預期結果 Expected Result"],
      [
        ["RAG 問答", "問「低收入可以申請甚麼」", "回覆包含相關獎學金，附帶 [X] 引用標註"],
        ["雙語支援", "英文提問 scholarship for indigenous", "自動翻譯為中文檢索，英文回覆"],
        ["篩選功能", "選擇特定獎學金後提問", "檢索範圍限縮於選定的獎學金"],
        ["回饋機制", "對回覆按倒讚並填寫意見", "資料庫正確記錄 feedback_type 和 feedback_text"],
        ["速率限制", "短時間內發送 >10 次查詢", "第 11 次收到 429 Too Many Requests"],
        ["管理登入", "輸入錯誤密碼", "回傳 401 Unauthorized"],
        ["SSRF 防護", "嘗試擷取 private IP 網址", "回傳 400 Bad Request"],
        ["Fallback", "問與獎學金無關的問題", "進入 Small Talk 模式，禮貌引導回正題"],
      ],
      [1800, 3000, CONTENT_WIDTH - 4800]
    ),
    emptyLine(),

    heading2("8.3 AI 回答品質評估指標 / AI Quality Metrics"),
    styledTable(
      ["指標 Metric", "說明 Description"],
      [
        ["Faithfulness (忠實度)", "回答是否忠實反映檢索到的文件內容，不捏造資訊"],
        ["Answer Relevancy (相關性)", "回答與使用者問題的相關程度"],
        ["Context Precision (檢索精確度)", "檢索到的文件是否與問題高度相關"],
        ["Context Recall (檢索召回率)", "相關文件是否被成功檢索到"],
        ["Reference Citation Accuracy", "引用標註 [X] 是否準確對應原始文件"],
      ],
      [3200, CONTENT_WIDTH - 3200]
    ),
    new Paragraph({ children: [new PageBreak()] }),
  ];
}

// ──────────────────────────────────────────────
// Section 9: Deployment & Maintenance
// ──────────────────────────────────────────────
function buildSection9() {
  return [
    heading1("9. 部署與維護 / Deployment & Maintenance"),

    heading2("9.1 部署步驟 / Deployment Steps"),
    bodyBold("後端部署（Zeabur）："),
    numberedItem("在 Zeabur 建立新專案，連接 GitHub Repository", 1),
    numberedItem("設定環境變數（參見 9.2 節）", 2),
    numberedItem("Zeabur 自動偵測 Python 專案，執行 pip install -r requirements.txt", 3),
    numberedItem("啟動指令：uvicorn main:app --host 0.0.0.0 --port 8000", 4),
    numberedItem("設定自訂域名並啟用 HTTPS", 5),
    emptyLine(),
    bodyBold("前端部署（Vercel）："),
    numberedItem("在 Vercel 建立新專案，連接 GitHub Repository 的 frontend-react 資料夾", 1),
    numberedItem("設定環境變數 VITE_API_URL 指向 Zeabur 後端 URL", 2),
    numberedItem("Build Command: npm run build", 3),
    numberedItem("Output Directory: dist", 4),
    numberedItem("設定自訂域名並啟用 HTTPS", 5),
    emptyLine(),
    bodyBold("資料庫設定："),
    numberedItem("在 Zeabur 建立 PostgreSQL 服務", 1),
    numberedItem("建立 scholarships 與 qa_logs2 資料表（依 5.2 欄位定義）", 2),
    numberedItem("在 Zilliz Cloud 建立 Serverless Cluster", 3),
    numberedItem("系統啟動時會自動初始化 Milvus Collection（如不存在）", 4),
    emptyLine(),

    heading2("9.2 環境變數設定 / Environment Variables"),
    styledTable(
      ["變數名稱 Variable", "說明 Description", "必要 Required"],
      [
        ["OPENAI_API_KEY", "OpenAI API 金鑰", "Yes"],
        ["OPENAI_MODEL_NAME", "模型名稱 (default: gpt-4o-mini)", "No"],
        ["EMBEDDING_MODEL", "嵌入模型 (default: text-embedding-3-small)", "No"],
        ["ZILLIZ_API_KEY", "Zilliz Cloud API 金鑰", "Yes"],
        ["CLUSTER_ENDPOINT", "Milvus Cluster 端點 URL", "Yes"],
        ["MILVUS_COLLECTION", "Collection 名稱 (default: rag6_scholarships_hybrid)", "No"],
        ["DB_HOST", "PostgreSQL 主機位址", "Yes"],
        ["DB_PORT", "PostgreSQL 連接埠 (default: 5432)", "No"],
        ["DB_NAME", "PostgreSQL 資料庫名稱", "Yes"],
        ["DB_USER", "PostgreSQL 使用者名稱", "Yes"],
        ["DB_PASSWORD", "PostgreSQL 密碼", "Yes"],
        ["DB_TABLE_NAME", "日誌資料表名稱 (default: qa_logs2)", "No"],
        ["ADMIN_USERNAME", "管理員帳號", "Yes"],
        ["ADMIN_PASSWORD_HASH", "Bcrypt 雜湊後的管理員密碼", "Yes"],
        ["JWT_SECRET_KEY", "JWT 簽名金鑰", "Yes"],
        ["CORS_ALLOWED_ORIGINS", "允許的 CORS 來源（逗號分隔）", "Yes"],
        ["RATE_LIMIT_CHAT", "Chat 端點速率限制 (default: 10/minute)", "No"],
        ["RATE_LIMIT_FEEDBACK", "Feedback 端點速率限制 (default: 20/minute)", "No"],
        ["LINE_CHANNEL_ACCESS_TOKEN", "LINE Messaging API Token", "No"],
        ["LINE_USER_ID", "接收通知的 LINE User ID", "No"],
        ["VITE_API_URL", "前端用：後端 API Base URL", "Yes (前端)"],
      ],
      [2800, 3200, CONTENT_WIDTH - 6000]
    ),
    emptyLine(),

    heading2("9.3 已知限制與未來改善 / Known Limitations & Roadmap"),
    bodyBold("已知限制："),
    bulletItem("知識庫更新非即時同步校務資料庫，需透過管理後台或排程器維護"),
    bulletItem("Cross-Encoder 推論為 CPU 密集操作，高並發時可能成為瓶頸"),
    bulletItem("BM25 Sparse 索引目前僅支援中文，英文提問需先翻譯"),
    bulletItem("AI 回覆仍有極小機率產生不準確資訊，使用者應以官方公告為準"),
    emptyLine(),
    bodyBold("未來改善方向："),
    bulletItem("整合校務系統 API，實現獎學金資料即時同步"),
    bulletItem("引入 GPU 加速 Cross-Encoder 推論，提升高並發效能"),
    bulletItem("新增多模態支援（上傳申請表圖片自動辨識）"),
    bulletItem("開發 LINE Bot / Teams Bot 介面，擴大觸及率"),
    bulletItem("建立 A/B 測試框架，持續優化 Prompt 與 RAG 管線"),
    bulletItem("導入使用者行為分析儀表板，追蹤常見問題與回答滿意度"),
    new Paragraph({ children: [new PageBreak()] }),
  ];
}

// ──────────────────────────────────────────────
// Appendix
// ──────────────────────────────────────────────
function buildAppendix() {
  return [
    heading1("附錄 / Appendix"),

    heading2("A. 名詞解釋 / Glossary"),
    styledTable(
      ["名詞 Term", "說明 Definition"],
      [
        ["RAG", "Retrieval-Augmented Generation — 檢索增強生成，結合知識檢索與 LLM 生成的技術"],
        ["LLM", "Large Language Model — 大型語言模型（例如 GPT-4o-mini）"],
        ["Embedding", "嵌入 — 將文字轉換為高維度數值向量的過程"],
        ["Dense Vector", "稠密向量 — 每個維度都有非零值的向量表示"],
        ["Sparse Vector", "稀疏向量 — 大部分維度為零的向量表示（如 BM25 TF-IDF）"],
        ["Cross-Encoder", "交叉編碼器 — 同時編碼查詢與文件的重排序模型"],
        ["RRF", "Reciprocal Rank Fusion — 倒數排名融合，用於合併多路檢索結果"],
        ["SSE", "Server-Sent Events — 伺服器推送事件，用於串流回覆"],
        ["JWT", "JSON Web Token — 用於 API 認證的令牌標準"],
        ["SSRF", "Server-Side Request Forgery — 伺服器端請求偽造攻擊"],
        ["Milvus", "開源向量資料庫，支援混合索引與檢索"],
        ["Zilliz Cloud", "Milvus 的雲端託管服務"],
        ["BM25", "Best Matching 25 — 經典的文件相關性評分演算法"],
        ["COSINE", "餘弦相似度 — 衡量向量方向相似性的度量"],
        ["衣珠專案", "慈濟大學整合性學生獎助學金專案名稱"],
      ],
      [2500, CONTENT_WIDTH - 2500]
    ),
    emptyLine(),

    heading2("B. 參考資料 / References"),
    bulletItem("Lewis, P. et al. (2020). 'Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks.' NeurIPS."),
    bulletItem("OpenAI API Documentation: https://platform.openai.com/docs"),
    bulletItem("Milvus Documentation: https://milvus.io/docs"),
    bulletItem("FastAPI Documentation: https://fastapi.tiangolo.com"),
    bulletItem("React Documentation: https://react.dev"),
    bulletItem("BAAI BGE Reranker: https://huggingface.co/BAAI/bge-reranker-base"),
    bulletItem("LangChain Text Splitters: https://python.langchain.com/docs/modules/data_connection/document_transformers/"),
    bulletItem("RAGAS Framework: https://docs.ragas.io"),
    emptyLine(),

    heading2("C. 版本更新紀錄 / Changelog"),
    styledTable(
      ["版本 Version", "日期 Date", "更新內容 Changes"],
      [
        ["v1.0.0", "2026-04-21", "初版發行：RAG 問答、管理後台、自動巡檢、LINE 通知、安全強化"],
      ],
      [1500, 1500, CONTENT_WIDTH - 3000]
    ),
  ];
}

// ──────────────────────────────────────────────
// Main Document Assembly
// ──────────────────────────────────────────────
async function main() {
  const doc = new Document({
    creator: "C.Y",
    title: "慈濟大學獎助學金 RAG 諮詢聊天機器人 — 系統技術文件",
    description: "Technical Documentation for TCU Scholarship RAG Chatbot",
    styles: {
      default: {
        document: {
          run: { size: 22, font: FONT.ch, color: COLOR.body },
        },
        heading1: {
          run: { size: 32, bold: true, color: COLOR.primary, font: FONT.en },
        },
        heading2: {
          run: { size: 26, bold: true, color: COLOR.accent, font: FONT.en },
        },
        heading3: {
          run: { size: 24, bold: false, color: COLOR.primary, font: FONT.en },
        },
        listParagraph: {
          run: { size: 22, font: FONT.ch },
        },
      },
    },
    numbering: {
      config: [
        {
          reference: "default-bullet",
          levels: [
            {
              level: 0,
              format: LevelFormat.BULLET,
              text: "\u2022",
              alignment: AlignmentType.LEFT,
              style: { paragraph: { indent: { left: convertInchesToTwip(0.5), hanging: convertInchesToTwip(0.25) } } },
            },
          ],
        },
      ],
    },
    sections: [
      {
        properties: {
          page: {
            size: { width: PAGE_WIDTH, height: PAGE_HEIGHT, orientation: 0 },
            margin: { top: MARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN },
          },
        },
        headers: {
          default: new Header({
            children: [
              new Paragraph({
                border: { bottom: { style: BorderStyle.SINGLE, size: 2, color: COLOR.accent } },
                children: [
                  new TextRun({ text: "慈濟大學獎助學金 RAG 聊天機器人", size: 16, font: FONT.ch, color: COLOR.accent }),
                  new TextRun({ text: "\t", size: 16 }),
                  new TextRun({ text: "系統技術文件 v1.0.0", size: 16, font: FONT.en, color: COLOR.accent }),
                ],
                tabStops: [{ type: TabStopType.RIGHT, position: CONTENT_WIDTH }],
              }),
            ],
          }),
        },
        footers: {
          default: new Footer({
            children: [
              new Paragraph({
                border: { top: { style: BorderStyle.SINGLE, size: 2, color: COLOR.accent } },
                children: [
                  new TextRun({ text: "慈濟大學 資訊工程學系", size: 16, font: FONT.ch, color: COLOR.accent }),
                  new TextRun({ text: "\t", size: 16 }),
                  new TextRun({ children: [PageNumber.CURRENT], size: 16, font: FONT.en, color: COLOR.accent }),
                ],
                tabStops: [{ type: TabStopType.RIGHT, position: CONTENT_WIDTH }],
              }),
            ],
          }),
        },
        children: [
          ...buildCoverPage(),
          ...buildTOC(),
          ...buildSection1(),
          ...buildSection2(),
          ...buildSection3(),
          ...buildSection4(),
          ...buildSection5(),
          ...buildSection6(),
          ...buildSection7(),
          ...buildSection8(),
          ...buildSection9(),
          ...buildAppendix(),
        ],
      },
    ],
  });

  const buffer = await Packer.toBuffer(doc);
  const outputPath = path.join(__dirname, "技術文件_慈濟大學獎助學金RAG聊天機器人_v1.0.docx");
  fs.writeFileSync(outputPath, buffer);
  console.log(`✅ Technical document generated successfully!`);
  console.log(`📄 Output: ${outputPath}`);
}

main().catch(err => {
  console.error("❌ Error generating document:", err);
  process.exit(1);
});
