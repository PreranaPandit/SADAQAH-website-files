"""SADAQAH — small neighborhood store, inquiry-first storefront."""
import csv
import asyncio
import hmac
import io
import os
import re
import secrets
import threading
import time
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime, select
from sqlalchemy.orm import declarative_base, sessionmaker
from starlette.middleware.sessions import SessionMiddleware
from starlette.templating import Jinja2Templates
from products import PRODUCTS, PRODUCT_BY_ID, CATEGORIES, PHOTOS

ROOT = Path(__file__).resolve().parent
DB_URL = os.getenv('DATABASE_URL', '').strip()
if not DB_URL:
    dbfile = ROOT / 'data' / 'sadaqah.db'
    dbfile.parent.mkdir(parents=True, exist_ok=True)
    DB_URL = 'sqlite:///' + str(dbfile)
if DB_URL.startswith('postgres://'):
    DB_URL = DB_URL.replace('postgres://', 'postgresql+psycopg://', 1)
elif DB_URL.startswith('postgresql://'):
    DB_URL = DB_URL.replace('postgresql://', 'postgresql+psycopg://', 1)
ENGINE = create_engine(DB_URL, pool_pre_ping=True, connect_args={'check_same_thread': False} if DB_URL.startswith('sqlite') else {})
Session = sessionmaker(bind=ENGINE, expire_on_commit=False)
Base = declarative_base()

class Inquiry(Base):
    __tablename__ = 'inquiries'
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    inquiry_type = Column(String(32), nullable=False)
    name = Column(String(100), nullable=False)
    email = Column(String(254), nullable=False)
    phone = Column(String(40), nullable=False, default='')
    preferred_date = Column(String(20), nullable=False, default='')
    guests = Column(Integer, nullable=True)
    budget = Column(String(30), nullable=False, default='')
    message = Column(Text, nullable=False)
    items = Column(Text, nullable=False, default='')
    status = Column(String(24), nullable=False, default='new')

class Special(Base):
    __tablename__ = 'specials'
    id = Column(Integer, primary_key=True)
    heading = Column(String(100), nullable=False)
    subtitle = Column(String(250), nullable=False)
    eyebrow = Column(String(45), nullable=False, default='This week')
    image = Column(String(30), nullable=False, default='hero')
    visible = Column(Boolean, nullable=False, default=True)

class Hours(Base):
    __tablename__ = 'hours'
    day = Column(Integer, primary_key=True)
    opens = Column(String(5), nullable=False, default='10:00')
    closes = Column(String(5), nullable=False, default='18:00')
    is_closed = Column(Boolean, nullable=False, default=False)

Base.metadata.create_all(ENGINE)
with Session.begin() as db:
    if not db.scalars(select(Hours)).first():
        for day in range(7):
            db.add(Hours(day=day,opens='13:00' if day==4 else '10:00',closes='19:00' if day==4 else '18:00',is_closed=day==6))
    if not db.scalars(select(Special)).first():
        db.add_all([
            Special(heading='The Welcome Home Edit',subtitle='A softer start: explore prayer mats, step-by-step guides and meaningful gifts for a new chapter.',eyebrow='Featured collection',image='hero'),
            Special(heading='Discover your signature scent',subtitle='Explore our sample attar pair, a lovely introduction to musk and warm amber notes.',eyebrow='Featured this week',image='fragrance'),
            Special(heading='Questions are always welcome',subtitle='Interested in a mentor or a beginner-friendly circle? Let us know and we’ll be in touch.',eyebrow='Community corner',image='books'),
        ])

app = FastAPI(title='SADAQAH')
app.add_middleware(SessionMiddleware, secret_key=os.getenv('SECRET_KEY') or secrets.token_urlsafe(48), same_site='lax', https_only=os.getenv('PUBLIC_BASE_URL','').startswith('https://'), max_age=60*60*8)
app.mount('/static', StaticFiles(directory=str(ROOT/'static')),name='static')
templates = Jinja2Templates(directory=str(ROOT/'templates'))

@app.middleware('http')
async def security_headers(request:Request, call_next):
    result = await call_next(request)
    result.headers['X-Content-Type-Options']='nosniff'
    result.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    result.headers['X-Frame-Options']='DENY'
    if request.url.path.startswith('/admin') or request.url.path=='/api/status':
        result.headers['Cache-Control']='no-store'
    return result

