import os, secrets, hashlib, sqlite3, json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
import database

APP_NAME = "KRUTIK CYBER EXPERT API"
DB_PATH = os.getenv("DB_PATH", "bot.db")
OWNER_CHAT_ID = os.getenv("OWNER_CHAT_ID", "")
WEB_SECRET = os.getenv("WEB_SECRET", "CHANGE_THIS_SECRET")
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))

app = FastAPI(title=APP_NAME, version="1.0.0")
app.add_middleware(SessionMiddleware, secret_key=WEB_SECRET, same_site="lax", https_only=False)
app.mount("/static", StaticFiles(directory="static"), name="static")

def db():
    c=sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    c.row_factory=sqlite3.Row
    return c

def init_web_db():
    database.init_db()
    c=db()
    c.execute("""CREATE TABLE IF NOT EXISTS web_users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        name TEXT DEFAULT '',
        chat_id INTEGER UNIQUE,
        blocked INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS web_sessions(
        token TEXT PRIMARY KEY,
        web_user_id INTEGER NOT NULL,
        created_at TEXT NOT NULL
    )""")
    c.commit(); c.close()

def ph(p): return hashlib.sha256(p.encode()).hexdigest()
def current_user(request):
    uid=request.session.get("web_user_id")
    if not uid: return None
    c=db(); r=c.execute("SELECT * FROM web_users WHERE id=?",(uid,)).fetchone(); c.close()
    return dict(r) if r else None
def require_user(request):
    u=current_user(request)
    if not u or u["blocked"]: raise HTTPException(401,"Login required")
    return u
def owner(request):
    return bool(OWNER_CHAT_ID and str(request.session.get("owner_id"))==str(OWNER_CHAT_ID))

CSS = """body{margin:0;font-family:Inter,system-ui;background:#070b14;color:#eaf0ff}a{color:#8ab4ff;text-decoration:none}.wrap{max-width:1180px;margin:auto;padding:24px}.nav{display:flex;justify-content:space-between;align-items:center;padding:16px 0}.brand{font-weight:800;font-size:21px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}.card{background:#101827;border:1px solid #22304a;border-radius:16px;padding:20px}.hero{padding:55px 0}.btn{display:inline-block;background:#2563eb;color:white;padding:11px 16px;border-radius:10px;border:0;cursor:pointer}.btn.red{background:#dc2626}.btn.green{background:#16a34a}.btn.gray{background:#334155}.input,select{width:100%;box-sizing:border-box;padding:12px;margin:7px 0 14px;border-radius:10px;border:1px solid #334155;background:#0b1220;color:white}.table{width:100%;border-collapse:collapse}.table th,.table td{padding:10px;border-bottom:1px solid #26334a;text-align:left}.muted{color:#94a3b8}.danger{color:#f87171}.ok{color:#4ade80}.err{background:#3b1111;padding:12px;border-radius:10px}.top{display:flex;gap:10px;flex-wrap:wrap}.code{background:#050912;padding:14px;border-radius:10px;overflow:auto}.pill{padding:5px 9px;border-radius:99px;background:#1e293b;font-size:12px}"""
HEAD=f"""<meta name="viewport" content="width=device-width,initial-scale=1"><style>{CSS}</style>"""
def page(title, body, request):
    u=current_user(request)
    nav=f'<div class="nav"><a class="brand" href="/">🛡️ {APP_NAME}</a><div class="top">'
    if u: nav+=f'<a class="btn gray" href="/dashboard">Dashboard</a><a class="btn gray" href="/keys">Keys</a><a class="btn gray" href="/docs">Docs</a><a class="btn red" href="/logout">Logout</a>'
    else: nav+='<a class="btn gray" href="/login">Login</a><a class="btn" href="/register">Register</a>'
    if owner(request): nav+='<a class="btn green" href="/admin">Admin</a>'
    nav+='</div></div>'
    return HTMLResponse(f'<!doctype html><html><head>{HEAD}<title>{title}</title></head><body><div class="wrap">{nav}{body}</div></body></html>')

