import streamlit as st
# ★ 変更点1：新しいパッケージのインポート
from google import genai
import firebase_admin
from firebase_admin import credentials, firestore

# --- 画面の設定 ---
st.set_page_config(page_title="職員向け AIナレッジクイズ", page_icon="🧩", layout="wide")

# ==========================================
# 🚨 セキュリティバウンサー & データベース初期化
# ==========================================
if "user_email" not in st.session_state:
    st.warning("⚠️ ログインが必要です。左のメニューから「Home」に戻ってログインしてください。")
    st.stop()

APP_NAME = "ai_matching_app"
if APP_NAME not in firebase_admin._apps:
    try:
        key_dict = dict(st.secrets["firebase_ai_matching"])
        cred = credentials.Certificate(key_dict)
        firebase_admin.initialize_app(cred, name=APP_NAME)
    except Exception as e:
        pass # Homeで初期化済み想定

# === 🔑 APIキーの読み込み ===
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    # ★ 変更点2：Client（通信係）を作成
    client = genai.Client(api_key=api_key)
except Exception:
    st.error("⚠️ `.streamlit/secrets.toml` に APIキーを設定してください。")
    st.stop()

TARGET_MODEL = "gemini-3.1-flash-lite"

# --- セッション初期化 ---
# モード1：添削道場用
if "dojo_scenario" not in st.session_state: st.session_state.dojo_scenario = ""
if "dojo_feedback" not in st.session_state: st.session_state.dojo_feedback = ""

# モード2：ダメな記録用
if "record_text" not in st.session_state: st.session_state.record_text = ""
if "record_feedback" not in st.session_state: st.session_state.record_feedback = ""

# モード3：自分の支援記録添削用（★追加）
if "my_record_feedback" not in st.session_state: st.session_state.my_record_feedback = ""

# ==========================================
# 🎨 サイドバー：モード選択と共通操作
# ==========================================
st.sidebar.title("🎮 クイズモード選択")
# ★ 新しいモードをここに追加しました！
app_mode = st.sidebar.radio(
    "挑戦するゲームを選んでください",
    ["1️⃣ 記述式 AI添削道場", "2️⃣ 「ダメな支援記録」間違い探し", "3️⃣ 実践！自分の支援記録をAI添削"]
)
st.sidebar.markdown("---")
st.sidebar.info("💡 **ヒント**\nAIがその場で問題を自動生成するため、毎回違う状況・記録に挑戦できます！")

st.sidebar.markdown("---")
if st.sidebar.button("🧹 画面をクリア", use_container_width=True):
    # すべてのモードの履歴を真っさらにリセットします
    st.session_state.dojo_scenario = ""
    st.session_state.dojo_feedback = ""
    st.session_state.record_text = ""
    st.session_state.record_feedback = ""
    st.session_state.my_record_feedback = "" # ★ 追加
    st.rerun()

st.title("🧩 職員向け AIナレッジクイズ")

# ==========================================
# 🎮 モード1：記述式 AI添削道場
# ==========================================
if app_mode == "1️⃣ 記述式 AI添削道場":
    st.subheader("1️⃣ 記述式 AI添削道場（対応力の強化）")
    st.write("支援現場でよくある「困ったお題」に対して、あなたならどう対応するかテキストで入力してください。AIが100点満点で採点し、プロ目線で添削します。")
    
    if st.button("🎲 新しいお題をAIに出してもらう", type="primary"):
        with st.spinner("AIがお題を考えています..."):
            prompt = "就労移行支援の現場で、支援員が対応に困るような利用者様のリアルな発言や状況（お題）を1つ作成してください。例：「もう就活したくない」と泣き出す、等。お題のテキスト本文のみを2〜3文で出力してください。"
            # ★ 変更点3：client経由で実行
            response = client.models.generate_content(
                model=TARGET_MODEL,
                contents=prompt
            )
            st.session_state.dojo_scenario = response.text
            st.session_state.dojo_feedback = ""
            st.rerun()
            
    if st.session_state.dojo_scenario:
        st.markdown(f'<div style="background-color: #F0F4F8; padding: 20px; border-radius: 10px; border-left: 5px solid #4A90E2;"><h4>💬 お題（利用者の状況・発言）</h4>{st.session_state.dojo_scenario}</div>', unsafe_allow_html=True)
        
        user_response = st.text_area("✍️ あなたなら、どう声をかけますか？（またはどう対応しますか？）", height=100)
        
        if st.button("👨‍🏫 AIスーパーバイザーに採点してもらう"):
            if user_response:
                with st.spinner("AIがあなたの対応を評価しています..."):
                    eval_prompt = f"""
                    あなたは就労支援のベテラン・スーパーバイザーです。
                    お題：「{st.session_state.dojo_scenario}」
                    支援員の対応：「{user_response}」
                    
                    この対応を100点満点で採点し、以下のフォーマットで出力してください。
                    ### 💯 総合点：〇〇点
                    ### 🌟 良かった点（共感性など）
                    ### 💡 改善のヒント（より良い声かけの提案）
                    """
                    # ★ 変更点3：client経由で実行
                    eval_response = client.models.generate_content(
                        model=TARGET_MODEL,
                        contents=eval_prompt
                    )
                    st.session_state.dojo_feedback = eval_response.text
                    st.rerun()
            else:
                st.warning("あなたの対応を入力してください！")
                
    if st.session_state.dojo_feedback:
        st.markdown("---")
        st.markdown(st.session_state.dojo_feedback)

