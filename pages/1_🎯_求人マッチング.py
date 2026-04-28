import streamlit as st
import pandas as pd
# ★ 変更点1：新しいパッケージのインポート方法に変更
from google import genai
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
import time

# --- 画面の設定 ---
st.set_page_config(page_title="AI就労支援システム PRO", page_icon="🤝", layout="wide", initial_sidebar_state="expanded")

# ==========================================
# 🚨 セキュリティバウンサー（未ログイン者を追い出す）
# ==========================================
if "user_email" not in st.session_state:
    st.warning("⚠️ ログインが必要です。左のメニューから「Home」に戻ってログインしてください。")
    st.stop()

# === 🌟 データベース（Firebase）のマルチアプリ接続設定 ===
APP_NAME = "ai_matching_app"

if APP_NAME not in firebase_admin._apps:
    try:
        key_dict = dict(st.secrets["firebase_ai_matching"])
        cred = credentials.Certificate(key_dict)
        firebase_admin.initialize_app(cred, name=APP_NAME)
    except Exception as e:
        st.error(f"ai-job-matching への接続に失敗しました: {e}")
        st.stop()
app = firebase_admin.get_app(APP_NAME)
db = firestore.client(app=app)

st.sidebar.success(f"🔌 接続先: {app.project_id}")

# === 🔑 APIキーの読み込み ===
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    # ★ 変更点2：Client（通信係）を作成する新しい書き方
    client = genai.Client(api_key=api_key)
except Exception:
    st.error("⚠️ `.streamlit/secrets.toml` に APIキーを設定してください。")
    st.stop()

TARGET_MODEL = "gemini-2.5-flash-lite"

# === 🌟 データ読み込み関数 ===
@st.cache_data(ttl=3600)
def load_data_from_db():
    docs = db.collection('jobs').stream()
    data = [doc.to_dict() for doc in docs]
    return pd.DataFrame(data)

# 記憶箱（セッション）の初期化
if 'ai_response' not in st.session_state: st.session_state.ai_response = None
if 'filtered_df' not in st.session_state: st.session_state.filtered_df = None
if 'interview_advice' not in st.session_state: st.session_state.interview_advice = {}

# === 🎨 カスタムCSS ===
st.markdown("""
<style>
.stApp { background-color: #F8F9FA; }
h1, h2, h3, h4, h5 { color: #2C3E50 !important; font-family: 'Helvetica Neue', Arial, sans-serif; }
div[data-testid="stButton"] > button {
    border-radius: 25px; font-weight: bold; border: none;
    transition: all 0.3s ease; box-shadow: 0 4px 10px rgba(0,0,0,0.08);
}
div[data-testid="stButton"] > button:hover {
    transform: translateY(-2px); box-shadow: 0 6px 15px rgba(0,0,0,0.12);
}
div[data-testid="stButton"] > button[kind="primary"] {
    background: linear-gradient(135deg, #2A9D8F 0%, #207567 100%);
    color: white; font-size: 1.1rem; padding: 0.5rem 2rem;
}
.result-card {
    background-color: #ffffff; padding: 30px; border-radius: 16px;
    border-top: 6px solid #2A9D8F; box-shadow: 0 10px 30px rgba(0,0,0,0.06); 
    margin-bottom: 25px; line-height: 1.8; color: #34495E; font-size: 1.05rem;
}
.job-detail-box {
    background-color: #ffffff; padding: 20px; border-radius: 12px;
    border-left: 5px solid #E9C46A; box-shadow: 0 4px 15px rgba(0,0,0,0.04); margin-bottom: 20px;
}
hr { border-color: #E2E8F0; }
</style>
""", unsafe_allow_html=True)

st.title("🤝 AI就労支援マッチング・プロ")
st.markdown("<p style='color:#7F8C8D; font-size:1.1rem;'>利用者の特性と求人データをAIが照合し、最適なキャリアパスと支援方針を提案します。</p>", unsafe_allow_html=True)

