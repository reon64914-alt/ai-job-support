import streamlit as st
# ★ 変更点1：新しいパッケージのインポート
from google import genai
from google.genai import types
import edge_tts
import asyncio
import base64
import os
import random
import streamlit.components.v1 as components
import firebase_admin
from firebase_admin import credentials, firestore

# --- 画面の設定 ---
st.set_page_config(page_title="支援員ロールプレイング", page_icon="🎓", layout="wide")

# ==========================================
# 🚨 セキュリティバウンサー & データベース初期化
# ==========================================
if "user_email" not in st.session_state:
    st.warning("⚠️ ログインが必要です。左のメニューから「Home」に戻ってログインしてください。")
    st.stop()

APP_NAME = "ai_matching_app"

if APP_NAME not in firebase_admin._apps:
    try:
        # 🔑 secrets.toml の [firebase_ai_matching] から鍵を読み込む
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
    # ★ 変更点2：Client（通信係）を作成
    client = genai.Client(api_key=api_key)
except Exception:
    st.error("⚠️ `.streamlit/secrets.toml` に APIキーを設定してください。")
    st.stop()

# ★ 混雑エラー対策として安定版を指定しています
TARGET_MODEL = "gemini-2.5-flash-lite"

VRM_DIR = "vrm_models"
os.makedirs(VRM_DIR, exist_ok=True)
vrm_files = [f for f in os.listdir(VRM_DIR) if f.endswith(".vrm")]

if not vrm_files:
    st.error(f"⚠️ `{VRM_DIR}` フォルダにVRMファイルがありません。")
    st.stop()

# ★ ロールプレイングで登場させる「利用者用アバター」だけをリストアップする
ALLOWED_VRMS = [
    "利用者女性01.vrm",
    "利用者女性02.vrm",
    "利用者男性01.vrm",
    "利用者男性02.vrm"
]
# フォルダ内にあるVRMファイルのうち、上のリストに一致するものだけを抽出して訓練用に使う
target_vrm_files = [f for f in vrm_files if f in ALLOWED_VRMS]

# ==========================================
# 📂 訓練ケースのデータベース処理
# ==========================================
DEFAULT_CASES = {
    "ケースA：激昂・クレーム型": {
        "prompt": "あなたは就労移行支援事業所の利用者です。現在、非常に怒っています。希望する求人が見つからないことや、支援員の対応に不満を持っています。支援員（ユーザー）に対して威圧的な態度でクレームを言ってください。ただし、支援員の適切な傾聴や共感、謝罪があれば、少しずつ落ち着いてください。最初は怒りの感情を前面に出してください。",
        "expression": "angry",
        "first_message": "ちょっと！いつになったら私の希望する求人を紹介してくれるんですか！？毎日同じ訓練ばかりで、時間の無駄じゃないですか！どうなってるんですか！"
    },
    "ケースB：抑うつ・無気力型": {
        "prompt": "あなたは就労移行支援事業所の利用者です。現在、ひどく落ち込んでおり、自己肯定感がどん底です。「どうせ自分なんてどこも受からない」「生きていても意味がない」とネガティブな発言を繰り返します。支援員の励ましが薄っぺらい（ポジティブすぎる）とさらに殻に閉じこもります。寄り添う姿勢が見られれば、少しだけ前を向きます。",
        "expression": "sad",
        "first_message": "……すみません、今日も訓練に集中できませんでした。どうせ私なんて、どこに行っても役に立たないんです。もう全部辞めたいです……。"
    },
    "ケースC：他責・パニック型": {
        "prompt": "あなたは就労移行支援事業所の利用者です。周囲の音が気になったり、他の利用者が自分の悪口を言っていると思い込んでパニック気味になっています。落ち着きがなく、被害妄想的な発言をします。支援員が「気のせいだ」と論理的に否定するとさらに混乱します。安心させる声かけを求めています。",
        "expression": "sad",
        "first_message": "あの、さっきから後ろの席の人が私のこと見て笑ってるんです！絶対に私の悪口言ってますよね！？もうここにはいられません、帰らせてください！"
    }
}

def load_cases_from_db():
    cases = {}
    try:
        docs = db.collection('roleplay_cases').stream()
        for doc in docs:
            cases[doc.id] = doc.to_dict()
            
        if not cases:
            for title, data in DEFAULT_CASES.items():
                db.collection('roleplay_cases').document(title).set(data)
                cases[title] = data
    except Exception as e:
        st.error(f"ケースの読み込みに失敗しました: {e}")
        cases = DEFAULT_CASES 
        
    sorted_cases = dict(sorted(cases.items()))
    return sorted_cases

