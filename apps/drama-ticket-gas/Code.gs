/**
 * PTT Drama-Ticket 孫燕姿演唱會售票監控爬蟲 (Google Apps Script 版本)
 *
 * 【安裝與執行說明】
 * 1. 在 Google Drive 建立一個新的 Google Apps Script 專案。
 * 2. 將此程式碼貼上覆蓋預設的 Code.gs。
 * 3. 填寫下方的 TELEGRAM_BOT_TOKEN 與 TELEGRAM_CHAT_ID。
 * 4. 點擊上方的「執行」按鈕測試 (第一次會要求授權連線)。
 * 5. 點擊左側時鐘圖示 (觸發條件)，新增一個「時間驅動」->「每分鐘」的觸發器。
 */

// ── 設定 ─────────────────────────────────────────────
const CONFIG = {
  PTT_BASE_URL: "https://www.ptt.cc",
  BOARD_URL: "https://www.ptt.cc/bbs/Drama-Ticket/index.html",
  TITLE_KEYWORDS: ["售票", "孫燕姿"],
  CONTENT_KEYWORDS: ["孫燕姿"],
  DATE_KEYWORDS: ["5/15", "5/17", "05/15", "05/17", "5月15", "5月17"],
  SEAT_KEYWORDS: ["連號", "連座", "兩張", "2張", "二張", "兩位", "一起"],
  MAX_PAGES: 3, // 每次掃描幾頁
  MAX_SEEN_POSTS: 500, // 記憶已通知的數量上限
};

// 🔴 請填入你的 Telegram 機器人憑證
const TELEGRAM_BOT_TOKEN = "TELEGRAM_BOT_TOKEN";
const TELEGRAM_CHAT_ID = "TELEGRAM_CHAT_ID";

// ── 主程式 ───────────────────────────────────────────
function main() {
  Logger.log("🎯 PTT Drama-Ticket GAS 監控啟動");

  if (!TELEGRAM_BOT_TOKEN || TELEGRAM_BOT_TOKEN.includes("請在此填入")) {
    Logger.log("[WARN] 尚未設定 Telegram Token，將無法發送通知！");
  }

  let seenPosts = loadSeenPosts();
  let newMatches = [];
  let currentUrl = CONFIG.BOARD_URL;

  for (let page = 0; page < CONFIG.MAX_PAGES; page++) {
    Logger.log(`📄 [頁面 ${page + 1}/${CONFIG.MAX_PAGES}] ${currentUrl}`);

    let html = fetchPage(currentUrl);
    if (!html) break;

    let posts = parsePostList(html);
    Logger.log(`   📊 本頁共 ${posts.length} 篇文章`);

    for (let post of posts) {
      let pid = Utilities.computeDigest(Utilities.DigestAlgorithm.MD5, post.url)
                         .map(b => (b < 0 ? b + 256 : b).toString(16).padStart(2, '0')).join('');

      // 跳過已看過的文章
      if (seenPosts.includes(pid)) continue;

      // 第一層篩選：標題必須同時包含「售票」和「孫燕姿」
      if (!matchesAllKeywords(post.title, CONFIG.TITLE_KEYWORDS)) continue;
      Logger.log(`   🔍 [標題符合] ${post.title}`);

      // 取得內文與精確時間
      let contentData = fetchPostContent(post.url);
      let content = contentData.content;
      if (contentData.exactTime) {
        post.date = `${post.date} (${contentData.exactTime})`;
      }
      Utilities.sleep(500); // 避免爬太快被鎖

      // 第二層篩選：內容
      let combinedText = post.title + " " + content;
      if (!matchesKeywords(combinedText, CONFIG.CONTENT_KEYWORDS)) continue;
      Logger.log(`   ✅ [內容符合] 孫燕姿相關!`);

      // 進階條件檢查
      let criteria = checkAdvancedCriteria(combinedText);
      if (criteria.isHighMatch) {
         Logger.log(`   🔥 [高度符合]`);
      }

      newMatches.push({
        post: post,
        criteria: criteria,
        content: content,
        pid: pid
      });

      // 標記為已看過 (本地暫存)
      seenPosts.push(pid);
    }

    // 取得上一頁連結
    let prevUrlMatch = html.match(/<a class="btn wide" href="(\/bbs\/Drama-Ticket\/index\d+\.html)">&lsaquo; 上頁<\/a>/);
    if (prevUrlMatch && prevUrlMatch[1]) {
      currentUrl = CONFIG.PTT_BASE_URL + prevUrlMatch[1];
      Utilities.sleep(500);
    } else {
      break;
    }
  }

  // ── 發送通知 ─────────────────────────────────────
  if (newMatches.length > 0) {
    Logger.log(`🎉 找到 ${newMatches.length} 篇新的符合文章!`);
    for (let match of newMatches) {
      let msg = formatTelegramMessage(match.post, match.criteria, match.content);
      sendTelegram(msg);
    }
    // 儲存已看過紀錄至 GAS Properties
    saveSeenPosts(seenPosts);
  } else {
    Logger.log("ℹ️ 本次掃描無新的符合文章");
  }
}

