from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core.cad_kit import Sheet
out=Path(__file__).parent/'smoke.dxf'
stamp={'org':'Smoke test','work':'Astra CAD route smoke','student':'','teacher':'','date':'','code':'SMOKE-01','sheets_total':1}
s=Sheet('Тестовый лист Astra',1,'1:100',stamp)
f=s.to_paper((60,150),100)
room=[f(0,0),f(12000,0),f(12000,8000),f(0,8000)]
s.polyline(room,'WALL',closed=True)
s.line(f(0,4000),f(12000,4000),'PIPE_FEED')
s.line(f(2000,0),f(2000,8000),'PIPE_DIST')
s.line(f(6000,0),f(6000,8000),'PIPE_DIST')
for x,y in [(2000,2000),(2000,6000),(6000,2000),(6000,6000)]: s.circle(f(x,y),3,'SPRINKLER',filled=False)
s.dim(f(0,0),f(12000,0),-12,'12000 мм',2.5)
s.dim(f(0,0),f(0,8000),-12,'8000 мм',2.5)
s.text('Тестовый план 12000×8000 мм',60,255,4,'left')
s.text('Вариант 99',60,247,3.5,'left')
s.text('Astra smoke',60,239,3.5,'left')
s.save(out)
print(out)