cases_db = load_cases_from_db()

voice_models_dict = {
    "👩 女性 (Nanami)": "ja-JP-NanamiNeural",
    "👨 男性 (Keita)": "ja-JP-KeitaNeural",
}

# --- セッション初期化 ---
if "rp_messages" not in st.session_state: st.session_state.rp_messages = []
if "rp_active" not in st.session_state: st.session_state.rp_active = False
if "rp_finished" not in st.session_state: st.session_state.rp_finished = False
if "rp_vrm" not in st.session_state: st.session_state.rp_vrm = target_vrm_files[0] if target_vrm_files else vrm_files[0]
if "rp_voice_name" not in st.session_state: st.session_state.rp_voice_name = "👩 女性 (Nanami)"
if "rp_voice_id" not in st.session_state: st.session_state.rp_voice_id = "ja-JP-NanamiNeural"
if "rp_feedback" not in st.session_state: st.session_state.rp_feedback = ""
if "rp_latest_audio_b64" not in st.session_state: st.session_state.rp_latest_audio_b64 = ""
if "rp_last_audio_val" not in st.session_state: st.session_state.rp_last_audio_val = None
if "input_mode" not in st.session_state: st.session_state.input_mode = "🎙️ 音声で対応する"

# --- 音声生成（Edge-TTS） ---
async def _generate_audio(text, voice, rate):
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    audio_data = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio": audio_data.extend(chunk["data"])
    return bytes(audio_data)

def generate_audio(text, voice, rate):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(_generate_audio(text, voice, rate))
    loop.close()
    return result

@st.cache_data(show_spinner=False)
def get_base64_vrm(file_path):
    with open(file_path, "rb") as f: return f"data:application/octet-stream;base64,{base64.b64encode(f.read()).decode()}"

def get_base64_audio(audio_bytes):
    return f"data:audio/mp3;base64,{base64.b64encode(audio_bytes).decode()}"

