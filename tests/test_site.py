"""Run with: python -m pytest -q"""
import os
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_db = Path(tempfile.mkdtemp(prefix='sadaqah-test-')) / 'test.db'
os.environ['DATABASE_URL'] = f'sqlite:///{_db}'
os.environ['ADMIN_PASSWORD'] = 'test-password-very-long'
os.environ['SECRET_KEY'] = 'test-secret-key-for-signed-cookies'
os.environ['STORE_TIMEZONE'] = 'America/Regina'

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from app import app, Session, Inquiry, Special, Hours, status_at


def csrf(response):
    return BeautifulSoup(response.text,'html.parser').select_one('input[name="csrf"]').get('value')


def test_public_routes():
    with TestClient(app) as c:
        for path in ('/','/shop','/shop?category=fragrance','/product/soft-sage-mat','/new-to-islam','/about','/contact','/inquire?kind=catering','/basket','/privacy','/api/status','/health'):
            r=c.get(path)
            assert r.status_code==200, (path,r.text[:200])
        assert 'Musk' in c.get('/shop?category=fragrance').text
        assert 'SADAQAH' in c.get('/').text
        assert c.get('/shop?category=none').status_code==200
        assert c.get('/product/does-not-exist').status_code==404


def test_validations_and_persistence():
    with TestClient(app) as c:
        tok=csrf(c.get('/inquire'))
        r=c.post('/inquire',data={'csrf':tok,'inquiry_type':'catering','name':'A','email':'not-email','message':'hi'})
        assert r.status_code==422
        tok=csrf(c.get('/inquire?kind=catering'))
        r=c.post('/inquire',data={'csrf':tok,'inquiry_type':'catering','name':'Amina','email':'amina@example.org','message':'An event for thirty-five guests next month.','guests':'35','consent':'yes'},follow_redirects=False)
        assert r.status_code==303 and r.headers['location']=='/thank-you'
        with Session() as db:
            q=db.query(Inquiry).filter_by(email='amina@example.org').one()
            assert q.guests==35 and q.status=='new' and q.inquiry_type=='catering'


def test_admin_auth_and_updates():
    with TestClient(app) as c:
        assert c.get('/admin',follow_redirects=False).status_code==303
        t=csrf(c.get('/admin/login'))
        assert c.post('/admin/login',data={'csrf':t,'password':'wrong'}).status_code==401
        t=csrf(c.get('/admin/login'))
        r=c.post('/admin/login',data={'csrf':t,'password':os.environ['ADMIN_PASSWORD']},follow_redirects=True)
        assert r.status_code==200 and 'Recent' in r.text
        assert c.get('/admin/export.csv').status_code==200
        t=csrf(c.get('/admin'))
        with Session() as db:
            special_id=db.query(Special).first().id
        r=c.post(f'/admin/specials/{special_id}',data={'csrf':t,'heading':'New Week', 'subtitle':'A freshly edited collection for everyone.', 'eyebrow':'This week','image':'books','visible':'on'},follow_redirects=False)
        assert r.status_code==303
        assert 'New Week' in c.get('/').text
        data={'csrf':t}
        for i in range(7):
            data[f'opens_{i}']='09:00'
            data[f'closes_{i}']='17:00'
            if i==6:data[f'closed_{i}']='on'
        assert c.post('/admin/hours',data=data,follow_redirects=False).status_code==303
        tz=ZoneInfo('America/Regina')
        assert status_at(datetime(2026,10,12,10,0,tzinfo=tz))['open'] is True
        assert status_at(datetime(2026,10,12,18,0,tzinfo=tz))['open'] is False
        assert status_at(datetime(2026,10,11,10,0,tzinfo=tz))['open'] is False
        with Session() as db: q=db.query(Inquiry).first()
        assert c.post(f'/admin/inquiries/{q.id}',data={'csrf':t,'status':'in_progress'},follow_redirects=False).status_code==303
        with Session() as db: assert db.get(Inquiry,q.id).status=='in_progress'
        assert c.post('/admin/logout',data={'csrf':t},follow_redirects=False).status_code==303
        assert c.get('/admin',follow_redirects=False).status_code==303


def test_missing_csrf_rejected():
    with TestClient(app) as c:
        assert c.post('/inquire',data={'name':'Fake'}).status_code==403
        assert c.post('/admin/login',data={'password':os.environ['ADMIN_PASSWORD']}).status_code==403
