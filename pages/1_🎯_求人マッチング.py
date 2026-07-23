import streamlit as st
import pandas as pd
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
    client = genai.Client(api_key=api_key)
except Exception:
    st.error("⚠️ `.streamlit/secrets.toml` に APIキーを設定してください。")
    st.stop()

TARGET_MODEL = "gemini-3.1-flash-lite"

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
# ★ 検索結果保存用のセッションを追加
if 'search_result_df' not in st.session_state: st.session_state.search_result_df = None

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
        # ★ リセット対象に検索用の状態も追加
        keys_to_clear = [
            'ai_response', 'filtered_df', 'interview_advice', 'search_result_df',
            'f_location', 'f_type', 'f_wage_hourly', 'f_wage_monthly',
            'profile_disability', 'profile_strengths', 'profile_weaknesses',
            'profile_training', 'profile_job', 'search_query_input'
        ]
        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]
        
        st.session_state.ai_response = None
        st.session_state.filtered_df = None
        st.session_state.interview_advice = {}
        st.session_state.search_result_df = None
        st.rerun()

# === 🌟 画面を3つのタブに分割 ===
# ★ 第3のタブ「登録データ内検索」を追加
tab_match, tab_stat, tab_search = st.tabs(["🎯 AIマッチング＆面接対策", "📊 求人データ・統計ダッシュボード", "🔍 登録データ内検索"])

