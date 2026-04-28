import streamlit as st
from streamlit_oauth import OAuth2Component
import requests
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

# --- 画面の設定 ---
st.set_page_config(page_title="AI就労支援プラットフォーム", page_icon="🤝", layout="centered")

# --- カスタムCSS ---
st.markdown("""
<style>
/* 既存のカードデザインなど */
.stApp { background-color: #F8F9FA; }
.portal-card {
    background-color: #ffffff; padding: 25px; border-radius: 12px;
    box-shadow: 0 4px 15px rgba(0,0,0,0.05); margin-bottom: 20px;
    border-top: 5px solid #2A9D8F;
}
.portal-card-user { border-top: 5px solid #E9C46A; }
.portal-card-diag { border-top: 5px solid #ffb3ba; }
.portal-card-plan { border-top: 5px solid #4A90E2; }
.portal-card-chart { border-top: 5px solid #8B5CF6; } 
.portal-card-avatar { border-top: 5px solid #FF9F1C; } 
.portal-card-rp { border-top: 5px solid #E63946; } 
.portal-card-quiz { border-top: 5px solid #10B981; }
.login-box {
    background-color: #ffffff; padding: 40px; border-radius: 15px;
    box-shadow: 0 4px 15px rgba(0,0,0,0.1); text-align: center; margin-top: 50px;
}

/* 👇 ここから追加：サイドバー（ページメニュー）を見やすくする魔法 */
[data-testid="stSidebarNav"] span {
    font-size: 1.15rem !important; /* メニューの文字を大きく */
    font-weight: bold !important;  /* メニューの文字を太く */
}

[data-testid="stSidebarNav"] ul li a {
    padding-top: 0.7rem !important;  /* メニュー同士の上下の隙間を広げて押しやすく */
    padding-bottom: 0.7rem !important;
}
/* 👆 ここまで */
</style>
""", unsafe_allow_html=True)