# ==========================================
# 🎮 モード2：「ダメな支援記録」間違い探し
# ==========================================
elif app_mode == "2️⃣ 「ダメな支援記録」間違い探し":
    st.subheader("2️⃣ 「ダメな支援記録」間違い探し（記録スキルの向上）")
    st.write("AIがわざと「ツッコミどころ満載のダメな記録」を作成します。どこがダメなのかを指摘してください！")
    
    if st.button("📄 ダメな記録を生成する", type="primary"):
        with st.spinner("AIがダメな記録を作成中..."):
            prompt = "就労移行支援の支援記録として、あえてツッコミどころ満載の「ダメな記録（主観的すぎる、事実が書かれていない、感情的、ネガティブすぎる等）」を150文字程度で作成してください。記録本文のみ出力してください。"
            # ★ 変更点3：client経由で実行
            response = client.models.generate_content(
                model=TARGET_MODEL,
                contents=prompt
            )
            st.session_state.record_text = response.text
            st.session_state.record_feedback = ""
            st.rerun()
            
    if st.session_state.record_text:
        st.markdown(f'<div style="background-color: #FFF0F0; padding: 20px; border-radius: 10px; border-left: 5px solid #E63946;"><h4>📋 今日の支援記録（AI作成）</h4>{st.session_state.record_text}</div>', unsafe_allow_html=True)
        
        user_finding = st.text_area("🔍 この記録の「どこがダメ」で、「どう直すべき」だと思いますか？", height=100)
        
        if st.button("💡 答え合わせをする"):
            if user_finding:
                with st.spinner("AIが解説を作成中..."):
                    eval_prompt = f"""
                    あなたは就労支援の記録指導員です。
                    ダメな記録：「{st.session_state.record_text}」
                    ユーザーの指摘：「{user_finding}」
                    
                    ユーザーの指摘を評価しつつ、以下のフォーマットで出力してください。
                    ### 🎯 ユーザーの指摘への評価（合っているかなど）
                    ### 🚨 本当のツッコミどころ（なぜこの記録がダメなのかの解説）
                    ### ✨ プロが書き直した「模範的な支援記録」
                    """
                    # ★ 変更点3：client経由で実行
                    eval_response = client.models.generate_content(
                        model=TARGET_MODEL,
                        contents=eval_prompt
                    )
                    st.session_state.record_feedback = eval_response.text
                    st.rerun()
            else:
                st.warning("ダメなポイントを指摘してください！")
                
    if st.session_state.record_feedback:
        st.markdown("---")
        st.markdown(st.session_state.record_feedback)

# ==========================================
# 🛠️ モード3：実践！自分の支援記録をAI添削（★新規追加）
# ==========================================
elif app_mode == "3️⃣ 実践！自分の支援記録をAI添削":
    st.subheader("3️⃣ 実践！自分の支援記録をAI添削")
    st.write("あなたが今日書いた支援記録をAIが客観的にチェックし、よりプロフェッショナルな表現にブラッシュアップします。")
    
    # ⚠️ 個人情報保護の注意喚起を強調表示
    st.warning("⚠️ **【重要】個人情報の保護について**\n利用者様の本名、具体的な企業名、その他個人を特定できる情報は絶対にそのまま入力しないでください。「Aさん」「B社」などに伏せ字化してから入力をお願いします。")
    
    my_record_input = st.text_area("📝 添削したい支援記録を入力してください", height=150, placeholder="例：Aさんが今日の訓練中にイライラしていた。声をかけたが「放っておいて」と言われたので様子を見ることにした。")
    
    if st.button("👨‍🏫 AIに記録を添削してもらう", type="primary"):
        if my_record_input:
            with st.spinner("AIスーパーバイザーが記録を分析しています..."):
                eval_prompt = f"""
                あなたは就労移行支援事業所の優秀なサービス管理責任者（記録指導のプロ）です。
                以下の支援員が書いた支援記録を添削し、より客観的で、具体的な事実に基づき、支援の意図が伝わる記録になるようアドバイスしてください。

                【支援員の記録】
                {my_record_input}

                以下のフォーマットで出力してください。
                ### 🌟 良い点（事実が書けているか、支援の視点があるか等）
                ### 💡 改善のポイント（主観的表現の修正、ネガティブ表現の言い換え、不足している情報の指摘等）
                ### ✨ 模範的な修正案（プロ視点での書き直し例）
                """
                # ★ 変更点3：client経由で実行
                response = client.models.generate_content(
                    model=TARGET_MODEL,
                    contents=eval_prompt
                )
                st.session_state.my_record_feedback = response.text
                st.rerun()
        else:
            st.warning("支援記録が入力されていません！")
            
    if st.session_state.my_record_feedback:
        st.markdown("---")
        st.markdown(st.session_state.my_record_feedback)