# ==========================================
# 🔍 タブ3：登録データ内検索機能（ハイブリッド＆期間選択版）
# ==========================================
with tab_search:
    st.header("🔍 AIアシスト付き データベース内検索")
    st.write("「奈良市内の求人」「未経験でできる事務」のような話し言葉でも、AIがキーワードを抽出して正確にデータベースを検索します。")
    st.info("※求人データ自体はデータベースから直接取得するため、架空の求人が作られることはありません。")

    # ★ 追加：検索対象の期間を選択するラジオボタン
    search_period = st.radio("📅 検索対象の期間を選択：", ["すべてのデータから検索", "直近1ヶ月以内のデータから検索"], horizontal=True)

    col_s_input, col_s_btn = st.columns([3, 1])
    with col_s_input:
        search_query = st.text_input("検索キーワードや希望を入力（例：奈良市内の清掃、未経験OKの事務 など）", key="search_query_input")
    with col_s_btn:
        st.write(" ") # 高さ合わせ
        search_btn = st.button("🔍 検索を実行", use_container_width=True)

    if search_btn:
        df_all = load_data_from_db()
        
        # ★ 追加：期間での事前絞り込み処理
        if not df_all.empty and "1ヶ月以内" in search_period:
            if '受付年月日' in df_all.columns:
                df_all['date_calc'] = pd.to_datetime(df_all['受付年月日'], errors='coerce')
                one_month_ago = pd.Timestamp.now() - pd.Timedelta(days=30)
                # 直近30日以内のデータだけを残す
                df_all = df_all[df_all['date_calc'] >= one_month_ago]

        if df_all.empty:
            st.error("⚠️ データベースに求人が登録されていないか、「直近1ヶ月以内」の条件に該当する求人が0件です。")
            st.session_state.search_result_df = None
        elif not search_query.strip():
            st.warning("⚠️ 検索キーワードを入力してください。")
        else:
            # 🌟 STEP1: AIに「キーワード」だけを抽出させる
            with st.spinner("AIが検索条件を翻訳中..."):
                try:
                    kw_prompt = f"""以下のユーザーの入力から、求人検索に必要な「名詞（キーワード）」だけを抽出して、スペース区切りで出力してください。
                    ルール：
                    ・「の」「求人」「探して」「できる」などの不要な言葉は排除する。
                    ・例：「奈良市内の求人」→「奈良市」
                    ・例：「未経験でできる事務」→「未経験 事務」
                    
                    【入力】{search_query}
                    【出力】"""
                    
                    kw_res = client.models.generate_content(
                        model=TARGET_MODEL,
                        contents=kw_prompt
                    )
                    # AIが出した答えをスペースで分割してリストにする
                    extracted_keywords = kw_res.text.strip().split()
                except Exception as e:
                    # 万が一AIがエラーを出した場合は、入力された文字をそのまま使う
                    extracted_keywords = search_query.split()

            st.success(f"🤖 AI翻訳キーワード: **{', '.join(extracted_keywords)}**")

            # 🌟 STEP2: 抽出したキーワードでデータベースを直接検索（AND検索）
            with st.spinner("データベースを直接検索中..."):
                # 最初は全データが対象（True）
                mask = pd.Series([True] * len(df_all), index=df_all.index)
                
                # キーワードが複数ある場合、すべてを含むもの（AND検索）に絞り込む
                for kw in extracted_keywords:
                    # いずれかの列（行のどこか）にキーワードが含まれているかチェック
                    kw_mask = df_all.astype(str).apply(lambda x: x.str.contains(kw, case=False, na=False)).any(axis=1)
                    mask = mask & kw_mask # 条件を掛け合わせる
                
                res_df = df_all[mask]
                
                if res_df.empty:
                    st.session_state.search_result_df = None
                    st.warning("条件に完全に一致する求人は見つかりませんでした。条件を少し減らして再検索してみてください。")
                else:
                    st.session_state.search_result_df = res_df
                    st.info(f"✨ {len(res_df)} 件の求人がヒットしました！")

    # --- 検索結果の表示エリア ---
    if st.session_state.search_result_df is not None:
        res_df = st.session_state.search_result_df
        
        st.markdown("### 📋 検索結果一覧")
        # 必要な項目だけ絞って一覧表示
        display_columns = ['事業所名', '職種', '就業場所', '雇用形態']
        available_columns = [col for col in display_columns if col in res_df.columns]
        st.dataframe(res_df[available_columns].fillna('未登録'), use_container_width=True)

        st.markdown("---")
        st.markdown("### 🏢 求人の詳細確認")
        st.write("一覧から気になる求人を選択すると、元のデータベースに登録されている詳細情報をそのまま表示します。")
        
        search_job_options = res_df['事業所名'].fillna('非公開').astype(str) + " / " + res_df['職種'].fillna('不明').astype(str)
        selected_search_job = st.selectbox("詳しく調べたい求人を選択：", ["選択してください..."] + search_job_options.tolist(), key="select_search_detail")
        
        if selected_search_job != "選択してください...":
            detail = res_df[search_job_options == selected_search_job].iloc[0]
            
            st.markdown(f'<div class="job-detail-box">', unsafe_allow_html=True)
            st.markdown(f"#### 📂 {selected_search_job}")
            col_a, col_b = st.columns(2)
            with col_a:
                st.write(f"**💰 賃金:** {detail.get('賃金', '-')}")
                st.write(f"**⏰ 就業時間:** {detail.get('就業時間', '-')}")
                st.write(f"**👤 雇用形態:** {detail.get('雇用形態', '-')}")
            with col_b:
                st.write(f"**🏢 就業場所:** {detail.get('就業場所', '-')}")
                st.write(f"**🗓️ 休日:** {detail.get('休日', '-')}")
                st.write(f"**🔢 求人番号:** {detail.get('求人番号', '-')}")
                st.write(f"**📅 受付年月日:** {detail.get('受付年月日', '-')}")
            st.info(f"**【募集要項：仕事の内容】**\n\n{detail.get('仕事の内容', '-')}")
            st.markdown('</div>', unsafe_allow_html=True)