@app.on_event("startup")
def startup(): init_web_db()

@app.get("/",response_class=HTMLResponse)
def home(request:Request):
    body=f"""<section class="hero"><h1>🛡️ {APP_NAME}</h1><p class="muted">API access, API keys, usage tracking and documentation — web edition.</p>
    <div class="top"><a class="btn" href="/register">Create account</a><a class="btn gray" href="/docs">API Docs</a></div></section>
    <div class="grid"><div class="card"><h3>🔑 API Plans</h3><p>Basic, Pro and Custom access plans.</p></div><div class="card"><h3>📊 Usage</h3><p>Track daily and total requests.</p></div><div class="card"><h3>🛡️ Key Security</h3><p>Hashed API keys, expiry, limits and revocation.</p></div><div class="card"><h3>⚙️ Admin</h3><p>Manage users, requests, keys and API state.</p></div></div>"""
    return page(APP_NAME,body,request)

@app.get("/register",response_class=HTMLResponse)
def register_get(request:Request):
    return page("Register",'<div class="card"><h2>Create account</h2><form method="post"><label>Name</label><input class="input" name="name" required><label>Email</label><input class="input" type="email" name="email" required><label>Password</label><input class="input" type="password" name="password" minlength="6" required><button class="btn">Register</button></form><p class="muted">Already registered? <a href="/login">Login</a></p></div>',request)

@app.post("/register")
def register(name:str=Form(...),email:str=Form(...),password:str=Form(...)):
    c=db()
    try:
        cur=c.execute("INSERT INTO web_users(email,password_hash,name,created_at) VALUES(?,?,?,?)",(email.strip().lower(),ph(password),name.strip(),database.now_iso()))
        wid=cur.lastrowid
        # Give the web account its own internal numeric identity for API ownership.
        c.execute("UPDATE web_users SET chat_id=? WHERE id=?",(1000000000+wid,wid))
        c.commit()
    except sqlite3.IntegrityError:
        c.close(); return HTMLResponse("Email already registered. <a href='/login'>Login</a>",409)
    c.close()
    r=RedirectResponse("/dashboard",303); r.set_cookie("registered","1"); return r

@app.get("/login",response_class=HTMLResponse)
def login_get(request:Request):
    return page("Login",'<div class="card"><h2>Login</h2><form method="post"><label>Email</label><input class="input" type="email" name="email" required><label>Password</label><input class="input" type="password" name="password" required><button class="btn">Login</button></form></div>',request)

@app.post("/login")
def login(request:Request,email:str=Form(...),password:str=Form(...)):
    c=db(); r=c.execute("SELECT * FROM web_users WHERE email=? AND password_hash=?",(email.strip().lower(),ph(password))).fetchone(); c.close()
    if not r: return page("Login failed",'<div class="err">Invalid email or password.</div><p><a href="/login">Try again</a></p>',request)
    if r["blocked"]: return page("Blocked",'<div class="err">Your account is blocked.</div>',request)
    request.session["web_user_id"]=r["id"]
    return RedirectResponse("/dashboard",303)

@app.get("/logout")
def logout(request:Request):
    request.session.clear(); return RedirectResponse("/",303)

@app.get("/dashboard",response_class=HTMLResponse)
def dashboard(request:Request):
    u=require_user(request); keys=database.get_user_keys(u["chat_id"])
    stats=database.get_usage_stats()
    cards=f"""<h1>Dashboard</h1><p>Welcome, <b>{u['name'] or u['email']}</b></p>
    <div class="grid"><div class="card"><h3>🔑 My Keys</h3><b>{len(keys)}</b></div><div class="card"><h3>📈 Total Requests</h3><b>{sum(k['total_requests'] for k in keys)}</b></div><div class="card"><h3>🟢 Active Keys</h3><b>{sum(k['status']=='active' for k in keys)}</b></div><div class="card"><h3>🌐 API</h3><b>{'ONLINE' if stats['global_api_enabled'] else 'OFFLINE'}</b></div></div>
    <div class="card" style="margin-top:16px"><h2>Quick actions</h2><div class="top"><a class="btn" href="/request-access">🚀 Request API Access</a><a class="btn gray" href="/keys">🔐 My API Keys</a><a class="btn gray" href="/usage">📊 Usage</a></div></div>"""
    return page("Dashboard",cards,request)