# --- サイドバー：絞り込みと管理 ---
with st.sidebar:
    st.header("🤖 システムステータス")
    st.info(f"✨ 稼働中: {TARGET_MODEL}")
    st.markdown("---")
    st.header("🔍 求人の事前絞り込み")
    st.caption("※未入力の項目は「すべて」を対象に検索します。")
    
    f_location = st.text_input("📍 希望勤務地", placeholder="例：大阪市、生駒市", key="f_location")
    f_type = st.multiselect("👤 雇用形態", ["正社員", "パート", "有期雇用派遣", "無期雇用派遣", "正社員以外"], key="f_type")
    f_wage_hourly = st.number_input("時給の下限（円）", min_value=0, value=0, step=50, key="f_wage_hourly")
    f_wage_monthly = st.number_input("月給の下限（円）", min_value=0, value=0, step=5000, key="f_wage_monthly")
    
    st.markdown("---")
    with st.expander("🔐 管理者メニュー（求人同期）"):
        uploaded_file = st.file_uploader("CSVファイルを選択", type=["csv"])
        if uploaded_file and st.button("データベースを同期する", use_container_width=True):
            try:
                df_up = pd.read_csv(uploaded_file, encoding='utf-8')
            except:
                uploaded_file.seek(0)
                df_up = pd.read_csv(uploaded_file, encoding='shift_jis')
            bar = st.progress(0, text="同期準備中...")
            for i, row in df_up.iterrows():
                doc = row.dropna().to_dict()
                doc['registered_at'] = datetime.now()
                job_id = str(doc.get('求人番号', f"job_{i}"))
                db.collection('jobs').document(job_id).set(doc)
                bar.progress((i+1)/len(df_up), text=f"書き込み中: {i+1}件目")
            
            st.success("✅ データベースの同期が完了しました！")
            st.cache_data.clear()
            st.rerun()

    with st.expander("🧹 データメンテナンス"):
        delete_target = st.radio("削除する対象を選択：", ["1年以上前のデータ", "2年以上前のデータ", "3年以上前のデータ"])
        confirm_delete = st.checkbox("本当に削除してもよろしいですか？")
        if st.button("🗑️ データを削除する", use_container_width=True):
            if confirm_delete:
                days_sub = 365 if "1年" in delete_target else 730 if "2年" in delete_target else 1095
                cutoff_date = datetime.now() - timedelta(days=days_sub)
                with st.spinner("検索・削除中..."):
                    old_docs = db.collection('jobs').where('registered_at', '<', cutoff_date).stream()
                    count = 0
                    for doc in old_docs:
                        doc.reference.delete()
                        count += 1
                    
                    if count > 0:
                        st.success(f"🗑️ {count}件の古いデータを削除しました！")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.info("対象となる古いデータはありませんでした。")
            else:
                st.error("確認のチェックを入れてください。")
                
    st.markdown("---")
    if st.button("🔄 入力と結果をすべてリセット", use_container_width=True):
        keys_to_clear = [
            'ai_response', 'filtered_df', 'interview_advice',
            'f_location', 'f_type', 'f_wage_hourly', 'f_wage_monthly',
            'profile_disability', 'profile_strengths', 'profile_weaknesses',
            'profile_training', 'profile_job'
        ]
        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]
        
        st.session_state.ai_response = None
        st.session_state.filtered_df = None
        st.session_state.interview_advice = {}
        st.rerun()

# === 🌟 画面を「マッチング」と「ダッシュボード」に分割 ===
tab_match, tab_stat = st.tabs(["🎯 AIマッチング＆面接対策", "📊 求人データ・統計ダッシュボード"])

