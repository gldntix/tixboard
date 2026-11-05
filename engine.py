import re, sqlite3, hashlib, time, html, calendar, os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus
import feedparser, requests

DB = Path(os.environ.get('TIXBOARD_DB_PATH', str(Path(__file__).with_name('ticket_news.sqlite3'))))
QUERIES = {
 'MLB': ['MLB injury trade lineup starting pitcher playoffs tickets', 'baseball Dodgers Yankees Mets Phillies injury roster'],
 'NBA': ['NBA star injury trade lineup rest return playoffs', 'NBA Lakers Celtics Knicks Warriors tickets'],
 'NFL': ['NFL quarterback injury trade starter playoffs schedule', 'NFL Chiefs Cowboys Eagles 49ers injury'],
 'NHL': ['NHL injury goalie trade playoffs lineup', 'NHL Rangers Bruins Maple Leafs ticket demand'],
 'Concerts': ['concert tour new dates cancellation postponed sold out USA', 'music artist stadium tour announced added show'],
 'Broadway': ['Broadway show closing extension cast replacement opening tickets', 'Broadway star cast departure musical cancellation'],
 'Entertainment': ['US comedy tour festival announcement cancellation live event', 'Las Vegas residency announced extended cancelled'],
}
POSITIVE = {'return':3,'returns':3,'comeback':3,'announces tour':4,'tour announced':4,'new tour':4,'sold out':3,'added date':3,'adds dates':3,'extra show':3,'extension':2,'extends':2,'playoffs':1,'debut':2,'record':1,'reunion':2,'opening':1,'headliner':2}
NEGATIVE = {'cancelled':5,'canceled':5,'cancellation':5,'postponed':5,'injury':2,'injured':3,'out for season':5,'ruled out':4,'suspended':3,'closing':3,'withdraws':3,'scratched':3,'rescheduled':3,'absence':2}
MIXED = {'trade':2,'traded':2,'new dates':2,'second show':2,'lineup change':2,'replacement':2,'schedule change':2,'weather':2,'ticket prices':1}
STOP = {'the','and','for','with','from','will','after','over','into','about','this','that','have','their','says','amid','news','report','reports','latest','update','updates','tickets','ticket','game','games','tour','show','shows','usa','mlb','nba','nfl','nhl'}

def connect():
    c=sqlite3.connect(DB,timeout=20)
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('''CREATE TABLE IF NOT EXISTS news (id TEXT PRIMARY KEY, category TEXT, title TEXT, source TEXT, url TEXT, published TEXT, detected TEXT, impact TEXT, priority INTEGER, reason TEXT, matched TEXT)''')
    c.execute('CREATE INDEX IF NOT EXISTS news_detected ON news(detected DESC)')
    return c

def assess(title, summary=''):
    text = re.sub('<[^>]*>', ' ', html.unescape(title+' '+summary)).lower()
    hits=[]; plus=minus=0
    for term,weight in POSITIVE.items():
        if re.search(r'(?<!\w)'+re.escape(term)+r'(?!\w)',text): plus+=weight;hits.append(term)
    for term,weight in NEGATIVE.items():
        if re.search(r'(?<!\w)'+re.escape(term)+r'(?!\w)',text): minus+=weight;hits.append(term)
    for term,weight in MIXED.items():
        if re.search(r'(?<!\w)'+re.escape(term)+r'(?!\w)',text): hits.append(term)
    if plus and minus: impact='Mixto'
    elif plus: impact='Positivo potencial'
    elif minus: impact='Negativo potencial'
    elif hits: impact='Mixto'
    else: impact='Sin señal clara'
    strength=max(plus,minus,2 if hits else 0)
    priority=min(100, 15 + strength*12 + min(len(set(hits)),4)*4)
    if not hits: priority=10
    reason=('Se detectaron señales: '+', '.join(list(dict.fromkeys(hits))[:5])) if hits else 'No se detectaron señales concluyentes de impacto en boletaje.'
    reason+=' Revisar relevancia del artista/equipo, ciudad, fecha y si el mercado ya incorporó la noticia.' if hits else ''
    return impact,priority,reason,', '.join(list(dict.fromkeys(hits))[:8])

def fetch_once(timeout=12):
    c=connect(); inserted=0; failures=[]; checked=0
    headers={'User-Agent':'TicketIntelligenceV1/1.0 (local research; RSS reader)'}
    for category,queries in QUERIES.items():
        for q in queries:
            url='https://news.google.com/rss/search?q='+quote_plus(q+' when:2d')+'&hl=en-US&gl=US&ceid=US:en'
            try:
                r=requests.get(url,timeout=timeout,headers=headers);r.raise_for_status()
                feed=feedparser.parse(r.content)
                if not feed.entries and feed.bozo: raise ValueError('Feed inválido')
                for e in feed.entries[:35]:
                    title=html.unescape(re.sub('<[^>]+>','',e.get('title',''))).strip()
                    link=e.get('link','')
                    if not title or not link: continue
                    checked+=1
                    uid=hashlib.sha256((link or title).encode()).hexdigest()
                    source=e.get('source',{}).get('title','Google News RSS') if isinstance(e.get('source',{}),dict) else 'Google News RSS'
                    pub=e.get('published_parsed')
                    published=datetime.fromtimestamp(calendar.timegm(pub),timezone.utc).isoformat() if pub else ''
                    impact,priority,reason,matched=assess(title,e.get('summary',''))
                    cur=c.execute('INSERT OR IGNORE INTO news VALUES (?,?,?,?,?,?,?,?,?,?,?)',(uid,category,title,source,link,published,datetime.now(timezone.utc).isoformat(),impact,priority,reason,matched))
                    inserted+=cur.rowcount
                c.commit()
            except Exception as exc: failures.append(f'{category}: {type(exc).__name__}: {exc}')
    c.close()
    return {'new':inserted,'checked':checked,'errors':failures,'at':datetime.now(timezone.utc).isoformat()}

if __name__=='__main__':
    print(fetch_once())