DAYS = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
TZN = os.getenv('STORE_TIMEZONE','America/Regina')
try: STORE_TZ = ZoneInfo(TZN)
except ZoneInfoNotFoundError:
    STORE_TZ = ZoneInfo('UTC'); TZN = 'UTC'


def status_at(now=None):
    current = now or datetime.now(STORE_TZ)
    day = current.weekday()
    with Session() as db:
        record = db.get(Hours,day)
        week = list(db.scalars(select(Hours).order_by(Hours.day)))
    hhmm = current.strftime('%H:%M')
    opened = bool(record and not record.is_closed and record.opens<=hhmm<record.closes)
    return {'open':opened, 'label':'Open now' if opened else 'Closed now', 'today':DAYS[day], 'hours':('Closed' if record.is_closed else f'{clock(record.opens)} – {clock(record.closes)}') if record else 'Hours unavailable', 'timezone':TZN, 'schedule':[{'day':DAYS[h.day],'opens':clock(h.opens),'closes':clock(h.closes),'closed':h.is_closed} for h in week], 'demo':True}

def clock(t):
    return datetime.strptime(t,'%H:%M').strftime('%I:%M %p').lstrip('0')

def token_for(request):
    token=request.session.get('csrf')
    if not token:
        token=secrets.token_urlsafe(32)
        request.session['csrf']=token
    return token

def valid_csrf(request, token):
    return bool(token and hmac.compare_digest(str(request.session.get('csrf','')),str(token)))

def context(request, **more):
    with Session() as db: specials=list(db.scalars(select(Special).where(Special.visible==True).order_by(Special.id)))
    return {'request':request,'current_path':request.url.path,'categories':CATEGORIES,'products':PRODUCTS,'photos':PHOTOS, 'specials':specials, 'hours_status':status_at(),'days':DAYS,'csrf':token_for(request),'demo_banner':True,**more}

def render(request,page,**kw):
    return templates.TemplateResponse(request,page,context(request,**kw))

def wants_admin(request):
    return request.session.get('admin') is True and bool(os.getenv('ADMIN_PASSWORD'))

def admin_guard(request):
    if not wants_admin(request):return RedirectResponse('/admin/login',status_code=303)
    return None

def clean(value,limit):return (value or '').strip()[:limit]

def validate_inquiry(data):
    error = []
    kind=clean(data.get('inquiry_type'),32)
    name=clean(data.get('name'),101)
    email=clean(data.get('email'),255).lower()
    phone=clean(data.get('phone'),41)
    message=clean(data.get('message'),2001)
    preferred_date=clean(data.get('preferred_date'),21)
    budget=clean(data.get('budget'),31)
    items=clean(data.get('items'),1500)
    raw_guests=clean(data.get('guests'),10)
    consent=data.get('consent','')
    if kind not in ('general','catering','bulk','mentor','order'):error.append('Choose an inquiry type.')
    if len(name)<2 or len(name)>100:error.append('Please enter your name (2–100 characters).')
    if len(email)>254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",email):error.append('Enter a valid email address.')
    if phone and (len(phone)>40 or not re.fullmatch(r'[0-9+() .-]{7,40}',phone)):error.append('Enter a valid phone number, or leave it blank.')
    if not (12<=len(message)<=2000):error.append('Tell us a little more (12–2000 characters).')
    if preferred_date:
        try:date.fromisoformat(preferred_date)
        except ValueError:error.append('Enter a valid preferred date.')
    guests=None
    if raw_guests:
        try: guests=int(raw_guests)
        except ValueError: guests=-1
        if not 1<=guests<=10000:error.append('Number of guests must be between 1 and 10,000.')
    if len(budget)>30:error.append('Budget must be 30 characters or fewer.')
    if data.get('consent')!='yes':error.append('Please consent to being contacted about this inquiry.')
    if len(items)>1499:error.append('Too many basket items; please shorten the message.')
    return error,{'inquiry_type':kind,'name':name,'email':email,'phone':phone,'message':message,'preferred_date':preferred_date,'guests':guests,'budget':budget,'items':items}

