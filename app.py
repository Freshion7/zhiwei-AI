import streamlit as st
import sqlite3
import bcrypt
import os
import shutil
from datetime import datetime, date, time
import requests
from bs4 import BeautifulSoup
from docx import Document
from io import BytesIO
from openpyxl import Workbook
from pypinyin import pinyin

# ================= 页面配置 =================
st.set_page_config(page_title="知微 - 你的私人AI助理", layout="wide")

# ================= 存储路径配置 =================
BASE_STORAGE = "D:/知微AI"
try:
    os.makedirs(BASE_STORAGE, exist_ok=True)
except:
    BASE_STORAGE = os.getcwd() + "/知微AI"
    os.makedirs(BASE_STORAGE, exist_ok=True)

def get_user_storage(user_id):
    user_dir = os.path.join(BASE_STORAGE, f"user_{user_id}")
    sub_dirs = ["notes_files", "contacts_avatars", "projects_files", "atom_notes_files"]
    for sub in sub_dirs:
        os.makedirs(os.path.join(user_dir, sub), exist_ok=True)
    return user_dir

# ================= 数据库初始化（带自动升级） =================
DB_PATH = os.path.join(BASE_STORAGE, "zhiwei.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 1. 创建老表结构（如果不存在）
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password_hash TEXT, identity_code TEXT UNIQUE, created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS notes
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, content TEXT, tags TEXT, file_paths TEXT, created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS contacts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, contact_code TEXT, name TEXT, company TEXT, department TEXT, position TEXT, phone TEXT, avatar_path TEXT, created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS projects
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, contact_id INTEGER, project_name TEXT, file_paths TEXT, created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS project_folders
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, contact_id INTEGER, folder_name TEXT, created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS atom_notes
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, title TEXT, content TEXT, file_paths TEXT, code_content TEXT, created_at TEXT)''')
    
    # 2. 自动检测并升级数据库
    c.execute("PRAGMA table_info(notes)")
    columns = [col[1] for col in c.fetchall()]
    if 'title' not in columns:
        c.execute("ALTER TABLE notes ADD COLUMN title TEXT DEFAULT '无标题'")
    if 'reminder' not in columns:
        c.execute("ALTER TABLE notes ADD COLUMN reminder TEXT DEFAULT ''")
    
    c.execute("PRAGMA table_info(atom_notes)")
    atom_columns = [col[1] for col in c.fetchall()]
    if 'code_content' not in atom_columns:
        c.execute("ALTER TABLE atom_notes ADD COLUMN code_content TEXT DEFAULT ''")
        
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
                st.error("用户名或密码错误，请尝试重新注册（若在云端运行，数据每次重启会重置）。")

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
            clean_username = new_username.strip()
            clean_password = new_password.strip()
            clean_confirm = confirm_password.strip()

            if not clean_username or not clean_password:
                st.error("用户名和密码不能为空")
            elif clean_password != clean_confirm:
                st.error("两次密码不一致")
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
                    st.success(f"注册成功！您的专属身份码是：**{identity_code}**")
                    st.session_state["page"] = "login"
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("用户名已存在，或身份码冲突。")
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
    menu = st.sidebar.radio("功能导航", ["📝 我的笔记", "📅 周报生成", "📊 思维导图", "🔍 联网搜索", "🤖 陪伴对话", "👤 联系人管理", "📒 原子笔记", "⚙️ 个人中心"])
    
    if st.sidebar.button("退出登录"):
        st.session_state.clear()
        st.rerun()

    # ---------- 笔记模块 ----------
    if menu == "📝 我的笔记":
        st.subheader("📝 我的笔记")
        
        search_query = st.text_input("🔍 按标题/标签快速搜索笔记")
        
        with st.expander("✏️ 写新笔记 / 上传附件", expanded=True):
            with st.form("new_note"):
                title = st.text_input("笔记标题（文件命名）")
                content = st.text_area("内容 (支持 Markdown 语法: # 标题, **加粗**, ```代码```)", height=150)
                tags = st.text_input("标签（用逗号分隔）")
                
                col_date, col_time = st.columns(2)
                with col_date:
                    note_date = st.date_input("提醒日期", value=date.today())
                with col_time:
                    note_time = st.time_input("提醒时间", value=time(hour=9, minute=0))
                
                uploaded_files = st.file_uploader("上传附件", type=['docx','xlsx','pdf','pptx','jpg','png'], accept_multiple_files=True)
                submitted = st.form_submit_button("保存笔记")
                
                if submitted and title:
                    file_paths = []
                    if uploaded_files:
                        notes_dir = os.path.join(user_storage, "notes_files")
                        for file in uploaded_files:
                            save_path = os.path.join(notes_dir, file.name)
                            with open(save_path, "wb") as f:
                                f.write(file.getbuffer())
                            file_paths.append(save_path)
                    file_paths_str = ",".join(file_paths)
                    reminder_str = note_date.strftime("%Y-%m-%d") + " " + note_time.strftime("%H:%M")
                    
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("INSERT INTO notes (user_id, title, content, tags, file_paths, reminder, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                              (user['id'], title, content, tags, file_paths_str, reminder_str, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    conn.commit()
                    conn.close()
                    st.success("✅ 笔记及附件已成功保存！")
                    st.rerun()

        conn = get_db_connection()
        c = conn.cursor()
        if search_query:
            c.execute('''SELECT id, title, content, tags, file_paths, reminder, created_at FROM notes 
                         WHERE user_id = ? AND (title LIKE ? OR tags LIKE ?) ORDER BY created_at DESC''', 
                         (user['id'], f"%{search_query}%", f"%{search_query}%"))
        else:
            c.execute("SELECT id, title, content, tags, file_paths, reminder, created_at FROM notes WHERE user_id = ? ORDER BY created_at DESC", (user['id'],))
        notes = c.fetchall()
        conn.close()

        if not notes:
            st.info("还没有笔记，写一条吧！")
        else:
            for note in notes:
                with st.container(border=True):
                    st.markdown(f"### {note[1]}") # 标题
                    st.write(f"**{note[6]}**") # 时间
                    if note[5]: # 提醒时间
                        st.caption(f"⏰ 提醒：{note[5]}")
                    
                    st.markdown(note[2][:300] + "..." if len(note[2]) > 300 else note[2])
                    
                    if note[3]:
                        st.caption(f"🏷️ {note[3]}")
                    if note[4]:
                        st.write("📎 **附件：**")
                        for path in note[4].split(","):
                            if path:
                                fname = os.path.basename(path)
                                if os.path.exists(path):
                                    with open(path, "rb") as f:
                                        st.download_button(label=f"📥 下载 {fname}", data=f, file_name=fname, key=f"dl_{note[0]}_{fname}")
                    if st.button(f"删除 #{note[0]}", key=f"del_{note[0]}"):
                        conn = get_db_connection()
                        c = conn.cursor()
                        c.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (note[0], user['id']))
                        conn.commit()
                        conn.close()
                        st.rerun()

    # ---------- 周报生成 ----------
    elif menu == "📅 周报生成":
        st.subheader("📅 本周周报生成")
        if st.button("🔄 一键生成本周周报"):
            conn = get_db_connection()
            c = conn.cursor()
            c.execute('''SELECT title, content, created_at FROM notes 
                         WHERE user_id = ? AND date(created_at) >= date('now', 'weekday 1', '-7 days')
                         ORDER BY created_at DESC''', (user['id'],))
            week_notes = c.fetchall()
            conn.close()
            
            if not week_notes:
                st.warning("本周暂无笔记记录。")
            else:
                report = f"# 知微 · 本周工作周报\n\n**生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n## 本周主要事项\n"
                for idx, note in enumerate(week_notes, 1):
                    report += f"{idx}. **{note[0]}**: {note[1][:50]}... (记录于 {note[2]})\n"
                st.markdown(report)
                
                doc = Document()
                doc.add_heading('知微 · 本周工作周报', 0)
                doc.add_paragraph(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
                doc.add_heading('本周主要事项', level=1)
                for idx, note in enumerate(week_notes, 1):
                    doc.add_paragraph(f"{idx}. {note[0]}: {note[1][:50]}...", style='List Bullet')
                doc_io = BytesIO()
                doc.save(doc_io)
                doc_io.seek(0)
                
                wb = Workbook()
                ws = wb.active
                ws.title = "本周周报"
                ws.append(["序号", "标题", "内容摘要", "记录时间"])
                for idx, note in enumerate(week_notes, 1):
                    ws.append([idx, note[0], note[1][:50], note[2]])
                excel_io = BytesIO()
                wb.save(excel_io)
                excel_io.seek(0)

                col1, col2 = st.columns(2)
                with col1:
                    st.download_button(label="📄 导出 Word (.docx)", data=doc_io, file_name="知微AI_本周周报.docx")
                with col2:
                    st.download_button(label="📊 导出 Excel (.xlsx)", data=excel_io, file_name="知微AI_本周周报.xlsx")

    # ---------- 思维导图 ----------
    elif menu == "📊 思维导图":
        st.info("💡 功能开发中：请确保本地安装了系统级 Graphviz。")

    # ---------- 联网搜索 ----------
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
                        st.success(f"找到 {len(results)} 条结果：")
                        for i, url in enumerate(results[:5], 1):
                            st.write(f"{i}. [{url}]({url})")
                    else:
                        st.warning("未找到相关结果。")
                except Exception as e:
                    st.error(f"搜索失败：{e}")

    # ---------- 陪伴对话 ----------
    elif menu == "🤖 陪伴对话":
        st.subheader("🤖 知微助手（轻量版）")
        if "chat_msg" not in st.session_state:
            st.session_state.chat_msg = []
        user_input = st.text_input("对我说句话吧")
        if st.button("发送", key="chat_send") and user_input:
            if "忙" in user_input or "累" in user_input:
                reply = "辛苦了！建议您梳理一下笔记，偶尔放空也是生产力。"
            elif "思路" in user_input or "计划" in user_input:
                reply = "您可以试试用'笔记'把想法写下来。"
            else:
                reply = "收到！您可以在'笔记'或'原子笔记'中记录详细内容。"
            st.session_state.chat_msg.append(("你", user_input))
            st.session_state.chat_msg.append(("知微", reply))
        for role, text in st.session_state.chat_msg:
            if role == "知微":
                st.info(f"🤖 **知微**：{text}")
            else:
                st.write(f"👤 **你**：{text}")

    # ---------- 联系人管理 ----------
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
                    c_code_input = st.text_input("粘贴对方18位身份码")
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

        search_query = st.text_input("🔍 快速搜索联系人")
        
        conn = get_db_connection()
        c = conn.cursor()
        if search_query:
            c.execute('''SELECT id, name, company, department, position, phone, contact_code, created_at 
                         FROM contacts WHERE user_id = ? AND name LIKE ? ORDER BY created_at DESC''', 
                         (user['id'], f"%{search_query}%"))
        else:
            c.execute("SELECT id, name, company, department, position, phone, contact_code, created_at FROM contacts WHERE user_id = ? ORDER BY created_at DESC", (user['id'],))
        contacts = c.fetchall()
        conn.close()

        if not contacts:
            st.info("暂无联系人。")
        else:
            for contact in contacts:
                cid, name, company, dept, pos, phone, code, c_time = contact
                with st.container(border=True):
                    cols = st.columns([1, 6, 2])
                    with cols[0]:
                        st.image(f"https://ui-avatars.com/api/?name={name}&background=random&color=fff&size=64", use_container_width=True)
                    with cols[1]:
                        st.markdown(f"**{name}**")
                        st.caption(f"🏢 {company} | {dept} | {pos} | 📞 {phone}")
                        st.caption(f"🆔 身份码: {code}")
                        
                        st.write("📂 **历史项目（文件夹）：**")
                        conn = get_db_connection()
                        c = conn.cursor()
                        c.execute("SELECT id, folder_name, created_at FROM project_folders WHERE user_id = ? AND contact_id = ? ORDER BY created_at DESC", (user['id'], cid))
                        folders = c.fetchall()
                        conn.close()
                        
                        if folders:
                            for folder in folders:
                                fid, fname, ftime = folder
                                st.write(f"- 🗂️ **{fname}** ({ftime})")
                                conn = get_db_connection()
                                c = conn.cursor()
                                c.execute("SELECT id, project_name, file_paths, created_at FROM projects WHERE folder_id = ? ORDER BY created_at DESC", (fid,))
                                projects = c.fetchall()
                                conn.close()
                                for proj in projects:
                                    st.write(f"  - 📄 **{proj[1]}** ({proj[3]})")
                                    if proj[2]:
                                        for fpath in proj[2].split(","):
                                            if fpath and os.path.exists(fpath):
                                                fname_file = os.path.basename(fpath)
                                                with open(fpath, "rb") as f:
                                                    st.download_button(label=f"📎 下载 {fname_file}", data=f, file_name=fname_file, key=f"proj_{proj[0]}_{fname_file}")
                        else:
                            st.write("*暂无文件夹/项目*")
                    
                    with cols[2]:
                        with st.popover("➕ 新增项目文件夹"):
                            new_folder_name = st.text_input("文件夹名称", key=f"folder_name_{cid}")
                            if st.button("创建文件夹", key=f"create_folder_{cid}") and new_folder_name:
                                conn = get_db_connection()
                                c = conn.cursor()
                                c.execute("INSERT INTO project_folders (user_id, contact_id, folder_name, created_at) VALUES (?, ?, ?, ?)",
                                          (user['id'], cid, new_folder_name.strip(), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                                conn.commit()
                                conn.close()
                                st.success("文件夹已创建！")
                                st.rerun()
                        
                        with st.popover("➕ 新增项目"):
                            all_folders = []
                            conn = get_db_connection()
                            c = conn.cursor()
                            c.execute("SELECT id, folder_name FROM project_folders WHERE user_id = ? AND contact_id = ?", (user['id'], cid))
                            all_folders = c.fetchall()
                            conn.close()
                            
                            if not all_folders:
                                st.warning("请先创建文件夹！")
                            else:
                                folder_options = {f[1]: f[0] for f in all_folders}
                                selected_folder_name = st.selectbox("选择文件夹", list(folder_options.keys()), key=f"folder_sel_{cid}")
                                proj_name = st.text_input("项目名称", key=f"proj_name_{cid}")
                                proj_files = st.file_uploader("上传项目附件", accept_multiple_files=True, key=f"proj_files_{cid}")
                                if st.button("保存项目", key=f"save_proj_{cid}") and proj_name:
                                    proj_dir = os.path.join(user_storage, "projects_files")
                                    file_paths = []
                                    for f in proj_files:
                                        save_path = os.path.join(proj_dir, f.name)
                                        with open(save_path, "wb") as f_out:
                                            f_out.write(f.getbuffer())
                                        file_paths.append(save_path)
                                    conn = get_db_connection()
                                    c = conn.cursor()
                                    c.execute("INSERT INTO projects (contact_id, folder_id, project_name, file_paths, created_at) VALUES (?, ?, ?, ?, ?)",
                                              (cid, folder_options[selected_folder_name], proj_name.strip(), ",".join(file_paths), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                                    conn.commit()
                                    conn.close()
                                    st.success("项目已添加！")
                                    st.rerun()

    # ---------- 原子笔记（彻底解决 DOM 崩溃问题） ----------
    elif menu == "📒 原子笔记":
        st.subheader("📒 原子笔记（知识库 + 流程图工具）")
        st.caption("默认直接展示代码，点击下方按钮可安全预览流程图，完美解决页面崩溃问题。")
        
        with st.expander("✏️ 新建笔记 / 制作流程图", expanded=True):
            with st.form("atom_note"):
                a_title = st.text_input("笔记标题")
                a_content = st.text_area("内容 (支持 Markdown、代码块、Mermaid流程图)", height=200)
                a_code_snippet = st.text_area("进阶：流程图源码 (直接粘贴 Mermaid 代码，或者描述逻辑生成)", height=100, placeholder="例: graph TD; A[开始] --> B{判断}; B -->|是| C[结束];")
                
                a_files = st.file_uploader("上传图片/音频/其他文件", accept_multiple_files=True)
                submitted = st.form_submit_button("保存笔记")
                
                if submitted and a_title:
                    file_paths = []
                    if a_files:
                        atom_dir = os.path.join(user_storage, "atom_notes_files")
                        for file in a_files:
                            save_path = os.path.join(atom_dir, file.name)
                            with open(save_path, "wb") as f:
                                f.write(file.getbuffer())
                            file_paths.append(save_path)
                    file_paths_str = ",".join(file_paths)
                    
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("INSERT INTO atom_notes (user_id, title, content, file_paths, code_content, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                              (user['id'], a_title, a_content, file_paths_str, a_code_snippet, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    conn.commit()
                    conn.close()
                    st.success("✅ 原子笔记已保存！")
                    st.rerun()
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id, title, content, file_paths, code_content, created_at FROM atom_notes WHERE user_id = ? ORDER BY created_at DESC", (user['id'],))
        atom_notes = c.fetchall()
        conn.close()

        # 修正了此处代码的缩进问题，彻底解决了 IndentationError
        if not atom_notes:
            st.info("知识库是空的，写一条原子笔记吧！")
        else:
            for note in atom_notes:
                with st.container(border=True):
                    st.markdown(f"### {note[1]}") 
                    st.caption(f"📅 创建时间: {note[5]}")
                    
                    # 使用 st.write 避免基础冲突
                    st.write(note[2])
                    
                    # === 核心修改：零风险展示流程图 ===
                    if note[4]:
                        st.write("🔄 **流程图源码：**")
                        st.code(note[4], language="mermaid")
                        
                        # 使用按钮动态触发流程图渲染，完美隔离 DOM 冲突
                        if st.button(f"📊 点击渲染/预览此流程图", key=f"render_mermaid_{note[0]}"):
                            try:
                                mermaid_html = f"""
                                <div style="background: white; padding: 10px; border-radius: 5px; margin-top: 10px;">
                                    <pre class="mermaid" style="text-align: center;">
                                        {note[4]}
                                    </pre>
                                    <script type="module">
                                        import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
                                        mermaid.initialize({{ startOnLoad: true, theme: 'default' }});
                                    </script>
                                </div>
                                """
                                st.components.v1.html(mermaid_html, height=400)
                            except Exception as e:
                                st.warning("前端加载流程图组件时发生隔离错误，请刷新重试。")
                    
                    if note[3]:
                        st.write("📎 **附件：**")
                        for path in note[3].split(","):
                            if path and os.path.exists(path):
                                ext = os.path.splitext(path)[1].lower()
                                fname = os.path.basename(path)
                                if ext in ['.png', '.jpg', '.jpeg', '.gif']:
                                    st.image(path, caption=fname, use_container_width=True)
                                elif ext in ['.mp3', '.wav', '.ogg']:
                                    st.audio(path)
                                else:
                                    with open(path, "rb") as f:
                                        st.download_button(label=f"📥 下载 {fname}", data=f, file_name=fname, key=f"atom_{note[0]}_{fname}")

    # ---------- 个人中心 ----------
    elif menu == "⚙️ 个人中心":
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT identity_code, created_at FROM users WHERE id = ?", (user['id'],))
        user_info = c.fetchone()
        conn.close()
        
        st.write(f"**用户名**：{user['username']}")
        st.write(f"**您的专属 18 位身份码**：`{user_info[0]}`")
        st.write(f"**注册时间**：{user_info[1]}")
        st.write("**云端说明**：若部署在 Streamlit Cloud，数据默认保存在临时硬盘。如需数据云端持久化，请联系技术团队修改数据库为 PostgreSQL 并配置 OSS 存储。")

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
