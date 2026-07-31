import streamlit as st
import sqlite3
import bcrypt
import os
import shutil
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from docx import Document
from io import BytesIO
from openpyxl import Workbook
from pypinyin import pinyin

# ================= 页面配置 =================
st.set_page_config(page_title="知微 - 你的私人AI助理", layout="wide")

# ================= 存储路径配置（适配电脑/手机/云端） =================
# 优先尝试 D盘，若存在则使用；否则使用当前项目目录
try:
    BASE_STORAGE = "D:/知微AI"
    os.makedirs(BASE_STORAGE, exist_ok=True)
except:
    BASE_STORAGE = os.getcwd() + "/知微AI"
    os.makedirs(BASE_STORAGE, exist_ok=True)

def get_user_storage(user_id):
    """确保每个用户有自己的独立文件夹及各个模块子文件夹"""
    user_dir = os.path.join(BASE_STORAGE, f"user_{user_id}")
    sub_dirs = ["notes_files", "contacts_avatars", "projects_files"]
    for sub in sub_dirs:
        os.makedirs(os.path.join(user_dir, sub), exist_ok=True)
    return user_dir

# ================= 数据库初始化 =================
DB_PATH = os.path.join(BASE_STORAGE, "zhiwei.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 用户表：增加 identity_code 字段
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password_hash TEXT, identity_code TEXT UNIQUE, created_at TEXT)''')
    # 笔记表
    c.execute('''CREATE TABLE IF NOT EXISTS notes
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, content TEXT, tags TEXT, file_paths TEXT, created_at TEXT)''')
    # 联系人表
    c.execute('''CREATE TABLE IF NOT EXISTS contacts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, contact_code TEXT, name TEXT, company TEXT, department TEXT, position TEXT, phone TEXT, avatar_path TEXT, created_at TEXT)''')
    # 历史项目表
    c.execute('''CREATE TABLE IF NOT EXISTS projects
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, contact_id INTEGER, project_name TEXT, file_paths TEXT, created_at TEXT)''')
    conn.commit()
    conn.close()

init_db()

# ================= 辅助函数 =================
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def get_db_connection():
    return sqlite3.connect(DB_PATH)

def get_identity_prefix(username):
    """生成身份码前3位：中文取拼音前3个字母，英文/数字直接取前3位"""
    if not username:
        return "def"
    first_char = username[0]
    if '\u4e00' <= first_char <= '\u9fff': # 是中文
        try:
            pinyin_list = pinyin(first_char)
            return pinyin_list[0][0][:3].lower()
        except:
            return username[:3].lower()
    else:
        return username[:3].upper()

# ================= 登录/注册逻辑 =================
def login_page():
    st.title("知微 · 登录")
    with st.form("login_form"):
        username = st.text_input("用户名")
        password = st.text_input("密码", type="password")
        submit = st.form_submit_button("登录")
        
        if submit:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT id, password_hash FROM users WHERE username = ?", (username.strip(),))
            user = c.fetchone()
            conn.close()
            if user and check_password(password.strip(), user[1]):
                st.session_state["user"] = {"id": user[0], "username": username.strip()}
                st.success("登录成功！")
                st.rerun()
            else:
                st.error("用户名或密码错误")

    st.divider()
    st.write("还没有账号？")
    if st.button("去注册"):
        st.session_state["page"] = "register"
        st.rerun()

def register_page():
    st.title("知微 · 注册")
    with st.form("register_form"):
        new_username = st.text_input("设置用户名")
        new_password = st.text_input("设置密码", type="password")
        confirm_password = st.text_input("确认密码", type="password")
        submit = st.form_submit_button("注册")
        
        if submit:
            # 核心修改：增加 .strip() 自动去除首尾空格，避免“密码不一致”
            clean_username = new_username.strip()
            clean_password = new_password.strip()
            clean_confirm = confirm_password.strip()

            if not clean_username or not clean_password:
                st.error("用户名和密码不能为空")
            elif clean_password != clean_confirm:
                st.error("两次密码不一致，请检查是否包含多余空格")
            else:
                conn = get_db_connection()
                c = conn.cursor()
                try:
                    prefix = get_identity_prefix(clean_username)
                    c.execute("SELECT MAX(id) FROM users")
                    max_id = c.fetchone()[0]
                    next_id = 1 if max_id is None else max_id + 1
                    identity_code = prefix + str(next_id).zfill(15)
                    
                    hashed = hash_password(clean_password)
                    c.execute("INSERT INTO users (username, password_hash, identity_code, created_at) VALUES (?, ?, ?, ?)",
                              (clean_username, hashed, identity_code, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    conn.commit()
                    st.success(f"注册成功！您的专属身份码是：**{identity_code}** (请复制保存，用于添加联系人)")
                    st.session_state["page"] = "login"
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("用户名已存在")
                finally:
                    conn.close()

    if st.button("返回登录"):
        st.session_state["page"] = "login"
        st.rerun()

# ================= 主应用逻辑 =================
def main_app():
    user = st.session_state["user"]
    user_storage = get_user_storage(user['id'])
    
    st.sidebar.title(f"👋 你好，{user['username']}")
    menu = st.sidebar.radio("功能导航", ["📝 我的笔记", "📅 周报生成", "📊 思维导图", "🔍 联网搜索", "🤖 陪伴对话", "👤 联系人管理", "⚙️ 个人中心"])
    
    if st.sidebar.button("退出登录"):
        st.session_state.clear()
        st.rerun()

    # ---------- 笔记模块 ----------
    if menu == "📝 我的笔记":
        st.subheader("📝 我的笔记")
        
        with st.expander("✏️ 写新笔记 / 上传附件", expanded=True):
            with st.form("new_note"):
                content = st.text_area("内容", height=100)
                tags = st.text_input("标签（用逗号分隔）")
                uploaded_files = st.file_uploader("上传附件 (Word/Excel/PDF/PPT)", 
                                                  type=['docx','xlsx','pdf','pptx'], 
                                                  accept_multiple_files=True)
                submitted = st.form_submit_button("保存笔记")
                
                if submitted and content:
                    file_paths = []
                    if uploaded_files:
                        notes_dir = os.path.join(user_storage, "notes_files")
                        for file in uploaded_files:
                            save_path = os.path.join(notes_dir, file.name)
                            with open(save_path, "wb") as f:
                                f.write(file.getbuffer())
                            file_paths.append(save_path)
                    file_paths_str = ",".join(file_paths)
                    
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("INSERT INTO notes (user_id, content, tags, file_paths, created_at) VALUES (?, ?, ?, ?, ?)",
                              (user['id'], content, tags, file_paths_str, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    conn.commit()
                    conn.close()
                    st.success("笔记及附件已保存！")
                    st.rerun()

        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id, content, tags, file_paths, created_at FROM notes WHERE user_id = ? ORDER BY created_at DESC", (user['id'],))
        notes = c.fetchall()
        conn.close()

        if not notes:
            st.info("还没有笔记，写一条吧！")
        else:
            for note in notes:
                with st.container(border=True):
                    st.write(f"**{note[4]}**")
                    st.write(note[1])
                    if note[2]:
                        st.caption(f"🏷️ {note[2]}")
                    if note[3]:
                        st.write("📎 **附件：**")
                        for path in note[3].split(","):
                            if path:
                                fname = os.path.basename(path)
                                with open(path, "rb") as f:
                                    st.download_button(label=f"下载 {fname}", data=f, file_name=fname, key=f"dl_{note[0]}_{fname}")
                    if st.button(f"删除 #{note[0]}", key=f"del_{note[0]}"):
                        conn = get_db_connection()
                        c = conn.cursor()
                        c.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (note[0], user['id']))
                        conn.commit()
                        conn.close()
                        st.rerun()

    # ---------- 周报生成模块 ----------
    elif menu == "📅 周报生成":
        st.subheader("📅 本周周报生成")
        if st.button("🔄 一键生成本周周报"):
            conn = get_db_connection()
            c = conn.cursor()
            c.execute('''SELECT content, created_at FROM notes 
                         WHERE user_id = ? AND date(created_at) >= date('now', 'weekday 1', '-7 days')
                         ORDER BY created_at DESC''', (user['id'],))
            week_notes = c.fetchall()
            conn.close()
            
            if not week_notes:
                st.warning("本周暂无笔记记录，无法生成周报。")
            else:
                report = f"# 知微 · 本周工作周报\n\n**生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n## 本周主要事项\n"
                for idx, note in enumerate(week_notes, 1):
                    report += f"{idx}. {note[0]} （记录于 {note[1]}）\n"
                st.markdown(report)
                
                doc = Document()
                doc.add_heading('知微 · 本周工作周报', 0)
                doc.add_paragraph(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
                doc.add_heading('本周主要事项', level=1)
                for idx, note in enumerate(week_notes, 1):
                    doc.add_paragraph(f"{idx}. {note[0]} （记录于 {note[1]}）", style='List Bullet')
                doc_io = BytesIO()
                doc.save(doc_io)
                doc_io.seek(0)
                
                wb = Workbook()
                ws = wb.active
                ws.title = "本周周报"
                ws.append(["序号", "笔记内容", "记录时间"])
                for idx, note in enumerate(week_notes, 1):
                    ws.append([idx, note[0], note[1]])
                excel_io = BytesIO()
                wb.save(excel_io)
                excel_io.seek(0)

                col1, col2 = st.columns(2)
                with col1:
                    st.download_button(label="📄 导出并下载 Word (.docx)", data=doc_io, file_name="知微AI_本周周报.docx")
                with col2:
                    st.download_button(label="📊 导出并下载 Excel (.xlsx)", data=excel_io, file_name="知微AI_本周周报.xlsx")

    # ---------- 思维导图 ----------
    elif menu == "📊 思维导图":
        st.info("💡 功能开发中：即将支持一键生成思维导图（请安装系统级 Graphviz）。")

    # ---------- 联网搜索模块 ----------
    elif menu == "🔍 联网搜索":
        st.subheader("🔍 联网搜索（Bing）")
        query = st.text_input("请输入要搜索的关键词")
        if st.button("开始搜索") and query:
            with st.spinner(f"正在搜索：{query} ..."):
                try:
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    url = f"https://www.bing.com/search?q={query}"
                    response = requests.get(url, headers=headers, timeout=10)
                    soup = BeautifulSoup(response.text, 'html.parser')
                    results = []
                    for li in soup.select('li.b_algo h2 a'):
                        href = li.get('href')
                        if href and href.startswith('http'):
                            results.append(href)
                    if results:
                        st.success(f"找到 {len(results)} 条搜索结果：")
                        for i, url in enumerate(results[:5], 1):
                            st.write(f"{i}. [{url}]({url})")
                    else:
                        st.warning("未找到相关结果。")
                except Exception as e:
                    st.error(f"搜索失败：{e}")

    # ---------- 陪伴对话模块 ----------
    elif menu == "🤖 陪伴对话":
        st.subheader("🤖 知微助手（轻量版）")
        if "chat_msg" not in st.session_state:
            st.session_state.chat_msg = []
        user_input = st.text_input("对我说句话吧")
        if st.button("发送", key="chat_send") and user_input:
            if "忙" in user_input or "累" in user_input:
                reply = "辛苦了！建议您梳理一下本周笔记，偶尔放空也是生产力。"
            elif "思路" in user_input or "计划" in user_input:
                reply = "您可以试试用'笔记'功能把想法写下来，周报会自动帮您汇总。"
            else:
                reply = f"收到！您可以在'我的笔记'中上传任何附件文件。"
            st.session_state.chat_msg.append(("你", user_input))
            st.session_state.chat_msg.append(("知微", reply))
        for role, text in st.session_state.chat_msg:
            if role == "知微":
                st.info(f"🤖 **知微**：{text}")
            else:
                st.write(f"👤 **你**：{text}")

    # ---------- 联系人管理模块 ----------
    elif menu == "👤 联系人管理":
        st.subheader("👤 联系人管理")
        
        with st.expander("➕ 添加新联系人", expanded=False):
            with st.form("add_contact"):
                col1, col2 = st.columns(2)
                with col1:
                    c_name = st.text_input("姓名 *")
                    c_company = st.text_input("公司")
                    c_dept = st.text_input("部门")
                    c_pos = st.text_input("职务")
                with col2:
                    c_phone = st.text_input("联系方式")
                    c_code_input = st.text_input("粘贴对方18位身份码 (若已知)")
                c_submit = st.form_submit_button("保存联系人")
                
                if c_submit and c_name:
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("INSERT INTO contacts (user_id, contact_code, name, company, department, position, phone, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                              (user['id'], c_code_input, c_name.strip(), c_company.strip(), c_dept.strip(), c_pos.strip(), c_phone.strip(), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    conn.commit()
                    conn.close()
                    st.success("联系人添加成功！")
                    st.rerun()

        search_query = st.text_input("🔍 快速搜索联系人 (姓名/公司/部门)")
        
        conn = get_db_connection()
        c = conn.cursor()
        if search_query:
            c.execute('''SELECT id, name, company, department, position, phone, contact_code, created_at 
                         FROM contacts WHERE user_id = ? AND (name LIKE ? OR company LIKE ? OR department LIKE ?) 
                         ORDER BY created_at DESC''', (user['id'], f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"))
        else:
            c.execute("SELECT id, name, company, department, position, phone, contact_code, created_at FROM contacts WHERE user_id = ? ORDER BY created_at DESC", (user['id'],))
        contacts = c.fetchall()
        conn.close()

        if not contacts:
            st.info("暂无联系人，快去添加吧！")
        else:
            for contact in contacts:
                cid, name, company, dept, pos, phone, code, c_time = contact
                with st.container(border=True):
                    cols = st.columns([1, 6, 2])
                    with cols[0]:
                        st.image("https://ui-avatars.com/api/?name=" + name + "&background=random&color=fff&size=64", use_container_width=True)
                    with cols[1]:
                        st.markdown(f"**{name}**")
                        st.caption(f"🏢 {company} | {dept} | {pos} | 📞 {phone}")
                        st.caption(f"🆔 身份码: {code}")
                        st.write("📂 **历史项目：**")
                        conn = get_db_connection()
                        c = conn.cursor()
                        c.execute("SELECT id, project_name, file_paths, created_at FROM projects WHERE contact_id = ? ORDER BY created_at DESC", (cid,))
                        projects = c.fetchall()
                        conn.close()
                        
                        if projects:
                            for proj in projects:
                                st.write(f"- **{proj[1]}** ({proj[3]})")
                                if proj[2]:
                                    for fpath in proj[2].split(","):
                                        if fpath:
                                            fname = os.path.basename(fpath)
                                            if os.path.exists(fpath):
                                                with open(fpath, "rb") as f:
                                                    st.download_button(label=f"📎 下载 {fname}", data=f, file_name=fname, key=f"proj_{proj[0]}_{fname}")
                        else:
                            st.write("*暂无项目*")
                    
                    with cols[2]:
                        with st.popover("➕ 新增项目"):
                            proj_name = st.text_input("项目名称", key=f"proj_name_{cid}")
                            proj_files = st.file_uploader("上传项目附件", accept_multiple_files=True, key=f"proj_files_{cid}")
                            if st.button("保存项目", key=f"save_proj_{cid}"):
                                if proj_name:
                                    proj_dir = os.path.join(user_storage, "projects_files")
                                    file_paths = []
                                    if proj_files:
                                        for f in proj_files:
                                            save_path = os.path.join(proj_dir, f.name)
                                            with open(save_path, "wb") as f_out:
                                                f_out.write(f.getbuffer())
                                            file_paths.append(save_path)
                                    conn = get_db_connection()
                                    c = conn.cursor()
                                    c.execute("INSERT INTO projects (contact_id, project_name, file_paths, created_at) VALUES (?, ?, ?, ?)",
                                              (cid, proj_name.strip(), ",".join(file_paths), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                                    conn.commit()
                                    conn.close()
                                    st.success("项目已添加！")
                                    st.rerun()

    # ---------- 个人中心 ----------
    elif menu == "⚙️ 个人中心":
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT identity_code, created_at FROM users WHERE id = ?", (user['id'],))
        user_info = c.fetchone()
        conn.close()
        
        st.write(f"**用户名**：{user['username']}")
        st.write(f"**您的专属 18 位身份码**：`{user_info[0]}` *(可复制此码发送给您的同事/客户，对方添加联系人时粘贴即可)*")
        st.write(f"**注册时间**：{user_info[1]}")
        st.write("密码管理功能即将上线。")

# ================= 路由控制 =================
if "user" not in st.session_state:
    if "page" not in st.session_state:
        st.session_state["page"] = "login"
    if st.session_state["page"] == "login":
        login_page()
    else:
        register_page()
else:
    main_app()