# ==========================================
# 1. Firebaseの準備（初期化）
# ==========================================
if not firebase_admin._apps:
    key_dict = dict(st.secrets["firebase_rimpota"])
    cred = credentials.Certificate(key_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# ==========================================
# 2. Googleログインの準備
# ==========================================
CLIENT_ID = st.secrets["google_auth"]["client_id"]
CLIENT_SECRET = st.secrets["google_auth"]["client_secret"]
REDIRECT_URI = "http://localhost:8501"

oauth2 = OAuth2Component(
    CLIENT_ID, CLIENT_SECRET, 
    "https://accounts.google.com/o/oauth2/v2/auth", 
    "https://oauth2.googleapis.com/token", 
    "https://oauth2.googleapis.com/token", 
    "https://revoke.googleapis.com/revoke"
)

# ==========================================
# 3. 🚪 扉の外（未ログイン時の画面）
# ==========================================
if "user_email" not in st.session_state:
    st.markdown('<div class="login-box">', unsafe_allow_html=True)
    st.title("🔐 AI就労支援プラットフォーム")
    st.write("「りんぽた」に登録しているGoogleアカウントでログインしてください。")
    st.write("") # スペース
    
    result = oauth2.authorize_button(
        name="Googleでログインして入室",
        icon="https://www.google.com/favicon.ico",
        redirect_uri=REDIRECT_URI,
        scope="openid email profile",
        key="google_login",
        use_container_width=True
    )
    st.markdown('</div>', unsafe_allow_html=True)
    
    if result:
        token = result["token"]
        headers = {"Authorization": f"Bearer {token['access_token']}"}
        user_info = requests.get("https://www.googleapis.com/oauth2/v3/userinfo", headers=headers).json()
        login_email = user_info["email"]
        
        # 名簿チェック
        doc_ref = db.collection("allow_users").document(login_email)
        doc = doc_ref.get()
        
        if doc.exists:
            st.session_state["user_email"] = login_email
            st.rerun()
        else:
            st.error(f"🛑 アクセス拒否\n\n「{login_email}」は名簿に登録されていません。管理者に連絡して権限をもらってください。")

# ==========================================
# 4. 🏠 扉の中（ログイン成功時のメイン画面）
# ==========================================
else:
    # ヘッダー
    col_title, col_logout = st.columns([4, 1])
    with col_title:
        st.title("🤝 AI就労支援プラットフォーム")
        st.markdown("<p style='color:#7F8C8D; font-size:1.1rem;'>就労支援の現場をテクノロジーでサポートする、次世代の統合システムです。</p>", unsafe_allow_html=True)
    with col_logout:
        st.caption(f"👤 {st.session_state['user_email']}")
        if st.button("ログアウト", type="primary", use_container_width=True):
            del st.session_state["user_email"]
            st.rerun()

    st.markdown("---")
    st.markdown("### 👈 左のメニューからシステムを選択してください")

    # 上段：利用者さん向けのツール
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
        <div class="portal-card portal-card-diag">
            <h3>🌱 AIじぶん発見＆働き方ナビ<br>（利用者・面談用）</h3>
            <p>直感的な質問から強みを可視化し、AIが温かいアドバイスを作成します。</p>
            <ul><li>5つの強みをレーダーチャート化</li><li>苦手を才能に「ポジティブ変換」</li><li>自己PRと配慮事項の自動ドラフト</li></ul>
            <b style="color:#e6739f;">用途：自己理解の促進、面談での目標設定</b>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown("""
        <div class="portal-card portal-card-user">
            <h3>🗣️ AI模擬面接<br>（利用者トレーニング用）</h3>
            <p>AI面接官を相手に、音声やテキストで実践的な面接練習ができます。</p>
            <ul><li>完全対面（没入）モード対応</li><li>プロ視点のフィードバック</li><li>振り返りレポートと音声DL</li></ul>
            <b style="color:#E9C46A;">用途：本番前の練習、自己効力感の向上</b>
        </div>
        """, unsafe_allow_html=True)

    # 中段：支援員向けのツール①（事務作業・分析）
    col3, col4 = st.columns(2)

    with col3:
        st.markdown("""
        <div class="portal-card">
            <h3>🎯 求人マッチング<br>（支援員・スタッフ用）</h3>
            <p>ハローワーク等の最新求人データと、利用者さんの特性をAIが照合します。</p>
            <ul><li>条件と特性からの適職分析</li><li>求人票の「3行要約」</li><li>古い求人のメンテナンス</li></ul>
            <b style="color:#2A9D8F;">用途：面談時の提案、開拓方針の検討</b>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        st.markdown("""
        <div class="portal-card portal-card-plan">
            <h3>📝 AI支援計画書アシスタント<br>（支援員・スタッフ用）</h3>
            <p>日々の面談記録や訓練ログ(CSV)から、支援計画書の下書きをAIが作成します。</p>
            <ul><li>記録の要約と強み・課題の抽出</li><li>次期の「短期目標」案の自動提案</li><li>匿名化データの読み込みで安全に分析</li></ul>
            <b style="color:#4A90E2;">用途：支援計画書の作成補助、支援方針の検討</b>
        </div>
        """, unsafe_allow_html=True)

    # 下段：支援員向けのツール②（対人スキル・分析）
    col5, col6 = st.columns(2)
    
    with col5:
        st.markdown("""
        <div class="portal-card portal-card-chart">
            <h3>📊 AIセルフケアデータ分析<br>（支援員・スタッフ用）</h3>
            <p>日々のセルフケア記録を直感的なグラフで可視化し、AIが調子の波を分析します。</p>
            <ul><li>インタラクティブな折れ線グラフ表示</li><li>AIによる強みや心配なサインの考察</li><li>次回の面談でかけるべき言葉の提案</li></ul>
            <b style="color:#8B5CF6;">用途：面談前の状況把握、声かけのヒント</b>
        </div>
        """, unsafe_allow_html=True)

    with col6:
        st.markdown("""
        <div class="portal-card portal-card-rp">
            <h3>🎓 支援員ロールプレイング<br>（支援員トレーニング用）</h3>
            <p>対人トラブルやメンタル不調など、難しいケースの対応をAIアバターと実践練習します。</p>
            <ul><li>現場の事例をDBに蓄積し共有可能</li><li>傷つかずに何度でも失敗できる安全な環境</li><li>AIスーパーバイザーからの客観的評価</li></ul>
            <b style="color:#E63946;">用途：若手の教育、対応力向上、メンタル保護</b>
        </div>
        """, unsafe_allow_html=True)
        
    # 最下段：サポート＆学習ツール
    col7, col8 = st.columns(2)
    
    with col7:
        st.markdown("""
        <div class="portal-card portal-card-avatar">
            <h3>🧑‍💼 AIアバター相談室<br>（利用者・職員サポート用）</h3>
            <p>3DアバターのAI支援員と音声で自然な会話ができ、日々の悩みやPC操作等の疑問に優しく答えます。</p>
            <ul><li>音声認識によるリアルタイム対話</li><li>アバターの表情と動きの同期</li><li>業務の相談やアイドリング時の癒やし</li></ul>
            <b style="color:#FF9F1C;">用途：対人コミュニケーション練習、日々の疑問解消</b>
        </div>
        """, unsafe_allow_html=True)

    with col8:
        st.markdown("""
        <div class="portal-card portal-card-quiz">
            <h3>🧩 職員向け AIナレッジクイズ<br>（支援員トレーニング用）</h3>
            <p>AIがその場で生成する実践的な問題で、支援員としての対応力や記録スキルをゲーム感覚で鍛えます。</p>
            <ul><li>記述式で対応力を磨く「AI添削道場」</li><li>ツッコミどころを探す「ダメな記録間違い探し」</li><li>AIスーパーバイザーからの的確なフィードバック</li></ul>
            <b style="color:#10B981;">用途：支援スキルの自己研鑽、記録業務の品質向上</b>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.info("💡 **セキュリティについて**：本システムはローカル環境で動作し、入力された特性や録音された音声データはサーバー上に永久保存されません。また、計画書作成ツールでは、事前に個人情報を削除（匿名化）したファイルのみをアップロードしていただく運用ルールを徹底することで、安全性を担保しています。")