@app.get("/plans",response_class=HTMLResponse)
def plans(request:Request):
    plans=[]
    for p in ("basic","pro","custom"):
        plans.append(f"<div class='card'><h2>{p.upper()}</h2><p>{database.get_setting(p+'_daily')} requests/day</p><p>{database.get_setting(p+'_days')} days</p><a class='btn' href='/request-access?plan={p}'>Request</a></div>")
    return page("Plans","<h1>🔑 API Plans</h1><div class='grid'>"+''.join(plans)+"</div>",request)

@app.get("/request-access",response_class=HTMLResponse)
def request_access_get(request:Request,plan:str="basic"):
    require_user(request)
    return page("Request Access",f"""<div class="card"><h2>🚀 Request API Access</h2><p>Plan: <b>{plan.upper()}</b></p><form method="post"><input type="hidden" name="plan" value="{plan}"><button class="btn">Submit Request</button></form></div>""",request)

@app.post("/request-access")
def request_access(request:Request,plan:str=Form(...)):
    u=require_user(request)
    if plan not in ("basic","pro","custom"): raise HTTPException(400,"Invalid plan")
    rid=database.create_access_request(u["chat_id"],u["email"],plan)
    return RedirectResponse(f"/request/{rid}",303)

@app.get("/request/{rid}",response_class=HTMLResponse)
def request_view(request:Request,rid:int):
    u=require_user(request); r=database.get_access_request(rid)
    if not r or r["chat_id"]!=u["chat_id"]: raise HTTPException(404)
    return page("Request",f"<div class='card'><h2>Request #{rid}</h2><p>Plan: {r['plan'].upper()}</p><p>Status: <span class='pill'>{r['status']}</span></p></div>",request)

@app.get("/keys",response_class=HTMLResponse)
def keys(request:Request):
    u=require_user(request); ks=database.get_user_keys(u["chat_id"])
    rows=''.join(f"<tr><td>{k['id']}</td><td>{k['key_name']}</td><td>{k['plan'].upper()}</td><td>{k['status']}</td><td>{k['today_requests']}/{k['daily_limit']}</td><td>{k['total_requests']}</td><td>{k['expires_at'] or '∞'}</td></tr>" for k in ks)
    body=f"<h1>🔐 My API Keys</h1><div class='card'><table class='table'><tr><th>ID</th><th>Name</th><th>Plan</th><th>Status</th><th>Today</th><th>Total</th><th>Expiry</th></tr>{rows or '<tr><td colspan=7>No keys yet.</td></tr>'}</table></div>"
    return page("Keys",body,request)

@app.get("/usage",response_class=HTMLResponse)
def usage(request:Request):
    u=require_user(request); logs=[x for x in database.get_recent_logs(100) if x.get("chat_id")==u["chat_id"]]
    rows=''.join(f"<tr><td>{x['created_at']}</td><td>{x['query']}</td><td>{'✅' if x['success'] else '❌'}</td><td>{x['status_code']}</td></tr>" for x in logs)
    return page("Usage",f"<h1>📊 Usage</h1><div class='card'><table class='table'><tr><th>Time</th><th>Query</th><th>Result</th><th>HTTP</th></tr>{rows or '<tr><td colspan=4>No usage yet.</td></tr>'}</table></div>",request)

