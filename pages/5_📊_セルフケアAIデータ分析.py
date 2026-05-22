import streamlit as st
import firebase_admin
from firebase_admin import firestore
# ★ 変更点1：新しいパッケージのインポート
from google import genai
import pandas as pd
from datetime import datetime

# ==========================================
# 🚨 セキュリティバウンサー（未ログイン者を追い出す）
# ==========================================
if "user_email" not in st.session_state:
    st.warning("⚠️ ログインが必要です。左のメニューから「Home」に戻ってログインしてください。")
    st.stop()

# --- 画面の設定 ---
st.set_page_config(page_title="AIデータ分析", page_icon="📊")
st.title("📊 AI セルフケア分析＆考察レポート")

# ==========================================
# 1. 初期設定（Firebase & Gemini）
# ==========================================
db = firestore.client()

# ★ 変更点2：Client（通信係）を作成
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    client = genai.Client(api_key=api_key)
except Exception:
    st.error("⚠️ `.streamlit/secrets.toml` に APIキーを設定してください。")
    st.stop()

TARGET_MODEL = "gemini-3.1-flash-lite"

# ==========================================
# 2. 対象者の選択とデータ取得
# ==========================================
st.markdown("### 1. 分析する利用者を選択")

@st.cache_data(ttl=10) 
def get_user_names():
    names = set()
    
    # 1. りんぽたの「登録名簿（meter_config）」から名前を取得する
    try:
        config_ref = db.collection("meter_config").document("users").get()
        if config_ref.exists:
            config_names = config_ref.to_dict().get("names", [])
            for n in config_names:
                names.add(n)
    except Exception:
        pass 
        
    # 2. 過去の記録（self_meter_history）に残っている名前も念のため拾う
    docs = db.collection("self_meter_history").stream()
    for doc in docs:
        u_name = doc.to_dict().get("userName")
        if u_name:
            names.add(u_name)
            
    return sorted(list(names))

user_names = get_user_names()

if not user_names:
    st.info("データがありません。")
    st.stop()

# 🌟🌟🌟 さっき消えてしまっていた「魔法の1行」がコレです！ 🌟🌟🌟
selected_user = st.selectbox("利用者名", user_names)
# 選んだ人の直近のデータ（最大30件）を取得
if selected_user:
    docs = db.collection("self_meter_history").where("userName", "==", selected_user).order_by("createdAt", direction=firestore.Query.DESCENDING).limit(30).stream()
    
    raw_data_text = ""
    chart_data = [] # 📈 グラフ用のデータ箱
    
    for doc in docs:
        data = doc.to_dict()
        
        # 日付と絵文字の取得
        if "createdAt" not in data:
            continue
            
        dt = data["createdAt"]
        date_str = dt.strftime('%m/%d') # グラフが見やすいように月/日のみ
        full_date_str = dt.strftime('%Y/%m/%d')
        emoji = data.get("emoji", "なし")
        
        # グラフ用の1行データを作成
        row_data = {"日付": date_str, "_sort": dt}
        
        # 点数（results）の文字列化とグラフ用データの抽出
        results_str_list = []
        for r in data.get("results", []):
            item_name = r['name']
            item_val = int(r['val'])
            results_str_list.append(f"{item_name}: {item_val}点")
            row_data[item_name] = item_val # グラフ用に項目と点数をセット
            
        # AI送信用のテキストに追加
        results_str = ", ".join(results_str_list)
        raw_data_text += f"- {full_date_str} [{emoji}] {results_str}\n"
        
        # グラフ用リストに追加
        chart_data.append(row_data)

    # 📈 --- 折れ線グラフの描画 ---
    if chart_data:
        st.markdown("---")
        st.markdown(f"### 📈 {selected_user} さんのセルフケア推移（直近）")
        
        # データをPandasデータフレームに変換し、古い順に並び替え
        df = pd.DataFrame(chart_data)
        df = df.sort_values("_sort").drop(columns=["_sort"])
        
        # 💡 ここからプロ仕様の美しいグラフ（Plotly）を作成！
        import plotly.express as px
        
        # 折れ線グラフを作成（マーカー付き）
        fig = px.line(
            df, 
            x="日付", 
            y=[col for col in df.columns if col != "日付"], # 日付以外の項目をすべて縦軸に
            markers=True, # 値のところに丸いポッチ（マーカー）をつける
            labels={"value": "点数", "variable": "項目"}
        )
        
        # グラフの見た目を調整
        fig.update_layout(
            yaxis_range=[0, 105], # 縦軸を0〜105に固定（100点満点の場合。はみ出ないように少し余裕を持たせる）
            legend_title_text='記録項目',
            hovermode="x unified", # マウスを乗せると、その日の全項目の点数が縦一列でポップアップ表示される！
            margin=dict(l=20, r=20, t=30, b=20)
        )
        
        # 作成した美しいグラフを画面に表示
        st.plotly_chart(fig, use_container_width=True)

    # 🔍 --- 生データの確認 ---
    with st.expander("🔍 AIに送信される生データ（クリックで確認）"):
        st.text(raw_data_text)