with tab_stat:
    st.header("📊 現在の求人データベース統計＆AI分析")
    st.write("チーム内での市場トレンド共有や、開拓方針の検討にご活用ください。")
    
    df_all = load_data_from_db()
    
    if df_all.empty:
        st.warning("現在、データベースに求人が登録されていません。左の「管理者メニュー」からCSVを同期してください。")
    else:
        # ▼▼▼ 追加箇所: 地域を選択するリスト ▼▼▼
        stat_region = st.selectbox("📍 統計データを集計する地域：", ["すべてのデータ", "大阪", "京都", "奈良", "それ以外"])
        # ▲▲▲ 追加箇所ここまで ▲▲▲
        
        stat_period = st.radio("📅 統計データを集計する期間：", ["すべてのデータ", "直近1ヶ月以内のデータ"], horizontal=True)
        
        df_stat = df_all.copy()

        # ▼▼▼ 追加箇所: 選択された地域ごとのデータ絞り込み処理 ▼▼▼
        if '就業場所' in df_stat.columns:
            if stat_region == "大阪":
                df_stat = df_stat[df_stat['就業場所'].fillna('').str.contains('大阪')]
            elif stat_region == "京都":
                df_stat = df_stat[df_stat['就業場所'].fillna('').str.contains('京都')]
            elif stat_region == "奈良":
                df_stat = df_stat[df_stat['就業場所'].fillna('').str.contains('奈良')]
            elif stat_region == "それ以外":
                df_stat = df_stat[~df_stat['就業場所'].fillna('').str.contains('大阪|京都|奈良')]
        # ▲▲▲ 追加箇所ここまで ▲▲▲

        if "1ヶ月以内" in stat_period and '受付年月日' in df_stat.columns:
            df_stat['date_calc'] = pd.to_datetime(df_stat['受付年月日'], errors='coerce')
            one_month_ago = pd.Timestamp.now() - pd.Timedelta(days=30)
            df_stat = df_stat[df_stat['date_calc'] >= one_month_ago]
            
        if df_stat.empty:
            st.info("指定された期間・地域の求人データがありません。")
        else:
            # --- 1. 基本指標（KPI）---
            col_s1, col_s2, col_s3 = st.columns(3)
            col_s1.metric("📦 総求人数", f"{len(df_stat)} 件")
            
            if '賃金' in df_stat.columns:
                wage_s = df_stat['賃金'].astype(str).str.replace(',', '', regex=False).str.extract(r'(\d+)').astype(float)[0]
                hourly_wages = wage_s[(wage_s >= 800) & (wage_s < 10000)].dropna()
                monthly_wages = wage_s[wage_s >= 100000].dropna()
                
                if not hourly_wages.empty:
                    col_s2.metric("💰 平均時給 (目安)", f"{int(hourly_wages.mean()):,} 円")
                    col_s2.caption(f"🔻最低: {int(hourly_wages.min()):,} 円 / 🔺最高: {int(hourly_wages.max()):,} 円")
                if not monthly_wages.empty:
                    col_s3.metric("💴 平均月給 (目安)", f"{int(monthly_wages.mean()):,} 円")
                    col_s3.caption(f"🔻最低: {int(monthly_wages.min()):,} 円 / 🔺最高: {int(monthly_wages.max()):,} 円")
            
            st.markdown("---")
            
            # --- 2. グラフ群 ---
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                target_col = '職種' if '職種' in df_stat.columns else '産業' if '産業' in df_stat.columns else None
                if target_col:
                    st.subheader(f"💼 {target_col}別の求人数 (上位10件)")
                    st.bar_chart(df_stat[target_col].value_counts().head(10))
            with col_g2:
                if '就業場所' in df_stat.columns:
                    st.subheader("📍 勤務地エリア (上位10件)")
                    st.bar_chart(df_stat['就業場所'].value_counts().head(10))
            
            if '雇用形態' in df_stat.columns:
                st.subheader("👤 雇用形態の割合")
                st.bar_chart(df_stat['雇用形態'].value_counts())

            st.markdown("---")
            
            # ==========================================
            # 🤖 新機能：ダッシュボードAI分析（参謀機能）
            # ==========================================
            st.header("🤖 AI データ分析＆戦略アドバイザー")
            st.write("上記の集計データをもとに、AIが支援現場に役立つインサイト（洞察）を生成します。")

            # AIへ渡すための「集計データのテキスト化」
            summary_lines = [f"■ 検索対象期間: {stat_period}", f"■ 総求人数: {len(df_stat)}件"]
            if not hourly_wages.empty: summary_lines.append(f"■ 時給: 平均{int(hourly_wages.mean())}円 (最低{int(hourly_wages.min())}〜最高{int(hourly_wages.max())}円)")
            if not monthly_wages.empty: summary_lines.append(f"■ 月給: 平均{int(monthly_wages.mean())}円 (最低{int(monthly_wages.min())}〜最高{int(monthly_wages.max())}円)")
            if target_col: summary_lines.append(f"■ 上位職種(件数): {df_stat[target_col].value_counts().head(5).to_dict()}")
            if '就業場所' in df_stat.columns: summary_lines.append(f"■ 上位エリア(件数): {df_stat['就業場所'].value_counts().head(5).to_dict()}")
            if '雇用形態' in df_stat.columns: summary_lines.append(f"■ 雇用形態(件数): {df_stat['雇用形態'].value_counts().to_dict()}")
            stats_summary_text = "\n".join(summary_lines)

            # セッションに結果を保持
            if 'ai_trend_report' not in st.session_state: st.session_state.ai_trend_report = None
            if 'ai_sales_strategy' not in st.session_state: st.session_state.ai_sales_strategy = None

            tab_trend, tab_sales = st.tabs(["📝 ①市場トレンド＆チャンス分析", "💼 ②企業開拓（営業）ターゲティング支援"])

            with tab_trend:
                st.markdown("#### 今月の市場トレンドと異常値（チャンス）の発見")
                st.write("現在のデータから、支援員が朝礼で共有すべきトレンドや、見落としがちな狙い目求人をAIが抽出します。")
                if st.button("✨ トレンド＆チャンス分析を実行", use_container_width=True):
                    with st.spinner("AIが統計データを分析中..."):
                        try:
                            trend_prompt = f"""あなたは就労移行支援のプロフェッショナルなマーケター兼データアナリストです。
                            以下の「現在の求人データベースの統計情報」をもとに、以下の2つのセクションで構成されたレポートを作成してください。

                            1. 【市場トレンドと今後の訓練方針】
                            データから読み取れる職種、賃金、エリアなどの傾向を分析し、支援員が朝礼で共有できるような解説をしてください。「〇〇の求人が多いため、今は〇〇の訓練を重点的に行うとマッチングしやすい」といった具体的なアドバイスを必ず入れてください。
                            
                            2. 【異常値（チャンス）の発見アラート】
                            データの中で「ニッチだが狙い目になりそうな部分」や「特異な点」を1〜2つ見つけ出し、支援員が見落としがちなチャンスとして指摘してください。

                            【統計データ】\n{stats_summary_text}"""
                            
                            res_trend = client.models.generate_content(model=TARGET_MODEL, contents=trend_prompt)
                            st.session_state.ai_trend_report = res_trend.text
                        except Exception as e:
                            st.error(f"分析エラー: {e}")
                
                if st.session_state.ai_trend_report:
                    st.success("💡 分析完了！")
                    st.markdown(f'<div class="result-card">{st.session_state.ai_trend_report}</div>', unsafe_allow_html=True)

            with tab_sales:
                st.markdown("#### 今いる利用者の特性に合わせた企業開拓戦略")
                st.write("事業所にいる利用者の大まかな特性を入力すると、AIがデータと照らし合わせて具体的な開拓・営業ルートを提案します。")
                user_chars = st.text_area("事業所の利用者の傾向（例：PC入力が得意な人が多い、静かな環境を好む人が3名いる、など）", height=100)
                
                if st.button("🚀 開拓戦略を生成", use_container_width=True):
                    if not user_chars.strip():
                        st.warning("利用者の傾向を入力してください。")
                    else:
                        with st.spinner("AIが営業戦略を立案中..."):
                            try:
                                sales_prompt = f"""あなたは就労移行支援事業所の敏腕営業戦略アドバイザーです。
                                以下の「現在の求人データベース統計」と、支援員が入力した「現在の事業所の利用者特性」を比較分析してください。
                                
                                データ上で不足している（＝自ら開拓すべき）領域や、逆にデータ上で需要が高い（＝アプローチしやすい）領域を推測し、具体的に「どのような企業」に、「どのような提案（例：業務の切り出し、実習の受け入れ等）」を持って営業・開拓を行うべきか、戦略を3つ提案してください。

                                【現在の事業所の利用者特性】: {user_chars}
                                【現在の統計データ】\n{stats_summary_text}"""
                                
                                res_sales = client.models.generate_content(model=TARGET_MODEL, contents=sales_prompt)
                                st.session_state.ai_sales_strategy = res_sales.text
                            except Exception as e:
                                st.error(f"戦略生成エラー: {e}")

                if st.session_state.ai_sales_strategy:
                    st.success("💡 戦略立案完了！")
                    st.markdown(f'<div class="result-card">{st.session_state.ai_sales_strategy}</div>', unsafe_allow_html=True)