@app.get("/docs",response_class=HTMLResponse)
def docs(request:Request):
    api=database.get_setting("api_url","http://localhost:10000")
    body=f"""<h1>📚 API Documentation</h1><div class="card"><p>Existing API endpoints are preserved.</p><h3>GET /api/search</h3><pre class="code">{api}/api/search?api_key=YOUR_KEY&query=TEST&limit=20</pre><h3>GET /api/status</h3><pre class="code">{api}/api/status?api_key=YOUR_KEY</pre><h3>GET /api/stats</h3><pre class="code">{api}/api/stats</pre><p>API key can also be sent with <b>X-API-Key</b>.</p></div>"""
    return page("Docs",body,request)

@app.get("/admin",response_class=HTMLResponse)
def admin(request:Request):
    if not owner(request): return RedirectResponse("/admin/login",303)
    s=database.get_usage_stats()
    body=f"""<h1>👑 Admin Panel</h1><div class="grid">
    <div class="card">👥 Users<br><b>{s['users']}</b></div><div class="card">🔑 Keys<br><b>{s['keys']}</b></div><div class="card">🟢 Active Keys<br><b>{s['active_keys']}</b></div><div class="card">📈 Requests<br><b>{s['requests']}</b></div><div class="card">📨 Pending<br><b>{s['pending']}</b></div><div class="card">🚫 Blocked<br><b>{s['blocked']}</b></div></div>
    <div class="card" style="margin-top:16px"><div class="top"><a class="btn" href="/admin/users">Users</a><a class="btn" href="/admin/requests">Requests</a><a class="btn" href="/admin/keys">Keys</a><a class="btn" href="/admin/logs">Logs</a><a class="btn gray" href="/admin/settings">Settings</a></div></div>"""
    return page("Admin",body,request)

@app.get("/admin/login",response_class=HTMLResponse)
def admin_login_get(request:Request):
    return page("Admin Login",'<div class="card"><h2>Owner Login</h2><form method="post"><label>Owner Chat ID</label><input class="input" name="owner_id" required><button class="btn">Login</button></form></div>',request)

@app.post("/admin/login")
def admin_login(request:Request,owner_id:str=Form(...)):
    if not OWNER_CHAT_ID or str(owner_id).strip()!=str(OWNER_CHAT_ID): return page("Denied",'<div class="err">Invalid owner ID.</div>',request)
    request.session["owner_id"]=str(owner_id).strip()
    return RedirectResponse("/admin",303)

@app.get("/admin/users",response_class=HTMLResponse)
def admin_users(request:Request):
    if not owner(request): raise HTTPException(403)
    users=database.get_users(200)
    rows=''.join(f"<tr><td>{u['chat_id']}</td><td>{u['username']}</td><td>{u['first_name']}</td><td>{'🚫' if u['blocked'] else '🟢'}</td><td><a href='/admin/user/{u['chat_id']}/block'>{'Unblock' if u['blocked'] else 'Block'}</a></td></tr>" for u in users)
    return page("Users",f"<h1>👥 Users</h1><div class='card'><table class='table'><tr><th>ID</th><th>Username</th><th>Name</th><th>Status</th><th>Action</th></tr>{rows}</table></div>",request)

@app.get("/admin/user/{chat_id}/{action}")
def admin_user_action(request:Request,chat_id:int,action:str):
    if not owner(request): raise HTTPException(403)
    if action=="block": database.block_user(chat_id)
    elif action=="unblock": database.unblock_user(chat_id)
    else: raise HTTPException(400)
    return RedirectResponse("/admin/users",303)

@app.get("/admin/requests",response_class=HTMLResponse)
def admin_requests(request:Request):
    if not owner(request): raise HTTPException(403)
    rs=database.get_pending_requests(200)
    rows=''.join(f"<tr><td>{r['id']}</td><td>{r['chat_id']}</td><td>{r['plan'].upper()}</td><td>{r['created_at']}</td><td><a class='ok' href='/admin/request/{r['id']}/approve'>Approve</a> | <a class='danger' href='/admin/request/{r['id']}/reject'>Reject</a></td></tr>" for r in rs)
    return page("Requests",f"<h1>📨 Pending Requests</h1><div class='card'><table class='table'><tr><th>ID</th><th>User</th><th>Plan</th><th>Created</th><th>Action</th></tr>{rows or '<tr><td colspan=5>No pending requests.</td></tr>'}</table></div>",request)