# === 🎨 サイドバー：設定画面 ===
with st.sidebar:
    st.header("⚙️ 訓練の設定")
    
    st.session_state.input_mode = st.radio("⌨️ 支援員の入力方法", ["🎙️ 音声で対応する", "⌨️ テキストで対応する"], 
                                           index=0 if "音声" in st.session_state.input_mode else 1)
    st.markdown("---")
    
    selected_case = st.selectbox("📂 挑戦するケースを選択", list(cases_db.keys()))
    case_data = cases_db[selected_case]
    
    with st.expander("📖 ケースの状況（詳細設定）", expanded=True):
        st.write(case_data['prompt'])
        
        if selected_case not in DEFAULT_CASES:
            if st.button("🗑️ この追加ケースを削除する"):
                try:
                    db.collection('roleplay_cases').document(selected_case).delete()
                    st.success(f"「{selected_case}」を削除しました。")
                    st.rerun()
                except Exception as e:
                    st.error(f"削除に失敗しました: {e}")
    
    st.markdown("---")
    if not st.session_state.rp_active and not st.session_state.rp_finished:
        if st.button("🚀 ランダムな相手で訓練スタート！", type="primary", use_container_width=True):
            if not target_vrm_files:
                st.error("⚠️ 指定された利用者のVRMファイルが見つかりません。")
                st.stop()
                
            st.session_state.rp_vrm = random.choice(target_vrm_files)
            
            female_voices = [k for k in voice_models_dict.keys() if "女性" in k]
            male_voices = [k for k in voice_models_dict.keys() if "男性" in k]
            
            if "男性" in st.session_state.rp_vrm:
                st.session_state.rp_voice_name = random.choice(male_voices)
            elif "女性" in st.session_state.rp_vrm:
                st.session_state.rp_voice_name = random.choice(female_voices)
            else:
                st.session_state.rp_voice_name = random.choice(list(voice_models_dict.keys()))
                
            st.session_state.rp_voice_id = voice_models_dict[st.session_state.rp_voice_name]
            
            st.session_state.rp_messages = []
            st.session_state.rp_active = True
            st.session_state.rp_finished = False
            st.session_state.rp_feedback = ""
            st.session_state.rp_latest_audio_b64 = ""
            
            first_text = case_data['first_message']
            
            if "🎙️" in st.session_state.input_mode:
                try:
                    audio_bytes = generate_audio(first_text, st.session_state.rp_voice_id, "+0%")
                    st.session_state.rp_latest_audio_b64 = get_base64_audio(audio_bytes)
                except:
                    st.session_state.rp_latest_audio_b64 = ""
            else:
                st.session_state.rp_latest_audio_b64 = ""
            
            st.session_state.rp_messages.append({"role": "assistant", "content": first_text})
            st.rerun()

    if st.session_state.rp_active and not st.session_state.rp_finished:
        if st.button("🛑 対応を終了して評価を受ける", type="primary", use_container_width=True):
            if len(st.session_state.rp_messages) <= 1:
                st.warning("⚠️ まだやり取りがありません！")
            else:
                with st.spinner("スーパーバイザーが評価中..."):
                    try:
                        history_text = "\n".join([f"{'利用者' if msg['role'] == 'assistant' else '支援員'}: {msg['content']}" for msg in st.session_state.rp_messages])
                        eval_prompt = f"""
                        あなたは就労支援のベテラン・スーパーバイザーです。
                        以下の「支援員」と「メンタル不調の利用者」のロールプレイングのやり取りを評価し、支援員（ユーザー）に向けてフィードバックを行ってください。
                        
                        【ケース設定】
                        {case_data['prompt']}
                        
                        【やり取り】
                        {history_text}
                        
                        出力形式:
                        ### 🌟 良かった点（傾聴や共感の姿勢など）
                        ### 💡 改善のヒント（より良い声かけの提案）
                        ### 💬 総合アドバイス
                        """
                        # ★ 変更点3：フィードバック生成（Client使用）
                        res = client.models.generate_content(
                            model=TARGET_MODEL,
                            contents=eval_prompt
                        )
                        st.session_state.rp_feedback = res.text
                        st.session_state.rp_finished = True
                        st.session_state.rp_active = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"エラー: {e}")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 リセットして最初から", use_container_width=True):
        st.session_state.rp_active = False
        st.session_state.rp_finished = False
        st.session_state.rp_messages = []
        st.session_state.rp_latest_audio_b64 = ""
        st.rerun()
        
    st.markdown("---")
    
    with st.expander("➕ 新しい訓練ケースを追加する"):
        with st.form("add_case_form", clear_on_submit=True):
            new_title = st.text_input("ケースのタイトル", placeholder="例：ケースD：面接前パニック型")
            new_prompt = st.text_area("ケースの状況設定（AIへの指示）", placeholder="利用者の現在の状況や、どのような対応を求めているかを記載してください。")
            new_first = st.text_area("利用者の第一声", placeholder="例：明日の面接、やっぱり行けません！怖くて吐き気がします！")
            
            expr_options = {"怒り": "angry", "悲しみ・不安": "sad", "普通": "neutral", "喜び": "happy", "リラックス": "relaxed"}
            new_expr_label = st.selectbox("アバターの基本表情", list(expr_options.keys()))
            
            submitted = st.form_submit_button("データベースに保存する")
            
            if submitted:
                if new_title and new_prompt and new_first:
                    try:
                        db.collection('roleplay_cases').document(new_title).set({
                            "prompt": new_prompt,
                            "expression": expr_options[new_expr_label],
                            "first_message": new_first
                        })
                        st.success("✅ 新しいケースを保存しました！")
                        st.rerun() 
                    except Exception as e:
                        st.error(f"保存に失敗しました: {e}")
                else:
                    st.warning("タイトル、状況設定、第一声はすべて入力してください。")

# === 🌟 画面レイアウト ===
st.title("🎓 支援員向け リアル対応シミュレーター")

if not st.session_state.rp_active and not st.session_state.rp_finished:
    st.info("👈 左のサイドバーからケースを選び、「ランダムな相手で訓練スタート！」を押してください。\n※毎回異なる見た目と声の利用者が登場します。")
    st.stop()

if st.session_state.rp_finished:
    st.markdown(f'<div style="background-color: #ffffff; padding: 25px; border-radius: 12px; border-top: 5px solid #2A9D8F; box-shadow: 0 4px 15px rgba(0,0,0,0.05);"><h3>📋 SVからの評価レポート</h3>{st.session_state.rp_feedback}</div>', unsafe_allow_html=True)
    st.markdown("---")
    st.subheader("💬 やり取りの振り返り")
    for msg in st.session_state.rp_messages:
        speaker = "👤 利用者" if msg['role'] == 'assistant' else "🧑‍💼 支援員（あなた）"
        st.markdown(f"**{speaker}：** {msg['content']}")
    st.stop()

