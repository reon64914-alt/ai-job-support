import streamlit as st
# ★ 変更点1：新しいパッケージのインポート
from google import genai
import pandas as pd
import plotly.express as px
import datetime
import streamlit.components.v1 as components

# --- 画面の設定 ---
st.set_page_config(page_title="AI じぶん発見＆働き方ナビ", page_icon="🌱", layout="centered")

# ==========================================
# 🚨 セキュリティバウンサー（未ログイン者を追い出す）
# ==========================================
if "user_email" not in st.session_state:
    st.warning("⚠️ ログインが必要です。左のメニューから「Home」に戻ってログインしてください。")
    st.stop()  # 👈 これが超重要！ここでプログラムの実行を強制ストップさせます
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

# --- セッションの初期化 ---
if "diagnostic_result" not in st.session_state: 
    st.session_state.diagnostic_result = None
if "radar_chart" not in st.session_state:
    st.session_state.radar_chart = None

# --- カスタムCSS（丸みを帯びた優しいデザイン） ---
st.markdown("""
<style>
.stApp { background-color: #FAFAF7; }
.feedback-box { background-color: #ffffff; padding: 25px; border-radius: 15px; border-top: 5px solid #ffb3ba; box-shadow: 0 4px 15px rgba(0,0,0,0.05); margin-top: 20px; margin-bottom: 20px;}
.question-box { background-color: #ffffff; padding: 20px; border-radius: 15px; border: 1px solid #f0f0f0; margin-bottom: 15px; }
.soft-text { color: #555555; font-size: 0.95rem; line-height: 1.6; }
</style>
""", unsafe_allow_html=True)

st.title("🌱 AI じぶん発見＆働き方ナビ")
st.markdown("<p class='soft-text'>あなたの「すてきなところ」や「ホッとできる環境」を一緒に見つけるツールです。<br>AIが、あなたにぴったりの働き方のヒントを優しくお伝えします。</p>", unsafe_allow_html=True)

# --- サイドバー：プロフィール設定 ---
with st.sidebar:
    st.header("👤 あなたのこと")
    st.write("少しだけ、あなたのことを教えてくださいね。")
    age = st.selectbox("年齢層", ["10代・20代", "30代・40代", "50代以上"])
    disability = st.selectbox("障害について（メイン）", ["発達障害", "知的障害", "精神障害", "身体障害", "その他・回答しない"])
    
    st.markdown("---")
    if st.button("🔄 最初からやりなおす", use_container_width=True):
        st.session_state.diagnostic_result = None
        st.session_state.radar_chart = None
        st.rerun()