with tab_stat:
    st.header("📊 現在の求人データベース統計")
    st.write("チーム内での市場トレンド共有や、開拓方針の検討にご活用ください。")
    df_all = load_data_from_db()
    if df_all.empty:
        st.warning("現在、データベースに求人が登録されていません。左の「管理者メニュー」からCSVを同期してください。")
    else:
        col_s1, col_s2, col_s3 = st.columns(3)
        col_s1.metric("📦 総求人登録数", f"{len(df_all)} 件")
        if '賃金' in df_all.columns:
            wage_s = df_all['賃金'].astype(str).str.replace(',', '', regex=False).str.extract(r'(\d+)').astype(float)[0]
            hourly_wages = wage_s[(wage_s >= 800) & (wage_s < 10000)].dropna()
            monthly_wages = wage_s[wage_s >= 100000].dropna()
            if not hourly_wages.empty:
                col_s2.metric("💰 平均時給 (目安)", f"{int(hourly_wages.mean()):,} 円")
            if not monthly_wages.empty:
                col_s3.metric("💴 平均月給 (目安)", f"{int(monthly_wages.mean()):,} 円")
        st.markdown("---")
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            if '雇用形態' in df_all.columns:
                st.subheader("👤 雇用形態別の求人数")
                st.bar_chart(df_all['雇用形態'].value_counts())
        with col_g2:
            if '就業場所' in df_all.columns:
                st.subheader("📍 主要な勤務エリア (上位10件)")
                st.bar_chart(df_all['就業場所'].value_counts().head(10))