# --- 面接進行中の画面 ---
col_avatar, col_chat = st.columns([1.2, 1])

with col_avatar:
    st.markdown(f"**現在の相手：** {st.session_state.rp_voice_name}")
    with st.container(border=True):
        vrm_path = os.path.join(VRM_DIR, st.session_state.rp_vrm)
        vrm_data_uri = get_base64_vrm(vrm_path)
        audio_data_uri = st.session_state.rp_latest_audio_b64
        target_expr = case_data["expression"]
        
        html_code = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ margin: 0; overflow: hidden; background-color: #F0F4F8; border-radius: 10px; }}
                #canvas-container {{ width: 100%; height: 500px; }}
                #play-button {{
                    position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
                    padding: 15px 30px; font-size: 18px; font-weight: bold; background-color: #2A9D8F; 
                    color: white; border: none; border-radius: 30px; cursor: pointer; z-index: 10;
                }}
            </style>
            <script type="importmap">
              {{
                "imports": {{
                  "three": "https://unpkg.com/three@0.154.0/build/three.module.js",
                  "three/addons/": "https://unpkg.com/three@0.154.0/examples/jsm/",
                  "@pixiv/three-vrm": "https://unpkg.com/@pixiv/three-vrm@2.0.6/lib/three-vrm.module.js"
                }}
              }}
            </script>
        </head>
        <body>
            <div id="canvas-container"></div>
            <button id="play-button" style="display: none;">🔊 相手の言葉を聞く</button>
            <script type="module">
                import * as THREE from 'three';
                import {{ GLTFLoader }} from 'three/addons/loaders/GLTFLoader.js';
                import {{ VRMLoaderPlugin, VRMUtils }} from '@pixiv/three-vrm';

                const vrmDataUrl = "{vrm_data_uri}";
                const audioDataUrl = "{audio_data_uri}";
                const targetExpression = "{target_expr}"; 
                let currentVrm = null, analyser = null, dataArray = null, isPlaying = false;

                const scene = new THREE.Scene();
                const camera = new THREE.PerspectiveCamera(35, window.innerWidth / 500, 0.1, 20.0);
                camera.position.set(0.0, 1.45, 1.1);
                const renderer = new THREE.WebGLRenderer({{ alpha: true, antialias: true }});
                renderer.setSize(window.innerWidth, 500);
                renderer.outputColorSpace = THREE.SRGBColorSpace;
                document.getElementById('canvas-container').appendChild(renderer.domElement);

                scene.add(new THREE.DirectionalLight(0xffffff, 0.5));
                scene.add(new THREE.AmbientLight(0xffffff, 0.4));

                const loader = new GLTFLoader();
                loader.register((parser) => new VRMLoaderPlugin(parser));
                loader.load(vrmDataUrl, (gltf) => {{
                    const vrm = gltf.userData.vrm;
                    VRMUtils.removeUnnecessaryJoints(gltf.scene);
                    scene.add(vrm.scene);
                    vrm.scene.rotation.y = Math.PI;
                    
                    vrm.humanoid.getNormalizedBoneNode('leftUpperArm').rotation.z = 1.45;
                    vrm.humanoid.getNormalizedBoneNode('rightUpperArm').rotation.z = -1.45;
                    
                    currentVrm = vrm;
                    if (audioDataUrl && audioDataUrl !== "data:audio/mp3;base64,") setupAudio();
                }});

                function setupAudio() {{
                    const audio = new Audio(audioDataUrl);
                    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
                    const source = audioContext.createMediaElementSource(audio);
                    analyser = audioContext.createAnalyser();
                    source.connect(analyser);
                    analyser.connect(audioContext.destination);
                    dataArray = new Uint8Array(analyser.frequencyBinCount);
                    const playBtn = document.getElementById('play-button');
                    audio.play().then(() => isPlaying = true).catch(() => {{
                        playBtn.style.display = "block";
                        playBtn.onclick = () => {{ audioContext.resume(); audio.play(); isPlaying = true; playBtn.style.display = "none"; }};
                    }});
                    audio.onended = () => {{ isPlaying = false; if(currentVrm) currentVrm.expressionManager.setValue('aa', 0); }};
                }}

                const clock = new THREE.Clock();
                let blinkTimer = 0;
                let isBlinking = false;

                function animate() {{
                    requestAnimationFrame(animate);
                    const deltaTime = clock.getDelta();
                    const elapsedTime = clock.elapsedTime;

                    if (currentVrm) {{
                        const spine = currentVrm.humanoid.getNormalizedBoneNode('spine');
                        
                        currentVrm.expressionManager.setValue(targetExpression, 0.8);
                        
                        if (spine) {{
                            spine.rotation.x = 0.05; 
                            spine.rotation.z = Math.sin(elapsedTime * 1.5) * 0.05; 
                            spine.rotation.y = Math.sin(elapsedTime * 1.0) * 0.08; 
                        }}

                        blinkTimer += deltaTime;
                        if (!isBlinking && blinkTimer > 3 + Math.random() * 4) {{
                            isBlinking = true; blinkTimer = 0;
                        }}
                        if (isBlinking) {{
                            let blinkValue = blinkTimer < 0.1 ? blinkTimer / 0.1 : (blinkTimer < 0.2 ? 1.0 - ((blinkTimer - 0.1) / 0.1) : 0);
                            if (blinkTimer >= 0.2) {{ isBlinking = false; blinkTimer = 0; }}
                            currentVrm.expressionManager.setValue('blink', blinkValue);
                        }}

                        currentVrm.update(deltaTime);

                        if (isPlaying && analyser) {{
                            analyser.getByteFrequencyData(dataArray);
                            let sum = 0;
                            for (let i = 0; i < dataArray.length; i++) sum += dataArray[i];
                            currentVrm.expressionManager.setValue('aa', Math.min(1.0, (sum / dataArray.length / 50.0)));
                        }}
                    }}
                    renderer.render(scene, camera);
                }}
                animate();
            </script>
        </body>
        </html>
        """
        components.html(html_code, height=500)

with col_chat:
    st.markdown(f"### {st.session_state.input_mode}")
    chat_container = st.container(height=350)
    with chat_container:
        for msg in st.session_state.rp_messages:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])

    user_input = None
    if "🎙️" in st.session_state.input_mode:
        audio_val = st.audio_input("支援員マイク", label_visibility="collapsed")
        if audio_val and audio_val != st.session_state.rp_last_audio_val:
            st.session_state.rp_last_audio_val = audio_val
            with st.spinner("AIが文字起こし中..."):
                try:
                    # ★ 変更点4：音声データの受け渡し（Client使用）
                    audio_part = types.Part.from_bytes(data=audio_val.getvalue(), mime_type="audio/wav")
                    
                    t_res = client.models.generate_content(
                        model=TARGET_MODEL,
                        contents=[audio_part, "音声データを文字起こししてください。無音の場合は「無音」と出力。"]
                    )
                    stt_text = t_res.text
                    if stt_text and "無音" not in stt_text:
                        user_input = stt_text
                    else:
                        st.warning("音声がうまく聞き取れませんでした。")
                except Exception as e: 
                    st.error(f"音声の読み取りに失敗しました: {e}")
    else:
        user_input = st.chat_input("支援員として対応を入力")

    if user_input:
        st.session_state.rp_messages.append({"role": "user", "content": user_input})
        with st.spinner("利用者が反応しています..."):
            try:
                system_instruction = f"あなたは以下に設定された利用者です。支援員からの言葉に対して、設定に従ってリアルに返答してください。\n\n{case_data['prompt']}\n\n※AIとは名乗らず、生の人間として感情的に振る舞うこと。返答は1回につき簡潔に。"
                
                # ★ 変更点5：チャットセッションの作成と送信（Client使用）
                config = types.GenerateContentConfig(system_instruction=system_instruction)
                
                formatted_history = []
                for m in st.session_state.rp_messages[:-1]:
                    role = "model" if m["role"] == "assistant" else "user"
                    formatted_history.append(
                        types.Content(role=role, parts=[types.Part.from_text(text=m["content"])])
                    )
                
                chat = client.chats.create(model=TARGET_MODEL, config=config, history=formatted_history)
                response = chat.send_message(user_input)
                ai_text = response.text.strip()
                
                if "🎙️" in st.session_state.input_mode:
                    try:
                        ai_audio_bytes = generate_audio(ai_text, st.session_state.rp_voice_id, "+0%")
                        st.session_state.rp_latest_audio_b64 = get_base64_audio(ai_audio_bytes)
                    except:
                        st.session_state.rp_latest_audio_b64 = ""
                else: 
                    st.session_state.rp_latest_audio_b64 = ""
                
                st.session_state.rp_messages.append({"role": "assistant", "content": ai_text})
                st.rerun()
            except Exception as e: 
                st.error(f"エラー: {e}")