@app.get("/admin/request/{rid}/{action}")
def admin_request_action(request:Request,rid:int,action:str):
    if not owner(request): raise HTTPException(403)
    r=database.get_access_request(rid)
    if not r or r["status"]!="pending": raise HTTPException(404)
    if action=="reject": database.update_access_request(rid,"rejected")
    elif action=="approve":
        plan=r["plan"]; daily=int(database.get_setting(plan+"_daily","50000")); days=int(database.get_setting(plan+"_days","30"))
        from datetime import timedelta
        expires=(datetime.now(timezone.utc)+timedelta(days=days)).isoformat() if days>0 else None
        database.create_api_key(r["chat_id"],plan=plan,key_name=f"{plan.upper()} API",daily_limit=daily,total_limit=None,expires_at=expires,rate_limit=None)
        database.update_access_request(rid,"approved")
    else: raise HTTPException(400)
    return RedirectResponse("/admin/requests",303)

@app.get("/admin/keys",response_class=HTMLResponse)
def admin_keys(request:Request):
    if not owner(request): raise HTTPException(403)
    ks=database.get_all_keys(300)
    rows=''.join(f"<tr><td>{k['id']}</td><td>{k['chat_id']}</td><td>{k['key_name']}</td><td>{k['plan']}</td><td>{k['status']}</td><td>{k['total_requests']}</td></tr>" for k in ks)
    return page("Admin Keys",f"<h1>🔑 API Keys</h1><div class='card'><table class='table'><tr><th>ID</th><th>User</th><th>Name</th><th>Plan</th><th>Status</th><th>Requests</th></tr>{rows}</table></div>",request)

@app.get("/admin/logs",response_class=HTMLResponse)
def admin_logs(request:Request):
    if not owner(request): raise HTTPException(403)
    ls=database.get_recent_logs(200)
    rows=''.join(f"<tr><td>{x['created_at']}</td><td>{x['chat_id']}</td><td>{x['query']}</td><td>{'✅' if x['success'] else '❌'}</td><td>{x['status_code']}</td></tr>" for x in ls)
    return page("Logs",f"<h1>📈 API Logs</h1><div class='card'><table class='table'><tr><th>Time</th><th>User</th><th>Query</th><th>Result</th><th>HTTP</th></tr>{rows}</table></div>",request)

@app.get("/admin/settings",response_class=HTMLResponse)
def admin_settings(request:Request):
    if not owner(request): raise HTTPException(403)
    on=database.is_global_api_enabled()
    body=f"""<h1>⚙️ Settings</h1><div class="card"><p>Global API: <b>{'🟢 ON' if on else '🔴 OFF'}</b></p>
    <div class="top"><a class="btn green" href="/admin/api/on">API ON</a><a class="btn red" href="/admin/api/off">API OFF</a></div>
    <h3>API URL</h3><p class="code">{database.get_setting('api_url')}</p>
    <h3>JSON datasets</h3><p>{len(list(DATA_DIR.glob('*.json')))} files</p></div>"""
    return page("Settings",body,request)

@app.get("/admin/api/{state}")
def admin_api_state(request:Request,state:str):
    if not owner(request): raise HTTPException(403)
    if state=="on": database.set_global_api_enabled(True)
    elif state=="off": database.set_global_api_enabled(False)
    else: raise HTTPException(400)
    return RedirectResponse("/admin/settings",303)

@app.get("/web/health")
def web_health():
    return {"service":APP_NAME,"website":"online","database":"sqlite"}

if __name__=="__main__":
    import uvicorn
    uvicorn.run(app,host="0.0.0.0",port=int(os.getenv("PORT","10000")))