with tab_match:
    st.markdown("### 👤 利用者プロファイルの入力")
    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1:
            disability = st.text_input("📝 障がい特性・診断名", placeholder="例：ASD（自閉スペクトラム症）、うつ病", key="profile_disability")
            strengths = st.text_area("✨ 得意なこと・強み", placeholder="例：単純作業の反復、正確なデータ入力、指示を忠実に守る", height=120, key="profile_strengths")
            weaknesses = st.text_area("⚠️ 苦手・配慮事項", placeholder="例：急な予定変更への対応、騒がしい場所での集中", height=120, key="profile_weaknesses")
        with col2:
            # ▼▼▼ 新たに追加 ▼▼▼
            home_address = st.text_input("🏠 自宅住所・最寄り駅", placeholder="例：奈良県生駒市、または 〇〇駅", key="profile_home")
            # ▲▲▲ 新たに追加 ▲▲▲
            current_training = st.text_area("🏫 現在の訓練内容", placeholder="例：Excelの基本操作、軽作業（ピッキング）", height=75, key="profile_training")
            desired_job = st.text_area("🎯 希望する働き方", placeholder="例：一般事務、商品管理、週4日勤務希望", height=75, key="profile_job")

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
                    # ★ 追加：受付年月日を日付データとして認識させる
                    if '受付年月日' in df_f.columns:
                        df_f['date_calc'] = pd.to_datetime(df_f['受付年月日'], errors='coerce')

                    if "①" in mode:
                        # 【モード①：最新求人マッチング】
                        if 'date_calc' in df_f.columns:
                            df_mode1 = df_f.sort_values(by='date_calc', ascending=False)
                            one_month_ago = pd.Timestamp.now() - pd.Timedelta(days=30)
                            df_mode1 = df_mode1[df_mode1['date_calc'] >= one_month_ago]
                            
                            if len(df_mode1) < 5:
                                df_mode1 = df_f.sort_values(by='date_calc', ascending=False)
                        else:
                            df_mode1 = df_f
                            
                        data_to_pass = df_mode1.drop(columns=['date_calc'], errors='ignore').head(50)
                        
                        prompt = f"""あなたは就労移行支援事業所のベテラン支援員です。
【利用者情報】特性:{disability}, 強み:{strengths}, 弱み:{weaknesses}, 訓練:{current_training}, 希望:{desired_job}
【指示】
1. まず冒頭で、利用者の特性と強みを表現するポジティブな【あなたのタイプ】を示してください。
2. 提供データから最もマッチする求人を5件厳選してください。
3. 各求人について、【AIマッチング度】の数値を算出して記載し、強みの活かし方と配慮事項を解説してください。
4. 最後に具体的な支援アドバイスを添えてください。
※重要：確実なデータ照合のため、求人を提案する際はデータにある【求人番号】を必ず記載してください（例：「【求人番号: 12345】株式会社〇〇」）。
【データ】\n{data_to_pass.to_csv(index=False)}"""

                    else:
                        # 【モード②：適職診断・アドバイス】
                        df_mode2 = df_f.sample(n=min(50, len(df_f)))
                        data_to_pass = df_mode2.drop(columns=['date_calc'], errors='ignore')

                        prompt = f"""あなたは就労移行支援のプロフェッショナルなキャリアコンサルタントです。
【利用者情報】特性:{disability}, 強み:{strengths}, 弱み:{weaknesses}, 訓練:{current_training}, 希望:{desired_job}
【指示】
1. まず冒頭で、利用者の特性と強みを表現するポジティブな【あなたのタイプ】を提示してください。
2. 特性と強みから適職を論理的に診断してください。
3. 根拠として実在の求人を3件厳選し、各求人に【AIマッチング度】の数値を添えて解説してください。
4. 適職に就くため、明日から事業所で追加・重点化すべき訓練アクションプランを提案してください。
※重要：確実なデータ照合のため、求人を提案する際はデータにある【求人番号】を必ず記載してください（例：「【求人番号: 12345】株式会社〇〇」）。
【データ】\n{data_to_pass.to_csv(index=False)}"""

                    res = client.models.generate_content(
                        model=TARGET_MODEL,
                        contents=prompt
                    )
                    st.session_state.ai_response = res.text
                    st.session_state.interview_advice = {}
                    
                    # ★修正ポイント：AIが実際に見た50件のデータをセッションに保存し、リストで使う
                    st.session_state.context_df = data_to_pass 
                    
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
        
        # ★ 修正ポイント：AIが実際に判定したデータを呼び出す
        if 'context_df' in st.session_state:
            context_df = st.session_state.context_df
        else:
            context_df = st.session_state.filtered_df.head(50)
            
        ai_text = st.session_state.ai_response
        
        matched_indices = []
        for idx, row in context_df.iterrows():
            company = str(row.get('事業所名', '')).strip()
            job_num = str(row.get('求人番号', '')).strip()
            
            # ★ 修正ポイント：「求人番号」と「表記揺れを除いた企業名」で強力にマッチング
            match_job_num = (job_num != 'nan' and job_num != '' and job_num in ai_text)
            
            # 事業所名から「株式会社」などを抜いた核となる名前でも検索する（表記ブレ対策）
            core_company = company.replace('株式会社', '').replace('有限会社', '').replace('合同会社', '').replace('(株)', '').replace('（株）', '').strip()
            match_company = (core_company != '' and len(core_company) >= 2 and core_company in ai_text)
            
            if match_job_num or match_company:
                matched_indices.append(idx)
        
        if matched_indices:
            matched_df = context_df.loc[matched_indices]
        else:
            matched_df = context_df.head(5)



        # ----------------------------------------------------
        # 以降の job_options = ... などのコードはそのまま残します
        # ----------------------------------------------------

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
                st.write(f"**📅 受付年月日:** {detail.get('受付年月日', '-')}")
            st.info(f"**【募集要項：仕事の内容】**\n\n{detail.get('仕事の内容', '-')}")
            st.markdown('</div>', unsafe_allow_html=True)

           # 2列を3列に変更
            col_btn1, col_btn2, col_btn3 = st.columns(3)
            with col_btn1:
                if st.button("📝 仕事内容を「3行」で要約", use_container_width=True):
                    with st.spinner("要約を作成中..."):
                        try:
                            sum_prompt = f"以下の仕事内容を、専門用語を避けて【簡潔な3行の箇条書き】に要約してください。\n\n{detail.get('仕事の内容', '-')}"
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
                            q_res = client.models.generate_content(
                                model=TARGET_MODEL,
                                contents=q_prompt
                            )
                            st.session_state.interview_advice[selected_job] = q_res.text
                        except Exception as e:
                            st.error(f"面接対策の生成に失敗しました: {e}")
                            
          # ▼▼▼ 個別のルート案内ボタン（企業名検索・非公開対応版） ▼▼▼
            with col_btn3:
                job_location = str(detail.get('就業場所', '')).strip()
                company_name = str(detail.get('事業所名', '')).strip()
                
                # 'nan' や 'None' などの無効な文字列を弾く
                if job_location and job_location.lower() not in ('nan', 'none', '', '-', '未登録'):
                    import urllib.parse
                    
                    # 企業名が非公開かどうかを判定する
                    is_hidden = False
                    if company_name.lower() in ('nan', 'none', '', '-', '非公開', '未登録') or '公開していません' in company_name:
                        is_hidden = True
                    
                    # 目的地（検索キーワード）とボタンのテキストを決定
                    if is_hidden:
                        # 非公開の場合は住所（エリア）のみで検索
                        search_dest = job_location
                        btn_suffix = "『就業エリア周辺』までのルート(目安)"
                    else:
                        # 公開されている場合は「住所＋企業名」で精度の高いピンポイント検索
                        search_dest = f"{job_location} {company_name}"
                        btn_suffix = "企業までのルートを調べる"
                        
                    # URL用に変換
                    encoded_address = urllib.parse.quote(search_dest)
                    home_addr = st.session_state.get('profile_home', '').strip()
                    
                    if home_addr:
                        # 自宅が入力されていれば自宅起点
                        encoded_home = urllib.parse.quote(home_addr)
                        maps_url = f"https://www.google.com/maps/dir/?api=1&origin={encoded_home}&destination={encoded_address}&hl=ja"
                        btn_label = f"🚃 自宅から{btn_suffix}"
                    else:
                        # 未入力なら現在地起点
                        maps_url = f"https://www.google.com/maps/dir/?api=1&origin=My+Location&destination={encoded_address}&hl=ja"
                        btn_label = f"📍 現在地から{btn_suffix}"
                        
                    # ボタンの表示
                    st.link_button(btn_label, url=maps_url, use_container_width=True)
                    
                    # 非公開の場合のみ、ボタンの下に小さな注意書きを出す
                    if is_hidden:
                        st.caption("※企業名非公開のため、エリア中心部への大まかなルートです。")
                else:
                    st.button("🚃 就業場所データなし", disabled=True, use_container_width=True)
            # ▲▲▲ 個別のルート案内ボタン ここまで ▲▲▲
            
            if selected_job in st.session_state.interview_advice:
                st.markdown("<br>", unsafe_allow_html=True)
                st.success("### ✨ AI模擬面接アドバイス")
                st.write(st.session_state.interview_advice[selected_job])