with tab_match:
    st.markdown("### 👤 利用者プロファイルの入力")
    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1:
            disability = st.text_input("📝 障がい特性・診断名", placeholder="例：ASD（自閉スペクトラム症）、うつ病", key="profile_disability")
            strengths = st.text_area("✨ 得意なこと・強み", placeholder="例：単純作業の反復、正確なデータ入力、指示を忠実に守る", height=120, key="profile_strengths")
            weaknesses = st.text_area("⚠️ 苦手・配慮事項", placeholder="例：急な予定変更への対応、騒がしい場所での集中", height=120, key="profile_weaknesses")
        with col2:
            current_training = st.text_area("🏫 現在の訓練内容", placeholder="例：Excelの基本操作、軽作業（ピッキング）", height=120, key="profile_training")
            desired_job = st.text_area("🎯 希望する働き方", placeholder="例：一般事務、商品管理、週4日勤務希望", height=120, key="profile_job")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### 🚀 AI分析の実行")
    col_mode, col_btn = st.columns([2, 1])
    with col_mode:
        mode = st.radio("分析モードを選択：", ["① 最新求人マッチング（条件重視）", "② 適職診断・アドバイス（傾向・訓練プラン重視）"], horizontal=True)
    with col_btn:
        st.write("準備ができたらクリック↓")
        run_button = st.button("✨ AIに分析を依頼する", type="primary", use_container_width=True)

    if run_button:
        if not disability:
            st.error("「障がい特性・診断名」は必須入力項目です。")
        else:
            with st.spinner("AIがデータベースを解析し、最適なプランを構成中..."):
                df = load_data_from_db()
                if df.empty:
                    st.error("⚠️ データベースに求人がありません。左のメニューからCSVを同期してください。")
                    st.stop()
                
                df_f = df.copy()
                if f_location: df_f = df_f[df_f['就業場所'].fillna('').str.contains(f_location)]
                if f_type: df_f = df_f[df_f['雇用形態'].isin(f_type)]
                if f_wage_hourly > 0 or f_wage_monthly > 0:
                    df_f['w_num'] = df_f['賃金'].astype(str).str.replace(',', '').str.extract(r'(\d+)').astype(float)
                    if f_wage_hourly > 0: df_f = df_f[(df_f['w_num'] >= f_wage_hourly) & (df_f['w_num'] <= 5000)]
                    else: df_f = df_f[df_f['w_num'] >= f_wage_monthly]

                if df_f.empty:
                    st.warning("⚠️ 条件に合う求人が見つかりませんでした。絞り込み条件を緩めてみてください。")
                    st.stop()
                
                st.session_state.filtered_df = df_f
                
                try:
                    if "①" in mode:
                        prompt = f"""あなたは就労移行支援事業所のベテラン支援員です。
【利用者情報】特性:{disability}, 強み:{strengths}, 弱み:{weaknesses}, 訓練:{current_training}, 希望:{desired_job}
【指示】
1. まず冒頭で、利用者の特性と強みを表現するポジティブな【あなたのタイプ】（例：「集中力抜群のコツコツ職人タイプ」など）を示してください。
2. 提供データから最もマッチする求人を5件厳選してください。
3. 各求人について、【AIマッチング度（例：85%）】の数値を算出して記載し、強みの活かし方と配慮事項を解説してください。
4. 最後に具体的な支援アドバイスを添えてください。
※重要：求人を提案する際は、データにある【事業所名】と【職種】を一言一句そのまま正確に記載してください（省略や言い換えは厳禁）。
【データ】\n{df_f.head(50).to_csv(index=False)}"""
                    else:
                        prompt = f"""あなたは就労移行支援のプロフェッショナルなキャリアコンサルタントです。
【利用者情報】特性:{disability}, 強み:{strengths}, 弱み:{weaknesses}, 訓練:{current_training}, 希望:{desired_job}
【指示】
1. まず冒頭で、利用者の特性と強みを表現するポジティブな【あなたのタイプ（キャッチコピー）】（例：「集中力抜群のコツコツ職人タイプ」など）を提示してください。
2. 特性と強みから適職を論理的に診断してください。
3. 根拠として実在の求人を3件厳選し、各求人に【AIマッチング度（例：85%）】の数値を算出して添えながら解説してください。
4. 適職に就くため、明日から事業所で追加・重点化すべき訓練アクションプランを提案してください。
※重要：求人を提案する際は、データにある【事業所名】と【職種】を一言一句そのまま正確に記載してください（省略や言い換えは厳禁）。
【データ】\n{df_f.head(50).to_csv(index=False)}"""

                    # ★ 変更点3：client経由でモデルを指定して実行する形に変更（メインの分析）
                    res = client.models.generate_content(
                        model=TARGET_MODEL,
                        contents=prompt
                    )
                    st.session_state.ai_response = res.text
                    st.session_state.interview_advice = {}
                    
                    st.toast("✨ 分析が完了しました！", icon="🎉")
                except Exception as e:
                    st.error(f"分析中にエラーが発生しました: {e}")

    # --- 結果表示エリア ---
    if st.session_state.ai_response:
        st.markdown("---")
        st.header("💡 AIからの提案・分析結果")
        st.markdown(f'<div class="result-card">{st.session_state.ai_response}</div>', unsafe_allow_html=True)
        
        report_html = f"""
        <html><head><meta charset="UTF-8"><title>AI就労支援 提案レポート</title>
        <style>
            body {{ font-family: 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 30px; }}
            h1 {{ color: #1e3a5f; border-bottom: 2px solid #1e3a5f; padding-bottom: 10px; font-size: 24px; }}
            h2 {{ color: #2e7d32; margin-top: 30px; font-size: 20px; }}
            .box {{ background: #f4f6f9; padding: 15px; border-radius: 8px; margin-bottom: 20px; font-size: 14px; }}
            pre {{ white-space: pre-wrap; font-family: inherit; font-size: 15px; background: #fff; padding: 10px; border: 1px solid #eee; }}
            .print-btn {{ display: block; width: 200px; margin: 20px auto; padding: 10px; text-align: center; background: #1e3a5f; color: #fff; text-decoration: none; border-radius: 5px; cursor: pointer; }}
            @media print {{ .no-print {{ display: none !important; }} }}
        </style></head>
        <body>
            <button class="no-print print-btn" onclick="window.print()">🖨️ PDFとして保存 / 印刷</button>
            <h1>就労支援 AI分析レポート</h1>
            <p style="text-align:right;">作成日: {datetime.now().strftime('%Y年%m月%d日')}</p>
            <div class="box">
                <b>【利用者プロファイル】</b><br>
                ▪️ 診断名・特性: {disability}<br>
                ▪️ 得意なこと・強み: {strengths}<br>
                ▪️ 苦手・配慮事項: {weaknesses}<br>
                ▪️ 本人の希望: {desired_job}
            </div>
            <h2>AIからの分析・提案内容</h2>
            <pre>{st.session_state.ai_response}</pre>
        </body></html>
        """
        
        col_dl, col_copy = st.columns(2)
        with col_dl:
            st.download_button(
                label="📄 提案書をダウンロード (PDF保存・印刷用)", 
                data=report_html, 
                file_name=f"AI提案レポート_{datetime.now().strftime('%Y%m%d')}.html", 
                mime="text/html",
                use_container_width=True
            )
        with col_copy:
            with st.expander("📋 支援記録システムへのコピペ用"):
                st.text_area("Ctrl+Aで全選択", st.session_state.ai_response, height=100, label_visibility="collapsed")

        st.markdown("---")
        st.header("🏢 関連求人の詳細と面接対策")
        
        df_f = st.session_state.filtered_df
        ai_text = st.session_state.ai_response
        context_df = df_f.head(50) 
        
        matched_indices = []
        for idx, row in context_df.iterrows():
            company = str(row.get('事業所名', '')).strip()
            job_num = str(row.get('求人番号', '')).strip()
            
            if (company != 'nan' and company != '' and company in ai_text) or \
               (job_num != 'nan' and job_num != '' and job_num in ai_text):
                matched_indices.append(idx)
        
        if matched_indices:
            matched_df = context_df.loc[matched_indices]
        else:
            matched_df = context_df.head(5)

        job_options = matched_df['事業所名'].fillna('非公開').astype(str) + " / " + matched_df['職種'].fillna('不明').astype(str)
        
        st.info("💡 **ヒント:** 下のドロップダウンの候補が多い場合、枠内をクリックしてキーボードで直接企業名を入力すると、リスト内を文字検索できます。")
        selected_job = st.selectbox("詳しく調べたい求人を選択してください：", ["選択してください..."] + job_options.tolist())

        if selected_job != "選択してください...":
            detail = matched_df[job_options == selected_job].iloc[0]
            
            st.markdown(f'<div class="job-detail-box">', unsafe_allow_html=True)
            st.markdown(f"#### 📂 {selected_job}")
            col_a, col_b = st.columns(2)
            with col_a:
                st.write(f"**💰 賃金:** {detail.get('賃金', '-')}")
                st.write(f"**⏰ 就業時間:** {detail.get('就業時間', '-')}")
                st.write(f"**👤 雇用形態:** {detail.get('雇用形態', '-')}")
            with col_b:
                st.write(f"**🏢 就業場所:** {detail.get('就業場所', '-')}")
                st.write(f"**🗓️ 休日:** {detail.get('休日', '-')}")
                st.write(f"**🔢 求人番号:** {detail.get('求人番号', '-')}")
            st.info(f"**【募集要項：仕事の内容】**\n\n{detail.get('仕事の内容', '-')}")
            st.markdown('</div>', unsafe_allow_html=True)

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("📝 仕事内容を「3行」で要約", use_container_width=True):
                    with st.spinner("要約を作成中..."):
                        try:
                            sum_prompt = f"以下の仕事内容を、専門用語を避けて【簡潔な3行の箇条書き】に要約してください。\n\n{detail.get('仕事の内容', '-')}"
                            # ★ 変更点3：client経由で実行（要約）
                            summary_res = client.models.generate_content(
                                model=TARGET_MODEL,
                                contents=sum_prompt
                            )
                            st.success(f"**💡 AIによる3行要約：**\n\n{summary_res.text}")
                        except Exception as e:
                            st.error(f"要約エラー: {e}")

            with col_btn2:
                if st.button(f"🗣️ この求人の面接対策を生成", use_container_width=True):
                    with st.spinner("想定質問と回答例を構成中..."):
                        try:
                            q_prompt = f"""以下の求人と利用者の特性に基づき、面接で聞かれそうな質問3つと、利用者本人が答える際の具体的な回答例を、前向きな表現で作成してください。
【求人内容】{detail.get('仕事の内容')}
【利用者の苦手・配慮】{weaknesses}"""
                            # ★ 変更点3：client経由で実行（面接対策）
                            q_res = client.models.generate_content(
                                model=TARGET_MODEL,
                                contents=q_prompt
                            )
                            st.session_state.interview_advice[selected_job] = q_res.text
                        except Exception as e:
                            st.error(f"面接対策の生成に失敗しました: {e}")
            
            if selected_job in st.session_state.interview_advice:
                st.markdown("<br>", unsafe_allow_html=True)
                st.success("### ✨ AI模擬面接アドバイス")
                st.write(st.session_state.interview_advice[selected_job])