_limiter={};_lock=threading.Lock()
def allow_submission(ip):
    now=time.time()
    with _lock:
        recent=[t for t in _limiter.get(ip,[]) if now-t<3600]
        if len(recent)>=12:return False
        recent.append(now)
        _limiter[ip]=recent
    return True

@app.get('/health')
def health():return {'status':'ok'}

@app.get('/',response_class=HTMLResponse)
def home(request:Request):
    featured=[PRODUCT_BY_ID[k] for k in ('soft-sage-mat','arabic-english-quran','new-muslim-guide','white-musk')]
    return render(request,'home.html',featured=featured)

@app.get('/shop',response_class=HTMLResponse)
def shop(request:Request, category:str='', q:str=''):
    filtered=[p for p in PRODUCTS if (not category or category==p['category']) and (not q or q.casefold() in (p['name']+' '+p['description']).casefold())]
    return render(request,'shop.html',shown=filtered,category=category,q=q)

@app.get('/product/{product_id}',response_class=HTMLResponse)
def product(request:Request,product_id:str):
    item=PRODUCT_BY_ID.get(product_id)
    if not item:return HTMLResponse('Product not found',status_code=404)
    related=[p for p in PRODUCTS if p['category']==item['category'] and p['id']!=item['id']][:3]
    return render(request,'product.html',product=item,related=related)

@app.get('/new-to-islam',response_class=HTMLResponse)
def new_to_islam(request:Request):return render(request,'new.html',beginner=[p for p in PRODUCTS if p['category']=='reverts'][:3])

@app.get('/about',response_class=HTMLResponse)
def about(request:Request):return render(request,'about.html')

@app.get('/contact',response_class=HTMLResponse)
def contact(request:Request):return render(request,'contact.html')

@app.get('/basket',response_class=HTMLResponse)
def basket(request:Request):return render(request,'basket.html',basket_catalog=[{**p,'image_url':PHOTOS[p['image']]} for p in PRODUCTS])

@app.get('/inquire',response_class=HTMLResponse)
def inquire(request:Request, kind:str='general'):
    if kind not in ('general','catering','bulk','mentor','order'): kind='general'
    return render(request,'inquire.html',kind=kind,errors=[],values={})

@app.post('/inquire',response_class=HTMLResponse)
async def send_inquiry(request:Request):
    form=await request.form()
    values={k:str(v) for k,v in form.items()}
    if not valid_csrf(request,values.get('csrf')):
        return HTMLResponse('Your session expired. Refresh and try again.',status_code=403)
    if values.get('website','').strip():
        return RedirectResponse('/thank-you',status_code=303) # honeypot
    errors, data=validate_inquiry(values)
    if not allow_submission(request.client.host if request.client else 'unknown'):
        errors.append('Too many requests. Please try again later.')
    if errors:
        return templates.TemplateResponse(request,'inquire.html',context(request,kind=data['inquiry_type'],errors=errors,values=values),status_code=422)
    with Session.begin() as db: db.add(Inquiry(**data))
    return RedirectResponse('/thank-you',status_code=303)

@app.get('/thank-you',response_class=HTMLResponse)
def thank_you(request:Request):return render(request,'thanks.html')

@app.get('/privacy',response_class=HTMLResponse)
def privacy(request:Request):return render(request,'privacy.html')

@app.get('/api/status')
def api_status():return status_at()

@app.get('/admin/login',response_class=HTMLResponse)
def admin_login(request:Request):
    if wants_admin(request):return RedirectResponse('/admin',status_code=303)
    return render(request,'login.html',login_error='')

@app.post('/admin/login',response_class=HTMLResponse)
async def do_login(request:Request):
    values=dict(await request.form())
    if not valid_csrf(request,values.get('csrf')):return HTMLResponse('Session expired',status_code=403)
    correct=os.getenv('ADMIN_PASSWORD','')
    valid=bool(correct) and hmac.compare_digest(str(values.get('password','')),correct)
    if not valid:
        await asyncio.sleep(.35)
        return templates.TemplateResponse(request,'login.html',context(request,login_error='Incorrect password or admin password not configured.'),status_code=401)
    request.session.clear()
    request.session['admin']=True
    token_for(request)
    return RedirectResponse('/admin',status_code=303)