# --- メイン画面：入力フォーム（★常に表示させます） ---
with st.form("diagnostic_form"):
    st.subheader("🍀 第1部：どんな作業が好きですか？")
    st.markdown("<p class='soft-text'>今の気持ちに近いものを、あまり悩まずに選んでみてくださいね。</p>", unsafe_allow_html=True)
    
    opts = {"あてはまる": 2, "どちらともいえない": 1, "あてはまらない": 0}
    
    st.markdown("<div class='question-box'>", unsafe_allow_html=True)
    st.write("📝 **【A：コツコツ・正確な作業】**")
    a1 = st.radio("1. 決められた手順やルールの通りに進めるのが安心する", list(opts.keys()), horizontal=True)
    a2 = st.radio("2. 間違いがないか、細かいところを確認するのは得意なほうだ", list(opts.keys()), horizontal=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='question-box'>", unsafe_allow_html=True)
    st.write("🏃‍♂️ **【B：体を動かす・アクティブな作業】**")
    b1 = st.radio("3. ずっと座っているより、立ったり体を動かすほうが気分が良い", list(opts.keys()), horizontal=True)
    b2 = st.radio("4. 掃除や片付けをして、部屋がきれいになるとスッキリする", list(opts.keys()), horizontal=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='question-box'>", unsafe_allow_html=True)
    st.write("🤝 **【C：サポート・人と関わる仕事】**")
    c1 = st.radio("5. 誰かの役に立ったり、「ありがとう」と言われるとすごく嬉しい", list(opts.keys()), horizontal=True)
    c2 = st.radio("6. 人の顔や名前を覚えたり、ちょっとした挨拶をするのが好きだ", list(opts.keys()), horizontal=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='question-box'>", unsafe_allow_html=True)
    st.write("🎨 **【D：アイデア・工夫する作業】**")
    d1 = st.radio("7. 「もっとこうすれば便利かも」と、自分なりに工夫を考えるのが好きだ", list(opts.keys()), horizontal=True)
    d2 = st.radio("8. 絵を描いたり、文章を書いたり、何かを作るのが好きだ", list(opts.keys()), horizontal=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='question-box'>", unsafe_allow_html=True)
    st.write("🔍 **【E：集中・もくもく作業】**")
    e1 = st.radio("9. 一人の空間で、自分のペースでもくもくと作業を進めたい", list(opts.keys()), horizontal=True)
    e2 = st.radio("10. 興味があることには、時間を忘れてのめり込むことがある", list(opts.keys()), horizontal=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.subheader("🏢 第2部：どんな環境だと安心しますか？")
    env1 = st.radio("・働くペースと環境について", ["周りに人がいて、少し活気がある環境のほうががんばれる", "静かな環境で、自分のペースを守って進めたい"])
    env2 = st.radio("・コミュニケーションについて", ["わからないことは、自分から「教えて」と質問できる", "言葉で言われるより、メモや図、マニュアルを見るほうが分かりやすい"])
    env3 = st.radio("・仕事のお願いのされ方について", ["一度にいくつか頼まれても、自分で順番を決めて進められる", "あわててしまうので、できれば一つずつ順番にお願いしてほしい"])

    st.subheader("💌 第3部：スタッフとAIへのひみつの相談")
    text_anxiety = st.text_area("Q. 最近の生活や、これからのお仕事のことで、少し不安に思っていることはありますか？", placeholder="例：面接のことを考えると、緊張して言葉が出なくなってしまいます。")
    text_negative = st.text_area("Q. ご自身の「ここが苦手だな」「ついやってしまうな」と思うところがあれば教えてください。", placeholder="例：こだわりが強くて、ひとつのことにすごく時間がかかってしまいます。")

    submit_btn = st.form_submit_button("✨ 診断して、アドバイスをもらう", type="primary", use_container_width=True)

# --- 診断とAI生成の処理 ---
if submit_btn:
    score_a = opts[a1] + opts[a2]
    score_b = opts[b1] + opts[b2]
    score_c = opts[c1] + opts[c2]
    score_d = opts[d1] + opts[d2]
    score_e = opts[e1] + opts[e2]

    df = pd.DataFrame({
        "タイプ": ["📝コツコツ・正確", "🏃‍♂️アクティブ・体力", "🤝サポート・対人", "🎨アイデア・工夫", "🔍集中・もくもく"],
        "スコア": [score_a, score_b, score_c, score_d, score_e]
    })
    fig = px.line_polar(df, r='スコア', theta='タイプ', line_close=True, range_r=[0, 4])
    fig.update_traces(fill='toself', line_color='#ffb3ba')
    st.session_state.radar_chart = fig

    with st.spinner("あなたのすてきなところを、AIが一生懸命さがしています...（約10〜15秒）"):
        prompt = f"""
        あなたは就労移行支援事業所の、とても優しくて温かいスタッフです。
        以下の相談者のデータをもとに、アドバイスと書類の下書きを作成してください。

        【重要ルール】
        ・あなたは凄腕の就労支援員でありジョブコーチです。
        ・専門用語や難しい言葉は絶対に避けてください。
        ・「〜ですね」「〜ですよ」といった、優しく語りかけるようなトーン（少しひらがなを多め）で書いてください。
        ・相手を否定せず、すべてを肯定し、温かく包み込むようなメッセージにしてください。
        ・指定した4つの見出し（###）以外で、文字を大きくする記号（# や ##）は絶対に使わないでください。本文は普通の文字サイズで書いてください。

        【相談者のデータ】
        ・年齢層: {age} / 障害特性: {disability}
        ・適性スコア: 正確性({score_a}点)、体力({score_b}点)、対人({score_c}点)、アイデア({score_d}点)、集中力({score_e}点)
        ・希望する環境: {env1}、{env2}、{env3}
        ・不安なこと: {text_anxiety}
        ・苦手なこと: {text_negative}

        【以下の4つの見出しを使って出力してください】
        ### 🌸 あなたへのメッセージ
        ### ✨ あなたの「隠れた才能」
        ### 📝 履歴書に書ける「あなたの魅力」
        ### 🤝 企業へのお願い（配慮事項）
        """

        try:
            # ★ 変更点3：client経由で実行するように変更
            response = client.models.generate_content(
                model=TARGET_MODEL,
                contents=prompt
            )
            st.session_state.diagnostic_result = response.text
            # ★ フォームを残すため、ここにあった st.rerun() を削除しました
        except Exception as e:
            st.error(f"ごめんなさい、AIの考え中にエラーが起きてしまいました: {e}")

# --- 結果表示画面（★フォームの下に表示されます） ---
if st.session_state.diagnostic_result:
    
    st.markdown("---")
    st.header("🎉 あなたの診断結果")

    st.markdown("### 📈 あなたの「得意」のバランス")
    st.plotly_chart(st.session_state.radar_chart, use_container_width=True)
    
    st.markdown(f'<div class="feedback-box">{st.session_state.diagnostic_result}</div>', unsafe_allow_html=True)

    result_formatted = st.session_state.diagnostic_result.replace('\n', '<br>')
    
    report_html = f"""
    <html><head><meta charset="UTF-8"><title>AI じぶん発見 レポート</title>
    <style>
        body {{ font-family: 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #444; max-width: 800px; margin: 0 auto; padding: 30px; background-color: #FAFAF7; }}
        h1 {{ color: #e6739f; border-bottom: 2px dashed #ffb3ba; padding-bottom: 10px; font-size: 24px; text-align: center; }}
        .feedback {{ background: #ffffff; padding: 25px; border-radius: 15px; border: 2px solid #ffb3ba; margin-bottom: 20px; }}
        .print-btn {{ display: block; width: 250px; margin: 20px auto; padding: 12px; text-align: center; background: #ffb3ba; color: #fff; text-decoration: none; border-radius: 30px; cursor: pointer; border: none; font-size: 16px; font-weight: bold; box-shadow: 0 4px 6px rgba(0,0,0,0.1);}}
        @media print {{ body {{ background-color: #fff; }} .no-print {{ display: none !important; }} }}
    </style></head>
    <body>
        <button class="no-print print-btn" onclick="window.print()">🖨️ PDFとして保存 / 印刷する</button>
        <h1>🌱 AI じぶん発見 レポート</h1>
        <p style="text-align:right; font-size: 12px; color: #888;">発行日: {datetime.datetime.now().strftime('%Y年%m月%d日')}</p>
        
        <div class="feedback">
            {result_formatted}
        </div>
    </body></html>
    """

    st.markdown("---")
    st.subheader("💾 結果の保存")
    
    st.download_button(
        label="📄 診断レポートをダウンロード (PDF保存用)",
        data=report_html,
        file_name=f"diagnostic_report_{datetime.datetime.now().strftime('%Y%m%d')}.html",
        mime="text/html",
        use_container_width=True
    )