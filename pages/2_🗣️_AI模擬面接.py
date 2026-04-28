import streamlit as st
# ★ 変更点1：新しいパッケージのインポート
from google import genai
from google.genai import types
import edge_tts
import asyncio
import io
import zipfile
import datetime

# --- 画面の設定 ---
st.set_page_config(page_title="AI模擬面接トレーニング", page_icon="🗣️", layout="centered")

# ==========================================
# 🚨 セキュリティバウンサー（未ログイン者を追い出す）
# ==========================================
if "user_email" not in st.session_state:
    st.warning("⚠️ ログインが必要です。左のメニューから「Home」に戻ってログインしてください。")
    st.stop()
# ==========================================

# === 🔑 APIキーの読み込み ===
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    # ★ 変更点2：Client（通信係）を作成
    client = genai.Client(api_key=api_key)
except Exception:
    st.error("⚠️ `.streamlit/secrets.toml` に APIキーを設定してください。")
    st.stop()

TARGET_MODEL = "gemini-2.5-flash-lite"

# --- セッション（記憶）の初期化 ---
if "messages" not in st.session_state: st.session_state.messages = []
if "current_setup" not in st.session_state: st.session_state.current_setup = ""
if "interview_started" not in st.session_state: st.session_state.interview_started = False
if "interview_finished" not in st.session_state: st.session_state.interview_finished = False
if "feedback" not in st.session_state: st.session_state.feedback = ""
if "last_audio" not in st.session_state: st.session_state.last_audio = None
if "played_msg_count" not in st.session_state: st.session_state.played_msg_count = 0

# --- 音声生成（Edge-TTS）関数 ---
async def _generate_audio(text, voice, rate):
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    audio_data = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data.extend(chunk["data"])
    return bytes(audio_data)

def generate_audio(text, voice, rate):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(_generate_audio(text, voice, rate))
    loop.close()
    return result

# --- 一括ダウンロード用ZIP生成関数 ---
def create_zip_archive(messages):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for i, msg in enumerate(messages):
            if "audio" in msg and msg["audio"] is not None:
                speaker = "面接官" if msg["role"] == "assistant" else "応募者"
                ext = "mp3" if msg["role"] == "assistant" else "wav"
                filename = f"{i+1:02d}_{speaker}.{ext}"
                zip_file.writestr(filename, msg["audio"])
    return zip_buffer.getvalue()

# --- カスタムCSS ---
st.markdown("""
<style>
.stApp { background-color: #F8F9FA; }
div[data-testid="stChatMessage"] { border-radius: 10px; padding: 10px; margin-bottom: 10px; }
div[data-testid="stChatMessage"]:nth-child(odd) { background-color: #E3F2FD; border: 1px solid #BBDEFB; }
div[data-testid="stChatMessage"]:nth-child(even) { background-color: #ffffff; border: 1px solid #E0E0E0; }
.feedback-box { background-color: #ffffff; padding: 25px; border-radius: 12px; border-top: 5px solid #E9C46A; box-shadow: 0 4px 15px rgba(0,0,0,0.05); margin-top: 20px; }
.interviewer-box { background-color: #E3F2FD; padding: 25px; border-radius: 12px; font-size: 1.2rem; line-height: 1.6; border: 2px solid #BBDEFB; color: #1E3A8A; margin-bottom: 5px; margin-top: 20px;}
div[data-testid="stAudioInput"] { transform: scale(1.3); transform-origin: top center; margin-top: 20px; margin-bottom: 20px;}
</style>
""", unsafe_allow_html=True)

# 画面の縦スペースを節約するため、音声モード中のみタイトルを隠す
is_voice_mode_active = st.session_state.interview_started and not st.session_state.interview_finished and "🎤" in st.session_state.get("current_setup", "")
if not is_voice_mode_active:
    st.title("🗣️ AI模擬面接トレーニング")