@app.post('/admin/logout')
async def admin_logout(request:Request):
    data=dict(await request.form())
    if not valid_csrf(request,data.get('csrf')):return HTMLResponse('Invalid token',status_code=403)
    request.session.clear()
    return RedirectResponse('/',status_code=303)

@app.get('/admin',response_class=HTMLResponse)
def admin(request:Request, status:str=''):
    guard=admin_guard(request)
    if guard:return guard
    with Session() as db:
        inquiries=list(db.scalars(select(Inquiry).order_by(Inquiry.id.desc())))
        specials=list(db.scalars(select(Special).order_by(Special.id)))
        hours=list(db.scalars(select(Hours).order_by(Hours.day)))
    return render(request,'admin.html',inquiries=inquiries,admin_specials=specials,admin_hours=hours,active_filter=status)

def csv_safe(value):
    if value is None:return ''
    if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')):
        return "'"+value
    return value

@app.get('/admin/export.csv')
def export_csv(request:Request):
    guard=admin_guard(request)
    if guard:return guard
    with Session() as db: inquiries=list(db.scalars(select(Inquiry).order_by(Inquiry.id.desc())))
    out=io.StringIO();writer=csv.writer(out)
    fields=('id','created_at','inquiry_type','name','email','phone','preferred_date','guests','budget','items','message','status')
    writer.writerow(fields)
    for q in inquiries:
        writer.writerow([csv_safe(getattr(q,f)) for f in fields])
    return StreamingResponse(iter([out.getvalue()]),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="sadaqah-inquiries.csv"'})

@app.post('/admin/inquiries/{inquiry_id}')
async def set_inquiry_status(request:Request,inquiry_id:int):
    guard=admin_guard(request)
    if guard:return guard
    data=dict(await request.form())
    if not valid_csrf(request,data.get('csrf')):return HTMLResponse('Invalid token',status_code=403)
    if data.get('status') not in ('new','in_progress','closed'):return HTMLResponse('Invalid status',status_code=400)
    with Session.begin() as db:
        item=db.get(Inquiry,inquiry_id)
        if item:item.status=data['status']
    return RedirectResponse('/admin#inquiries',status_code=303)

@app.post('/admin/specials/{special_id}')
async def update_special(request:Request,special_id:int):
    guard=admin_guard(request)
    if guard:return guard
    data=dict(await request.form())
    if not valid_csrf(request,data.get('csrf')):return HTMLResponse('Invalid token',status_code=403)
    heading=clean(data.get('heading'),100)
    subtitle=clean(data.get('subtitle'),250)
    eyebrow=clean(data.get('eyebrow'),45)
    image=data.get('image','hero')
    if not heading or not subtitle or image not in PHOTOS:return HTMLResponse('Invalid special',status_code=400)
    with Session.begin() as db:
        sp=db.get(Special,special_id)
        if not sp:return HTMLResponse('Not found',status_code=404)
        sp.heading=heading;sp.subtitle=subtitle;sp.eyebrow=eyebrow;sp.image=image;sp.visible=data.get('visible')=='on'
    return RedirectResponse('/admin#specials',status_code=303)

@app.post('/admin/hours')
async def update_hours(request:Request):
    guard=admin_guard(request)
    if guard:return guard
    data=dict(await request.form())
    if not valid_csrf(request,data.get('csrf')):return HTMLResponse('Invalid token',status_code=403)
    updates=[]
    for i in range(7):
        o=data.get(f'opens_{i}','');c=data.get(f'closes_{i}','')
        if not re.fullmatch(r'\d{2}:\d{2}',o) or not re.fullmatch(r'\d{2}:\d{2}',c) or not ('00:00'<=o<='23:59' and '00:00'<=c<='23:59') or o>=c:
            return HTMLResponse('Invalid hours: closing time must be after opening time.',status_code=400)
        updates.append((o,c,data.get(f'closed_{i}')=='on'))
    with Session.begin() as db:
        for i,(o,c,closed) in enumerate(updates):
            h=db.get(Hours,i);h.opens=o;h.closes=c;h.is_closed=closed
    return RedirectResponse('/admin#hours',status_code=303)

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='0.0.0.0',port=int(os.getenv('PORT','8000')))