// ── 工具函式 ──────────────────────────────────────────

function fetchPage(url) {
  try {
    let response = UrlFetchApp.fetch(url, {
      method: "get",
      headers: { "Cookie": "over18=1" },
      muteHttpExceptions: true
    });
    if (response.getResponseCode() === 200) {
      return response.getContentText("UTF-8");
    }
  } catch (e) {
    Logger.log(`[ERROR] 請求失敗: ${e}`);
  }
  return null;
}

function parsePostList(html) {
  let posts = [];
  // Regex 抓取列表項目
  let regex = /<div class="r-ent">[\s\S]*?<div class="nrec">([\s\S]*?)<\/div>[\s\S]*?<div class="title">\s*(<a href="([^"]+)">([^<]+)<\/a>|[^<]+)\s*<\/div>[\s\S]*?<div class="date">([^<]+)<\/div>/g;
  let match;

  while ((match = regex.exec(html)) !== null) {
    let nrecHtml = match[1];
    let nrec = "0";
    if (nrecHtml.includes("span")) {
      let nrecMatch = nrecHtml.match(/>([^<]+)<\/span>/);
      if (nrecMatch) nrec = nrecMatch[1];
    }

    let href = match[3];
    let title = match[4];
    let postDate = match[5] ? match[5].trim() : "";

    if (href && title) {
      posts.push({
        title: title.trim(),
        url: CONFIG.PTT_BASE_URL + href,
        nrec: nrec.trim(),
        date: postDate
      });
    }
  }
  return posts;
}

function parsePttTime(rawTime) {
  if (!rawTime) return "";
  // PTT time format: Mon Mar 24 14:12:17 2026
  let d = new Date(rawTime);
  if (isNaN(d.getTime())) return rawTime;
  return Utilities.formatDate(d, "Asia/Taipei", "yyyy/MM/dd HH:mm:ss");
}