# --- サイドバー：設定 ---
with st.sidebar:
    st.header("⚙️ 面接の設定")
    
    input_mode = st.radio("🎙️ 回答の入力方法", ["⌨️ テキストで入力する", "🎤 音声（マイク）で回答する"])
    
    st.markdown("---")
    st.subheader("👤 あなたのプロフィール")
    
    job_options = [
        "一般事務・データ入力",
        "軽作業（ピッキング・梱包・仕分け）",
        "清掃・ビルメンテナンス",
        "飲食・サービス（ホール・キッチン）",
        "製造・工場ライン",
        "IT・エンジニア・Web制作",
        "小売・販売",
        "福祉・介護",
        "その他"
    ]
    target_job = st.selectbox("🏢 希望職種・業界", job_options)
    
    trait_diagnosis = st.text_input("📝 障がい特性・診断名", placeholder="例：ASD、ADHD、うつ病など")
    trait_strength = st.text_area("✨ 得意なこと", placeholder="例：ルーチンワーク、正確な入力", height=68)
    trait_weakness = st.text_area("⚠️ 苦手なこと", placeholder="例：電話対応、マルチタスク、騒音", height=68)
    trait_accommodation = st.text_area("🤝 配慮してほしいこと", placeholder="例：質問は1つずつゆっくりしてほしい", height=68)
    
    user_traits = f"""
【障がい特性・診断名】 {trait_diagnosis}
【得意なこと】 {trait_strength}
【苦手なこと】 {trait_weakness}
【配慮してほしいこと】 {trait_accommodation}
    """.strip()

    st.markdown("---")
    st.subheader("🎭 面接官の設定")
    
    level = st.radio("難易度", ["🌱 レベル1（やさしい）", "🏢 レベル2（標準）"])
    
    col1, col2 = st.columns(2)
    with col1:
        voice_type = st.selectbox("🗣️ 声の性別", ["👩 女性（Nanami）", "👨 男性（Keita）"])
        voice_model = "ja-JP-NanamiNeural" if "女性" in voice_type else "ja-JP-KeitaNeural"
    with col2:
        speed_type = st.selectbox("⏱️ 話すスピード", ["ゆっくり (-20%)", "標準 (0%)", "少し早め (+20%)"], index=1)
        if "ゆっくり" in speed_type: voice_rate = "-20%"
        elif "早め" in speed_type: voice_rate = "+20%"
        else: voice_rate = "+0%"
    
    st.markdown("---")
    
    if st.session_state.interview_started and not st.session_state.interview_finished:
        if st.button("🛑 面接を終了してフィードバックをもらう", type="primary", use_container_width=True):
            if len(st.session_state.messages) <= 1:
                st.warning("⚠️ まだやり取りが少ないようです。まずは一度答えてみましょう！")
            else:
                with st.spinner("フィードバックを作成中..."):
                    try:
                        history_text = "\n".join([f"{'面接官' if msg['role'] == 'assistant' else '応募者'}: {msg['content']}" for msg in st.session_state.messages])
                        feedback_prompt = f"就労支援員として以下の面接を分析し、優しいフィードバックを作成してください。\n【面接のやり取り】\n{history_text}\n\n出力形式:\n### 🌟 良かった点\n### 💡 改善のヒント\n### 💬 総合アドバイス"
                        
                        # ★ 変更点3：フィードバックの生成
                        res = client.models.generate_content(
                            model=TARGET_MODEL,
                            contents=feedback_prompt
                        )
                        st.session_state.feedback = res.text
                        st.session_state.interview_finished = True
                        st.rerun()
                    except Exception as e:
                        st.error(f"エラー: {e}")

    st.markdown("<br>", unsafe_allow_html=True)
    reset_btn = st.button("🔄 設定をリセットして最初から始める", use_container_width=True)

# --- AIの設定生成 ---
persona = "あなたは就労移行支援事業所の優しいスタッフとして面接練習を行います。利用者の回答を肯定し、答えやすい簡単な質問を投げかけてください。" if "🌱" in level else "あなたは企業の標準的な採用面接官です。丁寧な口調で実践的な質問を投げかけてください。威圧する態度は絶対に取らないでください。"
system_instruction = f"{persona}\n【設定】希望職種:{target_job}\n特性:\n{user_traits}\n【ルール】AIとは名乗らず、質問は1回に1つだけ。応募者の回答を待つこと。"

# --- リセット処理 ---
setup_string = f"{target_job}_{user_traits}_{level}_{voice_model}_{voice_rate}_{input_mode}"
if reset_btn or st.session_state.current_setup != setup_string:
    st.session_state.messages = []
    st.session_state.current_setup = setup_string
    st.session_state.interview_started = False
    st.session_state.interview_finished = False
    st.session_state.feedback = ""
    st.session_state.last_audio = None
    st.session_state.played_msg_count = 0
    st.rerun()

# ★ 変更点4：チャットセッションの新しい書き方
config = types.GenerateContentConfig(system_instruction=system_instruction)

# これまでのメッセージ履歴を新しい形式に変換
formatted_history = []
for m in st.session_state.messages:
    role = "model" if m["role"] == "assistant" else "user"
    formatted_history.append(
        types.Content(role=role, parts=[types.Part.from_text(text=m["content"])])
    )