# ==========================================
# 3. AIに分析させる
# ==========================================
st.markdown("### 2. AIによる分析の実行")

if st.button("✨ このデータから考察レポートを作成する", type="primary"):
    if not raw_data_text:
        st.error("分析するデータがありません。")
    else:
        with st.spinner("AIが過去の記録を読み解いています..."):
            # AIへの指示書（プロンプト）
            prompt = f"""
            あなたは就労移行支援事業所の優秀なベテラン支援員です。
            以下のデータは、ある利用者（{selected_user}さん）の直近のセルフケア記録です。
            このデータから、以下の3点を踏まえて支援員向けの「考察とフィードバックの提案」を作成してください。
            
            1. 全体的な調子の波（安定しているか、特定の項目が落ち込んでいるか）
            2. 注目すべき強み、または心配なサイン
            3. 次回の面談でかけるべき温かい言葉の提案（具体的に）
            
            【利用者データ】
            {raw_data_text}
            """
            
            try:
                # ★ 変更点3：client経由で実行するように変更
                response = client.models.generate_content(
                    model=TARGET_MODEL,
                    contents=prompt
                )
                st.session_state["generated_insight"] = response.text
            except Exception as e:
                st.error(f"AIの生成中にエラーが発生しました: {e}")

# ==========================================
# 4. 分析結果の表示とHTML(PDF)保存
# ==========================================
if "generated_insight" in st.session_state:
    st.markdown("---")
    st.markdown("### 📝 分析結果")
    
    result_text = st.session_state["generated_insight"]
    st.info(result_text)
    
    # --- HTML形式のデータ（印刷・PDF用）作成 ---
    result_formatted = result_text.replace('\n', '<br>')
    report_html = f"""
    <html><head><meta charset="UTF-8"><title>AIセルフケア考察レポート</title>
    <style>
        body {{ font-family: 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 30px; background-color: #FAFAF7; }}
        h1 {{ color: #2A9D8F; border-bottom: 2px solid #2A9D8F; padding-bottom: 10px; font-size: 24px; text-align: center; }}
        .content {{ background: #ffffff; padding: 25px; border-radius: 15px; border: 1px solid #ddd; margin-bottom: 20px; }}
        .print-btn {{ display: block; width: 250px; margin: 20px auto; padding: 12px; text-align: center; background: #2A9D8F; color: #fff; text-decoration: none; border-radius: 30px; cursor: pointer; border: none; font-size: 16px; font-weight: bold; }}
        @media print {{ body {{ background-color: #fff; }} .no-print {{ display: none !important; }} }}
    </style></head>
    <body>
        <button class="no-print print-btn" onclick="window.print()">🖨️ PDFとして保存 / 印刷する</button>
        <h1>📊 AI セルフケア分析＆考察レポート</h1>
        <p><strong>対象者:</strong> {selected_user} さん</p>
        <p style="text-align:right; font-size: 12px; color: #888;">作成日: {datetime.now().strftime('%Y年%m月%d日')}</p>
        <div class="content">
            {result_formatted}
        </div>
    </body></html>
    """

    st.markdown("#### 💾 結果の保存・クリア")
    
    # ボタンを横に2つ並べる
    col1, col2 = st.columns(2)
    
    with col1:
        st.download_button(
            label="🖨️ 印刷・PDF用(HTML)で保存",
            data=report_html,
            file_name=f"セルフケア分析_{selected_user}さん_{datetime.now().strftime('%Y%m%d')}.html",
            mime="text/html",
            use_container_width=True
        )
        
    with col2:
        if st.button("🧹 結果をクリアする", use_container_width=True):
            del st.session_state["generated_insight"]
            st.rerun()