function fetchPostContent(url) {
  let html = fetchPage(url);
  if (!html) return { content: "", exactTime: "" };

  // 萃取 main-content (用 split 比 regex 穩定，不會被中間的 </div> 騙)
  let parts = html.split('<div id="main-content" class="bbs-screen bbs-content">');
  if (parts.length < 2) return { content: "", exactTime: "" };

  // 切掉尾巴的 article-polling 等不需要的區塊
  let content = parts[1].split('<div id="article-polling"')[0];

  // 提取精確發文時間
  let exactTime = "";
  let timeMatch = content.match(/<span class="article-meta-tag">時間<\/span><span class="article-meta-value">([^<]+)<\/span>/);
  if (timeMatch) exactTime = parsePttTime(timeMatch[1].trim());

  // 移除 span 標籤 (推文或屬性) 與 div (發文時間列等)
  content = content.replace(/<div class="article-metaline[^>]*>[\s\S]*?<\/div>/g, "");
  content = content.replace(/<div class="article-metaline-right[^>]*>[\s\S]*?<\/div>/g, "");
  content = content.replace(/<div class="push">[\s\S]*?<\/div>/g, "");
  content = content.replace(/<span class="f2">※ 發信站:[\s\S]*?<\/span>/g, ""); // 移除簽名檔與網址尾巴
  content = content.replace(/<[^>]+>/g, ""); // strip all remaining HTML

  // 將 PTT 常見的 HTML 符號轉回文字
  content = content.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");

  return { content: content.trim(), exactTime: exactTime };
}

function matchesKeywords(text, keywords) {
  return keywords.some(kw => text.includes(kw));
}

function matchesAllKeywords(text, keywords) {
  return keywords.every(kw => text.includes(kw));
}

function checkAdvancedCriteria(text) {
  let foundDates = CONFIG.DATE_KEYWORDS.filter(d => text.includes(d));
  let foundSeats = CONFIG.SEAT_KEYWORDS.filter(s => text.includes(s));
  return {
    dates: foundDates,
    seats: foundSeats,
    isHighMatch: foundDates.length > 0 && foundSeats.length > 0
  };
}

function formatTelegramMessage(post, criteria, content) {
  let matchLevel = criteria.isHighMatch ? "🔥 高度符合" : "📋 可能相關";
  let datesStr = criteria.dates.length > 0 ? criteria.dates.join(", ") : "未明確提到";
  let seatsStr = criteria.seats.length > 0 ? criteria.seats.join(", ") : "未明確提到";

  let preview = content.substring(0, 300).replace(/\n/g, "\n> ");

  // 取得台北時間
  let now = new Date();
  let timeStr = Utilities.formatDate(now, "Asia/Taipei", "yyyy-MM-dd HH:mm:ss");

  return `${matchLevel}
━━━━━━━━━━━━━━━━
⏰ 掃描時間: ${timeStr}
📌 ${post.title}
🔗 ${post.url}
🗓️ 發文日期: ${post.date}
👍 推文數: ${post.nrec}
📅 日期: ${datesStr}
💺 座位: ${seatsStr}
━━━━━━━━━━━━━━━━
📝 內文預覽:
> ${preview}
...`;
}

function sendTelegram(message) {
  if (!TELEGRAM_BOT_TOKEN || TELEGRAM_BOT_TOKEN.includes("請在此填入")) return;

  let url = `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage`;
  let payload = {
    "chat_id": TELEGRAM_CHAT_ID,
    "text": message,
    "disable_web_page_preview": false
  };

  let options = {
    "method": "post",
    "contentType": "application/json",
    "payload": JSON.stringify(payload),
    "muteHttpExceptions": true
  };

  try {
    let response = UrlFetchApp.fetch(url, options);
    Logger.log(`[Telegram] 回應碼: ${response.getResponseCode()}`);
  } catch (e) {
    Logger.log(`[Telegram] 發送失敗: ${e}`);
  }
}

// ── 儲存與讀取狀態 (PropertiesService) ───────────────────

function loadSeenPosts() {
  let props = PropertiesService.getScriptProperties();
  let data = props.getProperty("SEEN_POSTS");
  if (data) {
    try {
      return JSON.parse(data);
    } catch (e) {
      return [];
    }
  }
  return [];
}

function saveSeenPosts(seenArray) {
  let props = PropertiesService.getScriptProperties();
  // 只保留最新的 MAX_SEEN_POSTS 筆，避免 GAS Property 容量爆掉 (上限約 9KB)
  if (seenArray.length > CONFIG.MAX_SEEN_POSTS) {
    seenArray = seenArray.slice(-CONFIG.MAX_SEEN_POSTS);
  }
  props.setProperty("SEEN_POSTS", JSON.stringify(seenArray));
}

// 清除記憶 (測試時可用)
function clearSeenPosts() {
  PropertiesService.getScriptProperties().deleteProperty("SEEN_POSTS");
  Logger.log("已清除所有歷史通知記憶！");
}