# 新しいチャットの開始
chat = client.chats.create(model=TARGET_MODEL, config=config, history=formatted_history)

# === 🌟 画面表示コントロール ===

# 1. スタート前の画面
if not st.session_state.interview_started:
    st.markdown("### 📝 面接の準備")
    st.info("👈 左側のメニューで「希望職種」や「あなたのプロフィール」を入力してください。\n準備ができたら、下のボタンを押してAI面接官を呼び出します。")
    
    if st.button("🚀 面接をスタートする", type="primary", use_container_width=True):
        st.session_state.interview_started = True
        st.rerun()

# 2. スタート直後（最初の挨拶を取得）
elif st.session_state.interview_started and len(st.session_state.messages) == 0:
    with st.spinner("面接官が入室し、最初の質問を準備しています..."):
        try:
            response = chat.send_message(f"「{target_job}」の面接を開始し、最初の質問を1つ投げかけてください。")
            msg_ai = {"role": "assistant", "content": response.text}
            
            if "🎤" in input_mode:
                msg_ai["audio"] = generate_audio(response.text, voice_model, voice_rate)
                
            st.session_state.messages.append(msg_ai)
            st.rerun()
        except Exception as e:
            st.error(f"通信エラーが発生しました。設定を見直して再度お試しください: {e}")

# 3. 面接中の画面（スタート後、未終了）
elif st.session_state.interview_started and not st.session_state.interview_finished:
    
    user_text = None
    user_audio_bytes = None

    if "⌨️" in input_mode:
        # 【A】テキストモード（従来のチャット形式）
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                if "audio" in message and message["audio"] is not None:
                    fmt = "audio/mp3" if message["role"] == "assistant" else "audio/wav"
                    st.audio(message["audio"], format=fmt, autoplay=False)
        
        user_text = st.chat_input("回答を入力してEnter")

    elif "🎤" in input_mode:
        # 【B】音声モード：画像なしのシンプル没入UI（待機処理なし・常時マイク表示）
        st.markdown("<h4 style='text-align:center; color:#2C3E50; margin-top:-30px; margin-bottom:10px;'>🎙️ 音声面接モード</h4>", unsafe_allow_html=True)
        
        last_ai_msg = next((msg for msg in reversed(st.session_state.messages) if msg["role"] == "assistant"), None)
        
        if last_ai_msg:
            # 質問テキスト
            st.markdown(f"<div class='interviewer-box'><b>🗣️ 面接官：</b><br><br>{last_ai_msg['content']}</div>", unsafe_allow_html=True)
            
            # 音声プレイヤー
            msg_count = len(st.session_state.messages)
            should_play = (st.session_state.played_msg_count < msg_count)
            
            if "audio" in last_ai_msg and last_ai_msg["audio"] is not None:
                # 最新のメッセージのみ自動再生する
                st.audio(last_ai_msg["audio"], format="audio/mp3", autoplay=should_play)
            
            # 再生済みフラグを更新
            if should_play:
                st.session_state.played_msg_count = msg_count

        st.markdown("""
            <div style='text-align:center; margin-top:20px;'>
                <b style='color:#E74C3C;'>🎤 あなたの番です</b><br>
                <span style='color:#7F8C8D; font-size:0.9rem;'>※面接官が話し終わってから、マイクを押して録音してください</span>
            </div>
        """, unsafe_allow_html=True)
        
        audio_val = st.audio_input("マイク", label_visibility="collapsed", key=f"mic_{len(st.session_state.messages)}")
        
        if audio_val and audio_val != st.session_state.last_audio:
            st.session_state.last_audio = audio_val
            with st.spinner("AIがあなたの声を文字起こししています..."):
                try:
                    user_audio_bytes = audio_val.getvalue()
                    
                    # ★ 変更点5：音声データを渡すための新しい書き方
                    audio_part = types.Part.from_bytes(data=user_audio_bytes, mime_type="audio/wav")
                    
                    t_res = client.models.generate_content(
                        model=TARGET_MODEL,
                        contents=[audio_part, "この音声を正確に日本語で文字起こししてください。結果のテキストのみ出力してください。"]
                    )
                    user_text = t_res.text
                except Exception as e:
                    st.error("音声の読み取りに失敗しました。もう一度録音するか、テキストモードをお試しください。")

    # --- 共通の回答送信処理（AIからの返答） ---
    if user_text:
        msg_user = {"role": "user", "content": user_text}
        if user_audio_bytes:
            msg_user["audio"] = user_audio_bytes
        st.session_state.messages.append(msg_user)
        
        # テキストモードの時だけ画面に一瞬自分の文字を描画
        if "⌨️" in input_mode:
            with st.chat_message("user"):
                st.markdown(user_text)

        with st.spinner("面接官が次の言葉を考えています..."):
            try:
                response = chat.send_message(user_text)
                msg_ai = {"role": "assistant", "content": response.text}
                
                if "🎤" in input_mode:
                    msg_ai["audio"] = generate_audio(response.text, voice_model, voice_rate)
                
                st.session_state.messages.append(msg_ai)
                st.rerun() 
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")

# 4. フィードバック画面（終了後：元のチャット構成とPDFに戻る）
elif st.session_state.interview_finished:
    st.markdown(f'<div class="feedback-box"><h3>📋 面接お疲れ様でした！振り返りレポート</h3>{st.session_state.feedback}</div>', unsafe_allow_html=True)
    
    st.markdown("<br><h3>💬 面接のやり取り履歴</h3>", unsafe_allow_html=True)
    
    history_html = ""
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if "audio" in msg and msg["audio"] is not None:
                fmt = "audio/mp3" if msg["role"] == "assistant" else "audio/wav"
                st.audio(msg["audio"], format=fmt, autoplay=False)
        
        speaker = "面接官" if msg['role'] == 'assistant' else "応募者"
        history_html += f"<b>{speaker}：</b> {msg['content']}<br><br>"

    feedback_formatted = st.session_state.feedback.replace('\n', '<br>')
    traits_formatted = user_traits.replace('\n', '<br>')
    
    report_html = f"""
    <html><head><meta charset="UTF-8"><title>AI模擬面接 振り返りレポート</title>
    <style>
        body {{ font-family: 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 30px; }}
        h1 {{ color: #1e3a5f; border-bottom: 2px solid #1e3a5f; padding-bottom: 10px; font-size: 24px; }}
        h2 {{ color: #2e7d32; margin-top: 30px; font-size: 20px; }}
        .box {{ background: #f4f6f9; padding: 15px; border-radius: 8px; margin-bottom: 20px; font-size: 14px; }}
        .feedback {{ background: #fffae6; padding: 20px; border-radius: 8px; border-left: 5px solid #E9C46A; margin-bottom: 20px; }}
        .print-btn {{ display: block; width: 200px; margin: 20px auto; padding: 10px; text-align: center; background: #1e3a5f; color: #fff; text-decoration: none; border-radius: 5px; cursor: pointer; }}
        @media print {{ .no-print {{ display: none !important; }} }}
    </style></head>
    <body>
        <button class="no-print print-btn" onclick="window.print()">🖨️ PDFとして保存 / 印刷</button>
        <h1>AI模擬面接 振り返りレポート</h1>
        <p style="text-align:right;">実施日: {datetime.datetime.now().strftime('%Y年%m月%d日')}</p>
        
        <div class="box">
            <b>【設定内容】</b><br>
            ▪️ 希望職種・業界: {target_job}<br>
            ▪️ プロフィール: <br>{traits_formatted}<br>
            ▪️ 面接官のタイプ: {level}
        </div>
        
        <h2>💡 プロからのフィードバック</h2>
        <div class="feedback">
            {feedback_formatted}
        </div>

        <h2>💬 面接のやり取り履歴</h2>
        <div class="box">
            {history_html}
        </div>
    </body></html>
    """

    st.markdown("---")
    st.subheader("💾 記録の保存")
    
    col_dl1, col_dl2 = st.columns(2)
    
    with col_dl1:
        st.download_button(
            label="📄 振り返りレポートをダウンロード (PDF保存用)",
            data=report_html,
            file_name=f"interview_report_{datetime.datetime.now().strftime('%Y%m%d')}.html",
            mime="text/html",
            use_container_width=True
        )
        
    with col_dl2:
        has_audio = any("audio" in msg and msg["audio"] is not None for msg in st.session_state.messages)
        if has_audio:
            zip_data = create_zip_archive(st.session_state.messages)
            st.download_button(
                label="📦 音声データを一括ダウンロード (ZIP形式)",
                data=zip_data,
                file_name=f"interview_audio_{datetime.datetime.now().strftime('%Y%m%d')}.zip",
                mime="application/zip",
                use_container_width=True
            )
        else:
            st.info("※テキストモードのため音声データの保存はありません")

    st.success("✅ 左のサイドバーから「最初からやり直す」ボタンを押すと、何度でも再挑戦できます！")